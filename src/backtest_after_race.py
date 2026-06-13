from __future__ import annotations

from src.backtest import (
    backtest_prediction_file,
    find_latest_prediction_snapshot,
)


# Leave as None to use the latest saved prediction snapshot.
PREDICTION_CSV_PATH: str | None = None

# Usually leave these as None.
# The script will infer year/round from the snapshot metadata.
YEAR: int | None = None
EVENT_IDENTIFIER: int | str | None = None


def main() -> None:
    prediction_path = PREDICTION_CSV_PATH or find_latest_prediction_snapshot()

    print(f"Backtesting prediction snapshot:")
    print(f"- {prediction_path}")

    outputs = backtest_prediction_file(
        prediction_csv_path=prediction_path,
        year=YEAR,
        event_identifier=EVENT_IDENTIFIER,
    )

    print()
    print("Saved backtest files:")

    for name, path in outputs.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()