from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.historical_calibration import (
    DNF_MODEL_FILE,
    FINISH_MODEL_FILE,
    HistoricalCalibrationConfig,
    apply_historical_calibration,
    build_current_historical_feature_frame,
)


class _FinishModel:
    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.array([3.0, 1.0])


class _DnfModel:
    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return np.array([[0.90, 0.10], [0.60, 0.40]])


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["AAA", "BBB"],
            "Team": ["Team A", "Team B"],
            "grid_position": [1, 2],
            "race_pace_score": [0.0, 1.0],
            "long_run_pace_score": [0.0, 1.0],
            "reliability_score": [0.02, 0.04],
            "quali_pace_score": [0.1, 0.2],
            "best_lap": [80.0, 80.5],
        }
    )


def test_build_current_historical_feature_frame_maps_live_features() -> None:
    frame = build_current_historical_feature_frame(
        _features(),
        metadata={"year": 2026, "round": 4, "event": "Test Grand Prix"},
        weather_summary={"air_temp_avg": 22.5, "rainfall_flag": True},
    )

    assert frame["Year"].tolist() == [2026, 2026]
    assert frame["Round"].tolist() == [4, 4]
    assert frame["Event"].tolist() == ["Test Grand Prix", "Test Grand Prix"]
    assert frame["DriverCode"].tolist() == ["AAA", "BBB"]
    assert frame["rainfall_flag"].tolist() == [True, True]
    assert "grid_vs_quali_delta" in frame.columns


def test_apply_historical_calibration_blends_finish_and_dnf(tmp_path: Path) -> None:
    joblib.dump(_FinishModel(), tmp_path / FINISH_MODEL_FILE)
    joblib.dump(_DnfModel(), tmp_path / DNF_MODEL_FILE)

    calibrated = apply_historical_calibration(
        _features(),
        metadata={"year": 2026, "round": 4, "event": "Test Grand Prix"},
        weather_summary={},
        config=HistoricalCalibrationConfig(
            model_dir=tmp_path,
            finish_weight=0.25,
            dnf_weight=0.50,
        ),
    )

    assert calibrated["historical_model_available"].tolist() == [True, True]
    assert calibrated["historical_predicted_finish"].tolist() == [3.0, 1.0]
    assert calibrated["historical_dnf_probability"].round(2).tolist() == [0.10, 0.40]
    assert calibrated["reliability_score"].round(3).tolist() == [0.060, 0.220]
    assert calibrated.loc[0, "race_pace_score"] > 0.0
    assert calibrated.loc[1, "race_pace_score"] < 1.0


def test_apply_historical_calibration_skips_when_models_missing(tmp_path: Path) -> None:
    calibrated = apply_historical_calibration(
        _features(),
        config=HistoricalCalibrationConfig(model_dir=tmp_path),
    )

    assert calibrated["historical_model_available"].tolist() == [False, False]
    assert "Historical model artifacts missing" in calibrated["historical_calibration_note"].iloc[0]
    assert calibrated["race_pace_score"].tolist() == [0.0, 1.0]
