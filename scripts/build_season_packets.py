"""Build whole-season replay packets from the saved historical library.

Each season gets a folder that scripts.promotion_check score and
scripts.benchmark_safety_car accept as --packet, so candidates can be scored
on earlier seasons with a fit/held-out split. Nothing is downloaded.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.app_services.app_paths import user_workspace_dir
from src.season_packets import build_season_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=user_workspace_dir(),
                        help='Folder that holds data/historical_library (default: the app data folder).')
    parser.add_argument('--years', type=int, nargs='+', required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir or root / 'outputs/season_packets' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for year in args.years:
        report = build_season_packet(args.workspace, year, output / f'season-{year}')
        print(f"{year}: {report['races']} races ({report['safety_car_races']} with an SC, "
              f"{report['vsc_races']} with a VSC), {len(report['skipped'])} skipped")
        for row in report['skipped']:
            print(f"  skipped round {row['Round']} {row['Event']}: {row['reason']}")
    print(output)


if __name__ == '__main__':
    main()
