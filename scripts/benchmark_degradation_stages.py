"""Fixed single-degradation experiment across PRE/FP2/Q on saved archives."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from scripts.benchmark_grid_influence import load_archive
from src.circuit_calibration import sha256
from src.feature_ablation_benchmark import benchmark_feature_ablations
from src.inspection_ledger import discover_reports


def screen_diagnostics(metrics, baselines):
    """Screen matched later races; this can never supply fresh promotion evidence."""
    decisions = []
    keys = ['year', 'round', 'session']
    for stage in ('PRE', 'FP2', 'Q'):
        part = metrics[metrics.session.eq(stage) & metrics['split'].eq('previously_seen_diagnostic')]
        control = part[part.variant.eq('legacy')]
        candidate = part[part.variant.eq('single_degradation_v1')]
        pair = candidate.merge(control, on=keys, suffixes=('_candidate', '_control'), validate='one_to_one')
        reasons = []
        if len(pair) < 6 or len(pair) != len(candidate) or len(pair) != len(control):
            reasons.append('insufficient_matched_diagnostic_coverage')
        denominator = pair.loss_control.mean()
        gain = float(1 - pair.loss_candidate.mean()/denominator) if denominator > 0 else None
        if gain is None or gain < .05:
            reasons.append('diagnostic_loss_improvement_below_5_percent')
        for metric in ('win_brier', 'podium_brier', 'top10_brier', 'dnf_brier'):
            if pair.empty or pair[metric+'_candidate'].isna().any() or pair[metric+'_control'].isna().any():
                reasons.append(metric+'_missing')
            elif pair[metric+'_candidate'].mean() > pair[metric+'_control'].mean():
                reasons.append(metric+'_regressed')
        grid_mae = None
        if stage == 'Q':
            grid = baselines[baselines.session.eq(stage) & baselines['split'].eq('previously_seen_diagnostic')
                             & baselines.variant.eq('grid_order')]
            q = pair.merge(grid[keys+['finish_mae']], on=keys, validate='one_to_one')
            grid_mae = float(q.finish_mae.mean()) if not q.empty else None
            if len(q) != len(pair) or q.empty or q.finish_mae_candidate.mean() >= q.finish_mae.mean():
                reasons.append('does_not_beat_qualifying_order')
        decisions.append({'stage': stage, 'paired_races': len(pair), 'loss_improvement': gain,
            'legacy_mae': float(pair.finish_mae_control.mean()) if not pair.empty else None,
            'candidate_mae': float(pair.finish_mae_candidate.mean()) if not pair.empty else None,
            'qualifying_order_mae': grid_mae, 'passes_diagnostic_screen': not reasons,
            'reasons': reasons, 'fresh_races': 0, 'promotion_approved': False})
    return decisions


def run(workspace, output, *, years, fit_through=2024, n_sims=5000,
        seeds=(42, 123, 777), n_baseline_races=2):
    races, _, sources, failures, q_audit = load_archive(workspace, years)
    development = [list(r.key) for r in races if r.year <= fit_through]
    later = [list(r.key) for r in races if r.year > fit_through]
    if not development or not later:
        raise ValueError('Need earlier development and later diagnostic races.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'development_races': development, 'holdout_races': later,
        'attempted_races': [list(r.key) for r in races],
        'variants': ['legacy', 'single_degradation_v1'], 'sessions': ['PRE', 'FP2', 'Q'],
        'n_sims': n_sims, 'seeds': list(seeds), 'n_baseline_races': n_baseline_races,
        'single_degradation_multiplier': 2.0,
        'input_sources': sources, 'qualifying_audit': q_audit, 'load_failures': failures,
        'source_sha256': {str(Path(__file__).resolve()): sha256(Path(__file__))},
        'interpretation': 'All retrospective races are inspected diagnostics, never fresh validation.',
        'decision_rule': 'Each stage needs >=6 matched later races, >=5% lower loss, '
            'no outcome Brier regression; Q must beat qualifying order. '
            'A pass permits prospective review, never live activation.',
        'activated': False, 'promotion_approved': False}
    prior = output/'protocol.json'
    prior.write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    report = benchmark_feature_ablations(races, output/'comparison', prior,
        seeds=seeds, n_sims=n_sims, sessions=('PRE', 'FP2', 'Q'),
        load_failures=failures, inspected_reports=[prior, *discover_reports(root)],
        variants=('legacy', 'single_degradation_v1'), n_baseline_races=n_baseline_races)
    result = {'summary': report['summary'], 'promotion_gates': report['promotion_gates'],
              'diagnostic_screening': screen_diagnostics(pd.read_csv(output/'comparison/race_metrics.csv'),
                                                         pd.read_csv(output/'comparison/simple_baselines.csv')),
              'fresh_validation_races': report['fresh_validation_races'],
              'protocol_sha256': sha256(prior), 'activated': False}
    (output/'result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2021, 2027)))
    args = parser.parse_args()
    print(json.dumps(run(args.workspace, args.output_dir, years=args.years), indent=2))


if __name__ == '__main__':
    main()
