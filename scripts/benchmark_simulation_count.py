"""Paired offline simulation-count diagnostic; established model only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from scripts.benchmark_grid_influence import load_archive
from src.accuracy_benchmark import build_replay_inputs, evaluate_forecast, simple_baseline
from src.circuit_calibration import sha256
from src.feature_ablation_benchmark import METRICS, evaluate_with_dnf
from src.simulate import simulate_races


def run(workspace, output, *, years=(2024, 2025, 2026), score_from=2025,
        counts=(10_000, 50_000, 100_000), seeds=(42, 123, 777), history=5):
    counts, seeds = tuple(dict.fromkeys(counts)), tuple(dict.fromkeys(seeds))
    if len(counts) < 2 or min(counts) < 100 or len(seeds) < 2 or history < 1:
        raise ValueError('Need >=2 counts (>=100), >=2 seeds and positive history.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    import fastf1
    fastf1.Cache.offline_mode(True)
    races, venues, sources, failures, audit = load_archive(workspace, years)
    root = Path(__file__).resolve().parents[1]
    paths = [*sorted((root/'src').rglob('*.py')), Path(__file__),
             root/'scripts/benchmark_grid_influence.py', root/'data/track_profiles.csv',
             root/'data/team_power_units.csv']
    protocol = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        counts=counts, seeds=seeds, history=history, score_from=score_from,
        stages=['PRE', 'FP2', 'Q'], input_sources=sources, load_failures=failures,
        qualifying_audit=audit, model='established; active circuit difficulty; observed stage weather',
        source_sha256={str(p.resolve()): sha256(p) for p in paths},
        limitations=['Previously inspected historical diagnostics; no fresh validation claim.',
            'Retrospective archives cannot attest original publication timing.',
            'PRE uses the latest baseline roster assumption; incomplete coverage is excluded.',
            'Counts share seeds but RNG array shapes differ: draws are not nested.',
            'Only simulation count changes; candidate suite and frozen forecasts are untouched.'])
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    rows, predictions, skips, baselines = [], [], [], []
    for index, race in enumerate(races):
        if race.year < score_from or index < history:
            continue
        for stage in protocol['stages']:
            identity = dict(year=race.year, round=race.round, event=race.event, session=stage)
            current = None if stage == 'PRE' else race.sessions.get(stage)
            try:
                if stage != 'PRE' and current is None:
                    raise ValueError('Stage absent or invalid official classification')
                metadata = identity | {'venue': venues[race.key].get(stage, venues[race.key]['R'])}
                features, track, weather = build_replay_inputs(current, races[:index],
                    metadata=metadata, n_baseline_races=history)
                baseline, _ = evaluate_forecast(simple_baseline(features, races[:index], 'grid_order'),
                                                race.sessions['R'].results)
                episode_rows, episode_predictions = [], []
                for count in counts:
                    for seed in seeds:
                        start = perf_counter()
                        forecast, matrix, raw = simulate_races(features, n_sims=count, seed=seed,
                            overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather)
                        elapsed = perf_counter() - start
                        scores, data = evaluate_with_dnf(forecast, race.sessions['R'].results)
                        tag = identity | dict(n_sims=count, seed=seed)
                        episode_rows.append(tag | scores | dict(seconds=elapsed))
                        episode_predictions.append(data.assign(**tag))
                        del forecast, matrix, raw
                        gc.collect()
                rows.extend(episode_rows)
                predictions.extend(episode_predictions)
                baselines.append(identity | baseline)
                pd.DataFrame(rows).to_csv(output/'seed_metrics.csv', index=False)
                print(f'{race.year} R{race.round} {stage}: complete', flush=True)
            except (ValueError, KeyError) as exc:
                skips.append(identity | dict(reason=str(exc)))
                print(f'{race.year} R{race.round} {stage}: skipped: {exc}', flush=True)
    if not rows:
        raise ValueError('No complete matched episodes.')
    frame = pd.DataFrame(rows)
    keys = ['session', 'year', 'round', 'n_sims']
    race_metrics = frame.groupby(keys, as_index=False)[METRICS + ['seconds']].mean()
    summary = race_metrics.groupby(['session', 'n_sims'], as_index=False).agg(
        races=('round', 'count'), **{m: (m, 'mean') for m in METRICS + ['seconds']})
    pred = pd.concat(predictions, ignore_index=True)
    probabilities = ['win_chance', 'podium_chance', 'points_chance', 'dnf_chance']
    spread = pred.groupby(keys + ['Driver'])[probabilities].std().groupby(['session', 'n_sims']).mean()
    spread = spread.rename(columns={p: p + '_seed_sd' for p in probabilities}).reset_index()
    summary = summary.merge(spread, on=['session', 'n_sims'], validate='one_to_one')
    # Resample whole races after averaging seeds, never treat seeds as extra races.
    comparisons = []
    for stage in protocol['stages']:
        subset = race_metrics[race_metrics.session.eq(stage)]
        for baseline_count in counts[:-1]:
            for metric in METRICS:
                pairs = subset.pivot(index=['year', 'round'], columns='n_sims', values=metric).dropna()
                delta = (pairs[counts[-1]] - pairs[baseline_count]).to_numpy()
                if not len(delta):
                    continue
                rng = np.random.default_rng(20261025)
                boots = rng.choice(delta, size=(10000, len(delta)), replace=True).mean(axis=1)
                comparisons.append(dict(session=stage, baseline_count=baseline_count,
                    candidate_count=counts[-1], metric=metric, races=len(delta),
                    baseline=float(pairs[baseline_count].mean()), candidate=float(pairs[counts[-1]].mean()),
                    delta=float(delta.mean()), delta_ci95_low=float(np.quantile(boots, .025)),
                    delta_ci95_high=float(np.quantile(boots, .975))))
    race_metrics.to_csv(output/'race_metrics.csv', index=False)
    summary.to_csv(output/'summary.csv', index=False)
    pred.to_csv(output/'predictions.csv', index=False)
    pd.DataFrame(comparisons).to_csv(output/'paired_comparison.csv', index=False)
    pd.DataFrame(baselines).to_csv(output/'grid_baseline.csv', index=False)
    report = protocol | dict(completed_at_utc=datetime.now(timezone.utc).isoformat(),
        summary=summary.to_dict('records'), comparisons=comparisons, skipped=skips,
        matched_episodes=int(len(race_metrics) / len(counts)), fresh_validation_races=0,
        artifact_sha256={p.name: sha256(p) for p in output.iterdir() if p.is_file()})
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(summary.to_string(index=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--years', nargs='+', type=int, default=[2024, 2025, 2026])
    parser.add_argument('--score-from', type=int, default=2025)
    parser.add_argument('--counts', nargs='+', type=int, default=[10000, 50000, 100000])
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 777])
    parser.add_argument('--history', type=int, default=5)
    args = parser.parse_args()
    run(args.workspace, args.output_dir, years=args.years, score_from=args.score_from,
        counts=args.counts, seeds=args.seeds, history=args.history)


if __name__ == '__main__':
    main()
