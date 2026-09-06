"""Build the stable CSV contract consumed by the Simulink lap model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_RACE_LAPS = 57
DEFAULT_BASE_LAP_TIME_SECONDS = 90.0
DEFAULT_INITIAL_FUEL_PENALTY_SECONDS = 3.0
DEFAULT_FUEL_GAIN_PER_LAP_SECONDS = 0.05
DEFAULT_PIT_LOSS_SECONDS = 22.0
MAX_TYRE_DEGRADATION_SECONDS_PER_LAP = 0.25


def build_simulink_inputs(
    features: pd.DataFrame,
    strategies: pd.DataFrame | None = None,
    *,
    initial_fuel_penalty_seconds: float = DEFAULT_INITIAL_FUEL_PENALTY_SECONDS,
    fuel_gain_per_lap_seconds: float = DEFAULT_FUEL_GAIN_PER_LAP_SECONDS,
    pit_loss_seconds: float = DEFAULT_PIT_LOSS_SECONDS,
    max_tyre_degradation_seconds_per_lap: float = MAX_TYRE_DEGRADATION_SECONDS_PER_LAP,
) -> pd.DataFrame:
    """Translate model features into one Simulink simulation case per driver.

    The exporter intentionally keeps this boundary tabular. MATLAB/Simulink does
    not collect FastF1 data or reproduce Python feature engineering; it consumes
    model-ready values and provides a lap-level dynamics view of those values.
    """

    if features.empty:
        raise ValueError("No driver model features supplied for Simulink export.")

    required = {"Driver", "Team"}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"Simulink features missing columns: {sorted(missing)}")

    if initial_fuel_penalty_seconds < 0:
        raise ValueError("initial_fuel_penalty_seconds must be non-negative.")
    if fuel_gain_per_lap_seconds < 0:
        raise ValueError("fuel_gain_per_lap_seconds must be non-negative.")
    if pit_loss_seconds < 0:
        raise ValueError("pit_loss_seconds must be non-negative.")
    if max_tyre_degradation_seconds_per_lap <= 0:
        raise ValueError("max_tyre_degradation_seconds_per_lap must be positive.")

    frame = features.copy()
    frame["Driver"] = frame["Driver"].astype(str)
    frame["Team"] = frame["Team"].astype(str)

    race_laps = _numeric_column(frame, "estimated_race_laps")
    race_laps = race_laps.fillna(_finite_median(race_laps, DEFAULT_RACE_LAPS))
    race_laps = race_laps.round().clip(1, 100).astype(int)

    projected_lap_time = _projected_lap_time(frame, race_laps)
    reference_lap_time = _finite_quantile(
        projected_lap_time,
        0.20,
        DEFAULT_BASE_LAP_TIME_SECONDS,
    )

    raw_degradation = _first_numeric_column(
        frame,
        ["tyre_deg_score", "deg_per_lap"],
        default=0.0,
    )
    degradation = raw_degradation.clip(
        lower=0.0,
        upper=max_tyre_degradation_seconds_per_lap,
    )

    strategy_lookup = _strategy_lookup(strategies)
    expected_stops = frame["Driver"].map(strategy_lookup).fillna(1)
    expected_stops = pd.to_numeric(expected_stops, errors="coerce").fillna(1)
    expected_stops = expected_stops.round().clip(0, 3).astype(int)

    output = pd.DataFrame(
        {
            "Driver": frame["Driver"],
            "Team": frame["Team"],
            "race_laps": race_laps,
            "base_lap_time_seconds": reference_lap_time,
            "pace_offset_seconds": projected_lap_time - reference_lap_time,
            "tyre_degradation_seconds_per_lap": degradation,
            "raw_tyre_degradation_seconds_per_lap": raw_degradation,
            "degradation_was_capped": raw_degradation.gt(
                max_tyre_degradation_seconds_per_lap
            ),
            "initial_tyre_age_laps": 0,
            "initial_fuel_penalty_seconds": float(initial_fuel_penalty_seconds),
            "fuel_gain_per_lap_seconds": float(fuel_gain_per_lap_seconds),
            "expected_stops": expected_stops,
            "pit_laps": [
                _evenly_spaced_pit_laps(int(laps), int(stops))
                for laps, stops in zip(race_laps, expected_stops, strict=True)
            ],
            "pit_loss_seconds": float(pit_loss_seconds),
        }
    )

    return output.sort_values(["pace_offset_seconds", "Driver"]).reset_index(drop=True)


def export_simulink_inputs(
    features_path: str | Path,
    output_path: str | Path,
    strategies_path: str | Path | None = None,
    **kwargs: Any,
) -> Path:
    """Read Python outputs and write the Simulink input contract."""

    features_file = Path(features_path)
    if not features_file.is_file():
        raise FileNotFoundError(f"Feature CSV not found: {features_file}")

    strategies: pd.DataFrame | None = None
    if strategies_path:
        strategy_file = Path(strategies_path)
        if strategy_file.is_file():
            strategies = pd.read_csv(strategy_file)

    output = build_simulink_inputs(
        pd.read_csv(features_file),
        strategies,
        **kwargs,
    )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)
    return destination


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _first_numeric_column(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    default: float,
) -> pd.Series:
    output = pd.Series(np.nan, index=frame.index, dtype="float64")
    for column in columns:
        output = output.fillna(_numeric_column(frame, column))
    return output.replace([np.inf, -np.inf], np.nan).fillna(default)


def _finite_median(values: pd.Series, default: float) -> float:
    finite = values.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return float(default)
    return float(finite.median())


def _finite_quantile(values: pd.Series, quantile: float, default: float) -> float:
    finite = values.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return float(default)
    return float(finite.quantile(quantile))


def _projected_lap_time(frame: pd.DataFrame, race_laps: pd.Series) -> pd.Series:
    projected = _numeric_column(frame, "projected_lap_time")

    race_pace = _numeric_column(frame, "race_pace")
    plausible_race_pace = race_pace.where(race_pace.between(45.0, 160.0))
    projected = projected.fillna(plausible_race_pace)

    winner_time = _numeric_column(frame, "base_winner_race_time_seconds")
    derived_lap = winner_time / race_laps.replace(0, np.nan)
    projected = projected.fillna(derived_lap)

    race_pace_score = _numeric_column(frame, "race_pace_score").fillna(0.0)
    projected = projected.fillna(DEFAULT_BASE_LAP_TIME_SECONDS + race_pace_score * 0.20)

    return projected.replace([np.inf, -np.inf], np.nan).fillna(
        DEFAULT_BASE_LAP_TIME_SECONDS
    )


def _strategy_lookup(strategies: pd.DataFrame | None) -> pd.Series:
    if strategies is None or strategies.empty or "Driver" not in strategies.columns:
        return pd.Series(dtype="float64")

    stops_column = next(
        (name for name in ["expected_stops", "ExpectedStops"] if name in strategies.columns),
        None,
    )
    if stops_column is None:
        return pd.Series(dtype="float64")

    lookup = strategies[["Driver", stops_column]].copy()
    lookup["Driver"] = lookup["Driver"].astype(str)
    lookup[stops_column] = pd.to_numeric(lookup[stops_column], errors="coerce")
    return lookup.drop_duplicates("Driver").set_index("Driver")[stops_column]


def _evenly_spaced_pit_laps(race_laps: int, expected_stops: int) -> str:
    if expected_stops <= 0:
        return ""

    laps = [
        int(round(stop_number * race_laps / (expected_stops + 1)))
        for stop_number in range(1, expected_stops + 1)
    ]
    laps = [min(max(lap, 2), race_laps - 1) for lap in laps]
    return ";".join(str(lap) for lap in sorted(set(laps)))
