"""Tune qualifying grid influence without treating inspected races as fresh validation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.accuracy_benchmark import load_cached_races
from src.grid_weight_benchmark import benchmark_grid_weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-report', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, default=Path('data/cache'))
    parser.add_argument('--years', type=int, nargs='+', default=[2025, 2026])
    parser.add_argument('--weights', type=float, nargs='+', default=[1.65, 3.3, 6.6, 13.2])
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.n_sims < 100:
        parser.error('Use at least 100 simulations.')
    output = args.output_dir or Path('outputs/grid_weight_benchmarks') / datetime.now(
        timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    races, failures = load_cached_races(args.cache_dir.resolve(), args.years)
    report = benchmark_grid_weights(races, output, args.prior_report, weights=args.weights,
                                    seeds=args.seeds, n_sims=args.n_sims, load_failures=failures)
    print(json.dumps({'output_dir': str(output.resolve()), 'report': report}, indent=2))


if __name__ == '__main__':
    main()
