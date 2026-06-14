from __future__ import annotations

import pandas as pd

from src.simulate import simulate_races


def _minimal_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["RUS", "HAM", "ANT", "LEC"],
            "Team": ["Mercedes", "Ferrari", "Mercedes", "Ferrari"],
            "grid_position": [1, 2, 3, 10],
            "grid_source": ["actual_session_results"] * 4,
            "grid_confidence": [1.0, 1.0, 1.0, 1.0],
            "quali_pace_score": [0.25, 0.33, 0.00, 0.45],
            "race_pace_score": [0.64, 0.54, 0.00, 0.59],
            "long_run_pace_score": [0.64, 0.54, 0.00, 0.59],
            "tyre_deg_score": [-0.02, -0.01, -0.03, -0.02],
            "strategy_score": [0.15, 0.15, 0.15, 0.15],
            "reliability_score": [0.04, 0.04, 0.04, 0.04],
            "performance_uncertainty": [1.8, 1.6, 1.4, 1.7],
            "estimated_race_laps": [66, 66, 66, 66],
            "base_winner_race_time_seconds": [5400.0, 5400.0, 5400.0, 5400.0],
        }
    )


def test_simulate_races_returns_expected_outputs() -> None:
    summary, position_matrix, results = simulate_races(
        features=_minimal_features(),
        n_sims=100,
        seed=123,
        overtaking_difficulty=0.72,
        weather_modifiers={
            "chaos_factor": 1.0,
            "strategy_factor": 1.0,
            "dnf_factor": 1.0,
            "degradation_factor": 1.0,
            "uncertainty_factor": 1.0,
            "rainfall_flag": False,
            "wind_speed_avg": 2.0,
        },
    )

    assert len(summary) == 4
    assert len(position_matrix) == 4
    assert len(results) == 400

    required_result_cols = {
        "sim_id",
        "Driver",
        "Team",
        "grid_position",
        "finish_position",
        "points",
        "projected_race_time_seconds",
        "classified_race_time_seconds",
        "dnf",
        "positions_gained",
        "fastest_lap",
        "dotd",
    }

    assert required_result_cols.issubset(results.columns)

    for _, group in results.groupby("sim_id"):
        assert sorted(group["finish_position"].tolist()) == [1, 2, 3, 4]


def test_simulation_summary_contains_probability_columns() -> None:
    summary, _, _ = simulate_races(
        features=_minimal_features(),
        n_sims=50,
        seed=456,
        overtaking_difficulty=0.72,
        weather_modifiers=None,
    )

    required_summary_cols = {
        "Driver",
        "Team",
        "avg_finish",
        "win_chance",
        "podium_chance",
        "points_chance",
        "avg_points",
        "race_pace_score",
        "performance_uncertainty",
    }

    assert required_summary_cols.issubset(summary.columns)
    assert summary["win_chance"].between(0, 1).all()
    assert summary["podium_chance"].between(0, 1).all()
    assert summary["points_chance"].between(0, 1).all()