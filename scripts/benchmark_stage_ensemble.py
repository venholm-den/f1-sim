"""Fit and diagnose an inactive stage-specific blend from saved benchmark data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.stage_ensemble_benchmark import benchmark


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-report',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--component-sims',type=int,default=20_000)
    args = parser.parse_args()
    if args.component_sims < 100:
        parser.error('Use at least 100 complete-field simulations.')
    output = args.output_dir or Path('outputs/stage_ensemble')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = benchmark(args.source_report,args.dataset,output,n_sims=args.component_sims)
    print(json.dumps({'output_dir':str(output.resolve()),'episodes':report['race_stage_episodes'],
                      'activated':report['activated'],'summary':report['summary']},indent=2))


if __name__ == '__main__':
    main()
