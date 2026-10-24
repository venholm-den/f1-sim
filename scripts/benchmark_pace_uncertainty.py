"""Offline A/B of pace uncertainty and the tuned shadow settings.

Replays the same recent-baseline packet as scripts.promotion_check: earlier
races' pace plus the actual grid. Arms share features and seeds:

- established: aggregate engine, live settings
- multi_score_tuned_v1: aggregate engine with the tuned pace and grid
  settings from src/shadow_settings.py
- multi_score_tuned_team_noise: the same plus team_noise_v1 (3 s)
- agent_laps_v1: car-agent engine
- pace_uncertainty_v1: agent engine with team and driver pace drawn per sim
  (spreads estimated from races before the target only) and incidents
- pace_uncertainty_pace_only / pace_uncertainty_incidents_only: ablations
- pace_uncertainty_half_spread: both pace spreads halved, a sensitivity check
  for misses inflated by measurement noise in a single race's pace

Rows carry every score from src/race_scores.py in the long format that
`python -m scripts.promotion_check gate` reads. These races were already
inspected, so results are diagnostics, not promotion evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.benchmark_safety_car import DEFAULT_PACKET, _features
from src.pace_uncertainty import estimate_pace_error, simulate_uncertain_agent_races
from src.race_scores import race_scores
from src.shadow_settings import shadow_overrides
from src.simulate import simulate_races
from src.track import load_track_profile

ARMS = ('established', 'multi_score_tuned_v1', 'multi_score_tuned_team_noise', 'agent_laps_v1',
        'pace_uncertainty_v1', 'pace_uncertainty_pace_only', 'pace_uncertainty_incidents_only',
        'pace_uncertainty_half_spread')


def _simulate(arm, features, n_sims, seed, difficulty, spreads):
    if arm == 'established':
        return simulate_races(features, n_sims=n_sims, seed=seed, overtaking_difficulty=difficulty)
    if arm.startswith('multi_score_tuned'):
        extra = {'team_noise_seconds': 3.0} if arm.endswith('team_noise') else {}
        return simulate_races(features, n_sims=n_sims, seed=seed, overtaking_difficulty=difficulty,
                              parameter_overrides=shadow_overrides('multi_score_tuned_v1'), **extra)
    if arm == 'agent_laps_v1':
        return simulate_races(features, n_sims=n_sims, seed=seed, overtaking_difficulty=difficulty,
                              agent_settings={})
    settings = dict(spreads)
    if arm == 'pace_uncertainty_pace_only':
        settings['incident_probability'] = 0.0
    if arm == 'pace_uncertainty_incidents_only':
        settings.update(team_pace_sd=0.0, driver_pace_sd=0.0)
    if arm == 'pace_uncertainty_half_spread':
        settings = {key: value / 2 for key, value in settings.items()}
    return simulate_uncertain_agent_races(features, n_sims, seed, uncertainty=settings,
                                          overtaking_difficulty=difficulty)


def run(packet, history_races, n_sims, seeds, arms=ARMS, rounds=None):
    packet = Path(packet)
    pace = pd.read_csv(packet / 'baseline_race_features.csv')
    results = pd.read_csv(packet / 'fastf1_race_results.csv')
    rows = []
    for round_ in sorted(results.Round.unique())[history_races:]:
        if rounds and round_ not in rounds:
            continue
        race = results[results.Round.eq(round_)]
        event = str(race.Event.iloc[0])
        profile = load_track_profile(event, metadata={'year': int(race.Year.iloc[0]), 'round': int(round_), 'event': event})
        laps = float(profile.get('race_laps') or 57)
        history = pace[pace.source_round.between(round_ - history_races, round_ - 1)]
        features = _features(history, race, laps)
        actual = race.rename(columns={'Abbreviation': 'Driver'})[['Driver', 'Position']]
        estimate = estimate_pace_error(pace, history_races, before_round=round_)
        spreads = {'team_pace_sd': estimate['team_pace_sd'], 'driver_pace_sd': estimate['driver_pace_sd']}
        difficulty = float(profile['overtaking_difficulty'])
        print(f"round {round_}: team {spreads['team_pace_sd']:.3f} s/lap, driver {spreads['driver_pace_sd']:.3f} s/lap "
              f"from {estimate['races_used']} earlier races")
        for arm in arms:
            for seed in seeds:
                summary, matrix, sims = _simulate(arm, features, n_sims, seed, difficulty, spreads)
                rows.append({'round': int(round_), 'event': event, 'seed': seed, 'arm': arm,
                             **race_scores(summary, matrix, sims, actual)})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    parser.add_argument('--history-races', type=int, default=3)
    parser.add_argument('--n-sims', type=int, default=1000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--arms', nargs='+', choices=ARMS, default=list(ARMS))
    parser.add_argument('--rounds', type=int, nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f'{output} already exists; choose a new file.')
    frame = run(args.packet, args.history_races, args.n_sims, args.seeds, args.arms, args.rounds)
    frame.to_csv(output, index=False)
    metrics = [c for c in frame.select_dtypes('number').columns if c not in {'round', 'seed'}]
    print(frame.groupby('arm')[metrics].mean().round(4).to_string())
    print(f'\nsaved: {output}')


if __name__ == '__main__':
    main()
