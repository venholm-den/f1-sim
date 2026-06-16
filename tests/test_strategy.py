from __future__ import annotations

import pandas as pd

from src.strategy import predict_driver_strategy


def _driver_row(driver: str = "RUS", team: str = "Mercedes") -> pd.Series:
    return pd.Series(
        {
            "Driver": driver,
            "Team": team,
            "grid_position": 1,
            "avg_fantasy_points": 22.0,
            "avg_points": 14.0,
            "win_chance": 0.25,
            "podium_chance": 0.6,
        }
    )


def _inventory(confidence: str = "High") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "Compound": "HARD",
                "estimated_new_sets_remaining": 2,
                "observed_stints": 0,
                "likely_new_sets_used": 0,
                "max_tyre_life_seen": None,
                "tyre_data_source": "fastf1_lap_stint_data",
                "tyre_confidence": confidence,
                "inventory_confidence": confidence,
            },
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "Compound": "MEDIUM",
                "estimated_new_sets_remaining": 2,
                "observed_stints": 0,
                "likely_new_sets_used": 0,
                "max_tyre_life_seen": None,
                "tyre_data_source": "fastf1_lap_stint_data",
                "tyre_confidence": confidence,
                "inventory_confidence": confidence,
            },
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "Compound": "SOFT",
                "estimated_new_sets_remaining": 4,
                "observed_stints": 0,
                "likely_new_sets_used": 0,
                "max_tyre_life_seen": None,
                "tyre_data_source": "fastf1_lap_stint_data",
                "tyre_confidence": confidence,
                "inventory_confidence": confidence,
            },
        ]
    )


def _weather() -> dict[str, float | bool]:
    return {
        "rainfall_flag": False,
        "degradation_factor": 1.0,
    }


def _track() -> dict[str, float]:
    return {
        "overtaking_difficulty": 0.62,
    }


def test_strategy_confidence_is_capped_when_inventory_confidence_is_low() -> None:
    long_run = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "degradation_per_lap": 0.06,
                "laps_in_run": 20,
            }
        ]
    )

    strategy = predict_driver_strategy(
        driver_row=_driver_row(),
        inventory=_inventory(confidence="Low"),
        long_run_summary=long_run,
        weather_summary=_weather(),
        track_profile=_track(),
    )

    assert strategy["inventory_confidence"] == "Low"
    assert strategy["degradation_confidence"] == "High"
    assert strategy["strategy_confidence"] == "Medium"
    assert "Inventory confidence is Low" in strategy["confidence_reason"]


def test_strategy_uses_team_degradation_before_default() -> None:
    long_run = pd.DataFrame(
        [
            {
                "Driver": "ANT",
                "Team": "Mercedes",
                "degradation_per_lap": 0.09,
                "laps_in_run": 10,
            },
            {
                "Driver": "ANT",
                "Team": "Mercedes",
                "degradation_per_lap": 0.07,
                "laps_in_run": 8,
            },
        ]
    )

    strategy = predict_driver_strategy(
        driver_row=_driver_row(driver="RUS", team="Mercedes"),
        inventory=_inventory(confidence="High"),
        long_run_summary=long_run,
        weather_summary=_weather(),
        track_profile=_track(),
    )

    assert strategy["degradation_source"] == "team_long_run"
    assert strategy["degradation_confidence"] == "Medium"
    assert strategy["degradation_sample_laps"] == 18
    assert strategy["EstimatedDegPerLap"] == ((0.09 * 10) + (0.07 * 8)) / 18


def test_candidate_scoring_selects_two_stop_for_high_degradation() -> None:
    long_run = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "degradation_per_lap": 0.09,
                "laps_in_run": 20,
            }
        ]
    )

    strategy = predict_driver_strategy(
        driver_row=_driver_row(),
        inventory=_inventory(confidence="High"),
        long_run_summary=long_run,
        weather_summary=_weather(),
        track_profile=_track(),
    )

    assert strategy["strategy_source"] == "candidate_score_model"
    assert strategy["expected_stops"] == 2
    assert strategy["alternative_strategy_score"] is not None
    assert strategy["strategy_score_gap"] >= 0
    assert strategy["candidate_strategy_count"] >= 6
    assert "MEDIUM-HARD-MEDIUM" in strategy["candidate_strategy_summary"]


def test_candidate_scoring_keeps_one_stop_for_low_degradation_front_runner() -> None:
    long_run = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "degradation_per_lap": 0.05,
                "laps_in_run": 20,
            }
        ]
    )

    strategy = predict_driver_strategy(
        driver_row=_driver_row(),
        inventory=_inventory(confidence="High"),
        long_run_summary=long_run,
        weather_summary=_weather(),
        track_profile=_track(),
    )

    assert strategy["primary_strategy"] == "Medium(new) → Hard(new)"
    assert strategy["expected_stops"] == 1
    assert strategy["alternative_strategy"] != strategy["primary_strategy"]
    assert strategy["selected_strategy_score"] > strategy["alternative_strategy_score"]
