from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.model_config import (
    DEFAULT_BASE_LAP_TIME,
    DEFAULT_PIT_AND_RACE_ALLOWANCE,
    DEFAULT_RACE_LAPS,
    MODEL_VERSION,
    RACE_LAPS_BY_EVENT_KEYWORD,
    SESSION_WEIGHTS,
)


def _to_numeric_series(
    df: pd.DataFrame,
    column: str,
    default: float = np.nan,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")

    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _normalise_lower_is_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")

    if values.notna().sum() == 0:
        return pd.Series([0.0] * len(values), index=values.index)

    values = values.fillna(values.median())
    values = values - values.min()

    return values.clip(lower=0.0)


def _estimate_race_laps(metadata: dict | None) -> int:
    if not metadata:
        return DEFAULT_RACE_LAPS

    event_name = str(metadata.get("event", "")).lower()

    for keyword, laps in RACE_LAPS_BY_EVENT_KEYWORD.items():
        if keyword in event_name:
            return laps

    return DEFAULT_RACE_LAPS


def _estimate_base_lap_time(features: pd.DataFrame) -> float:
    candidates: list[float] = []

    for col in ["race_pace", "projected_lap_time", "best_lap", "true_pace"]:
        if col not in features.columns:
            continue

        values = pd.to_numeric(features[col], errors="coerce").dropna()
        values = values[(values >= 45) & (values <= 160)]

        if not values.empty:
            candidates.append(float(values.quantile(0.20)))

    if candidates:
        return float(np.median(candidates))

    return DEFAULT_BASE_LAP_TIME


def _session_weight(
    session_type: str | None,
    key: str,
    default: float,
) -> float:
    session = str(session_type or "").upper()

    if session not in SESSION_WEIGHTS:
        return default

    return float(SESSION_WEIGHTS[session].get(key, default))


def add_performance_profile(
    model_features: pd.DataFrame,
    current_features: pd.DataFrame | None = None,
    baseline_features: pd.DataFrame | None = None,
    current_session_type: str | None = None,
    metadata: dict | None = None,
) -> pd.DataFrame:
    """
    Adds the central performance profile used by the simulation engine.

    Lower score is better for pace-style columns.

    This does not remove any existing columns, so old reports should keep working.
    """

    if model_features.empty:
        return model_features.copy()

    output = model_features.copy()

    race_laps = _estimate_race_laps(metadata)
    base_lap_time = _estimate_base_lap_time(output)

    model_pace = _normalise_lower_is_better(
        _to_numeric_series(output, "model_pace", 0.0)
    )

    relative_pace = _normalise_lower_is_better(
        _to_numeric_series(output, "relative_pace", 0.0)
    )

    current_pace = _normalise_lower_is_better(
        _to_numeric_series(output, "current_relative_pace_capped", np.nan)
    )

    if current_pace.isna().all():
        current_pace = _normalise_lower_is_better(
            _to_numeric_series(output, "current_relative_pace", np.nan)
        )

    baseline_pace = _normalise_lower_is_better(
        _to_numeric_series(output, "baseline_relative_pace", np.nan)
    )

    baseline_pace = baseline_pace.fillna(model_pace)

    current_signal_quality = _to_numeric_series(
        output,
        "current_signal_quality",
        0.50,
    ).clip(0.0, 1.0)

    quali_weight_base = _session_weight(
        current_session_type,
        "quali",
        0.25,
    )

    race_weight_base = _session_weight(
        current_session_type,
        "race",
        0.25,
    )

    strategy_weight_base = _session_weight(
        current_session_type,
        "strategy",
        0.15,
    )

    quali_weight = (
        quali_weight_base * current_signal_quality
    ).clip(0.0, 0.85)

    race_weight = (
        race_weight_base * current_signal_quality
    ).clip(0.0, 0.80)

    strategy_weight = (
        strategy_weight_base * current_signal_quality
    ).clip(0.0, 0.65)

    output["quali_pace_score"] = (
        quali_weight * current_pace.fillna(model_pace)
        + (1 - quali_weight) * model_pace
    )

    output["quali_pace_score"] = _normalise_lower_is_better(
        output["quali_pace_score"]
    )

    output["race_pace_score"] = (
        race_weight * relative_pace.fillna(model_pace)
        + (1 - race_weight) * baseline_pace.fillna(model_pace)
    )

    output["race_pace_score"] = _normalise_lower_is_better(
        output["race_pace_score"]
    )

    deg_per_lap = _to_numeric_series(output, "deg_per_lap", 0.0)
    lap_std = _to_numeric_series(output, "lap_std", 1.5)
    uncertainty = _to_numeric_series(output, "model_uncertainty", 1.2)

    output["tyre_deg_score"] = deg_per_lap.clip(-0.04, 0.18)

    output["long_run_pace_score"] = (
        output["race_pace_score"]
        + output["tyre_deg_score"].clip(lower=0.0) * 12.0
        + lap_std.clip(0.0, 8.0) * 0.04
    )

    output["long_run_pace_score"] = _normalise_lower_is_better(
        output["long_run_pace_score"]
    )

    dnf_prob = _to_numeric_series(output, "dnf_prob", 0.045)
    output["reliability_score"] = dnf_prob.clip(0.005, 0.30)

    grid_position = _to_numeric_series(output, "grid_position", np.nan)

    if grid_position.notna().any():
        grid_position = grid_position.fillna(grid_position.median())
        output["start_score"] = ((grid_position - 1) / 19.0).clip(0.0, 1.0)
    else:
        output["start_score"] = 0.50

    output["strategy_score"] = (
        strategy_weight * (
            output["tyre_deg_score"].clip(lower=0.0) * 4.0
            + uncertainty.clip(0.8, 3.0) * 0.10
        )
        + (1 - strategy_weight) * (
            output["tyre_deg_score"].clip(lower=0.0) * 2.0
            + 0.15
        )
    ).clip(0.0, 1.50)

    output["performance_uncertainty"] = (
        uncertainty
        + lap_std.clip(0.0, 8.0) * 0.06
        + (1 - current_signal_quality) * 0.30
    ).clip(0.70, 4.00)

    output["quali_weight_used"] = quali_weight
    output["race_weight_used"] = race_weight
    output["strategy_weight_used"] = strategy_weight

    output["estimated_race_laps"] = race_laps
    output["projected_lap_time"] = base_lap_time + output["race_pace_score"]

    output["base_winner_race_time_seconds"] = (
        base_lap_time * race_laps + DEFAULT_PIT_AND_RACE_ALLOWANCE
    )

    output["performance_model_version"] = MODEL_VERSION

    return output