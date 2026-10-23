"""Build a versioned same-season baseline for the next race or a named cutoff."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.app_services.beta import next_race
from src.recent_baselines import build_recent_baselines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int)
    parser.add_argument('--target-round', type=int)
    parser.add_argument('--races', type=int, default=16)
    parser.add_argument('--cutoff-utc', help='Timezone-aware cutoff; cannot be in the future.')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if (args.year is None) != (args.target_round is None):
        parser.error('Supply --year and --target-round together, or neither for the next race.')
    root = Path(__file__).resolve().parents[1]
    if args.year is None:
        context = next_race(root)
        args.year, args.target_round = context['year'], context['round']
    destination = args.output_dir or root / 'data/recent_baselines' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if not destination.is_absolute():
        destination = root / destination
    report = build_recent_baselines(args.year, args.target_round, destination, count=args.races, cutoff=args.cutoff_utc)
    print(f"Completed {report['completed_races']} races, {report['lap_rows']:,} laps, {report['feature_rows']} feature rows.")
    print(destination / 'report.md')


if __name__ == '__main__':
    main()
