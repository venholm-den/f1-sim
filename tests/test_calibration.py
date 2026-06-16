from __future__ import annotations

import json

import pandas as pd

from src.calibration import (
    build_calibration_report,
    calibrate_from_metric_paths,
    format_calibration_report,
    load_backtest_metrics,
    resolve_metric_paths,
)


def test_build_calibration_report_suggests_conservative_parameter_changes() -> None:
    metrics = pd.DataFrame(
        [
            {
                "finish_mae": 3.8,
                "finish_spearman": 0.52,
                "podium_brier": 0.21,
                "points_finish_brier": 0.20,
                "fantasy_basic_mae": 9.2,
                "top10_overlap": 0.62,
                "predicted_winner_hit": 0,
            }
        ]
    )

    report = build_calibration_report(
        metrics,
        parameters={
            "race_pace_seconds_multiplier": 0.20,
            "grid_loss_multiplier": 1.65,
            "race_noise_multiplier": 3.80,
            "chaos_noise_seconds": 1.25,
            "strategy_noise_seconds": 1.50,
        },
    )

    proposed = report["proposed_parameters"]

    assert proposed["race_pace_seconds_multiplier"] > 0.20
    assert proposed["chaos_noise_seconds"] > 1.25
    assert proposed["strategy_noise_seconds"] > 1.50
    assert "Fantasy MAE is high" in " ".join(report["notes"])

    text = format_calibration_report(report)

    assert "Backtests analysed: 1" in text
    assert "Suggested parameter changes" in text


def test_calibrate_from_metric_paths_writes_json_and_text_outputs(tmp_path) -> None:
    metrics_path = tmp_path / "sample_metrics.csv"
    strategy_metrics_path = tmp_path / "sample_strategy_metrics.csv"
    output_dir = tmp_path / "calibration"

    pd.DataFrame(
        [
            {
                "finish_mae": 2.4,
                "finish_spearman": 0.72,
                "podium_brier": 0.12,
                "points_finish_brier": 0.10,
                "top10_overlap": 0.82,
            }
        ]
    ).to_csv(metrics_path, index=False)
    pd.DataFrame([{"stop_count_accuracy": 0.8}]).to_csv(strategy_metrics_path, index=False)

    resolved = resolve_metric_paths([str(tmp_path / "*_metrics.csv")])
    metrics = load_backtest_metrics(resolved)
    outputs = calibrate_from_metric_paths(resolved, output_dir=output_dir)

    assert resolved == [metrics_path]
    assert len(metrics) == 1
    assert set(outputs) == {"json", "text"}
    assert (output_dir / "calibration_report.json").exists()
    assert (output_dir / "calibration_report.txt").exists()

    report = json.loads((output_dir / "calibration_report.json").read_text(encoding="utf-8"))

    assert report["metric_summary"]["events"] == 1
    assert report["proposed_parameters"] == {}
