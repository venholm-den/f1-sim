from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.model_config import SIMULATION_PARAMETERS


def _number(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return float(number)


def _series(df: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")

    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _sim_param(key: str, default: float) -> float:
    return _number(SIMULATION_PARAMETERS.get(key), default)


def _rank_lower_is_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")

    if values.notna().sum() == 0:
        return pd.Series([np.nan] * len(values), index=values.index)

    return values.rank(method="min", ascending=True).astype("Int64")


def _rank_higher_is_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")

    if values.notna().sum() == 0:
        return pd.Series([np.nan] * len(values), index=values.index)

    return values.rank(method="min", ascending=False).astype("Int64")


def _grid_reason(row: pd.Series) -> str:
    source = str(row.get("grid_source", "estimated_model_grid"))
    position = row.get("grid_position", row.get("avg_grid", ""))

    if source == "fia_official_grid":
        reason = f"Grid P{position} from FIA official grid documents."
    elif source == "actual_session_results":
        reason = f"Grid P{position} from qualifying/session classification."
    else:
        reason = f"Grid P{position} estimated from current and model pace."

    penalties = str(row.get("fia_penalty_notes", "")).strip()

    if penalties:
        reason = f"{reason} Penalty context: {penalties}"

    return reason


def _race_reason(row: pd.Series) -> str:
    parts: list[str] = []

    grid_rank = row.get("grid_rank")
    race_pace_rank = row.get("race_pace_rank")
    tyre_rank = row.get("tyre_deg_rank")
    reliability_rank = row.get("reliability_rank")

    if pd.notna(grid_rank):
        parts.append(f"grid rank {int(grid_rank)}")

    if pd.notna(race_pace_rank):
        parts.append(f"race pace rank {int(race_pace_rank)}")

    if pd.notna(tyre_rank):
        parts.append(f"tyre degradation rank {int(tyre_rank)}")

    if pd.notna(reliability_rank):
        parts.append(f"reliability risk rank {int(reliability_rank)}")

    finish = row.get("avg_finish", "")
    win = _number(row.get("win_chance"), 0.0) * 100
    podium = _number(row.get("podium_chance"), 0.0) * 100
    points = _number(row.get("points_chance"), 0.0) * 100
    dnf = _number(row.get("dnf_chance"), 0.0) * 100

    summary = (
        f"Average finish {finish:.2f}; "
        f"win {win:.1f}%, podium {podium:.1f}%, points {points:.1f}%, DNF {dnf:.1f}%."
    )

    if not parts:
        return summary

    return f"{summary} Main inputs: {', '.join(parts)}."


def build_prediction_reasoning(
    race_summary: pd.DataFrame,
    model_features: pd.DataFrame,
    overtaking_difficulty: float,
    weather_summary: dict | None = None,
) -> pd.DataFrame:
    """
    Builds a driver-level audit table for explaining grid and race predictions.

    Lower score/rank is better for pace, degradation, reliability, and time-loss
    fields. Probability columns remain in 0-1 form for easy spreadsheet use.
    """

    if race_summary.empty:
        return pd.DataFrame()

    output = race_summary.copy()
    features = model_features.copy()

    if not features.empty and "Driver" in features.columns:
        existing = set(output.columns)
        feature_columns = [
            "Driver",
            *[
                col
                for col in [
                    "actual_grid_position",
                    "estimated_grid_position",
                    "fia_grid_position",
                    "fia_penalty_notes",
                    "quali_weight_used",
                    "race_weight_used",
                    "strategy_weight_used",
                ]
                if col in features.columns and col not in existing
            ],
        ]

        if len(feature_columns) > 1:
            output = output.merge(
                features[feature_columns].drop_duplicates(subset=["Driver"]),
                on="Driver",
                how="left",
            )

    race_laps = _series(output, "estimated_race_laps", 57.0)
    race_pace = _series(output, "race_pace_score", 0.0)
    long_run_pace = _series(output, "long_run_pace_score", 0.0)
    tyre_deg = _series(output, "tyre_deg_score", 0.0)
    strategy = _series(output, "strategy_score", 0.35)
    grid = _series(output, "grid_position", np.nan).fillna(_series(output, "avg_grid", 10.5))
    grid_confidence = _series(output, "grid_confidence", 0.38).clip(0.10, 1.00)

    degradation_factor = 1.0
    strategy_factor = 1.0

    if weather_summary:
        degradation_factor = _number(weather_summary.get("degradation_factor"), 1.0)
        strategy_factor = _number(weather_summary.get("strategy_factor"), 1.0)

    output["overtaking_difficulty"] = float(overtaking_difficulty)
    output["race_pace_loss_seconds"] = (
        race_pace
        * race_laps
        * _sim_param("race_pace_seconds_multiplier", 0.20)
    )
    output["long_run_loss_seconds"] = (
        np.maximum(long_run_pace - race_pace, 0)
        * race_laps
        * _sim_param("long_run_penalty_multiplier", 0.25)
    )
    output["tyre_deg_loss_seconds"] = (
        np.maximum(tyre_deg, 0)
        * race_laps
        * _sim_param("tyre_deg_multiplier", 7.00)
        * degradation_factor
    )
    output["grid_loss_seconds"] = (
        (grid - 1)
        * float(overtaking_difficulty)
        * grid_confidence
        * _sim_param("grid_loss_multiplier", 1.65)
    )
    output["strategy_loss_seconds"] = (
        strategy
        * _sim_param("strategy_loss_multiplier", 2.50)
        * strategy_factor
    )
    output["deterministic_loss_seconds"] = (
        output["race_pace_loss_seconds"]
        + output["long_run_loss_seconds"]
        + output["tyre_deg_loss_seconds"]
        + output["grid_loss_seconds"]
        + output["strategy_loss_seconds"]
    )

    output["predicted_finish_rank"] = _rank_lower_is_better(output["avg_finish"])
    output["grid_rank"] = _rank_lower_is_better(grid)
    output["quali_pace_rank"] = _rank_lower_is_better(_series(output, "quali_pace_score"))
    output["race_pace_rank"] = _rank_lower_is_better(race_pace)
    output["long_run_rank"] = _rank_lower_is_better(long_run_pace)
    output["tyre_deg_rank"] = _rank_lower_is_better(tyre_deg)
    output["strategy_rank"] = _rank_lower_is_better(strategy)
    output["reliability_rank"] = _rank_lower_is_better(_series(output, "reliability_score"))
    output["deterministic_loss_rank"] = _rank_lower_is_better(output["deterministic_loss_seconds"])
    output["win_chance_rank"] = _rank_higher_is_better(_series(output, "win_chance"))
    output["podium_chance_rank"] = _rank_higher_is_better(_series(output, "podium_chance"))
    output["points_chance_rank"] = _rank_higher_is_better(_series(output, "points_chance"))

    output["grid_prediction_reason"] = output.apply(_grid_reason, axis=1)
    output["race_sim_reason"] = output.apply(_race_reason, axis=1)

    preferred = [
        "predicted_finish_rank",
        "Driver",
        "Team",
        "avg_finish",
        "avg_points",
        "win_chance",
        "podium_chance",
        "top5_chance",
        "points_chance",
        "dnf_chance",
        "grid_position",
        "avg_grid",
        "grid_source",
        "grid_confidence",
        "actual_grid_position",
        "fia_grid_position",
        "estimated_grid_position",
        "grid_prediction_reason",
        "race_sim_reason",
        "overtaking_difficulty",
        "deterministic_loss_seconds",
        "deterministic_loss_rank",
        "race_pace_loss_seconds",
        "long_run_loss_seconds",
        "tyre_deg_loss_seconds",
        "grid_loss_seconds",
        "strategy_loss_seconds",
        "quali_pace_score",
        "race_pace_score",
        "long_run_pace_score",
        "tyre_deg_score",
        "strategy_score",
        "reliability_score",
        "performance_uncertainty",
        "quali_pace_rank",
        "race_pace_rank",
        "long_run_rank",
        "tyre_deg_rank",
        "strategy_rank",
        "reliability_rank",
        "win_chance_rank",
        "podium_chance_rank",
        "points_chance_rank",
        "current_signal_quality",
        "effective_current_weight",
        "quali_weight_used",
        "race_weight_used",
        "strategy_weight_used",
        "model_uncertainty",
        "historical_model_available",
        "historical_predicted_finish",
        "historical_dnf_probability",
        "historical_calibration_note",
        "fia_penalty_notes",
    ]
    ordered = [column for column in preferred if column in output.columns]
    remaining = [column for column in output.columns if column not in ordered]

    return output[ordered + remaining].sort_values(
        ["predicted_finish_rank", "Driver"],
        na_position="last",
    ).reset_index(drop=True)


def save_prediction_reasoning_csv(
    race_summary: pd.DataFrame,
    model_features: pd.DataFrame,
    output_dir: str | Path,
    overtaking_difficulty: float,
    weather_summary: dict | None = None,
) -> str:
    output = build_prediction_reasoning(
        race_summary=race_summary,
        model_features=model_features,
        overtaking_difficulty=overtaking_difficulty,
        weather_summary=weather_summary,
    )
    path = Path(output_dir) / "prediction_reasoning.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)

    return str(path)
