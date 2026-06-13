from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.model_config import FANTASY_SCORING


def _ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)


def _to_float_or_nan(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")

    if not np.isfinite(number):
        return float("nan")

    return float(number)


def _to_bool_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "bool":
        return series.fillna(False).astype(bool)

    text = series.astype(str).str.strip().str.lower()

    return text.isin({"true", "1", "yes", "y"})


def _series_or_default(
    df: pd.DataFrame,
    column: str,
    default: Any,
) -> pd.Series:
    if column in df.columns:
        return df[column]

    return pd.Series([default] * len(df), index=df.index)


def _scoring_value(key: str, default: float) -> float:
    value = FANTASY_SCORING.get(key, default)

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_points_mapping(mapping: dict[Any, Any]) -> dict[int, float]:
    output: dict[int, float] = {}

    for key, value in mapping.items():
        try:
            position = int(key)
            points = float(value)
        except (TypeError, ValueError):
            continue

        output[position] = points

    return output


def _finish_points_mapping() -> dict[int, float]:
    return _normalise_points_mapping(
        FANTASY_SCORING.get(
            "finish_points",
            {
                1: 25,
                2: 18,
                3: 15,
                4: 12,
                5: 10,
                6: 8,
                7: 6,
                8: 4,
                9: 2,
                10: 1,
            },
        )
    )


def _quali_points_mapping() -> dict[int, float]:
    return _normalise_points_mapping(
        FANTASY_SCORING.get(
            "quali_points",
            {
                1: 10,
                2: 9,
                3: 8,
                4: 7,
                5: 6,
                6: 5,
                7: 4,
                8: 3,
                9: 2,
                10: 1,
            },
        )
    )


def _points_from_position(
    position: Any,
    mapping: dict[int, float],
) -> float:
    number = _to_float_or_nan(position)

    if not np.isfinite(number):
        return 0.0

    return float(mapping.get(int(round(number)), 0.0))


def _load_prices(prices_path: str) -> pd.DataFrame:
    path = Path(prices_path)

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["Driver", "Team", "fantasy_price"])

    try:
        prices = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["Driver", "Team", "fantasy_price"])

    if "Driver" not in prices.columns:
        prices["Driver"] = ""

    if "Team" not in prices.columns:
        prices["Team"] = ""

    if "fantasy_price" not in prices.columns:
        prices["fantasy_price"] = np.nan

    prices["Driver"] = prices["Driver"].astype(str)
    prices["Team"] = prices["Team"].astype(str)
    prices["fantasy_price"] = pd.to_numeric(
        prices["fantasy_price"],
        errors="coerce",
    )

    return prices[["Driver", "Team", "fantasy_price"]].copy()


def ensure_price_template(
    model_features: pd.DataFrame,
    prices_path: str = "data/fantasy_prices.csv",
) -> str:
    """
    Ensures data/fantasy_prices.csv exists and contains every current driver.

    Fill in fantasy_price manually if you want xPPM/value calculations.
    """

    _ensure_data_dir()

    path = Path(prices_path)

    required_cols = ["Driver", "Team", "fantasy_price"]

    if model_features.empty:
        if not path.exists():
            pd.DataFrame(columns=required_cols).to_csv(path, index=False)

        return str(path)

    current = model_features[["Driver", "Team"]].copy()
    current["Driver"] = current["Driver"].astype(str)
    current["Team"] = current["Team"].astype(str)
    current["fantasy_price"] = np.nan

    if path.exists() and path.stat().st_size > 0:
        existing = _load_prices(prices_path)
    else:
        existing = pd.DataFrame(columns=required_cols)

    combined = current.merge(
        existing[["Driver", "fantasy_price"]],
        on="Driver",
        how="left",
        suffixes=("", "_existing"),
    )

    combined["fantasy_price"] = combined["fantasy_price_existing"]
    combined = combined.drop(columns=["fantasy_price_existing"])

    combined = combined[required_cols].drop_duplicates(subset=["Driver"])

    combined.to_csv(path, index=False)

    return str(path)


def add_simulated_fantasy_points(results: pd.DataFrame) -> pd.DataFrame:
    """
    Adds fantasy-point columns to every simulated driver result.

    Fantasy is scored per simulation, then averaged later.
    """

    if results.empty:
        return results.copy()

    df = results.copy()

    if "Driver" not in df.columns:
        raise ValueError("results must contain Driver")

    if "Team" not in df.columns:
        df["Team"] = "Unknown"

    df["Driver"] = df["Driver"].astype(str)
    df["Team"] = df["Team"].astype(str)

    finish_points_map = _finish_points_mapping()
    quali_points_map = _quali_points_mapping()

    position_gain_points_per_place = _scoring_value(
        "position_gain_points_per_place",
        1.0,
    )
    position_loss_points_per_place = _scoring_value(
        "position_loss_points_per_place",
        -0.5,
    )
    position_change_min = _scoring_value("position_change_min", -5.0)
    position_change_max = _scoring_value("position_change_max", 10.0)
    fastest_lap_bonus = _scoring_value("fastest_lap_bonus", 5.0)
    dotd_bonus = _scoring_value("dotd_bonus", 10.0)
    dnf_penalty = _scoring_value("dnf_penalty", -10.0)

    finish_position = pd.to_numeric(
        _series_or_default(df, "finish_position", np.nan),
        errors="coerce",
    )

    grid_position = pd.to_numeric(
        _series_or_default(df, "grid_position", np.nan),
        errors="coerce",
    )

    if "points" in df.columns:
        race_points = pd.to_numeric(df["points"], errors="coerce").fillna(0.0)
    elif "race_points" in df.columns:
        race_points = pd.to_numeric(df["race_points"], errors="coerce").fillna(0.0)
    else:
        race_points = finish_position.map(
            lambda value: _points_from_position(value, finish_points_map)
        ).fillna(0.0)

    if "positions_gained" in df.columns:
        positions_gained = pd.to_numeric(
            df["positions_gained"],
            errors="coerce",
        ).fillna(0.0)
    else:
        positions_gained = grid_position - finish_position

    fastest_lap = _to_bool_series(
        _series_or_default(df, "fastest_lap", False)
    )

    dotd = _to_bool_series(
        _series_or_default(df, "dotd", False)
    )

    dnf = _to_bool_series(
        _series_or_default(df, "dnf", False)
    )

    quali_points = grid_position.map(
        lambda value: _points_from_position(value, quali_points_map)
    ).fillna(0.0)

    position_change_points = np.where(
        positions_gained >= 0,
        positions_gained * position_gain_points_per_place,
        positions_gained.abs() * position_loss_points_per_place,
    )

    position_change_points = pd.Series(
        position_change_points,
        index=df.index,
        dtype="float64",
    ).clip(position_change_min, position_change_max)

    # Avoid double-punishing DNFs.
    # A DNF already gets a DNF penalty, so do not also apply a large
    # position-loss penalty caused by being classified last.
    position_change_points = position_change_points.where(~dnf, 0.0)

    fastest_lap_points = fastest_lap.astype(float) * fastest_lap_bonus
    dotd_points = dotd.astype(float) * dotd_bonus
    dnf_points = dnf.astype(float) * dnf_penalty

    df["finish_fantasy_points"] = race_points
    df["quali_fantasy_points"] = quali_points
    df["position_change_points"] = position_change_points
    df["fastest_lap_points"] = fastest_lap_points
    df["dotd_points"] = dotd_points
    df["dnf_penalty_points"] = dnf_points

    df["fantasy_points"] = (
        df["finish_fantasy_points"]
        + df["quali_fantasy_points"]
        + df["position_change_points"]
        + df["fastest_lap_points"]
        + df["dotd_points"]
        + df["dnf_penalty_points"]
    )

    df["avg_positions_gained_input"] = positions_gained

    return df


def calculate_fantasy_summary(
    results: pd.DataFrame,
    race_summary: pd.DataFrame,
    prices_path: str = "data/fantasy_prices.csv",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
    - race summary merged with fantasy metrics
    - raw per-simulation fantasy results
    """

    if results.empty:
        summary = race_summary.copy()

        for col in [
            "avg_fantasy_points",
            "fantasy_p25",
            "fantasy_p75",
            "fantasy_std",
            "fantasy_floor_p10",
            "fantasy_ceiling_p90",
            "avg_positions_gained",
            "fastest_lap_chance",
            "dotd_chance",
            "avg_quali_points",
            "avg_finish_fantasy_points",
            "avg_position_change_points",
            "avg_fastest_lap_points",
            "avg_dotd_points",
            "avg_dnf_penalty",
            "fantasy_price",
            "fantasy_xppm",
        ]:
            summary[col] = np.nan

        return summary, results.copy()

    fantasy_results = add_simulated_fantasy_points(results)

    grouped = fantasy_results.groupby(["Driver", "Team"], dropna=False)

    fantasy_summary = grouped.agg(
        avg_fantasy_points=("fantasy_points", "mean"),
        fantasy_p25=("fantasy_points", lambda s: float(s.quantile(0.25))),
        fantasy_p75=("fantasy_points", lambda s: float(s.quantile(0.75))),
        fantasy_std=("fantasy_points", "std"),
        fantasy_floor_p10=("fantasy_points", lambda s: float(s.quantile(0.10))),
        fantasy_ceiling_p90=("fantasy_points", lambda s: float(s.quantile(0.90))),
        avg_positions_gained=("avg_positions_gained_input", "mean"),
        fastest_lap_chance=("fastest_lap", lambda s: float(_to_bool_series(s).mean())),
        dotd_chance=("dotd", lambda s: float(_to_bool_series(s).mean())),
        avg_quali_points=("quali_fantasy_points", "mean"),
        avg_finish_fantasy_points=("finish_fantasy_points", "mean"),
        avg_position_change_points=("position_change_points", "mean"),
        avg_fastest_lap_points=("fastest_lap_points", "mean"),
        avg_dotd_points=("dotd_points", "mean"),
        avg_dnf_penalty=("dnf_penalty_points", "mean"),
    ).reset_index()

    fantasy_summary["fantasy_std"] = fantasy_summary["fantasy_std"].fillna(0.0)

    prices = _load_prices(prices_path)

    if not prices.empty:
        fantasy_summary = fantasy_summary.merge(
            prices[["Driver", "fantasy_price"]],
            on="Driver",
            how="left",
        )
    else:
        fantasy_summary["fantasy_price"] = np.nan

    fantasy_summary["fantasy_xppm"] = np.where(
        pd.to_numeric(fantasy_summary["fantasy_price"], errors="coerce") > 0,
        fantasy_summary["avg_fantasy_points"]
        / pd.to_numeric(fantasy_summary["fantasy_price"], errors="coerce"),
        np.nan,
    )

    summary = race_summary.copy()

    if "Driver" not in summary.columns:
        raise ValueError("race_summary must contain Driver")

    if "Team" not in summary.columns:
        summary["Team"] = ""

    summary["Driver"] = summary["Driver"].astype(str)
    summary["Team"] = summary["Team"].astype(str)

    fantasy_merge_cols = [
        "Driver",
        "avg_fantasy_points",
        "fantasy_p25",
        "fantasy_p75",
        "fantasy_std",
        "fantasy_floor_p10",
        "fantasy_ceiling_p90",
        "avg_positions_gained",
        "fastest_lap_chance",
        "dotd_chance",
        "avg_quali_points",
        "avg_finish_fantasy_points",
        "avg_position_change_points",
        "avg_fastest_lap_points",
        "avg_dotd_points",
        "avg_dnf_penalty",
        "fantasy_price",
        "fantasy_xppm",
    ]

    summary = summary.merge(
        fantasy_summary[fantasy_merge_cols],
        on="Driver",
        how="left",
    )

    summary = summary.sort_values(
        ["avg_fantasy_points", "avg_points"],
        ascending=[False, False],
    ).reset_index(drop=True)

    return summary, fantasy_results