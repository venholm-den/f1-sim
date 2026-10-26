"""Offline, stage-separated retirement diagnostics on checksum-verified archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.benchmark_grid_influence import load_archive
from src.accuracy_benchmark import build_replay_inputs, evaluate_forecast, simple_baseline
from src.app_services.accuracy import finishers_only
from src.circuit_calibration import sha256
from src.feature_ablation_benchmark import evaluate_with_dnf
from src.race_scores import race_scores
from src.result_status import RETIREMENT_POLICY_VERSION, retirement_label, retirement_outcome
from src.retirement_risk import apply_retirement_risk
from src.retirement_season import apply_season_retirement_risk
from src.simulate import simulate_races
from src.venues import venue_for_context

ARMS = ('established', 'all_cause_dnf_v2', 'season_dnf_v1')
METRICS = ('finish_mae', 'finishers_finish_mae', 'win_brier', 'podium_brier',
           'top10_brier', 'dnf_brier', 'rps', 'threshold_rps', 'log_score', 'pair_brier',
           'expected_retirements', 'expected_retirements_all', 'actual_retirements',
           'dnf_known_drivers', 'dnf_unknown_drivers')
KEYS = ['year', 'round', 'session']


def audit_labels(races):
    """Expose original status-only disagreements and retain every input row."""
    rows = []
    for race in races:
        for row in race.sessions['R'].results.itertuples():
            label = retirement_outcome(row)
            old = retirement_label(getattr(row, 'Status', None))
            rows.append(dict(year=race.year, round=race.round, event=race.event,
                Driver=row.Abbreviation, Status=getattr(row, 'Status', None),
                ClassifiedPosition=getattr(row, 'ClassifiedPosition', ''),
                VerifiedRetirement=getattr(row, 'VerifiedRetirement', np.nan),
                status_only_label=old, actual_dnf=label,
                label_changed=bool(not (np.isnan(old) and np.isnan(label)) and old != label)))
    return pd.DataFrame(rows)


def paired_interval(values, *, seed=20261026):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = values[rng.integers(0, len(values), size=(4000, len(values)))].mean(axis=1)
    return [float(v) for v in np.quantile(samples, [.025, .975])]


def decisions(metrics, baselines):
    """Historical screen only. Never grants prospective or live promotion."""
    output = []
    for stage in ('PRE', 'FP2', 'Q'):
        later = metrics[metrics.session.eq(stage) & metrics['split'].eq('previously_seen_diagnostic')]
        dev = metrics[metrics.session.eq(stage) & metrics['split'].eq('development')]
        control = later[later.arm.eq('established')]
        for arm in ARMS[1:]:
            candidate = later[later.arm.eq(arm)]
            pair = candidate.merge(control, on=KEYS, suffixes=('_new', '_old'), validate='one_to_one')
            reasons, differences = [], {}
            if len(pair) < 6 or len(pair) != len(candidate) or len(pair) != len(control):
                reasons.append('insufficient_matched_later_races')
            for metric in ('finish_mae', 'finishers_finish_mae', 'rps', 'dnf_brier',
                           'win_brier', 'podium_brier', 'top10_brier'):
                delta = pair[metric+'_new'] - pair[metric+'_old']
                differences[metric] = {'mean_delta': float(delta.mean()) if len(delta) else None,
                                       'race_bootstrap_95': paired_interval(delta)}
            gain = float(1-pair.rps_new.mean()/pair.rps_old.mean()) if len(pair) else None
            if gain is None or gain < .05:
                reasons.append('diagnostic_rps_improvement_below_5_percent')
            interval = differences['finish_mae']['race_bootstrap_95']
            if interval is None or interval[0] > 0:
                reasons.append('finish_mae_clearly_worse_or_unknown')
            for name in ('win_brier', 'podium_brier', 'top10_brier', 'dnf_brier'):
                if pair.empty or pair[name+'_new'].isna().any() or pair[name+'_old'].isna().any():
                    reasons.append(name+'_missing')
                elif pair[name+'_new'].mean() > pair[name+'_old'].mean():
                    reasons.append(name+'_regressed')
            if pair.empty or pair.dnf_brier_new.mean() >= pair.dnf_brier_old.mean():
                reasons.append('retirement_brier_not_improved')
            selected = dev[dev.arm.eq(arm)]
            old = dev[dev.arm.eq('established')]
            if selected.empty or (selected.rps.mean() >= old.rps.mean()
                                  or selected.dnf_brier.mean() >= old.dnf_brier.mean()):
                reasons.append('not_selected_on_development')
            grid_mae = None
            if stage == 'Q':
                grid = baselines[baselines['split'].eq('previously_seen_diagnostic') & baselines.session.eq('Q')]
                q = pair.merge(grid[KEYS+['finish_mae']], on=KEYS, validate='one_to_one')
                grid_mae = float(q.finish_mae.mean()) if len(q) else None
                if len(q) != len(pair) or q.empty or q.finish_mae_new.mean() >= q.finish_mae.mean():
                    reasons.append('does_not_beat_qualifying_order')
            output.append(dict(stage=stage, arm=arm, paired_races=len(pair), rps_improvement=gain,
                qualifying_order_mae=grid_mae, paired_metrics=differences,
                diagnostic_decision='collect_fresh_evidence' if not reasons else 'retain_established',
                reasons=reasons, fresh_races=0, activated=False, promotion_approved=False))
    return output


def run(workspace, output, *, years=tuple(range(2021, 2027)), n_sims=5000,
        seeds=(42, 123, 777), history=5):
    if n_sims < 100 or not seeds or history < 1:
        raise ValueError('Use >=100 simulations, nonempty seeds and positive pace history.')
    import fastf1
    fastf1.Cache.offline_mode(True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    source_paths = [*sorted((root/'src').rglob('*.py')), Path(__file__),
                    root/'scripts/benchmark_grid_influence.py', root/'data/track_profiles.csv',
                    root/'data/team_power_units.csv', root/'data/retirement_labels/verified_outcomes_v1.csv']
    hashes = {str(p.resolve()): sha256(p) for p in source_paths}
    protocol = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), arms=list(ARMS),
        n_sims=n_sims, seeds=list(seeds), pace_history_races=history,
        retirement_history_races=30, season_history='Same 30 earlier races; filtered to current and two prior seasons',
        label_policy=RETIREMENT_POLICY_VERSION, source_sha256=hashes,
        split='2021-2024 development; 2025-2026 previously inspected diagnostics; zero fresh validation',
        stage_policy='PRE/FP2/Q separate; identical driver episodes across arms; no Q rank imputation',
        primary='Paired whole-race RPS; Brier guardrails, finish MAE and Q qualifying-order baseline',
        uncertainty='Seeds averaged inside a race, equal race weights; whole-race bootstrap 95% intervals',
        activated=False, promotion_approved=False)
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    races, _, inputs, failures, q_audit = load_archive(workspace, years)
    audit = audit_labels(races)
    audit.to_csv(output/'retirement_labels.csv', index=False)
    label_summary = audit.groupby('year', as_index=False).agg(entries=('Driver', 'size'),
        retirements=('actual_dnf', 'sum'), known=('actual_dnf', 'count'),
        status_only_disagreements=('label_changed', 'sum'))
    label_summary['unknown_or_excluded'] = label_summary.entries-label_summary.known
    label_summary.to_csv(output/'label_summary.csv', index=False)
    rows, predictions, baselines, skipped = [], [], [], []
    history_sessions = []
    for index, race in enumerate(races):
        metadata = dict(year=race.year, round=race.round, event=race.event)
        metadata['venue'] = venue_for_context(metadata, session=race.sessions['R'])
        # Histories are appended only after the target has been evaluated.
        earlier = list(history_sessions)
        if index >= history:
            for stage in ('PRE', 'FP2', 'Q'):
                identity = dict(year=race.year, round=race.round, event=race.event, session=stage,
                                split='development' if race.year <= 2024 else 'previously_seen_diagnostic')
                current = None if stage == 'PRE' else race.sessions.get(stage)
                if stage != 'PRE' and current is None:
                    skipped.append({**identity, 'reason': 'session_unavailable_or_invalid_classification'})
                    continue
                try:
                    base, track, weather = build_replay_inputs(current, races[:index],
                        metadata={**metadata, 'session': stage}, n_baseline_races=history)
                    variants = {'established': base,
                        'all_cause_dnf_v2': apply_retirement_risk(base, earlier[-30:], metadata),
                        'season_dnf_v1': apply_season_retirement_risk(base, earlier[-30:], metadata)}
                    actual = race.sessions['R'].results
                    grid, _ = evaluate_forecast(simple_baseline(base, races[:index], 'grid_order'), actual)
                    episode_rows, episode_predictions = [], []
                    print(f'Retirement replay {race.year} R{race.round} {stage}', flush=True)
                    for arm, features in variants.items():
                        for seed in seeds:
                            summary, matrix, draws = simulate_races(features, n_sims=n_sims, seed=seed,
                                overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather)
                            scores, data = evaluate_with_dnf(summary, actual)
                            scores.update(race_scores(summary, matrix, draws, actual.rename(columns={'Abbreviation': 'Driver'})))
                            scores.update(finishers_only(data))
                            known = data.actual_dnf.notna()
                            scores.update(expected_retirements=float(data.loc[known, 'dnf_chance'].sum()),
                                expected_retirements_all=float(data.dnf_chance.sum()),
                                actual_retirements=float(data.actual_dnf.sum()))
                            episode_rows.append({**identity, 'arm': arm, 'seed': seed, **scores})
                            episode_predictions.append(data.assign(**identity, arm=arm, seed=seed))
                    rows.extend(episode_rows)
                    predictions.extend(episode_predictions)
                    baselines.append({**identity, **grid})
                except (ValueError, KeyError) as exc:
                    skipped.append({**identity, 'reason': str(exc)})
        history_sessions.append((race.sessions['R'], metadata))
    if not rows:
        raise ValueError('No matched retirement comparison episodes.')
    seed_metrics = pd.DataFrame(rows)
    metrics = seed_metrics.groupby(KEYS+['split', 'arm'], as_index=False)[list(METRICS)].mean()
    summary = metrics.groupby(['session', 'split', 'arm'], as_index=False).agg(
        races=('round', 'size'), **{name: (name, 'mean') for name in METRICS})
    yearly = metrics.groupby(['year', 'session', 'arm'], as_index=False).agg(
        races=('round', 'size'), expected_retirements=('expected_retirements', 'sum'),
        actual_retirements=('actual_retirements', 'sum'), dnf_brier=('dnf_brier', 'mean'))
    pooled = pd.concat(predictions, ignore_index=True).groupby(KEYS+['split', 'arm', 'Driver'], as_index=False)[
        ['avg_finish', 'win_chance', 'podium_chance', 'points_chance', 'dnf_chance', 'actual_position', 'actual_dnf']].mean()
    known = pooled[pooled.actual_dnf.notna()].copy()
    known['bucket'] = (known.dnf_chance*10).astype(int).clip(0, 9)
    bins = known.groupby(['session', 'split', 'arm', 'bucket'], as_index=False).agg(
        driver_races=('Driver', 'size'), predicted=('dnf_chance', 'mean'), observed=('actual_dnf', 'mean'))
    baselines = pd.DataFrame(baselines)
    for name, frame in (('seed_metrics', seed_metrics), ('race_metrics', metrics), ('summary', summary),
                        ('yearly_retirements', yearly), ('predictions', pooled),
                        ('retirement_calibration', bins), ('qualifying_baseline', baselines)):
        frame.to_csv(output/(name+'.csv'), index=False)
    for path, expected in hashes.items():
        if sha256(Path(path)) != expected:
            raise ValueError('Benchmark source changed during replay: '+path)
    report = {**protocol, 'input_sources': inputs, 'load_failures': failures, 'qualifying_audit': q_audit,
        'inspected_races': [list(r.key) for r in races], 'fresh_validation_races': [], 'skipped': skipped,
        'label_summary': label_summary.to_dict('records'), 'summary': summary.to_dict('records'),
        'decisions': decisions(metrics, baselines),
        'artifact_sha256': {p.name: sha256(p) for p in output.glob('*') if p.is_file()}}
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(summary.round(5).to_string(index=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--history', type=int, default=5)
    args = parser.parse_args()
    run(args.workspace, args.output_dir, n_sims=args.n_sims, history=args.history)
