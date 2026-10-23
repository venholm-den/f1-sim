"""Offline check of sprint_v1 against saved sprint results.

Uses only a saved historical_library (no FastF1 network): each sprint is
forecast from earlier Grands Prix' clean race pace plus the actual sprint
grid, then scored against the sprint classification. The established run has
no sprint forecast, so the reference is the sprint grid order. Races are split
chronologically into development and holdout; this is a diagnostic, not a
promotion test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.benchmark_safety_car import _features
from src.accuracy_benchmark import chronological_partitions
from src.sprint import simulate_sprints
from src.track import load_track_profile

DEFAULT_LIBRARY = Path('data/historical_library')


def _table(folder: Path, table: str) -> pd.DataFrame | None:
    """Read one table of a complete saved session, or None."""
    try:
        saved = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if saved.get('status') != 'complete':
        return None
    for name, info in saved.get('files', {}).items():
        if info.get('table') == table:
            return pd.read_csv(folder / Path(name.replace('\\', '/')), low_memory=False)
    return None


def load_sessions(library: Path, years) -> tuple[dict, dict]:
    """Return {(year, round): results} for sprints and {(year, round): laps} for races."""
    sprints, races = {}, {}
    for year in years:
        for folder in sorted((library / str(year) / 'detailed').glob('*_[RS]')):
            round_ = int(folder.name.split('_', 1)[0])
            if folder.name.endswith('_S'):
                results = _table(folder, 'results')
                if results is not None and not results.empty:
                    sprints[(year, round_)] = results
            else:
                laps = _table(folder, 'laps')
                if laps is not None and not laps.empty:
                    races[(year, round_)] = laps
    return sprints, races


def race_pace(laps: pd.DataFrame, source_round) -> pd.DataFrame:
    """Per-driver median clean-lap gap to the quickest driver, in seconds."""
    clean = laps[laps.LapTimeSeconds.notna() & laps.PitIn.isna() & laps.PitOut.isna()]
    if 'IsAccurate' in clean:
        clean = clean[clean.IsAccurate.astype(str).str.lower().eq('true')]
    stats = clean.groupby('Driver').LapTimeSeconds.agg(['median', 'std', 'count'])
    stats = stats[stats['count'] >= 5]
    return pd.DataFrame({'Driver': stats.index, 'source_round': source_round,
                         'relative_pace': stats['median'] - stats['median'].min(),
                         'lap_std': stats['std'], 'deg_per_lap': 0.0,
                         'dnf_prob': .045, 'model_uncertainty': 1.2}).reset_index(drop=True)


def _score(predicted: pd.DataFrame, actual: pd.DataFrame) -> dict:
    merged = predicted.merge(actual, on='Driver')
    finish = merged.Position
    return {'finish_mae': float((merged.avg_finish - finish).abs().mean()),
            'win_brier': float(((merged.win_chance - (finish == 1)) ** 2).mean()),
            'podium_brier': float(((merged.podium_chance - (finish <= 3)) ** 2).mean()),
            'points_brier': float(((merged.points_chance - (finish <= 8)) ** 2).mean()),
            'points_mae': float((merged.avg_points - merged.Points).abs().mean())}


def _summarise(sims: pd.DataFrame) -> pd.DataFrame:
    return sims.groupby('Driver').agg(avg_finish=('sprint_position', 'mean'),
                                      win_chance=('sprint_position', lambda p: (p == 1).mean()),
                                      podium_chance=('sprint_position', lambda p: (p <= 3).mean()),
                                      points_chance=('sprint_points', lambda p: (p > 0).mean()),
                                      avg_points=('sprint_points', 'mean')).reset_index()


def _grid_order(features: pd.DataFrame) -> pd.DataFrame:
    grid = features.grid_position.astype(int)
    points = grid.map({1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}).fillna(0)
    return pd.DataFrame({'Driver': features.Driver, 'avg_finish': grid, 'win_chance': (grid == 1).astype(float),
                         'podium_chance': (grid <= 3).astype(float), 'points_chance': (grid <= 8).astype(float),
                         'avg_points': points})


def run(library, years, history_races, n_sims, seeds):
    sprints, races = load_sessions(Path(library), years)
    rows, skipped = [], []
    for key, results in sorted(sprints.items()):
        earlier = [race for race in sorted(races) if race < key][-history_races:]
        if len(earlier) < history_races:
            skipped.append({'year': key[0], 'round': key[1], 'reason': 'insufficient_history'})
            continue
        history = pd.concat([race_pace(races[race], i) for i, race in enumerate(earlier)], ignore_index=True)
        event = str(results.Event.iloc[0])
        profile = load_track_profile(event, metadata={'year': key[0], 'round': key[1], 'event': event})
        features = _features(history, results, float(profile.get('race_laps') or 57))
        actual = results.rename(columns={'Abbreviation': 'Driver'})[['Driver', 'Position', 'Points']].copy()
        actual['Points'] = actual.Points.fillna(0)
        base = {'year': key[0], 'round': key[1], 'event': event}
        rows.append({**base, 'seed': None, 'arm': 'grid_order', **_score(_grid_order(features), actual)})
        for seed in seeds:
            sims = simulate_sprints(features, n_sims, seed, overtaking_difficulty=profile['overtaking_difficulty'])
            rows.append({**base, 'seed': seed, 'arm': 'sprint_v1', **_score(_summarise(sims), actual)})
    frame = pd.DataFrame(rows)
    development, _ = chronological_partitions(list(zip(frame.year, frame['round'])))
    frame['split'] = ['development' if key in development else 'holdout' for key in zip(frame.year, frame['round'])]
    frame['loss'] = frame.finish_mae + frame.points_brier
    return frame, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument('--years', type=int, nargs='+', default=[2021, 2022, 2023, 2024, 2025, 2026])
    parser.add_argument('--history-races', type=int, default=3)
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--output')
    args = parser.parse_args()
    frame, skipped = run(args.library, args.years, args.history_races, args.n_sims, args.seeds)
    metrics = ['finish_mae', 'win_brier', 'podium_brier', 'points_brier', 'points_mae', 'loss']
    counts = frame.drop_duplicates(['year', 'round']).groupby('split').size()
    print(f"sprints: {counts.to_dict()}, skipped: {len(skipped)}")
    print(frame.groupby(['split', 'arm'])[metrics].mean().round(4).to_string())
    if args.output:
        frame.to_csv(args.output, index=False)
        print(f'\nsaved: {args.output}')


if __name__ == '__main__':
    main()
