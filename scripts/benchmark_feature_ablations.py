"""Evaluate DNF decoupling and circuit-normalised history independently, offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.accuracy_benchmark import load_cached_races
from src.feature_ablation_benchmark import benchmark_feature_ablations
from src.accuracy_candidates import FEATURE_VARIANTS, SUPPORTED_VARIANTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-report', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, default=Path('data/cache'))
    parser.add_argument('--years', type=int, nargs='+', default=[2025, 2026])
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--n-baseline-races', type=int, default=2)
    parser.add_argument('--retirement-history-races', type=int, default=30)
    parser.add_argument('--sessions', choices=['PRE', 'FP2', 'Q'], nargs='+', default=['PRE', 'FP2', 'Q'])
    parser.add_argument('--inspected-reports', type=Path, nargs='*', default=[])
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--qualifying-results', type=Path,
                        help='Explicit saved Q CSV or historical_library directory; no cache mutation.')
    parser.add_argument('--variants', nargs='+', choices=SUPPORTED_VARIANTS, default=FEATURE_VARIANTS)
    args = parser.parse_args()
    if args.n_sims < 100:
        parser.error('Use at least 100 simulations.')
    if args.n_baseline_races < 1 or not 1 <= args.retirement_history_races <= 100:
        parser.error('Use positive baseline history and 1 to 100 retirement history races.')
    output = args.output_dir or Path('outputs/feature_ablations') / datetime.now(
        timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    races, failures = load_cached_races(args.cache_dir.resolve(), args.years)
    if args.qualifying_results:
        from src.qualifying_archive import attach_archive
        races = attach_archive(races, args.qualifying_results)
    report = benchmark_feature_ablations(races, output, args.prior_report, seeds=args.seeds,
        n_sims=args.n_sims, sessions=args.sessions, load_failures=failures,
        inspected_reports=args.inspected_reports, variants=args.variants,
        n_baseline_races=args.n_baseline_races, retirement_history_races=args.retirement_history_races)
    print(json.dumps({'output_dir': str(output.resolve()), 'selected': report['selected_on_development'],
                      'promotion_gates': report['promotion_gates'], 'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    main()
