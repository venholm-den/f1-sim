from __future__ import annotations

import pandas as pd

from src.prediction_reasoning import build_prediction_reasoning, save_prediction_reasoning_csv


def _summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "avg_grid": [1.0, 2.0],
            "grid_position": [1, 2],
            "grid_source": ["actual_session_results", "estimated_model_grid"],
            "grid_confidence": [1.0, 0.38],
            "avg_finish": [1.4, 2.2],
            "avg_points": [22.0, 14.0],
            "win_chance": [0.62, 0.18],
            "podium_chance": [0.93, 0.75],
            "top5_chance": [1.0, 0.98],
            "points_chance": [1.0, 0.97],
            "dnf_chance": [0.03, 0.07],
            "quali_pace_score": [0.0, 0.2],
            "race_pace_score": [0.0, 0.3],
            "long_run_pace_score": [0.1, 0.4],
            "tyre_deg_score": [0.01, 0.04],
            "strategy_score": [0.12, 0.20],
            "reliability_score": [0.03, 0.07],
            "performance_uncertainty": [1.1, 1.4],
            "estimated_race_laps": [66, 66],
        }
    )


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "actual_grid_position": [1, pd.NA],
            "estimated_grid_position": [1, 2],
            "quali_weight_used": [0.5, 0.5],
            "race_weight_used": [0.4, 0.4],
            "strategy_weight_used": [0.2, 0.2],
        }
    )


def test_prediction_reasoning_contains_explanation_columns() -> None:
    reasoning = build_prediction_reasoning(
        race_summary=_summary(),
        model_features=_features(),
        overtaking_difficulty=0.72,
        weather_summary={"degradation_factor": 1.1, "strategy_factor": 1.0},
    )

    required = {
        "predicted_finish_rank",
        "grid_prediction_reason",
        "race_sim_reason",
        "overtaking_difficulty",
        "race_pace_loss_seconds",
        "grid_loss_seconds",
        "deterministic_loss_seconds",
        "race_pace_rank",
        "reliability_rank",
    }

    assert required.issubset(reasoning.columns)
    assert list(reasoning["Driver"]) == ["RUS", "HAM"]
    assert reasoning.loc[0, "grid_prediction_reason"].startswith("Grid P1")
    assert reasoning.loc[1, "grid_loss_seconds"] > reasoning.loc[0, "grid_loss_seconds"]
    assert "win 62.0%" in reasoning.loc[0, "race_sim_reason"]


def test_save_prediction_reasoning_csv(tmp_path) -> None:
    path = save_prediction_reasoning_csv(
        race_summary=_summary(),
        model_features=_features(),
        output_dir=tmp_path,
        overtaking_difficulty=0.55,
        weather_summary=None,
    )

    saved = pd.read_csv(path)

    assert saved.iloc[0]["Driver"] == "RUS"
    assert "prediction_reasoning.csv" in path
