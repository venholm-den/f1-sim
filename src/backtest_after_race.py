from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest import backtest_prediction_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest the latest saved F1 prediction snapshot after race results are available."
    )

    parser.add_argument(
        "--snapshot",
        default="outputs/history/latest_prediction_snapshot.csv",
        help="Path to the prediction snapshot CSV.",
    )

    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Override season year. If omitted, year is read from the snapshot.",
    )

    parser.add_argument(
        "--event",
        default=None,
        help='Override event name, for example "Barcelona Grand Prix". If omitted, event is read from the snapshot.',
    )

    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)

    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"Prediction snapshot not found: {snapshot_path}\n"
            "Run `python main.py` before the race to create a snapshot."
        )

    paths = backtest_prediction_snapshot(
        snapshot_path=str(snapshot_path),
        year=args.year,
        event=args.event,
    )

    print()
    print("Backtest complete:")
    for label, path in paths.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()