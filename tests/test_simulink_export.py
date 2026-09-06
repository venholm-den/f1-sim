from __future__ import annotations

import pandas as pd
import pytest

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
