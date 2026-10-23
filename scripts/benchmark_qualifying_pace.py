"""Offline Q pace comparison on verified detailed archives; no suite mutation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.benchmark_grid_influence import load_archive
from src.circuit_calibration import sha256
from src.feature_ablation_benchmark import benchmark_feature_ablations


def run(workspace, output, *, years, fit_through=2024, histories=(2, 5),
        n_sims=1000, seeds=(42, 123, 777), inspected_reports=()):
    if not histories or any(n < 1 for n in histories):
        raise ValueError('Positive baseline history lengths required.')
    races, _, sources, failures, q_audit = load_archive(workspace, years)
    development = [list(r.key) for r in races if r.year <= fit_through]
    later = [list(r.key) for r in races if r.year > fit_through]
    if not development or not later:
        raise ValueError('Need development and later diagnostic races.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'development_races': development, 'holdout_races': later,
        'attempted_races': [list(r.key) for r in races],
        'evaluated_races': [], 'activated': False,
        'later_interpretation': 'previously inspected diagnostic; never fresh validation',
        'primary_baseline_history': histories[0], 'sensitivity_histories': list(histories[1:]),
        'variants': ['legacy', 'qualifying_partial_pooling_v1'], 'sessions': ['Q'],
        'n_sims': n_sims, 'seeds': list(seeds), 'input_sources': sources,
        'qualifying_audit': q_audit, 'load_failures': failures,
        'source_sha256': {str(Path(__file__).resolve()): sha256(Path(__file__))},
        'decision_rule': 'Primary development loss must improve; later paired loss must improve >=5%; '
            'no outcome Brier regression; Q finish MAE must beat qualifying order. '
            'Diagnostic promise permits review for a separate cohort only; live promotion still needs fresh races.'}
    prior = output/'protocol.json'
    prior.write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    decisions = []
    for history in dict.fromkeys(histories):
        report = benchmark_feature_ablations(races, output/f'history_{history}', prior,
            seeds=seeds, n_sims=n_sims, sessions=('Q',), load_failures=failures,
            inspected_reports=[prior, *inspected_reports],
            variants=('legacy', 'qualifying_partial_pooling_v1'), n_baseline_races=history)
        import pandas as pd
        folder = output/f'history_{history}'
        metrics = pd.read_csv(folder/'race_metrics.csv')
        baselines = pd.read_csv(folder/'simple_baselines.csv')
        diagnostic = metrics[metrics['split'].eq('previously_seen_diagnostic')]
        candidate = diagnostic[diagnostic.variant.eq('qualifying_partial_pooling_v1')]
        control = diagnostic[diagnostic.variant.eq('legacy')]
        grid = baselines[baselines['split'].eq('previously_seen_diagnostic') & baselines.variant.eq('grid_order')]
        reasons = []
        if not report['selected_on_development']['qualifying_partial_pooling_v1']:
            reasons.append('not_selected_on_development')
        if len(candidate) < 6 or len(control) != len(candidate) or len(grid) != len(candidate):
            reasons.append('insufficient_matched_diagnostic_coverage')
        if candidate.empty or candidate.loss.mean() > .95 * control.loss.mean():
            reasons.append('diagnostic_loss_improvement_below_5_percent')
        for metric in ('win_brier', 'podium_brier', 'top10_brier', 'dnf_brier'):
            if candidate.empty or candidate[metric].isna().any() or candidate[metric].mean() > control[metric].mean():
                reasons.append(metric+'_missing_or_regressed')
        if grid.empty or candidate.empty or candidate.finish_mae.mean() >= grid.finish_mae.mean():
            reasons.append('does_not_beat_qualifying_order')
        decisions.append({'baseline_history': history, 'matched_later_races': len(candidate),
            'candidate_finish_mae': None if candidate.empty else candidate.finish_mae.mean(),
            'control_finish_mae': None if control.empty else control.finish_mae.mean(),
            'qualifying_order_finish_mae': None if grid.empty else grid.finish_mae.mean(),
            'promising_for_new_shadow_review': not reasons, 'reasons': reasons,
            'promotion_approved': False, 'fresh_validation_races': 0,
            'report_sha256': sha256(folder/'report.json')})
    result = {'activated': False, 'cohort_changed': False, 'decisions': decisions,
        'protocol_sha256': sha256(prior),
        'new_shadow_cohort_created': False,
        'interpretation': 'Historical promise is a screening result, not fresh validation or activation.'}
    (output/'decision.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2021, 2027)))
    parser.add_argument('--fit-through', type=int, default=2024)
    parser.add_argument('--histories', type=int, nargs='+', default=[2, 5])
    parser.add_argument('--n-sims', type=int, default=1000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--inspected-reports', type=Path, nargs='*', default=[])
    args = parser.parse_args()
    print(json.dumps(run(args.workspace, args.output_dir, years=args.years,
        fit_through=args.fit_through, histories=tuple(args.histories), n_sims=args.n_sims,
        seeds=tuple(args.seeds), inspected_reports=args.inspected_reports), indent=2))


if __name__ == '__main__':
    main()
