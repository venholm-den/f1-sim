"""Offline A/B of the per-pair pass model in the agent engine.

Replays the same recent-baseline packet as scripts.benchmark_safety_car:
earlier races' pace plus the actual grid. Arms share features and seeds:

- established: aggregate engine (context only)
- agent_laps_v1: agent engine, single factor passability = 1 - difficulty
- agent_pair_overtaking_v1: agent engine, pair model refitted for each target
  race on earlier races' pair-laps only

Both agent arms and the aggregate arm use calibrated_v1 track difficulties.
These races were already inspected, so this is a diagnostic, not a promotion
test.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.benchmark_safety_car import DEFAULT_PACKET, _features, _score
from src.pair_overtaking import build_dataset, fit_model
from src.simulate import simulate_races
from src.track import load_track_profile
from src.track_calibration import apply_track_calibration

ARMS = ('established', 'agent_laps_v1', 'agent_pair_overtaking_v1')
METRICS = ['finish_mae', 'win_brier', 'podium_brier', 'top10_brier']


def run(packet, history_races, n_sims, seeds, arms=ARMS, step_seconds=2.0,
        calibration='data/track_calibration/track_calibration_v1.csv'):
    packet = Path(packet)
    pace = pd.read_csv(packet / 'baseline_race_features.csv')
    results = pd.read_csv(packet / 'fastf1_race_results.csv')
    pairs = build_dataset(pd.read_csv(packet / 'fastf1_laps.csv'), pd.read_csv(calibration))
    rows = []
    for round_ in sorted(results.Round.unique())[history_races:]:
        race = results[results.Round.eq(round_)]
        event = str(race.Event.iloc[0])
        profile = apply_track_calibration(load_track_profile(
            event, metadata={'year': int(race.Year.iloc[0]), 'round': int(round_), 'event': event}))
        laps = float(profile.get('race_laps') or 57)
        history = pace[pace.source_round.between(round_ - history_races, round_ - 1)]
        features = _features(history, race, laps)
        actual = race.rename(columns={'Abbreviation': 'Driver'})[['Driver', 'Position']]
        model = fit_model(pairs[pairs['round'] < round_])
        difficulty = float(profile['overtaking_difficulty'])
        for seed in seeds:
            for arm in arms:
                options = {}
                if arm != 'established':
                    options['agent_settings'] = {'step_seconds': step_seconds}
                if arm == 'agent_pair_overtaking_v1':
                    options['agent_settings']['pair_pass_model'] = model
                summary, _, raw = simulate_races(features, n_sims=n_sims, seed=seed,
                                                 overtaking_difficulty=difficulty, **options)
                overtakes = float(raw.groupby('sim_id').overtakes.sum().mean()) if 'overtakes' in raw else float('nan')
                rows.append({'round': int(round_), 'event': event, 'seed': seed, 'arm': arm,
                             'overtaking_difficulty': difficulty, 'fit_pair_laps': model['pair_laps'],
                             'mean_race_overtakes': overtakes,
                             'observed_proxy_passes': int(pairs[pairs['round'] == round_].passed.sum()),
                             **_score(summary, actual)})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    parser.add_argument('--history-races', type=int, default=3)
    parser.add_argument('--n-sims', type=int, default=1000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--arms', nargs='+', choices=ARMS, default=list(ARMS))
    parser.add_argument('--step-seconds', type=float, default=2.0)
    parser.add_argument('--output')
    args = parser.parse_args()
    frame = run(args.packet, args.history_races, args.n_sims, args.seeds, args.arms, args.step_seconds)
    print(frame.groupby('arm')[METRICS + ['mean_race_overtakes', 'observed_proxy_passes']].mean().round(4).to_string())
    if args.output:
        frame.to_csv(args.output, index=False)
        print(f'\nsaved: {args.output}')


if __name__ == '__main__':
    main()
