from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.actual_strategy import (
    build_strategy_comparison,
    build_strategy_metrics,
    extract_actual_strategy_from_session,
    save_strategy_outputs,
)
from src.backtest_visuals import (
    make_backtest_metrics_png,
    make_finish_comparison_png,
    make_strategy_comparison_png,
)
from src.collect import load_session
from src.model_config import FANTASY_SCORING, SIMULATION_PARAMETERS


def _safe_slug(value: Any) -> str:
    text = str(value or "unknown").strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _to_float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None

    return float(number)


def _prob(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)

    if values.max() > 1.0:
        values = values / 100.0

    return values.clip(0.0, 1.0)


def _normalise_driver(value: Any) -> str:
    return str(value or "").strip().upper()


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
    Save a pre-race prediction snapshot for later backtesting.

    This should be called after fantasy scoring has been added to the race summary.
    Extra columns are preserved, so strategy columns can be backtested later.
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
        "GridPosition",
        "Grid",
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
        "PredictedStrategy",
        "history_adjusted_strategy",
        "HistoryAdjustedStrategy",
        "primary_strategy",
        "PrimaryStrategy",
        "expected_stops",
        "ExpectedStops",
        "strategy_confidence",
        "StrategyConfidence",
        "strategy_source",
        "StrategySource",
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


def _load_race_session(year: int, event: str) -> Any:
    loaded = load_session(year, event, "R")

    if isinstance(loaded, tuple):
        race_session = loaded[0]
    else:
        race_session = loaded

    if hasattr(race_session, "load"):
        race_session.load()

    return race_session


def _extract_actual_results_from_race_session(race_session: Any) -> pd.DataFrame:
    results = getattr(race_session, "results", pd.DataFrame())

    if results is not None and not results.empty:
        actual = results.copy()

        driver_col = None
        for candidate in ["Abbreviation", "Driver", "BroadcastName"]:
            if candidate in actual.columns:
                driver_col = candidate
                break

        if driver_col is None:
            raise ValueError("FastF1 race results are available, but no usable driver column was found.")

        if "Position" not in actual.columns:
            raise ValueError("FastF1 race results are available, but no Position column was found.")

        actual["Driver"] = actual[driver_col].astype(str).str.strip().str.upper()

        if "TeamName" in actual.columns:
            actual["Team"] = actual["TeamName"]
        elif "Team" not in actual.columns:
            actual["Team"] = ""

        actual["actual_position"] = pd.to_numeric(actual["Position"], errors="coerce")
        actual = actual.dropna(subset=["Driver", "actual_position"]).copy()
        actual["actual_position"] = actual["actual_position"].astype(int)
        actual["actual_points"] = actual["actual_position"].map(_finish_points_for_position).fillna(0.0)

        if "Status" in actual.columns:
            actual["actual_status"] = actual["Status"].fillna("").astype(str)
            actual["actual_dnf"] = actual["actual_status"].str.contains(
                "accident|collision|retired|dnf|engine|gearbox|brakes|hydraulics",
                case=False,
                na=False,
            )
        else:
            actual["actual_status"] = "classified"
            actual["actual_dnf"] = False

        actual["actual_result_source"] = "fastf1_results"

        return actual[
            [
                "Driver",
                "Team",
                "actual_position",
                "actual_points",
                "actual_dnf",
                "actual_status",
                "actual_result_source",
            ]
        ].sort_values("actual_position").reset_index(drop=True)

    laps = getattr(race_session, "laps", pd.DataFrame())

    if laps is None or laps.empty:
        raise ValueError(
            "Race results are not available yet from FastF1, and no lap data "
            "was available to build a provisional classification."
        )

    provisional = laps.copy()
    required_cols = {"Driver", "LapNumber", "Position"}
    missing_cols = required_cols.difference(provisional.columns)

    if missing_cols:
        raise ValueError(
            "Race results are not available yet from FastF1, and lap data is "
            f"missing required columns for provisional classification: {sorted(missing_cols)}"
        )

    provisional = provisional.dropna(subset=["Driver", "LapNumber", "Position"])
    provisional = provisional.sort_values(["Driver", "LapNumber"])

    final_laps = (
        provisional.groupby("Driver", as_index=False)
        .tail(1)
        .copy()
        .sort_values("Position")
        .reset_index(drop=True)
    )

    if "Team" not in final_laps.columns:
        final_laps["Team"] = ""

    final_laps["Driver"] = final_laps["Driver"].astype(str).str.strip().str.upper()
    final_laps["actual_position"] = (
        pd.to_numeric(final_laps["Position"], errors="coerce")
        .rank(method="first")
        .astype(int)
    )
    final_laps["actual_points"] = final_laps["actual_position"].map(_finish_points_for_position).fillna(0.0)
    final_laps["actual_dnf"] = False
    final_laps["actual_status"] = "provisional_from_final_lap"
    final_laps["actual_result_source"] = "fastf1_laps_fallback"

    return final_laps[
        [
            "Driver",
            "Team",
            "actual_position",
            "actual_points",
            "actual_dnf",
            "actual_status",
            "actual_result_source",
        ]
    ].sort_values("actual_position").reset_index(drop=True)


def _extract_actual_results_from_session(year: int, event: str) -> pd.DataFrame:
    """Compatibility wrapper for older callers/tests."""

    race_session = _load_race_session(year, event)
    return _extract_actual_results_from_race_session(race_session)


def _calculate_basic_actual_fantasy(row: pd.Series) -> float:
    grid_position = row.get("grid_position", row.get("GridPosition", np.nan))
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


def _read_strategy_predictions_fallback(predictions: pd.DataFrame) -> pd.DataFrame:
    strategy_columns = [
        "PredictedStrategy",
        "predicted_strategy",
        "history_adjusted_strategy",
        "HistoryAdjustedStrategy",
        "primary_strategy",
        "PrimaryStrategy",
    ]

    if any(column in predictions.columns for column in strategy_columns):
        return predictions

    fallback_paths = [
        Path("outputs/strategy/predicted_tyre_strategy_history_adjusted.csv"),
        Path("outputs/strategy/predicted_tyre_strategy.csv"),
    ]

    for path in fallback_paths:
        if not path.exists() or path.stat().st_size == 0:
            continue

        try:
            fallback = pd.read_csv(path)
        except Exception:
            continue

        if fallback.empty or "Driver" not in fallback.columns:
            continue

        fallback["Driver"] = fallback["Driver"].map(_normalise_driver)
        prediction_keys = predictions[["Driver"]].copy()
        strategy_cols = [column for column in fallback.columns if column != "Driver"]

        return prediction_keys.merge(
            fallback[["Driver"] + strategy_cols],
            on="Driver",
            how="left",
        )

    return predictions


def _build_png_outputs(
    output_path: Path,
    stem: str,
    year: int,
    event: str,
    comparison: pd.DataFrame,
    metrics_df: pd.DataFrame,
    strategy_comparison: pd.DataFrame | None,
    strategy_metrics: pd.DataFrame | None,
) -> dict[str, str]:
    png_paths: dict[str, str] = {}

    finish_png = output_path / f"{stem}_finish_comparison.png"
    metrics_png = output_path / f"{stem}_metrics.png"

    png_paths["finish_comparison_png"] = make_finish_comparison_png(
        comparison=comparison,
        output_path=finish_png,
        title=f"{year} {event}: Predicted vs Actual Finish",
    )

    png_paths["backtest_metrics_png"] = make_backtest_metrics_png(
        metrics=metrics_df,
        strategy_metrics=strategy_metrics,
        output_path=metrics_png,
        title=f"{year} {event}: Backtest Metrics Summary",
    )

    if strategy_comparison is not None and not strategy_comparison.empty:
        strategy_png = output_path / f"{stem}_strategy_comparison.png"
        png_paths["strategy_comparison_png"] = make_strategy_comparison_png(
            comparison=strategy_comparison,
            output_path=strategy_png,
            title=f"{year} {event}: Predicted vs Actual Tyre Strategy",
        )

    return png_paths


def backtest_prediction_snapshot(
    snapshot_path: str = "outputs/history/latest_prediction_snapshot.csv",
    output_dir: str = "outputs/backtest",
    year: int | None = None,
    event: str | None = None,
    generate_pngs: bool = True,
    post_discord: bool = False,
    discord_webhook_url: str | None = None,
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

    race_session = _load_race_session(year=year, event=event)
    actual = _extract_actual_results_from_race_session(race_session)
    actual_strategy = extract_actual_strategy_from_session(
        race_session,
        metadata={"year": year, "event": event},
    )

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
        suffixes=("", "_actual"),
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
        comparison["predicted_fantasy_points"] - comparison["actual_fantasy_points_basic"]
    )
    comparison["fantasy_basic_abs_error"] = comparison["fantasy_basic_error"].abs()

    comparison = comparison.sort_values("actual_position").reset_index(drop=True)
    comparison.to_csv(comparison_path, index=False)

    valid = comparison.dropna(subset=["actual_position", "predicted_finish"]).copy()

    predicted_order = valid.sort_values("predicted_finish")["Driver"].astype(str).tolist()
    actual_order = valid.sort_values("actual_position")["Driver"].astype(str).tolist()

    predicted_winner = (
        valid.sort_values("win_chance", ascending=False)["Driver"].iloc[0]
        if "win_chance" in valid.columns and not valid.empty
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

    paths: dict[str, str] = {
        "actual_results": str(actual_path),
        "comparison": str(comparison_path),
        "metrics": str(metrics_path),
        "recommendations": str(recommendations_path),
    }

    strategy_comparison = pd.DataFrame()
    strategy_metrics = pd.DataFrame()

    if not actual_strategy.empty:
        strategy_prediction_frame = _read_strategy_predictions_fallback(predictions)
        strategy_comparison = build_strategy_comparison(strategy_prediction_frame, actual_strategy)
        strategy_metrics = build_strategy_metrics(strategy_comparison, year=year, event=event)
        paths.update(
            save_strategy_outputs(
                actual_strategy=actual_strategy,
                strategy_comparison=strategy_comparison,
                strategy_metrics=strategy_metrics,
                output_dir=output_path,
                stem=stem,
            )
        )
    else:
        print("Actual tyre strategy comparison skipped: no FastF1 lap/stint compound data available.")

    if generate_pngs:
        png_paths = _build_png_outputs(
            output_path=output_path,
            stem=stem,
            year=year,
            event=event,
            comparison=comparison,
            metrics_df=metrics_df,
            strategy_comparison=strategy_comparison,
            strategy_metrics=strategy_metrics,
        )
        paths.update(png_paths)

    if post_discord:
        from src.discord_post import post_backtest_to_discord, write_discord_post_result

        result = post_backtest_to_discord(
            paths=paths,
            webhook_url=discord_webhook_url,
            event_title=f"{year} {event}",
        )
        discord_result_path = output_path / f"{stem}_discord_post_result.json"
        paths["discord_post_result"] = write_discord_post_result(result, discord_result_path)

        if result.get("ok"):
            print("Posted backtest PNGs to Discord.")
        else:
            print(f"Discord post skipped/failed: {result}")

    return paths


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

    suggestions_added = 0

    if np.isfinite(finish_mae) and finish_mae > 3.0:
        lines.append("- Finish MAE is high. Check race_pace_seconds_multiplier, grid_loss_multiplier, and race_noise_multiplier.")
        suggestions_added += 1

    if np.isfinite(spearman) and spearman < 0.65:
        lines.append("- Finishing-order correlation is weak. Check whether current weekend data is overpowering recent race baseline.")
        suggestions_added += 1

    if np.isfinite(podium_brier) and podium_brier > 0.18:
        lines.append("- Podium probability calibration looks poor. Check top-driver race noise and pace spread.")
        suggestions_added += 1

    if np.isfinite(points_brier) and points_brier > 0.18:
        lines.append("- Points probability calibration looks poor. Check midfield variance, DNF rate, and overtaking difficulty.")
        suggestions_added += 1

    if metrics.get("predicted_winner_hit") == 0:
        lines.append("- Predicted winner missed. Do not tune from one race alone, but inspect whether grid or race pace was overweighted.")
        suggestions_added += 1

    if suggestions_added == 0:
        lines.append("- No major tuning flags from the headline metrics.")

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
    parser.add_argument(
        "--output-dir",
        default="outputs/backtest",
        help="Directory for backtest outputs.",
    )
    parser.add_argument(
        "--no-pngs",
        action="store_true",
        help="Skip Discord-friendly PNG generation.",
    )
    parser.add_argument(
        "--post-discord",
        action="store_true",
        help="Post generated PNG outputs to Discord.",
    )
    parser.add_argument(
        "--discord-webhook-url",
        default=None,
        help="Discord webhook URL. Defaults to BACKTEST_DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL.",
    )

    args = parser.parse_args()

    webhook_url = (
        args.discord_webhook_url
        or os.getenv("BACKTEST_DISCORD_WEBHOOK_URL")
        or os.getenv("DISCORD_WEBHOOK_URL")
    )

    paths = backtest_prediction_snapshot(
        snapshot_path=args.snapshot,
        output_dir=args.output_dir,
        year=args.year,
        event=args.event,
        generate_pngs=not args.no_pngs,
        post_discord=args.post_discord,
        discord_webhook_url=webhook_url,
    )

    print("Backtest complete:")
    for label, path in paths.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
