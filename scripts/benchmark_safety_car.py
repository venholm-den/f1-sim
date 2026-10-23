"""Offline A/B of aggregate-engine candidates on a recent-baseline packet.

Uses only files already in data/recent_baselines: each target race is
forecast from earlier races' race pace plus the actual starting grid, once
with the established engine and once per candidate arm (--arms). Arms share
features and seeds, so each difference isolates one candidate. The
estimated_grid arms replace the actual grid with a pace-ranked estimate, which
is what a pre-qualifying forecast sees. This is a diagnostic on inspected
races, not a promotion test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.pit_scenarios import assumed_plans
from src.simulate import simulate_races
from src.track import load_track_profile

DEFAULT_PACKET = 'data/recent_baselines/singapore-20261005-v4-venues'


def _features(history, results, race_laps):
    grid = results.set_index('Abbreviation')['GridPosition'].replace(0, np.nan)
    grid = grid.fillna(grid.max() + 1).rank(method='first')
    means = history.groupby('Driver')[['relative_pace', 'deg_per_lap', 'lap_std',
                                       'dnf_prob', 'model_uncertainty']].mean()
    frame = pd.DataFrame({'Driver': grid.index, 'Team': results.set_index('Abbreviation').loc[grid.index, 'TeamName'].values,
                          'grid_position': grid.values}).join(means, on='Driver')
    # Drivers without earlier pace start slightly behind the median.
    frame['relative_pace'] = frame.relative_pace.fillna(frame.relative_pace.median() + .5)
    frame = frame.fillna({'deg_per_lap': frame.deg_per_lap.median(), 'lap_std': frame.lap_std.median(),
                          'dnf_prob': .045, 'model_uncertainty': 1.2})
    pace = frame.relative_pace - frame.relative_pace.min()
    deg = frame.deg_per_lap.clip(-.04, .18)
    long_run = pace + deg.clip(lower=0) * 12 + frame.lap_std.clip(0, 8) * .04
    return frame.assign(grid_source='actual_session_results', grid_confidence=1.0,
                        race_pace_score=pace, quali_pace_score=pace,
                        long_run_pace_score=long_run - long_run.min(), tyre_deg_score=deg,
                        strategy_score=(deg.clip(lower=0) * 2 + .15).clip(0, 1.5),
                        reliability_score=frame.dnf_prob.clip(.005, .3),
                        performance_uncertainty=(frame.model_uncertainty + frame.lap_std.clip(0, 8) * .06 + .3).clip(.7, 4),
                        estimated_race_laps=race_laps, base_winner_race_time_seconds=90. * race_laps)


def _estimated(features):
    frame = features.copy()
    frame['grid_position'] = frame.race_pace_score.rank(method='first').astype(int)
    return frame.assign(grid_source='estimated_model_grid', grid_confidence=0.38)


ARMS = {
    'established': (lambda f, p: f, lambda f, p: {}),
    'track_sc_v1': (lambda f, p: f, lambda f, p: {'safety_car_probability': p['safety_car_chance']}),
    'team_noise_v1': (lambda f, p: f, lambda f, p: {'team_noise_seconds': 3.0}),
    'estimated_grid': (lambda f, p: _estimated(f), lambda f, p: {}),
    'estimated_grid_v1': (lambda f, p: _estimated(f), lambda f, p: {'sample_estimated_grid': True}),
    'pit_scenarios_v1': (lambda f, p: f, lambda f, p: {'pit_plans': assumed_plans(f, f.estimated_race_laps.iloc[0])}),
}


def _score(summary, actual):
    merged = summary.merge(actual, on='Driver')
    finish = merged.Position
    return {'finish_mae': float((merged.avg_finish - finish).abs().mean()),
            'win_brier': float(((merged.win_chance - (finish == 1)) ** 2).mean()),
            'podium_brier': float(((merged.podium_chance - (finish <= 3)) ** 2).mean()),
            'top10_brier': float(((merged.top10_chance - (finish <= 10)) ** 2).mean())}


def run(packet, history_races, n_sims, seeds, arms=('established', 'track_sc_v1')):
    packet = Path(packet)
    pace = pd.read_csv(packet / 'baseline_race_features.csv')
    results = pd.read_csv(packet / 'fastf1_race_results.csv')
    control = pd.read_csv(packet / 'fastf1_race_control_summary.csv').set_index('Round')
    rows = []
    for round_ in sorted(results.Round.unique())[history_races:]:
        race = results[results.Round.eq(round_)]
        event = str(race.Event.iloc[0])
        profile = load_track_profile(event, metadata={'year': int(race.Year.iloc[0]), 'round': int(round_), 'event': event})
        laps = float(profile.get('race_laps') or 57)
        history = pace[pace.source_round.between(round_ - history_races, round_ - 1)]
        features = _features(history, race, laps)
        actual = race.rename(columns={'Abbreviation': 'Driver'})[['Driver', 'Position']]
        for seed in seeds:
            for arm in arms:
                transform, options = ARMS[arm]
                arm_features = transform(features, profile)
                summary, _, _ = simulate_races(arm_features, n_sims=n_sims, seed=seed,
                                               overtaking_difficulty=profile['overtaking_difficulty'],
                                               **options(arm_features, profile))
                rows.append({'round': int(round_), 'event': event, 'seed': seed, 'arm': arm,
                             'sc_chance': profile['safety_car_chance'], 'profile_status': profile['profile_status'],
                             'actual_sc': bool(control.loc[round_, 'safety_car_flag']), **_score(summary, actual)})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    parser.add_argument('--history-races', type=int, default=3)
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--arms', nargs='+', choices=sorted(ARMS), default=['established', 'track_sc_v1'])
    parser.add_argument('--output')
    args = parser.parse_args()
    frame = run(args.packet, args.history_races, args.n_sims, args.seeds, args.arms)
    metrics = ['finish_mae', 'win_brier', 'podium_brier', 'top10_brier']
    print(frame.groupby('arm')[metrics].mean().round(4).to_string())
    print()
    print(frame.groupby(['actual_sc', 'arm'])[metrics].mean().round(4).to_string())
    if args.output:
        frame.to_csv(args.output, index=False)
        print(f'\nsaved: {args.output}')


if __name__ == '__main__':
    main()
