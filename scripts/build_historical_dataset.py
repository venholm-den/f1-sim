from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.historical_data import DEFAULT_SESSIONS, HistoricalBuildConfig, build_historical_dataset


def parse_args() -> argparse.Namespace:
    current_year = datetime.now(UTC).year
    parser = argparse.ArgumentParser(
        description="Build a normalized multi-season historical dataset from FastF1 and OpenF1."
    )
    parser.add_argument("--start-year", type=int, default=current_year - 4)
    parser.add_argument("--end-year", type=int, default=current_year)
    parser.add_argument("--output-dir", default="data/historical_model")
    parser.add_argument("--sessions", nargs="+", default=DEFAULT_SESSIONS)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--no-openf1", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Pause between session loads to reduce API pressure.",
    )
    parser.add_argument(
        "--continue-on-rate-limit",
        action="store_true",
        help="Keep trying remaining sessions after FastF1 reports its hourly API limit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = HistoricalBuildConfig(
        start_year=args.start_year,
        end_year=args.end_year,
        output_dir=args.output_dir,
        sessions=tuple(args.sessions),
        include_openf1=not args.no_openf1,
        max_events=args.max_events,
        skip_existing=not args.no_skip_existing,
        sleep_seconds=args.sleep_seconds,
        stop_on_rate_limit=not args.continue_on_rate_limit,
    )
    outputs = build_historical_dataset(config)

    print("Historical dataset build complete.")
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
