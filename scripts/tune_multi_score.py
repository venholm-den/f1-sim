"""Fit simulation settings jointly on rank correlation, Brier and calibration error."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.accuracy_benchmark import load_cached_races
from src.multi_score_tuning import tune_multi_score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=Path('data/cache'))
    parser.add_argument('--fit-years', type=int, nargs='+', default=[2022, 2023])
    parser.add_argument('--holdout-years', type=int, nargs='+', default=[2024])
    parser.add_argument('--sessions', nargs='+', default=['Q'], choices=['PRE', 'FP2', 'Q'])
    parser.add_argument('--tune-sims', type=int, default=500)
    parser.add_argument('--eval-sims', type=int, default=2000)
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 777])
    parser.add_argument('--maxiter', type=int, default=12)
    parser.add_argument('--popsize', type=int, default=6)
    parser.add_argument('--inspected-reports', type=Path, nargs='*', default=[])
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if min(args.tune_sims, args.eval_sims) < 100:
        parser.error('Use at least 100 simulations.')
    output = args.output_dir or Path('outputs/multi_score_tuning') / datetime.now(
        timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    years = sorted(set(args.fit_years) | set(args.holdout_years))
    races, failures = load_cached_races(args.cache_dir.resolve(), years)
    report = tune_multi_score(races, output, fit_years=args.fit_years, holdout_years=args.holdout_years,
                              sessions=args.sessions, tune_sims=args.tune_sims, eval_sims=args.eval_sims,
                              seeds=args.seeds, maxiter=args.maxiter, popsize=args.popsize,
                              inspected_reports=args.inspected_reports, load_failures=failures)
    keys = ['tuned_parameters', 'live_parameters', 'identifiability', 'holdout_live', 'holdout_tuned',
            'promotion_gate_passed', 'promotion_reasons']
    print(json.dumps({'output_dir': str(output.resolve()), **{key: report[key] for key in keys}}, indent=2))


if __name__ == '__main__':
    main()
