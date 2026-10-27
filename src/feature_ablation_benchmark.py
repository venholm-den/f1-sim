"""Compare independent feature changes with fixed chronological partitions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.accuracy_benchmark import (build_replay_inputs, calibration_bins, evaluate_forecast,
                                    simple_baseline, session_input_frame)
from src.accuracy_candidates import (FEATURE_VARIANTS, SUPPORTED_VARIANTS, candidate_grid_multiplier,
                                     candidate_simulation_options)
from src.reliability import classify_result_status
from src.result_status import retirement_outcome
from src.simulate import simulate_races
from src.inspection_ledger import inspected_race_keys


METRICS = ['finish_mae', 'win_brier', 'podium_brier', 'top10_brier', 'dnf_brier', 'loss']


def nonfinish_status(status):
    return classify_result_status(status)


def evaluate_with_dnf(prediction, actual):
    metrics, data = evaluate_forecast(prediction, actual)
    labels = pd.Series([retirement_outcome(row) for row in actual.itertuples()],
                       index=actual.Abbreviation, dtype=float)
    data['actual_dnf'] = data.Driver.map(labels)
    known = data.actual_dnf.notna()
    metrics['dnf_known_drivers'] = int(known.sum())
    metrics['dnf_unknown_drivers'] = int((~known).sum())
    metrics['dnf_brier'] = float(((data.loc[known, 'dnf_chance']
                                 - data.loc[known, 'actual_dnf']) ** 2).mean()) if known.any() else None
    return metrics, data


def choose_on_development(race_metrics, variants=FEATURE_VARIANTS):
    dev = race_metrics[race_metrics['split'].eq('development')]
    if dev.empty:
        raise ValueError('No complete development episodes.')
    # Independent candidates are selected separately, not combined. The DNF
    # candidate must improve failure probability, not only finishing order.
    selected = {}
    for variant in variants[1:]:
        loss = dev.groupby('variant')['loss'].mean()
        dnf = dev.groupby('variant')['dnf_brier'].mean()
        eligible = loss[variant] < loss['legacy']
        if variant in {'decoupled_dnf_v1', 'all_cause_dnf_v2', 'retirement_progress_v1', 'single_pace_retirement_v1', 'survival_dnf_v1', 'season_dnf_v1', 'season_grid_dnf_v1'}:
            eligible = eligible and pd.notna(dnf[variant]) and dnf[variant] < dnf['legacy']
        selected[variant] = bool(eligible)
    return selected


def benchmark_feature_ablations(races, output_dir, prior_report, *, seeds=(42, 123, 777),
                               n_sims=5000, sessions=('PRE', 'FP2', 'Q'), load_failures=None,
                               inspected_reports=(), variants=FEATURE_VARIANTS,
                               n_baseline_races=2, retirement_history_races=30):
    # Enforce this even when callers supply deserialised Session objects rather
    # than using load_cached_races. Optional lazy FastF1 loads must stay offline.
    import fastf1
    fastf1.Cache.offline_mode(True)
    variants = tuple(dict.fromkeys(variants))
    if n_baseline_races < 1 or not 1 <= retirement_history_races <= 100:
        raise ValueError('Use positive baseline history and 1 to 100 retirement history races.')
    if not variants or variants[0] != 'legacy' or len(variants) < 2 or set(variants) - set(SUPPORTED_VARIANTS):
        raise ValueError('Choose legacy followed by supported independent candidates.')
    prior_report = Path(prior_report)
    prior = json.loads(prior_report.read_text(encoding='utf-8'))
    development = {tuple(key) for key in prior['development_races']}
    seen = {tuple(key) for key in prior['holdout_races']}
    if not development or not seen or max(development) >= min(seen):
        raise ValueError('Prior report must define disjoint chronological partitions.')
    # Even previously skipped race outcomes are not untouched evidence.
    seen.update((int(row['year']), int(row['round'])) for row in prior.get('skipped', [])
                if 'year' in row and 'round' in row
                and (int(row['year']), int(row['round'])) not in development)
    output_dir = Path(output_dir)
    # Never relabel outcomes inspected in earlier ablations as fresh evidence.
    inspected = set(Path(path) for path in inspected_reports)
    inspected.update(output_dir.parent.glob('*/report.json'))
    inspection_hashes = {}
    for path in sorted(inspected):
        report = json.loads(path.read_text(encoding='utf-8'))
        seen.update(inspected_race_keys([path]) - development)
        inspection_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    seeds = list(dict.fromkeys(int(seed) for seed in seeds))
    if not seeds or n_sims < 100 or not sessions or set(sessions) - {'PRE', 'FP2', 'Q'}:
        raise ValueError('Use valid stages, seeds and at least 100 simulations.')
    sessions = tuple(dict.fromkeys(sessions))
    races = sorted(races, key=lambda race: race.key)
    if len({race.key for race in races}) != len(races):
        raise ValueError('Duplicate race keys.')
    output_dir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    source_files = ['src/feature_ablation_benchmark.py', 'src/inspection_ledger.py', 'src/accuracy_candidates.py',
                    'src/accuracy_benchmark.py', 'src/features.py', 'src/model.py', 'src/model_config.py',
                    'src/performance.py', 'src/reliability.py', 'src/simulate.py', 'src/grid.py',
                    'src/forecast_roster.py', 'src/track.py', 'src/weather.py', 'src/result_status.py',
                    'src/retirement_risk.py', 'src/retirement_progress.py', 'src/retirement_survival.py',
                    'src/qualifying_features.py', 'src/qualifying_pace.py', 'src/qualifying_archive.py', 'src/pit_scenarios.py',
                    'src/agent_race.py', 'src/venues.py', 'data/track_profiles.csv']
    source_hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in source_files}
    rows, prediction_rows, skipped, baselines, references, weather_coverage = [], [], [], [], [], []
    for index, race in enumerate(races):
        if race.key in development:
            split = 'development'
        elif race.key in seen:
            split = 'previously_seen_diagnostic'
        elif race.key > max(seen):
            split = 'fresh_validation'
        else:
            continue
        if index < n_baseline_races:
            continue
        for code in sessions:
            metadata = dict(year=race.year, round=race.round, event=race.event, session=code)
            current = None if code == 'PRE' else race.sessions.get(code)
            if code != 'PRE' and current is None:
                skipped.append(dict(metadata, reason='session_not_cached'))
                continue
            print(f'Ablation {race.year} R{race.round} {code} {split}', flush=True)
            stage_rows, stage_predictions, stage_baselines, stage_references = [], [], [], []
            try:
                for variant in variants:
                    features, track, weather = build_replay_inputs(current, races[:index],
                        metadata=metadata, feature_variant=variant, n_baseline_races=n_baseline_races,
                        retirement_history_races=retirement_history_races)
                    if variant == 'normalised_history_v1':
                        stage_references.append(dict(metadata, split=split,
                            reference_lap_seconds=float(features.historical_reference_lap_seconds.iloc[0]),
                            reference_source=str(features.historical_reference_source.iloc[0])))
                    if variant == 'legacy':
                        weather_coverage.append(dict(metadata, split=split,
                            weather_source=weather.get('weather_source', 'not_observed_before_session'),
                            rainfall_flag=weather.get('rainfall_flag')))
                        for baseline in ('grid_order', 'recent_form'):
                            scores, _ = evaluate_forecast(simple_baseline(features, races[:index], baseline,
                                                                         n_baseline_races=n_baseline_races),
                                                         race.sessions['R'].results)
                            stage_baselines.append(dict(metadata, split=split, variant=baseline, **scores))
                    for seed in seeds:
                        forecast, _, _ = simulate_races(features, n_sims=n_sims, seed=seed,
                            overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather,
                            grid_loss_multiplier=candidate_grid_multiplier(variant, code),
                            **candidate_simulation_options(variant, features))
                        scores, data = evaluate_with_dnf(forecast, race.sessions['R'].results)
                        identity = dict(metadata, split=split, variant=variant, seed=seed)
                        stage_rows.append(dict(identity, **scores))
                        stage_predictions.append(data.assign(**identity))
                # Complete-driver, identical episodes across all three variants.
                rows.extend(stage_rows)
                prediction_rows.extend(stage_predictions)
                baselines.extend(stage_baselines)
                references.extend(stage_references)
            except (ValueError, KeyError) as exc:
                skipped.append(dict(metadata, reason=str(exc)))
    if not rows:
        (output_dir / 'no_coverage.json').write_text(json.dumps({'skipped': skipped,
            'variants': list(variants), 'activated': False, 'promotion_eligible': False}, indent=2), encoding='utf-8')
        raise ValueError('No complete ablation episodes.')
    metrics = pd.DataFrame(rows)
    race_metrics = metrics.groupby(['variant', 'session', 'split', 'year', 'round'], as_index=False)[
        METRICS + ['dnf_known_drivers', 'dnf_unknown_drivers']].mean()
    selected = choose_on_development(race_metrics, variants)
    summary = race_metrics.groupby(['variant', 'session', 'split'], as_index=False).agg(
        races=('round', 'count'), **{metric: (metric, 'mean') for metric in METRICS},
        dnf_known_drivers=('dnf_known_drivers', 'sum'), dnf_unknown_drivers=('dnf_unknown_drivers', 'sum'))
    gates = {}
    for variant in variants[1:]:
        reasons = []
        if not selected[variant]:
            reasons.append('candidate_not_selected_on_development')
        for code in sessions:
            dev = race_metrics[(race_metrics.variant == variant) & (race_metrics.session == code)
                               & (race_metrics['split'] == 'development')]
            fresh = race_metrics[(race_metrics.session == code) & (race_metrics['split'] == 'fresh_validation')]
            candidate = fresh[fresh.variant.eq(variant)]
            legacy = fresh[fresh.variant.eq('legacy')]
            if len(dev) < 6 or len(candidate) < 6:
                reasons.append(f'{code}_insufficient_development_or_fresh_races')
                continue
            if candidate.loss.mean() > .95 * legacy.loss.mean():
                reasons.append(f'{code}_loss_improvement_below_5_percent')
            for metric in ['win_brier', 'podium_brier', 'top10_brier', 'dnf_brier']:
                if pd.isna(candidate[metric].mean()) or candidate[metric].mean() > legacy[metric].mean():
                    reasons.append(f'{code}_{metric}_missing_or_regressed')
            if variant in {'decoupled_dnf_v1', 'all_cause_dnf_v2', 'retirement_progress_v1', 'single_pace_retirement_v1', 'survival_dnf_v1', 'season_dnf_v1', 'season_grid_dnf_v1'} and candidate.dnf_brier.mean() >= legacy.dnf_brier.mean():
                reasons.append(f'{code}_dnf_brier_not_improved')
        gates[variant] = dict(passed=not reasons, reasons=reasons)
    predictions = pd.concat(prediction_rows, ignore_index=True)
    # Seeds describe sampling sensitivity, not independent race outcomes.
    # Average forecasts per driver/episode before building calibration bins.
    calibration_predictions = predictions.groupby(
        ['variant', 'session', 'split', 'year', 'round', 'Driver'], as_index=False).agg(
        win_chance=('win_chance', 'mean'), podium_chance=('podium_chance', 'mean'),
        points_chance=('points_chance', 'mean'), dnf_chance=('dnf_chance', 'mean'),
        actual_position=('actual_position', 'first'), actual_dnf=('actual_dnf', 'first'))
    bins = calibration_bins(calibration_predictions)
    dnf_bins = []
    known = calibration_predictions[calibration_predictions.actual_dnf.notna()]
    for keys, group in known.groupby(['variant', 'session', 'split']):
        for bucket, part in group.groupby((group.dnf_chance * 10).astype(int).clip(0, 9)):
            dnf_bins.append(dict(zip(['variant', 'session', 'split'], keys), outcome='dnf_chance',
                bucket=int(bucket), count=len(part), predicted=float(part.dnf_chance.mean()),
                observed=float(part.actual_dnf.mean())))
    bins = pd.concat([bins, pd.DataFrame(dnf_bins)], ignore_index=True)
    report = dict(schema_version=2, variants=list(variants), n_sims=n_sims, seeds=seeds,
        n_baseline_races=n_baseline_races, retirement_history_races=retirement_history_races,
        sessions=list(sessions), development_races=[list(key) for key in sorted(development)],
        inspected_races=[list(key) for key in sorted(seen)],
        evaluated_races=[list(key) for key in sorted(set(zip(metrics.year, metrics['round'])))],
        attempted_races=[list(key) for key in sorted(set(zip(metrics.year, metrics['round']))
            | {(row['year'], row['round']) for row in skipped})],
        fresh_validation_races=[list(key) for key in sorted(set(zip(
            metrics[metrics['split'].eq('fresh_validation')].year,
            metrics[metrics['split'].eq('fresh_validation')]['round'])))],
        selected_on_development=selected, promotion_gates=gates,
        promotion_policy='Separate ablations plus a declared combined diagnostic; >=6 development and fresh races per stage, '
                         '>=5% lower MAE+top10 Brier, no outcome Brier regression; DNF candidate improves DNF Brier.',
        offline_enforced=True,
        summary=summary.astype(object).where(pd.notna(summary), None).to_dict('records'),
        skipped=skipped, load_failures=list(load_failures or []),
        session_weather_availability=weather_coverage,
        prior_report_sha256=hashlib.sha256(prior_report.read_bytes()).hexdigest(),
        inspected_report_sha256=inspection_hashes,
        source_sha256=source_hashes,
        limitations=['Retrospectively corrected cache and latest cached baseline limitations remain.',
            'DNF labels include Retired without assigning a cause; other unknown statuses excluded and counted.',
            'Calibration bins average seeds before counting unique driver/race/stage observations.',
            'The all-cause candidate uses declared shrinkage/recency assumptions; calibration is unproven.',
            'PRE target-lap reference uses prior same-event race or an explicit 90-second assumption.',
            'Lap-fraction normalisation does not identify car, driver, fuel, tyres or track evolution.',
            'Earlier inspected races are diagnostics; no live model defaults are changed.'])
    if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
           for name, digest in source_hashes.items()):
        raise ValueError('Benchmark source changed during execution; rerun in a stable checkout.')
    report['input_sha256'] = {}
    for race in races:
        for code, session in race.sessions.items():
            for name in ['laps', 'results', 'weather_data']:
                frame = session_input_frame(session, name)
                report['input_sha256'][f'{race.year}/{race.round}/{code}/{name}'] = hashlib.sha256(
                    frame.to_csv(index=True).encode('utf-8')).hexdigest()
    for name, frame in [('seed_metrics', metrics), ('race_metrics', race_metrics), ('summary', summary),
                        ('predictions', predictions), ('calibration_bins', bins),
                        ('simple_baselines', pd.DataFrame(baselines)), ('pace_references', pd.DataFrame(references))]:
        frame.to_csv(output_dir / f'{name}.csv', index=False)
    report['artifact_sha256'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in output_dir.glob('*.csv')}
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report
