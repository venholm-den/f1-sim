from __future__ import annotations

import pandas as pd
import pytest
import numpy as np

from src.simulink_export import build_simulink_inputs


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "estimated_race_laps": [60, 60],
            "projected_lap_time": [82.0, 82.4],
            "tyre_deg_score": [0.08, 0.60],
        }
    )


def test_build_simulink_inputs_creates_strategy_aware_contract() -> None:
    strategies = pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "expected_stops": [1, 2],
        }
    )

    output = build_simulink_inputs(_features(), strategies)
    indexed = output.set_index("Driver")

    assert indexed.loc["RUS", "pit_laps"] == "30"
    assert indexed.loc["HAM", "pit_laps"] == "20;40"
    assert indexed.loc["HAM", "tyre_degradation_seconds_per_lap"] == 0.25
    assert bool(indexed.loc["HAM", "degradation_was_capped"])
    assert indexed.loc["RUS", "pace_offset_seconds"] < indexed.loc["HAM", "pace_offset_seconds"]


def test_build_simulink_inputs_uses_safe_defaults_without_optional_columns() -> None:
    features = pd.DataFrame({"Driver": ["ALO"], "Team": ["Aston Martin"]})

    output = build_simulink_inputs(features)

    assert output.loc[0, "race_laps"] == 57
    assert output.loc[0, "base_lap_time_seconds"] == 90.0
    assert output.loc[0, "pit_laps"] == "28"


def test_build_simulink_inputs_requires_driver_and_team() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        build_simulink_inputs(pd.DataFrame({"Driver": ["NOR"]}))


@pytest.mark.parametrize('parameter', ['initial_fuel_penalty_seconds',
    'fuel_gain_per_lap_seconds', 'pit_loss_seconds', 'max_tyre_degradation_seconds_per_lap'])
@pytest.mark.parametrize('value', [np.nan, np.inf, -np.inf])
def test_rejects_nonfinite_parameters(parameter, value) -> None:
    with pytest.raises(ValueError, match='finite'):
        build_simulink_inputs(_features(), **{parameter: value})


def test_preserves_raw_degradation_before_model_score_clipping() -> None:
    features = _features()
    features['deg_per_lap'] = [0.4, -0.03]
    features['tyre_deg_score'] = [0.18, -0.03]
    output = build_simulink_inputs(features).set_index('Driver')
    assert output.loc['RUS', 'raw_tyre_degradation_seconds_per_lap'] == .4
    assert output.loc['RUS', 'tyre_degradation_seconds_per_lap'] == .25
    assert output.loc['RUS', 'degradation_was_capped']
    assert output.loc['HAM', 'degradation_was_floored']


def test_single_lap_does_not_schedule_impossible_pit() -> None:
    features = _features().iloc[:1].copy()
    features['estimated_race_laps'] = 1
    output = build_simulink_inputs(features)
    assert output.loc[0, 'expected_stops'] == 0
    assert output.loc[0, 'pit_laps'] == ''


def test_rejects_duplicate_drivers_and_incomparable_race_distances() -> None:
    features = _features()
    with pytest.raises(ValueError, match='unique'):
        build_simulink_inputs(pd.concat([features, features]))
    features.loc[0, 'estimated_race_laps'] = 50
    with pytest.raises(ValueError, match='same race distance'):
        build_simulink_inputs(features)


def test_nonfinite_feature_values_use_fallbacks() -> None:
    features = _features()
    features['projected_lap_time'] = [np.inf, np.nan]
    features['race_pace'] = [85., 86.]
    features['estimated_race_laps'] = [np.inf, 60]
    output = build_simulink_inputs(features)
    assert np.isfinite(output.select_dtypes('number')).all().all()
    assert output['race_laps'].eq(60).all()
    assert np.allclose(output.base_lap_time_seconds + output.pace_offset_seconds, [85,86])
