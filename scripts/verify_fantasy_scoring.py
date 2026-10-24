"""Check the Fantasy scoring table against the archived points of each season."""
import argparse
import json
from pathlib import Path

from src.fantasy import check_scoring_against_archive
from src.fantasy_market import FIRST_SEASON, latest_tools_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--years', nargs='+', type=int)
    parser.add_argument('--show', type=int, default=10, help='Mismatches to print per season.')
    args = parser.parse_args()
    failed = False
    for year in args.years or range(FIRST_SEASON, 2100):
        payload = latest_tools_payload(args.workspace.resolve(), year)
        if payload is None:
            if args.years:
                print(f'{year}: no archived capture')
                failed = True
            continue
        report = check_scoring_against_archive(payload, year)
        wrong = report['mismatches']
        print(f"{year}: {report['drivers']} driver weekends, {report['constructors']} constructor weekends, "
              f"matched {json.dumps(report['matched'])}, {len(wrong)} mismatches"
              + (f", {report['pit_stops_without_time']} pit awards taken as given (no stop time in the capture)"
                 if report['pit_stops_without_time'] else ''))
        for row in wrong[:args.show]:
            print('   ', row)
        failed = failed or bool(wrong)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
