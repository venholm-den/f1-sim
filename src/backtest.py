from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.collect import load_session
from src.model_config import FANTASY_SCORING, SIMULATION_PARAMETERS


def _safe_slug(value: Any) -> str:
    text = str(value or "unknown").strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _to_numeric(series: pd.Series, default: float = np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _prob(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)

    if values.max() > 1.0:
        values = values / 100.0

    return values.clip(0.0, 1.0)


def _normalise_driver(value: Any) -> str:
    return str(value).strip().upper()


def _mapping_to_float(mapping: dict[Any, Any]) -> dict[int, float]:
    output: dict[int, float] = {}

    for key, value in mapping.items():
        try:
            output[int(key)] = float(value)
        except (TypeError, ValueError):
            continue

    return output


def _scoring_value(key: str, default: float) -> float:
    try:
        return float(FANTASY_SCORING.get(key, default))
    except (TypeError, ValueError):
        return default


def _finish_points_for_position(position: Any) -> float:
    finish_points = _mapping_to_float(
        FANTASY_SCORING.get(
            "finish_points",
            {
                1: 25,
                2: 18,
                3: 15,
                4: 12,
                5: 10,
                6: 8,
                7: 6,
                8: 4,
                9: 2,
                10: 1,
            },
        )
    )

    try:
        return float(finish_points.get(int(round(float(position))), 0.0))
    except (TypeError, ValueError):
        return 0.0


def _quali_points_for_grid(grid_position: Any) -> float:
    quali_points = _mapping_to_float(
        FANTASY_SCORING.get(
            "quali_points",
            {
                1: 10,
                2: 9,
                3: 8,
                4: 7,
                5: 6,
                6: 5,
                7: 4,
                8: 3,
                9: 2,
                10: 1,
            },
        )
    )

    try:
        return float(quali_points.get(int(round(float(grid_position))), 0.0))
    except (TypeError, ValueError):
        return 0.0


def save_prediction_snapshot(
    race_summary: pd.DataFrame | None = None,
    metadata: dict[str, Any] | None = None,
    output_dir: str = "outputs/history",
    filename: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Saves a pre-race prediction snapshot for later backtesting.

    This should be called after fantasy scoring has been added to the race summary.
    """

    if race_summary is None:
        race_summary = kwargs.get("summary")
    if race_summary is None:
        race_summary = kwargs.get("prediction_summary")
    if race_summary is None:
        race_summary = kwargs.get("predictions")

    if race_summary is None or race_summary.empty:
        raise ValueError("No race_summary supplied for prediction snapshot.")

    metadata = metadata or kwargs.get("metadata") or {}

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    snapshot = race_summary.copy()

    if "Driver" not in snapshot.columns:
        raise ValueError("Prediction snapshot needs a Driver column.")

    snapshot["Driver"] = snapshot["Driver"].map(_normalise_driver)

    if "Team" not in snapshot.columns:
        snapshot["Team"] = ""

    snapshot["Team"] = snapshot["Team"].astype(str)

    year = metadata.get("year", metadata.get("season", "unknown"))
    round_number = metadata.get("round", metadata.get("round_number", "unknown"))
    event = metadata.get("event", metadata.get("event_name", "unknown"))
    session = metadata.get("session", metadata.get("session_type", "unknown"))

    snapshot.insert(0, "snapshot_created_at", datetime.now().isoformat(timespec="seconds"))
    snapshot.insert(1, "snapshot_type", "pre_race_prediction")
    snapshot.insert(2, "year", year)
    snapshot.insert(3, "round", round_number)
    snapshot.insert(4, "event", event)
    snapshot.insert(5, "session", session)

    useful_cols = [
        "snapshot_created_at",
        "snapshot_type",
        "year",
        "round",
        "event",
        "session",
        "Driver",
        "Team",
        "grid_position",
        "avg_finish",
        "finish_p25",
        "finish_p75",
        "win_chance",
        "podium_chance",
        "top5_chance",
        "points_chance",
        "dnf_chance",
        "avg_points",
        "points_p25",
        "points_p75",
        "avg_fantasy_points",
        "fantasy_p25",
        "fantasy_p75",
        "fantasy_std",
        "fantasy_floor_p10",
        "fantasy_ceiling_p90",
        "avg_positions_gained",
        "fastest_lap_chance",
        "dotd_chance",
        "avg_quali_points",
        "avg_finish_fantasy_points",
        "avg_position_change_points",
        "avg_fastest_lap_points",
        "avg_dotd_points",
        "avg_dnf_penalty",
        "fantasy_price",
        "fantasy_xppm",
        "race_pace_score",
        "quali_pace_score",
        "long_run_pace_score",
        "tyre_deg_score",
        "reliability_score",
        "strategy_score",
        "performance_uncertainty",
        "grid_source",
        "grid_confidence",
        "performance_model_version",
    ]

    existing_cols = [col for col in useful_cols if col in snapshot.columns]
    extra_cols = [col for col in snapshot.columns if col not in existing_cols]
    snapshot = snapshot[existing_cols + extra_cols]

    if filename is None:
        round_slug = f"R{int(round_number):02d}" if str(round_number).isdigit() else f"R_{_safe_slug(round_number)}"
        filename = (
            f"{_safe_slug(year)}_"
            f"{round_slug}_"
            f"{_safe_slug(event)}_"
            f"{_safe_slug(session)}_"
            f"prediction_snapshot_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

    full_path = output_path / filename
    snapshot.to_csv(full_path, index=False)

    latest_path = output_path / "latest_prediction_snapshot.csv"
    shutil.copyfile(full_path, latest_path)

    config_path = full_path.with_suffix(".config.json")
    config_payload = {
        "metadata": metadata,
        "simulation_parameters": SIMULATION_PARAMETERS,
        "fantasy_scoring": FANTASY_SCORING,
    }

    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    return str(full_path)


def _extract_actual_results_from_session(year: int, event: str) -> pd.DataFrame:
    session = load_session(year, event, "R")

    results = getattr(session, "results", None)

    if results is None or not isinstance(results, pd.DataFrame) or results.empty:
        raise ValueError("Race results are not available yet from FastF1.")

    df = results.copy()

    driver_col = _first_existing_column(df, ["Abbreviation", "Driver", "BroadcastName", "FullName"])
    team_col = _first_existing_column(df, ["TeamName", "Team", "TeamId"])
    position_col = _first_existing_column(df, ["Position", "ClassifiedPosition"])
    points_col = _first_existing_column(df, ["Points"])
    status_col = _first_existing_column(df, ["Status"])

    if driver_col is None or position_col is None:
        raise ValueError("Could not identify driver/position columns in FastF1 race results.")

    actual = pd.DataFrame()
    actual["Driver"] = df[driver_col].map(_normalise_driver)

    if team_col is not None:
        actual["actual_team"] = df[team_col].astype(str)
    else:
        actual["actual_team"] = ""

    actual["actual_position"] = pd.to_numeric(df[position_col], errors="coerce")

    if points_col is not None:
        actual["actual_points"] = pd.to_numeric(df[points_col], errors="coerce").fillna(0.0)
    else:
        actual["actual_points"] = actual["actual_position"].map(_finish_points_for_position)

    if status_col is not None:
        status_text = df[status_col].astype(str).str.lower()
        actual["actual_status"] = df[status_col].astype(str)
        actual["actual_dnf"] = ~status_text.str.contains("finished|lap|\\+", regex=True, na=False)
    else:
        actual["actual_status"] = ""
        actual["actual_dnf"] = False

    actual = actual.dropna(subset=["Driver", "actual_position"]).copy()
    actual["actual_position"] = actual["actual_position"].astype(int)

    actual = actual.sort_values("actual_position").reset_index(drop=True)

    return actual


def _calculate_basic_actual_fantasy(row: pd.Series) -> float:
    grid_position = row.get("grid_position", np.nan)
    actual_position = row.get("actual_position", np.nan)
    actual_dnf = bool(row.get("actual_dnf", False))

    finish_points = _finish_points_for_position(actual_position)
    quali_points = _quali_points_for_grid(grid_position)

    try:
        positions_gained = float(grid_position) - float(actual_position)
    except (TypeError, ValueError):
        positions_gained = 0.0

    gain_value = _scoring_value("position_gain_points_per_place", 1.0)
    loss_value = _scoring_value("position_loss_points_per_place", -0.5)
    min_value = _scoring_value("position_change_min", -5.0)
    max_value = _scoring_value("position_change_max", 10.0)

    if positions_gained >= 0:
        position_points = positions_gained * gain_value
    else:
        position_points = abs(positions_gained) * loss_value

    position_points = float(np.clip(position_points, min_value, max_value))

    if actual_dnf:
        position_points = 0.0

    dnf_points = _scoring_value("dnf_penalty", -10.0) if actual_dnf else 0.0

    return finish_points + quali_points + position_points + dnf_points


def _brier(predicted_probability: pd.Series, actual_outcome: pd.Series) -> float:
    predicted = _prob(predicted_probability)
    actual = pd.to_numeric(actual_outcome, errors="coerce").fillna(0.0).clip(0.0, 1.0)

    return float(((predicted - actual) ** 2).mean())


def _rmse(error: pd.Series) -> float:
    values = pd.to_numeric(error, errors="coerce").dropna()

    if values.empty:
        return float("nan")

    return float(math.sqrt((values ** 2).mean()))


def _overlap_score(predicted: list[str], actual: list[str], n: int) -> float:
    if n <= 0:
        return float("nan")

    return len(set(predicted[:n]) & set(actual[:n])) / n


def backtest_prediction_snapshot(
    snapshot_path: str = "outputs/history/latest_prediction_snapshot.csv",
    output_dir: str = "outputs/backtest",
    year: int | None = None,
    event: str | None = None,
) -> dict[str, str]:
    snapshot_file = Path(snapshot_path)

    if not snapshot_file.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_file}")

    predictions = pd.read_csv(snapshot_file)

    if predictions.empty:
        raise ValueError("Prediction snapshot is empty.")

    predictions["Driver"] = predictions["Driver"].map(_normalise_driver)

    if year is None:
        year = int(pd.to_numeric(predictions["year"], errors="coerce").dropna().iloc[0])

    if event is None:
        event = str(predictions["event"].dropna().iloc[0])

    actual = _extract_actual_results_from_session(year=year, event=event)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stem = snapshot_file.stem
    actual_path = output_path / f"{stem}_actual_results.csv"
    comparison_path = output_path / f"{stem}_comparison.csv"
    metrics_path = output_path / f"{stem}_metrics.csv"
    recommendations_path = output_path / f"{stem}_recommendations.txt"

    actual.to_csv(actual_path, index=False)

    comparison = predictions.merge(
        actual,
        on="Driver",
        how="left",
    )

    comparison["predicted_finish"] = pd.to_numeric(comparison.get("avg_finish"), errors="coerce")
    comparison["predicted_points"] = pd.to_numeric(comparison.get("avg_points"), errors="coerce")
    comparison["predicted_fantasy_points"] = pd.to_numeric(
        comparison.get("avg_fantasy_points"),
        errors="coerce",
    )

    comparison["finish_error"] = comparison["predicted_finish"] - comparison["actual_position"]
    comparison["finish_abs_error"] = comparison["finish_error"].abs()

    comparison["points_error"] = comparison["predicted_points"] - comparison["actual_points"]
    comparison["points_abs_error"] = comparison["points_error"].abs()

    comparison["actual_win"] = (comparison["actual_position"] == 1).astype(int)
    comparison["actual_podium"] = (comparison["actual_position"] <= 3).astype(int)
    comparison["actual_top5"] = (comparison["actual_position"] <= 5).astype(int)
    comparison["actual_points_finish"] = (comparison["actual_points"] > 0).astype(int)

    comparison["actual_fantasy_points_basic"] = comparison.apply(
        _calculate_basic_actual_fantasy,
        axis=1,
    )

    comparison["fantasy_basic_error"] = (
        comparison["predicted_fantasy_points"]
        - comparison["actual_fantasy_points_basic"]
    )

    comparison["fantasy_basic_abs_error"] = comparison["fantasy_basic_error"].abs()

    comparison = comparison.sort_values("actual_position").reset_index(drop=True)
    comparison.to_csv(comparison_path, index=False)

    valid = comparison.dropna(subset=["actual_position", "predicted_finish"]).copy()

    predicted_order = (
        valid.sort_values("predicted_finish")["Driver"]
        .astype(str)
        .tolist()
    )

    actual_order = (
        valid.sort_values("actual_position")["Driver"]
        .astype(str)
        .tolist()
    )

    predicted_winner = (
        valid.sort_values("win_chance", ascending=False)["Driver"].iloc[0]
        if "win_chance" in valid.columns
        else predicted_order[0]
    )

    actual_winner = actual_order[0]

    metrics = {
        "snapshot_path": str(snapshot_file),
        "year": year,
        "event": event,
        "drivers_compared": int(len(valid)),
        "finish_mae": float(valid["finish_abs_error"].mean()),
        "finish_rmse": _rmse(valid["finish_error"]),
        "finish_spearman": float(valid["predicted_finish"].corr(valid["actual_position"], method="spearman")),
        "points_mae": float(valid["points_abs_error"].mean()),
        "points_rmse": _rmse(valid["points_error"]),
        "win_brier": _brier(valid.get("win_chance", pd.Series(0, index=valid.index)), valid["actual_win"]),
        "podium_brier": _brier(valid.get("podium_chance", pd.Series(0, index=valid.index)), valid["actual_podium"]),
        "top5_brier": _brier(valid.get("top5_chance", pd.Series(0, index=valid.index)), valid["actual_top5"]),
        "points_finish_brier": _brier(valid.get("points_chance", pd.Series(0, index=valid.index)), valid["actual_points_finish"]),
        "fantasy_basic_mae": float(valid["fantasy_basic_abs_error"].mean()),
        "predicted_winner": predicted_winner,
        "actual_winner": actual_winner,
        "predicted_winner_hit": int(predicted_winner == actual_winner),
        "top3_overlap": _overlap_score(predicted_order, actual_order, 3),
        "top10_overlap": _overlap_score(predicted_order, actual_order, 10),
    }

    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(metrics_path, index=False)

    recommendations = _build_recommendations(metrics, valid)
    recommendations_path.write_text(recommendations, encoding="utf-8")

    return {
        "actual_results": str(actual_path),
        "comparison": str(comparison_path),
        "metrics": str(metrics_path),
        "recommendations": str(recommendations_path),
    }


def _build_recommendations(metrics: dict[str, Any], comparison: pd.DataFrame) -> str:
    lines: list[str] = []

    lines.append("F1 simulation backtest recommendations")
    lines.append("=" * 42)
    lines.append("")
    lines.append(f"Event: {metrics.get('year')} {metrics.get('event')}")
    lines.append(f"Drivers compared: {metrics.get('drivers_compared')}")
    lines.append("")
    lines.append("Headline metrics")
    lines.append("-" * 16)

    for key in [
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
        value = metrics.get(key)
        if isinstance(value, float):
            lines.append(f"- {key}: {value:.4f}")
        else:
            lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("Winner")
    lines.append("-" * 6)
    lines.append(f"- Predicted winner: {metrics.get('predicted_winner')}")
    lines.append(f"- Actual winner: {metrics.get('actual_winner')}")
    lines.append(f"- Hit: {metrics.get('predicted_winner_hit')}")
    lines.append("")

    worst = comparison.sort_values("finish_abs_error", ascending=False).head(6)

    lines.append("Largest finishing-position misses")
    lines.append("-" * 34)

    for _, row in worst.iterrows():
        lines.append(
            f"- {row['Driver']}: predicted {row['predicted_finish']:.2f}, "
            f"actual P{int(row['actual_position'])}, "
            f"error {row['finish_error']:.2f}"
        )

    lines.append("")
    lines.append("Suggested tuning checks")
    lines.append("-" * 23)

    finish_mae = float(metrics.get("finish_mae", np.nan))
    spearman = float(metrics.get("finish_spearman", np.nan))
    podium_brier = float(metrics.get("podium_brier", np.nan))
    points_brier = float(metrics.get("points_finish_brier", np.nan))

    if np.isfinite(finish_mae) and finish_mae > 3.0:
        lines.append("- Finish MAE is high. Check race_pace_seconds_multiplier, grid_loss_multiplier, and race_noise_multiplier.")

    if np.isfinite(spearman) and spearman < 0.65:
        lines.append("- Finishing-order correlation is weak. Check whether current weekend data is overpowering recent race baseline.")

    if np.isfinite(podium_brier) and podium_brier > 0.18:
        lines.append("- Podium probability calibration looks poor. Check top-driver race noise and pace spread.")

    if np.isfinite(points_brier) and points_brier > 0.18:
        lines.append("- Points probability calibration looks poor. Check midfield variance, DNF rate, and overtaking difficulty.")

    if metrics.get("predicted_winner_hit") == 0:
        lines.append("- Predicted winner missed. Do not tune from one race alone, but inspect whether grid or race pace was overweighted.")

    if len(lines) == 0:
        lines.append("- No recommendations generated.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest an F1 prediction snapshot.")
    parser.add_argument(
        "--snapshot",
        default="outputs/history/latest_prediction_snapshot.csv",
        help="Prediction snapshot CSV path.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Override season year.",
    )
    parser.add_argument(
        "--event",
        default=None,
        help="Override event name.",
    )

    args = parser.parse_args()

    paths = backtest_prediction_snapshot(
        snapshot_path=args.snapshot,
        year=args.year,
        event=args.event,
    )

    print("Backtest complete:")
    for label, path in paths.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()