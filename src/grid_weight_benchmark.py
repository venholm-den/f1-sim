"""Development-only grid sensitivity tuning; previously seen races are diagnostics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.accuracy_benchmark import build_replay_forecast, evaluate_forecast, simple_baseline
from src.model_config import SIMULATION_PARAMETERS
from src.simulate import simulate_races
from src.track import load_track_profile
from src.weather import summarize_weather


def select_grid_weight(metrics: pd.DataFrame) -> float:
    """Selection never sees diagnostic or fresh validation labels."""
    if metrics.empty:
        raise ValueError('No development races were evaluated.')
    development = metrics[metrics['split'].eq('development')]
    if development.empty:
        raise ValueError('No development races were evaluated.')
    # Average seeds within each race before averaging races equally.
    losses = development.groupby(['weight', 'year', 'round']).loss.mean()
    means = losses.groupby('weight').mean().sort_index()
    return float(means.idxmin())


def benchmark_grid_weights(races, output_dir: Path, prior_report: Path, *,
                           weights=(1.65, 3.3, 6.6, 13.2), seeds=(42, 123, 777),
                           n_sims=5000, load_failures=None):
    prior_report = Path(prior_report)
    prior = json.loads(prior_report.read_text(encoding='utf-8'))
    development = {tuple(key) for key in prior['development_races']}
    seen = {tuple(key) for key in prior['holdout_races']}
    if not development or not seen or max(development) >= min(seen):
        raise ValueError('Prior report must define disjoint chronological race partitions.')
    baseline = float(SIMULATION_PARAMETERS['grid_loss_multiplier'])
    weights = sorted(set(float(weight) for weight in weights) | {baseline})
    if any(not np.isfinite(weight) or not 0 <= weight <= 50 for weight in weights):
        raise ValueError('Weights must be finite and between 0 and 50.')
    seeds = list(dict.fromkeys(int(seed) for seed in seeds))
    if not seeds or n_sims < 100:
        raise ValueError('At least one seed and 100 simulations are required.')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    races = sorted(races, key=lambda race: race.key)
    episodes, skipped, sensitivity = [], [], []
    for index, race in enumerate(races):
        if race.key in development:
            split = 'development'
        elif race.key in seen:
            split = 'previously_seen_diagnostic'
        elif race.key > max(seen):
            split = 'fresh_validation'
        else:
            continue
        if 'Q' not in race.sessions or index < 2:
            skipped.append({'year': race.year, 'round': race.round, 'reason': 'missing_Q_or_baseline'})
            continue
        metadata = dict(year=race.year, round=race.round, event=race.event, session='Q')
        try:
            print(f'Preparing {race.year} R{race.round} {split}', flush=True)
            _, features = build_replay_forecast(race.sessions['Q'], races[:index], metadata=metadata,
                                               n_sims=100, seed=seeds[0])
            # Validate coverage before including this episode for any variant.
            grid = simple_baseline(features, races[:index], 'grid_order')
            grid_scores, _ = evaluate_forecast(grid, race.sessions['R'].results)
            weather = summarize_weather(race.sessions['Q'], use_forecast=False)
            from src.venues import venue_for_context
            metadata['venue'] = venue_for_context(metadata, session=race.sessions['Q'])
            track = load_track_profile(race.event, metadata=metadata)
            episodes.append((race, split, features, weather, track, grid_scores))
            sensitivity.append(dict(metadata, split=split,
                race_pace_loss_span=float(np.ptp(features.race_pace_score * features.estimated_race_laps
                    * SIMULATION_PARAMETERS['race_pace_seconds_multiplier'])),
                grid_loss_span=float(np.ptp((features.grid_position - 1)
                    * track['overtaking_difficulty'] * features.grid_confidence * baseline))))
        except (ValueError, KeyError) as exc:
            skipped.append(dict(metadata, reason=str(exc)))

    rows, prediction_rows = [], []

    def score_episode(episode, tested_weights):
        race, split, features, weather, track, grid_scores = episode
        for weight in tested_weights:
            for seed in seeds:
                summary, _, _ = simulate_races(features, n_sims=n_sims, seed=seed,
                    overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather,
                    grid_loss_multiplier=weight)
                scores, predictions = evaluate_forecast(summary, race.sessions['R'].results)
                identity = dict(year=race.year, round=race.round, event=race.event,
                                split=split, weight=weight, seed=seed)
                rows.append(dict(identity, **scores))
                prediction_rows.append(predictions.assign(**identity))

    for episode in episodes:
        if episode[1] == 'development':
            score_episode(episode, weights)
    selected = select_grid_weight(pd.DataFrame(rows))
    # Freeze the choice before evaluating later races; do not sweep on these.
    print(f'Development-selected multiplier: {selected}', flush=True)
    for episode in episodes:
        if episode[1] != 'development':
            score_episode(episode, sorted({baseline, selected}))
    metrics = pd.DataFrame(rows)
    race_metrics = metrics.groupby(['split', 'weight', 'year', 'round'], as_index=False)[
        ['finish_mae', 'win_brier', 'podium_brier', 'top10_brier', 'loss']].mean()
    summary = race_metrics.groupby(['split', 'weight'], as_index=False).agg(
        races=('round', 'count'), finish_mae=('finish_mae', 'mean'),
        win_brier=('win_brier', 'mean'), podium_brier=('podium_brier', 'mean'),
        top10_brier=('top10_brier', 'mean'), loss=('loss', 'mean'))
    fresh = summary[summary['split'].eq('fresh_validation')].set_index('weight')
    dev_count = sum(episode[1] == 'development' for episode in episodes)
    fresh_count = sum(episode[1] == 'fresh_validation' for episode in episodes)
    gain = None if fresh.empty else 1 - float(fresh.loc[selected, 'loss'] / fresh.loc[baseline, 'loss'])
    nonregression = not fresh.empty and all(fresh.loc[selected, metric] <= fresh.loc[baseline, metric]
        for metric in ['win_brier', 'podium_brier', 'top10_brier'])
    grid_rows = [dict(year=ep[0].year, round=ep[0].round, split=ep[1], **ep[5]) for ep in episodes]
    report = dict(schema_version=1, baseline_weight=baseline, candidate_weights=weights,
        selected_on_development=selected, seeds=seeds, n_sims=n_sims,
        development_race_count=dev_count, fresh_validation_race_count=fresh_count,
        fresh_validation_loss_improvement=gain,
        promotion_gate_passed=selected != baseline and dev_count >= 6 and fresh_count >= 6
                              and gain is not None and gain >= .05 and nonregression,
        promotion_gate='>=6 development and 6 fresh Q races, >=5% loss reduction, no Brier regression',
        inspected_validation_races=[list(key) for key in sorted(seen)],
        selection_policy='Development only; later already-inspected races are diagnostic, never confirmation.',
        summary=summary.to_dict('records'), skipped=skipped, load_failures=list(load_failures or []),
        prior_report_sha256=hashlib.sha256(prior_report.read_bytes()).hexdigest(),
        limitations=['Small cached qualifying sample; not a production accuracy claim.',
            'Grid weight is a heuristic, not a physically measured overtaking cost.',
            'Seed variation estimates Monte Carlo sensitivity, not statistical generalisation.',
            'Previous benchmark cutoff and cache limitations still apply.'])
    root = Path(__file__).resolve().parents[1]
    report['source_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ['src/grid_weight_benchmark.py', 'src/accuracy_benchmark.py', 'src/simulate.py',
                     'src/model_config.py', 'src/features.py', 'src/model.py', 'src/performance.py',
                     'src/grid.py', 'src/weather.py', 'src/track.py', 'src/reliability.py',
                     'src/forecast_roster.py', 'data/track_profiles.csv'] if (root / name).is_file()}
    report['input_sha256'] = {}
    for race in races:
        for code, session in race.sessions.items():
            for name in ['laps', 'results', 'weather_data']:
                frame = getattr(session, name, pd.DataFrame())
                report['input_sha256'][f'{race.year}/{race.round}/{code}/{name}'] = hashlib.sha256(
                    frame.to_csv(index=True).encode('utf-8')).hexdigest()
    metrics.to_csv(output_dir / 'seed_metrics.csv', index=False)
    race_metrics.to_csv(output_dir / 'race_metrics.csv', index=False)
    summary.to_csv(output_dir / 'summary.csv', index=False)
    pd.concat(prediction_rows, ignore_index=True).to_csv(output_dir / 'predictions.csv', index=False)
    pd.DataFrame(sensitivity).to_csv(output_dir / 'input_sensitivity.csv', index=False)
    pd.DataFrame(grid_rows).to_csv(output_dir / 'grid_baseline.csv', index=False)
    report['artifact_sha256'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in output_dir.glob('*.csv')}
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report
