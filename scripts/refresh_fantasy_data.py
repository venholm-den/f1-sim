"""Collect public weekly Fantasy prices and actual points into the local archive."""
import argparse
import json
from pathlib import Path
from src.fantasy_market import collect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--years', nargs='+', type=int)
    parser.add_argument('--force', action='store_true', help='Refresh even when a saved capture is recent.')
    args = parser.parse_args()
    result = collect(args.workspace.resolve(), args.years, force=args.force)
    print(json.dumps(result, indent=2))
    return 1 if any(r['status'] == 'error' for r in result['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
