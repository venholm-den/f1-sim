"""Create new, inactive circuit estimates and chronological event-rate diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.circuit_calibration import build_report, render_report, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=list(range(2021, 2027)))
    parser.add_argument('--profiles', type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    profiles = args.profiles or root/'data/track_profiles.csv'
    output = args.output_dir.resolve()
    if output.exists():
        raise ValueError('Choose a new output directory; existing evidence is never overwritten')
    report = build_report(root, sorted(set(args.years)), profiles)
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    (output/'report.html').write_text(render_report(report), encoding='utf-8')
    pd.json_normalize(report['candidates']).to_csv(output/'candidate_profiles.csv', index=False)
    pd.DataFrame(report['benchmark_predictions']).to_csv(output/'benchmark_predictions.csv', index=False)
    pd.DataFrame(report['benchmark_scores']).to_csv(output/'benchmark_scores.csv', index=False)
    (output/'provenance.json').write_text(json.dumps({'active': False, 'source_sha256': {
        str(Path(__file__).resolve()): sha256(__file__),
        str(Path(__file__).resolve().parents[1]/'src/circuit_calibration.py'):
            sha256(Path(__file__).resolve().parents[1]/'src/circuit_calibration.py')},
        'artifacts': {p.name: sha256(p) for p in output.iterdir() if p.is_file()}}, indent=2), encoding='utf-8')
    print(json.dumps({'output_dir': str(output), 'active': False, 'coverage': report['coverage']}, indent=2))


if __name__ == '__main__':
    main()
