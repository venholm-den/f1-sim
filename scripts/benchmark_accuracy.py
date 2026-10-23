"""Run the reproducible accuracy benchmark against cached FastF1 sessions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

from src.accuracy_benchmark import benchmark, load_cached_races


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path('data/cache'))
    parser.add_argument('--years', type=int, nargs='+', default=[2026])
    parser.add_argument('--n-sims', type=int, default=5000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--sessions', nargs='+', choices=['PRE', 'FP2', 'Q'], default=['PRE', 'FP2', 'Q'])
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.n_sims < 100:
        parser.error('Use at least 100 simulations.')
    output = args.output_dir or Path('outputs/accuracy_benchmarks') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    races, failures = load_cached_races(args.cache_dir.resolve(), args.years)
    report = benchmark(races, output, n_sims=args.n_sims, seed=args.seed,
                       sessions=tuple(args.sessions), load_failures=failures)
    print(json.dumps({'output_dir': str(output.resolve()), 'report': report,
                      'load_failures': failures}, indent=2))


if __name__ == '__main__':
    main()
