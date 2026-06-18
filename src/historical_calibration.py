from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


DEFAULT_MODEL_DIR = "data/models"
FINISH_MODEL_FILE = "historical_finish_model.joblib"
DNF_MODEL_FILE = "historical_dnf_model.joblib"

HISTORICAL_FEATURE_COLUMNS = [
    "Year",
    "Round",
    "grid_position",
    "q_rank",
    "q_gap_to_best",
    "q_best_lap",
    "q_best_s1",
    "q_best_s2",
    "q_best_s3",
    "q_best_speed_trap",
    "grid_vs_quali_delta",
    "air_temp_avg",
    "track_temp_avg",
    "humidity_avg",
    "pressure_avg",
    "wind_speed_avg",
    "chaos_factor",
    "strategy_factor",
    "dnf_factor",
    "degradation_factor",
    "uncertainty_factor",
    "safety_car_count",
    "virtual_safety_car_count",
    "red_flag_count",
    "yellow_flag_count",
    "track_status_disruption_score",
    "race_control_disruption_score",
    "Event",
    "DriverCode",
    "Team",
    "rainfall_flag",
]


@dataclass(frozen=True)
class HistoricalCalibrationConfig:
    model_dir: str | Path = DEFAULT_MODEL_DIR
    finish_weight: float = 0.15
    dnf_weight: float = 0.30


def _series(
    frame: pd.DataFrame,
    column: str,
    default: Any = np.nan,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index)

    return frame[column]


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
    default: float = np.nan,
) -> pd.Series:
    return pd.to_numeric(_series(frame, column, default), errors="coerce")


def _first_available_numeric(
    frame: pd.DataFrame,
    columns: list[str],
    default: float = np.nan,
) -> pd.Series:
    output = pd.Series([np.nan] * len(frame), index=frame.index, dtype="float64")

    for column in columns:
        if column not in frame.columns:
            continue

        output = output.fillna(pd.to_numeric(frame[column], errors="coerce"))

    return output.fillna(default)


def _normalise_lower_is_better(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")

    if values.notna().sum() == 0:
        return pd.Series([0.0] * len(values), index=values.index)

    values = values.fillna(values.median())
    values = values - values.min()
    max_value = values.max()

    if pd.isna(max_value) or max_value <= 0:
        return pd.Series([0.0] * len(values), index=values.index)

    return values / max_value


def _race_control_from_metadata(metadata: dict[str, Any]) -> dict[str, float]:
    return {
        "safety_car_count": float(metadata.get("safety_car_count", 0.0) or 0.0),
        "virtual_safety_car_count": float(
            metadata.get("virtual_safety_car_count", 0.0) or 0.0
        ),
        "red_flag_count": float(metadata.get("red_flag_count", 0.0) or 0.0),
        "yellow_flag_count": float(metadata.get("yellow_flag_count", 0.0) or 0.0),
        "track_status_disruption_score": float(
            metadata.get("track_status_disruption_score", 0.0) or 0.0
        ),
        "race_control_disruption_score": float(
            metadata.get("race_control_disruption_score", 0.0) or 0.0
        ),
    }


def build_current_historical_feature_frame(
    model_features: pd.DataFrame,
    metadata: dict[str, Any] | None = None,
    weather_summary: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Maps the current weekend feature frame into the schema used by the
    historical finish and DNF models.
    """

    metadata = metadata or {}
    weather_summary = weather_summary or {}

    if model_features.empty:
        return pd.DataFrame(columns=HISTORICAL_FEATURE_COLUMNS)

    output = pd.DataFrame(index=model_features.index)
    output["Year"] = int(metadata.get("year", 0) or 0)
    output["Round"] = int(metadata.get("round", 0) or 0)
    output["Event"] = str(metadata.get("event", "unknown"))
    output["DriverCode"] = _series(model_features, "Driver", "")
    output["Team"] = _series(model_features, "Team", "")

    grid = _numeric_series(model_features, "grid_position", np.nan)
    if grid.isna().all():
        grid = pd.Series(
            np.arange(1, len(model_features) + 1),
            index=model_features.index,
            dtype="float64",
        )
    else:
        grid = grid.fillna(grid.median())

    output["grid_position"] = grid

    quali_signal = _first_available_numeric(
        model_features,
        [
            "quali_pace_score",
            "current_relative_pace_capped",
            "current_relative_pace",
            "model_pace",
            "relative_pace",
        ],
    )
    output["q_rank"] = quali_signal.rank(method="min", ascending=True).fillna(grid)
    output["q_gap_to_best"] = (
        quali_signal - quali_signal.min()
        if quali_signal.notna().any()
        else pd.Series([np.nan] * len(model_features), index=model_features.index)
    )

    output["q_best_lap"] = _first_available_numeric(
        model_features,
        ["best_lap", "projected_lap_time", "race_pace"],
    )
    output["q_best_s1"] = _first_available_numeric(
        model_features,
        ["best_s1", "sector1_seconds", "Sector1Seconds"],
    )
    output["q_best_s2"] = _first_available_numeric(
        model_features,
        ["best_s2", "sector2_seconds", "Sector2Seconds"],
    )
    output["q_best_s3"] = _first_available_numeric(
        model_features,
        ["best_s3", "sector3_seconds", "Sector3Seconds"],
    )
    output["q_best_speed_trap"] = _first_available_numeric(
        model_features,
        ["best_speed_trap", "speed_trap", "SpeedST"],
    )
    output["grid_vs_quali_delta"] = output["grid_position"] - output["q_rank"]

    for column, default in [
        ("air_temp_avg", np.nan),
        ("track_temp_avg", np.nan),
        ("humidity_avg", np.nan),
        ("pressure_avg", np.nan),
        ("wind_speed_avg", np.nan),
        ("chaos_factor", 1.0),
        ("strategy_factor", 1.0),
        ("dnf_factor", 1.0),
        ("degradation_factor", 1.0),
        ("uncertainty_factor", 1.0),
    ]:
        output[column] = weather_summary.get(column, default)

    output["rainfall_flag"] = bool(weather_summary.get("rainfall_flag", False))

    race_control = _race_control_from_metadata(metadata)
    for column, value in race_control.items():
        output[column] = value

    return output[HISTORICAL_FEATURE_COLUMNS]


def _load_models(model_dir: str | Path) -> tuple[Any, Any]:
    root = Path(model_dir)
    finish_path = root / FINISH_MODEL_FILE
    dnf_path = root / DNF_MODEL_FILE

    if not finish_path.exists() or not dnf_path.exists():
        missing = [
            str(path)
            for path in [finish_path, dnf_path]
            if not path.exists()
        ]
        raise FileNotFoundError(f"Historical model artifacts missing: {', '.join(missing)}")

    return joblib.load(finish_path), joblib.load(dnf_path)


def apply_historical_calibration(
    model_features: pd.DataFrame,
    metadata: dict[str, Any] | None = None,
    weather_summary: dict[str, Any] | None = None,
    config: HistoricalCalibrationConfig | None = None,
) -> pd.DataFrame:
    """
    Blends trained historical-model signals into the live simulation features.

    The historical finish prediction lightly nudges race pace, and the
    historical DNF probability blends with the existing reliability estimate.
    Lower race pace remains better.
    """

    if model_features.empty:
        return model_features.copy()

    config = config or HistoricalCalibrationConfig()
    output = model_features.copy()
    output["historical_model_available"] = False
    output["historical_calibration_note"] = "not_run"

    try:
        finish_model, dnf_model = _load_models(config.model_dir)
        prediction_features = build_current_historical_feature_frame(
            output,
            metadata=metadata,
            weather_summary=weather_summary,
        )
        finish_prediction = np.asarray(finish_model.predict(prediction_features), dtype=float)
        dnf_probability = np.asarray(dnf_model.predict_proba(prediction_features)[:, 1], dtype=float)
    except Exception as exc:
        output["historical_calibration_note"] = str(exc)
        return output

    output["historical_model_available"] = True
    output["historical_calibration_note"] = "applied"
    output["historical_predicted_finish"] = finish_prediction
    output["historical_dnf_probability"] = np.clip(dnf_probability, 0.0, 1.0)

    finish_weight = float(np.clip(config.finish_weight, 0.0, 0.60))
    dnf_weight = float(np.clip(config.dnf_weight, 0.0, 0.75))
    output["historical_finish_weight"] = finish_weight
    output["historical_dnf_weight"] = dnf_weight

    current_race_pace = _first_available_numeric(
        output,
        ["race_pace_score", "model_pace", "relative_pace"],
        default=0.0,
    )
    historical_finish_score = _normalise_lower_is_better(
        pd.Series(finish_prediction, index=output.index)
    )
    current_race_score = _normalise_lower_is_better(current_race_pace)

    output["historical_finish_score"] = historical_finish_score
    output["race_pace_score"] = (
        (1.0 - finish_weight) * current_race_score
        + finish_weight * historical_finish_score
    )

    if "long_run_pace_score" in output.columns:
        long_run = _normalise_lower_is_better(_numeric_series(output, "long_run_pace_score", 0.0))
        output["long_run_pace_score"] = (
            (1.0 - finish_weight) * long_run
            + finish_weight * historical_finish_score
        )

    current_reliability = _first_available_numeric(
        output,
        ["reliability_score", "dnf_prob"],
        default=0.045,
    ).clip(0.005, 0.30)
    output["reliability_score"] = (
        (1.0 - dnf_weight) * current_reliability
        + dnf_weight * output["historical_dnf_probability"]
    ).clip(0.005, 0.30)

    return output
