"""Replay PRE forecasts from saved recent-baseline CSVs to compare degradation weights.

Uses only race laps and results already in data/recent_baselines, so it runs
without a FastF1 cache. It is a diagnostic: these races have been inspected,
and it cannot enable a candidate.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import src.accuracy_candidates as candidates
from src.accuracy_benchmark import (ReplayRace, build_replay_forecast, chronological_partitions,
    evaluate_forecast, simple_baseline)


def load_saved_races(folder: Path) -> list[ReplayRace]:
    laps = pd.read_csv(folder / 'fastf1_laps.csv')
    results = pd.read_csv(folder / 'fastf1_race_results.csv')
    races = []
    for (year, number, event), part in results[results.Session.eq('R')].groupby(['Year', 'Round', 'Event']):
        race_laps = laps[laps.Session.eq('R') & laps.Year.eq(year) & laps.Round.eq(number)]
        session = SimpleNamespace(laps=race_laps.reset_index(drop=True), results=part.reset_index(drop=True),
                                  weather_data=pd.DataFrame(), track_status=pd.DataFrame())
        races.append(ReplayRace(int(year), int(number), event, {'R': session}))
    return sorted(races, key=lambda race: race.key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path,
                        default=Path('data/recent_baselines/singapore-20261005-v4-venues'))
    parser.add_argument('--multipliers', type=float, nargs='+', default=[0.0, 1.0, 2.0, 3.0, 5.0, 7.0])
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--n-baseline-races', type=int, default=2)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    races = load_saved_races(args.baseline_dir)
    arms = [('legacy', 'legacy', None)] + [(f'single_x{value:g}', 'single_degradation_v1', value)
                                           for value in args.multipliers]
    rows = []
    for index, race in enumerate(races[args.n_baseline_races:], start=args.n_baseline_races):
        metadata = dict(year=race.year, round=race.round, event=race.event, session='PRE')
        try:
            episode = []
            for seed in args.seeds:
                for name, variant, multiplier in arms:
                    if multiplier is not None:
                        candidates.SINGLE_DEGRADATION_MULTIPLIER = multiplier
                    forecast, features = build_replay_forecast(None, races[:index], metadata=metadata,
                        n_sims=args.n_sims, seed=seed, feature_variant=variant,
                        n_baseline_races=args.n_baseline_races)
                    scores, _ = evaluate_forecast(forecast, race.sessions['R'].results)
                    episode.append(dict(metadata, seed=seed, arm=name, **scores))
            scores, _ = evaluate_forecast(simple_baseline(features, races[:index], 'grid_order'),
                                          race.sessions['R'].results)
            episode.append(dict(metadata, seed=None, arm='grid_order', **scores))
        except (ValueError, KeyError) as exc:
            # Score identical episodes for every arm, or not at all.
            print(f'Skipped R{race.round} {race.event}: {exc}')
            continue
        rows.extend(episode)
    metrics = pd.DataFrame(rows)
    development, holdout = chronological_partitions(list(zip(metrics.year, metrics['round'])))
    metrics['split'] = ['development' if key in development else 'holdout'
                        for key in zip(metrics.year, metrics['round'])]
    summary = metrics.groupby(['split', 'arm'])[
        ['finish_mae', 'top10_brier', 'podium_brier', 'win_brier', 'loss']].mean().round(4)
    print(summary.to_string())
    if args.output:
        metrics.to_csv(args.output, index=False)


if __name__ == '__main__':
    main()
