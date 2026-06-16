from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.model_config import SIMULATION_PARAMETERS


DEFAULT_METRICS_PATTERN = "outputs/backtest/*_metrics.csv"


@dataclass(frozen=True)
class ParameterAdjustment:
    parameter: str
    current_value: float
    proposed_value: float
    reason: str

    @property
    def change_percent(self) -> float:
        if self.current_value == 0:
            return 0.0

        return (self.proposed_value / self.current_value) - 1.0


def _to_float(value: Any, default: float = float("nan")) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return float(number)


def _numeric_mean(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return float("nan")

    values = pd.to_numeric(df[column], errors="coerce").dropna()

    if values.empty:
        return float("nan")

    return float(values.mean())


def _adjust_parameter(
    parameters: dict[str, Any],
    key: str,
    multiplier: float,
    reason: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> ParameterAdjustment | None:
    if key not in parameters:
        return None

    current = _to_float(parameters.get(key))

    if not np.isfinite(current):
        return None

    proposed = current * multiplier

    if minimum is not None:
        proposed = max(proposed, minimum)

    if maximum is not None:
        proposed = min(proposed, maximum)

    if np.isclose(current, proposed):
        return None

    return ParameterAdjustment(
        parameter=key,
        current_value=float(current),
        proposed_value=float(proposed),
        reason=reason,
    )


def resolve_metric_paths(patterns: Iterable[str]) -> list[Path]:
    paths: list[Path] = []

    for pattern in patterns:
        matches = sorted(Path(path) for path in glob(pattern))

        if matches:
            paths.extend(matches)
            continue

        literal = Path(pattern)

        if literal.exists():
            paths.append(literal)

    race_metric_paths = [
        path for path in paths if not path.name.endswith("_strategy_metrics.csv")
    ]
    unique: dict[str, Path] = {str(path.resolve()): path for path in race_metric_paths}

    return list(unique.values())


def load_backtest_metrics(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for path in paths:
        file_path = Path(path)

        if not file_path.exists() or file_path.stat().st_size == 0:
            continue

        metrics = pd.read_csv(file_path)

        if metrics.empty:
            continue

        metrics = metrics.copy()
        metrics["metrics_path"] = str(file_path)
        frames.append(metrics)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def summarize_backtest_metrics(metrics: pd.DataFrame) -> dict[str, Any]:
    if metrics.empty:
        return {"events": 0}

    summary: dict[str, Any] = {
        "events": int(len(metrics)),
    }

    for column in [
        "finish_mae",
        "finish_rmse",
        "finish_spearman",
        "points_mae",
        "win_brier",
        "podium_brier",
        "top5_brier",
        "points_finish_brier",
        "fantasy_basic_mae",
        "top3_overlap",
        "top10_overlap",
    ]:
        value = _numeric_mean(metrics, column)

        if np.isfinite(value):
            summary[column] = value

    if "predicted_winner_hit" in metrics.columns:
        summary["winner_hit_rate"] = _numeric_mean(metrics, "predicted_winner_hit")

    return summary


def build_parameter_adjustments(
    metric_summary: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> list[ParameterAdjustment]:
    parameters = parameters or SIMULATION_PARAMETERS
    adjustments: list[ParameterAdjustment] = []

    finish_mae = _to_float(metric_summary.get("finish_mae"))
    finish_spearman = _to_float(metric_summary.get("finish_spearman"))
    podium_brier = _to_float(metric_summary.get("podium_brier"))
    points_brier = _to_float(metric_summary.get("points_finish_brier"))
    top10_overlap = _to_float(metric_summary.get("top10_overlap"))

    if np.isfinite(finish_mae) and finish_mae > 3.0:
        for key in ["race_pace_seconds_multiplier", "grid_loss_multiplier"]:
            adjustment = _adjust_parameter(
                parameters,
                key,
                1.05,
                "Finish MAE is above 3.0; strengthen deterministic pace/grid signal.",
            )

            if adjustment:
                adjustments.append(adjustment)

    if np.isfinite(finish_spearman) and finish_spearman < 0.65:
        adjustment = _adjust_parameter(
            parameters,
            "race_noise_multiplier",
            0.95,
            "Finishing-order correlation is weak; reduce race noise slightly.",
            minimum=1.0,
        )

        if adjustment:
            adjustments.append(adjustment)

    if np.isfinite(podium_brier) and podium_brier > 0.18:
        adjustment = _adjust_parameter(
            parameters,
            "race_noise_multiplier",
            1.05,
            "Podium probability Brier score is high; widen front-runner uncertainty.",
        )

        if adjustment:
            adjustments.append(adjustment)

    if np.isfinite(points_brier) and points_brier > 0.18:
        for key in ["chaos_noise_seconds", "strategy_noise_seconds"]:
            adjustment = _adjust_parameter(
                parameters,
                key,
                1.05,
                "Points-finish calibration is weak; add modest midfield variance.",
            )

            if adjustment:
                adjustments.append(adjustment)

    if np.isfinite(top10_overlap) and top10_overlap < 0.70:
        adjustment = _adjust_parameter(
            parameters,
            "grid_loss_multiplier",
            0.95,
            "Top-10 overlap is low; avoid over-anchoring results to starting grid.",
            minimum=0.5,
        )

        if adjustment:
            adjustments.append(adjustment)

    merged: dict[str, ParameterAdjustment] = {}

    for adjustment in adjustments:
        existing = merged.get(adjustment.parameter)

        if existing is None:
            merged[adjustment.parameter] = adjustment
            continue

        current = existing.current_value
        combined = existing.proposed_value * (1.0 + adjustment.change_percent)
        merged[adjustment.parameter] = ParameterAdjustment(
            parameter=adjustment.parameter,
            current_value=current,
            proposed_value=combined,
            reason=f"{existing.reason} {adjustment.reason}",
        )

    return list(merged.values())


def build_calibration_report(
    metrics: pd.DataFrame,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric_summary = summarize_backtest_metrics(metrics)
    adjustments = build_parameter_adjustments(metric_summary, parameters=parameters)

    notes: list[str] = []

    if metric_summary.get("events", 0) == 0:
        notes.append("No backtest metrics were available. Run post-race backtests first.")
    elif metric_summary.get("events", 0) < 3:
        notes.append("Fewer than 3 backtests are available; treat suggestions as directional.")

    if "fantasy_basic_mae" in metric_summary and metric_summary["fantasy_basic_mae"] > 8:
        notes.append("Fantasy MAE is high; inspect fantasy scoring assumptions before tuning race pace.")

    return {
        "metric_summary": metric_summary,
        "proposed_parameters": {
            adjustment.parameter: adjustment.proposed_value
            for adjustment in adjustments
        },
        "adjustments": [
            {
                "parameter": adjustment.parameter,
                "current_value": adjustment.current_value,
                "proposed_value": adjustment.proposed_value,
                "change_percent": adjustment.change_percent,
                "reason": adjustment.reason,
            }
            for adjustment in adjustments
        ],
        "notes": notes,
    }


def format_calibration_report(report: dict[str, Any]) -> str:
    lines = ["F1 simulation calibration report", "=" * 32, ""]

    metric_summary = report.get("metric_summary", {})
    lines.append(f"Backtests analysed: {metric_summary.get('events', 0)}")
    lines.append("")

    lines.append("Metric summary")
    lines.append("-" * 14)

    for key, value in metric_summary.items():
        if key == "events":
            continue

        if isinstance(value, float):
            lines.append(f"- {key}: {value:.4f}")
        else:
            lines.append(f"- {key}: {value}")

    adjustments = report.get("adjustments", [])
    lines.append("")
    lines.append("Suggested parameter changes")
    lines.append("-" * 27)

    if adjustments:
        for adjustment in adjustments:
            change = float(adjustment["change_percent"])
            lines.append(
                f"- {adjustment['parameter']}: "
                f"{float(adjustment['current_value']):.4f} -> "
                f"{float(adjustment['proposed_value']):.4f} "
                f"({change:+.1%})"
            )
            lines.append(f"  Reason: {adjustment['reason']}")
    else:
        lines.append("- No parameter changes suggested.")

    notes = report.get("notes", [])

    if notes:
        lines.append("")
        lines.append("Notes")
        lines.append("-" * 5)
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines) + "\n"


def write_calibration_outputs(
    report: dict[str, Any],
    output_dir: str | Path = "outputs/calibration",
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_path = output_path / "calibration_report.json"
    text_path = output_path / "calibration_report.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    text_path.write_text(format_calibration_report(report), encoding="utf-8")

    return {
        "json": str(json_path),
        "text": str(text_path),
    }


def calibrate_from_metric_paths(
    metric_paths: Iterable[str | Path],
    output_dir: str | Path = "outputs/calibration",
) -> dict[str, str]:
    metrics = load_backtest_metrics(metric_paths)
    report = build_calibration_report(metrics)
    return write_calibration_outputs(report, output_dir=output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build calibration recommendations from backtest metrics.")
    parser.add_argument(
        "--metrics",
        action="append",
        default=None,
        help=(
            "Metrics CSV path or glob. Can be supplied multiple times. "
            f"Defaults to {DEFAULT_METRICS_PATTERN}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/calibration",
        help="Directory for calibration report outputs.",
    )

    args = parser.parse_args()

    patterns = args.metrics or [DEFAULT_METRICS_PATTERN]
    metric_paths = resolve_metric_paths(patterns)

    if not metric_paths:
        raise FileNotFoundError(
            "No backtest metrics found. Run `python -m src.backtest` after a race "
            "or pass --metrics with one or more metrics CSV paths."
        )

    output_paths = calibrate_from_metric_paths(metric_paths, output_dir=args.output_dir)

    print("Calibration report created:")
    for label, path in output_paths.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
