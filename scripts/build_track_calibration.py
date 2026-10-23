"""Build the calibrated_v1 track-factor table from a circuit-calibration report.

Reads the report written by scripts.calibrate_circuits (its observations and
current layouts), plus each observed race's archived classification for
grid-to-finish statistics. Writes a new CSV; never edits track_profiles.csv.

  python -m scripts.build_track_calibration --report outputs\\circuit_calibration\\<run>\\report.json
      --output data\\track_calibration\\track_calibration_v1.csv

The per-race grid statistics are read from each observation's archived
session manifest (hash-checked). --grid-stats accepts a saved CSV of them
instead, for reproducing a table without the archive.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.track_calibration import build_calibration, file_sha256, grid_order_stats, read_report


def archived_grid_stats(observations):
    rows = []
    for o in observations:
        manifest_path = Path(o['manifest_path'])
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        name, info = next(((n, i) for n, i in manifest['files'].items() if i.get('table') == 'results'),
                          (None, None))
        if name is None:
            continue
        file = (manifest_path.parent / name.replace('\\', '/')).resolve()
        if file_sha256(file) != info['sha256']:
            raise ValueError(f'Changed results file: {file}')
        stats = grid_order_stats(pd.read_csv(file))
        if stats:
            rows.append({'year': o['year'], 'round': o['round'], **stats})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--profiles', default='data/track_profiles.csv')
    parser.add_argument('--grid-stats', help='Saved per-race grid statistics CSV instead of the archive.')
    parser.add_argument('--save-grid-stats', help='Also write the per-race grid statistics used.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f'{output} exists; choose a new path.')
    report, report_sha = read_report(args.report)
    grid = (pd.read_csv(args.grid_stats) if args.grid_stats
            else archived_grid_stats(report['observations']))
    if args.save_grid_stats:
        grid.to_csv(args.save_grid_stats, index=False)
    table = build_calibration(report, grid, pd.read_csv(args.profiles), report_sha)
    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output, index=False)
    print(table[['CircuitId', 'SafetyCarChance', 'ActiveSafetyCarChance', 'OvertakingDifficulty',
                 'ActiveOvertakingDifficulty', 'overtaking_source']].to_string(index=False))
    print(f"\nfit: {table.attrs['fit']}\nsaved: {output}")


if __name__ == '__main__':
    main()
