"""Score candidates on every part of each race and apply their promotion lane.

score: re-run offline arms on one or more packets (the same features, seeds
and arms as scripts.benchmark_safety_car) and save one row per race, seed and
arm with the full set of race scores from src/race_scores.py. Packets can be
recent baselines or whole seasons from scripts.build_season_packets; rows
carry the year, so seasons can be pooled.

gate: read rows in that long format (from `score`, or any benchmark that
writes round/seed/arm/metric columns) and print the lane decision, the power
table and, for accuracy candidates, the sequential test.

Results on inspected races are diagnostics. Nothing here changes live
settings or approves a promotion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.benchmark_safety_car import ARMS, DEFAULT_PACKET, _features, arm_settings
from src.promotion_evidence import accuracy_decision, correctness_decision, paired_races, power_table
from src.race_scores import race_scores
from src.simulate import simulate_races
from src.track import load_track_profile
from src.track_calibration import apply_track_calibration


def score(packets, history_races, n_sims, seeds, arms):
    packets = [packets] if isinstance(packets, (str, Path)) else packets
    return pd.concat([_score_packet(packet, history_races, n_sims, seeds, arms) for packet in packets],
                     ignore_index=True)


def _score_packet(packet, history_races, n_sims, seeds, arms):
    packet = Path(packet)
    pace = pd.read_csv(packet / 'baseline_race_features.csv')
    results = pd.read_csv(packet / 'fastf1_race_results.csv')
    rows = []
    for round_ in sorted(results.Round.unique())[history_races:]:
        race = results[results.Round.eq(round_)]
        event = str(race.Event.iloc[0])
        profile = load_track_profile(event, metadata={'year': int(race.Year.iloc[0]), 'round': int(round_), 'event': event})
        laps = float(profile.get('race_laps') or 57)
        history = pace[pace.source_round.between(round_ - history_races, round_ - 1)]
        features = _features(history, race, laps)
        actual = race.rename(columns={'Abbreviation': 'Driver'})[['Driver', 'Position']]
        calibrated = apply_track_calibration(profile)
        for arm in arms:
            arm_profile = dict(profile)
            if arm in ('calibrated_sc', 'calibrated_v1', 'calibrated_multi_sc'):
                arm_profile['safety_car_chance'] = calibrated['safety_car_chance']
            if arm in ('calibrated_overtaking', 'calibrated_v1'):
                arm_profile['overtaking_difficulty'] = calibrated['overtaking_difficulty']
            transform, options = ARMS[arm]
            arm_features = transform(features, arm_profile)
            for seed in seeds:
                with arm_settings(arm):
                    summary, matrix, sims = simulate_races(arm_features, n_sims=n_sims, seed=seed,
                                                           overtaking_difficulty=arm_profile['overtaking_difficulty'],
                                                           **options(arm_features, arm_profile))
                rows.append({'year': int(race.Year.iloc[0]), 'round': int(round_), 'event': event, 'seed': seed, 'arm': arm,
                             **race_scores(summary, matrix, sims, actual)})
    return pd.DataFrame(rows)


def gate(rows, candidate, baseline, lane):
    decide = correctness_decision if lane == 'correctness' else accuracy_decision
    # Rows pooled across seasons repeat round numbers, so the year is part of the race key.
    keys = ('year', 'round')
    decision = decide(rows, candidate, baseline, keys)
    if lane == 'correctness':
        decision['power'] = power_table(paired_races(rows, candidate, baseline, keys)).to_dict('records')
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('score', help='Re-run arms on a packet with full race scores.')
    run.add_argument('--packet', nargs='+', default=[DEFAULT_PACKET])
    run.add_argument('--history-races', type=int, default=3)
    run.add_argument('--n-sims', type=int, default=2000)
    run.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    run.add_argument('--arms', nargs='+', choices=sorted(ARMS), default=['established', 'multi_sc_v1'])
    run.add_argument('--output', required=True)
    check = commands.add_parser('gate', help='Apply a lane decision to saved metric rows.')
    check.add_argument('--metrics', required=True)
    check.add_argument('--candidate', required=True)
    check.add_argument('--baseline', default='established')
    check.add_argument('--lane', choices=['correctness', 'accuracy'], required=True)
    check.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'score':
        output = Path(args.output)
        if output.exists():
            raise SystemExit(f'{output} already exists; choose a new file.')
        frame = score(args.packet, args.history_races, args.n_sims, args.seeds, args.arms)
        frame.to_csv(output, index=False)
        metrics = [c for c in frame.select_dtypes('number').columns if c not in {'year', 'round', 'seed'}]
        print(frame.groupby('arm')[metrics].mean().round(4).to_string())
        print(f'\nsaved: {output}')
        return
    decision = gate(pd.read_csv(args.metrics), args.candidate, args.baseline, args.lane)
    text = json.dumps(decision, indent=2, default=float)
    if args.output:
        Path(args.output).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
