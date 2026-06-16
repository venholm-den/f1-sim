from __future__ import annotations

import pandas as pd

from src.backtest_visuals import (
    make_backtest_metrics_png,
    make_finish_comparison_png,
    make_strategy_comparison_png,
)


def test_backtest_visual_pngs_are_created(tmp_path) -> None:
    strategy_comparison = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "predicted_strategy_sequence": "MEDIUM-HARD",
                "actual_strategy_sequence": "MEDIUM-HARD",
                "predicted_stops": 1,
                "actual_stops": 1,
                "stops_match": True,
                "exact_strategy_match": True,
                "strategy_score": 1.0,
            },
            {
                "Driver": "HAM",
                "predicted_strategy_sequence": "MEDIUM-HARD",
                "actual_strategy_sequence": "SOFT-HARD-MEDIUM",
                "predicted_stops": 1,
                "actual_stops": 2,
                "stops_match": False,
                "exact_strategy_match": False,
                "strategy_score": 0.25,
            },
        ]
    )

    finish_comparison = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "predicted_finish": 1.5,
                "actual_position": 1,
                "finish_abs_error": 0.5,
                "predicted_points": 23,
                "actual_points": 25,
                "points_abs_error": 2,
            }
        ]
    )

    metrics = pd.DataFrame(
        [
            {
                "drivers_compared": 2,
                "finish_mae": 1.2,
                "finish_rmse": 1.6,
                "finish_spearman": 0.9,
                "points_mae": 3.0,
                "fantasy_basic_mae": 5.0,
                "top3_overlap": 0.67,
                "top10_overlap": 0.8,
                "predicted_winner": "RUS",
                "actual_winner": "RUS",
                "predicted_winner_hit": 1,
            }
        ]
    )

    strategy_metrics = pd.DataFrame(
        [
            {
                "exact_strategy_accuracy": 0.5,
                "stop_count_accuracy": 0.5,
                "average_strategy_score": 0.625,
            }
        ]
    )

    strategy_png = make_strategy_comparison_png(
        strategy_comparison,
        tmp_path / "strategy.png",
        "Strategy Test",
    )
    finish_png = make_finish_comparison_png(
        finish_comparison,
        tmp_path / "finish.png",
        "Finish Test",
    )
    metrics_png = make_backtest_metrics_png(
        metrics,
        tmp_path / "metrics.png",
        "Metrics Test",
        strategy_metrics=strategy_metrics,
    )

    assert (tmp_path / "strategy.png").exists()
    assert (tmp_path / "finish.png").exists()
    assert (tmp_path / "metrics.png").exists()
    assert strategy_png.endswith("strategy.png")
    assert finish_png.endswith("finish.png")
    assert metrics_png.endswith("metrics.png")
