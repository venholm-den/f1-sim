"""Freeze, verify and evaluate a season-long combined challenger (shadow only).

  freeze   --spec config/challenger.example.json   write the write-once frozen file
  verify   --frozen FILE                           list sources changed since freezing
  config   --frozen FILE --base config/default_run_config.json --output RUN.json
  evaluate --frozen FILE --metrics ROWS.csv [--baseline live]

See docs/promotion-lanes-and-challenger.md. Nothing here changes live settings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src import challenger

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    frozen = commands.add_parser('freeze')
    frozen.add_argument('--spec', required=True)
    frozen.add_argument('--output-dir', default='outputs/challengers')
    for name in ('verify', 'config', 'evaluate'):
        command = commands.add_parser(name)
        command.add_argument('--frozen', required=True)
    commands.choices['config'].add_argument('--base', default='config/default_run_config.json')
    commands.choices['config'].add_argument('--output', required=True)
    commands.choices['evaluate'].add_argument('--metrics', required=True)
    commands.choices['evaluate'].add_argument('--baseline', default='live')
    args = parser.parse_args()

    if args.command == 'freeze':
        spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
        print(f'frozen: {challenger.freeze(spec, ROOT, args.output_dir)}')
    elif args.command == 'verify':
        result = challenger.verify(args.frozen, ROOT)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['unchanged'] else 1)
    elif args.command == 'config':
        output = Path(args.output)
        if output.exists():
            raise SystemExit(f'{output} already exists; choose a new file.')
        base = json.loads(Path(args.base).read_text(encoding='utf-8'))
        output.write_text(json.dumps(challenger.run_config(args.frozen, base), indent=2), encoding='utf-8')
        print(f'saved: {output}')
    else:
        evidence = challenger.season_evidence(args.frozen, pd.read_csv(args.metrics), args.baseline)
        print(json.dumps(evidence, indent=2, default=float))


if __name__ == '__main__':
    main()
