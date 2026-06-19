"""Export Python model features into the Rust simulation input contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_VERSION = "1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        default="outputs/driver_model_features.csv",
        help="Python driver model feature CSV produced by main.py.",
    )
    parser.add_argument(
        "--fantasy-prices",
        default="data/fantasy_prices.csv",
        help="Optional fantasy price CSV to merge by driver.",
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument(
        "--output",
        default="outputs/rust/model_inputs.json",
        help="Rust model input JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    features = pd.read_csv(args.features)
    prices = _read_prices(Path(args.fantasy_prices))
    if not prices.empty:
        features = features.merge(prices, on="Driver", how="left", suffixes=("", "_price_file"))
        if "fantasy_price_price_file" in features.columns:
            features["fantasy_price"] = features.get("fantasy_price").fillna(
                features["fantasy_price_price_file"]
            )

    drivers = [_driver_payload(row, idx + 1) for idx, row in features.iterrows()]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": str(Path(args.features)),
        "run": {
            "year": args.year,
            "event": args.event,
            "session": args.session,
        },
        "drivers": drivers,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(drivers)} Rust model inputs to {output_path}")


def _read_prices(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Driver", "fantasy_price"])
    prices = pd.read_csv(path)
    if "Driver" not in prices.columns or "fantasy_price" not in prices.columns:
        return pd.DataFrame(columns=["Driver", "fantasy_price"])
    return prices[["Driver", "fantasy_price"]].copy()


def _driver_payload(row: pd.Series, fallback_grid: int) -> dict[str, Any]:
    driver = str(_first_present(row, ["Driver", "driver", "Abbreviation"], "UNKNOWN"))
    team = str(_first_present(row, ["Team", "team"], "Unknown"))
    grid = int(float(_first_present(row, ["grid_position", "GridPosition", "grid"], fallback_grid)))
    race_pace = _score_higher_is_better(_first_present(row, ["race_pace_score", "model_pace"], 0.5))
    quali_pace = _score_higher_is_better(_first_present(row, ["quali_pace_score"], race_pace))
    long_run = _score_higher_is_better(_first_present(row, ["long_run_pace_score"], race_pace))
    strategy = _score_higher_is_better(_first_present(row, ["strategy_score"], 0.5))
    dnf_probability = _probability(
        _first_present(
            row,
            ["historical_dnf_probability", "reliability_score", "dnf_prob"],
            0.045,
        )
    )

    return {
        "driver": driver,
        "team": team,
        "grid": max(1, grid),
        "pace_score": _clip01(quali_pace * 0.35 + race_pace * 0.45 + long_run * 0.20),
        "strategy_score": strategy,
        "dnf_probability": dnf_probability,
        "fantasy_price": _nullable_number(row.get("fantasy_price")),
    }


def _first_present(row: pd.Series, columns: list[str], default: Any) -> Any:
    for column in columns:
        if column in row and pd.notna(row[column]):
            return row[column]
    return default


def _score_higher_is_better(value: Any) -> float:
    numeric = _number(value, 0.5)
    if 0.0 <= numeric <= 1.0:
        return _clip01(1.0 - numeric)
    return _clip01(numeric)


def _probability(value: Any) -> float:
    return _clip01(_number(value, 0.045))


def _nullable_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _number(value: Any, default: float) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


if __name__ == "__main__":
    main()
