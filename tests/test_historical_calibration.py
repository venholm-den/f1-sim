from __future__ import annotations

from pathlib import Path

import joblib
import json
import numpy as np
import pandas as pd
import pytest
from src.qualifying_features import QUALIFYING_CONTRACT

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
    classes_ = np.array([0, 1])
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
            'q_rank': [2, 1],
            'q_best_lap': [80., 80.5],
            'q_gap_to_best': [0., .5],
            'qualifying_feature_contract': [QUALIFYING_CONTRACT] * 2,
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
    assert frame.q_rank.tolist() == [2, 1]
    assert frame.grid_position.tolist() == [2, 1]
    assert frame.q_gap_to_best.tolist() == [0., .5]
    assert frame.grid_vs_quali_delta.eq(0).all()


def test_apply_historical_calibration_blends_finish_and_dnf(tmp_path: Path) -> None:
    joblib.dump(_FinishModel(), tmp_path / FINISH_MODEL_FILE)
    joblib.dump(_DnfModel(), tmp_path / DNF_MODEL_FILE)
    (tmp_path/'historical_model_metrics.json').write_text(json.dumps({'promotion_eligible': True, 'activated': True,
        'qualifying_feature_contract': QUALIFYING_CONTRACT}))

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


def test_unpromoted_or_legacy_artifacts_cannot_silently_activate(tmp_path):
    joblib.dump(_FinishModel(), tmp_path / FINISH_MODEL_FILE)
    joblib.dump(_DnfModel(), tmp_path / DNF_MODEL_FILE)
    for metrics in [{}, {'activated': False, 'promotion_eligible': False}]:
        (tmp_path/'historical_model_metrics.json').write_text(json.dumps(metrics))
        result = apply_historical_calibration(_features(), config=HistoricalCalibrationConfig(model_dir=tmp_path))
        assert not result.historical_model_available.any()
        assert result.race_pace_score.equals(_features().race_pace_score)
        assert 'inactive' in result.historical_calibration_note.iloc[0]


def test_calibration_rejects_synthetic_ranks_and_old_contract(tmp_path):
    with pytest.raises(ValueError, match='contract missing'):
        build_current_historical_feature_frame(_features().drop(columns='qualifying_feature_contract'))
    for ranks in ([1, 1], [1, np.nan]):
        with pytest.raises(ValueError, match='incomplete'):
            build_current_historical_feature_frame(_features().assign(q_rank=ranks))
    joblib.dump(_FinishModel(), tmp_path / FINISH_MODEL_FILE)
    joblib.dump(_DnfModel(), tmp_path / DNF_MODEL_FILE)
    (tmp_path/'historical_model_metrics.json').write_text(json.dumps({'promotion_eligible': True, 'activated': True}))
    result = apply_historical_calibration(_features(), config=HistoricalCalibrationConfig(model_dir=tmp_path))
    assert not result.historical_model_available.any()
    assert 'incompatible' in result.historical_calibration_note.iloc[0]


def test_swapped_model_file_is_refused_before_unpickling(tmp_path):
    import hashlib
    joblib.dump(_FinishModel(), tmp_path / FINISH_MODEL_FILE)
    joblib.dump(_DnfModel(), tmp_path / DNF_MODEL_FILE)
    hashes = {name: hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in (FINISH_MODEL_FILE, DNF_MODEL_FILE)}
    metrics = {'promotion_eligible': True, 'activated': True,
               'qualifying_feature_contract': QUALIFYING_CONTRACT, 'model_sha256': hashes}
    (tmp_path/'historical_model_metrics.json').write_text(json.dumps(metrics))
    config = HistoricalCalibrationConfig(model_dir=tmp_path)
    assert apply_historical_calibration(_features(), config=config).historical_model_available.all()
    joblib.dump(_DnfModel(), tmp_path / FINISH_MODEL_FILE)
    result = apply_historical_calibration(_features(), config=config)
    assert not result.historical_model_available.any()
    assert 'does not match' in result.historical_calibration_note.iloc[0]
