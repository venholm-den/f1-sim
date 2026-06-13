from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from src.collect import (
    enable_fastf1_cache,
    load_latest_predictor_session,
    load_recent_race_sessions,
    load_session,
)
from src.features import build_driver_features
from src.model import build_model_features
from src.grid import build_grid_features
from src.weather import summarize_weather
from src.simulate import simulate_races
from src.performance import add_performance_profile
from src.fantasy import ensure_price_template, calculate_fantasy_summary
from src.fantasy_charts import make_fantasy_points_chart, make_fantasy_value_chart
from src.charts import make_probability_chart, make_text_report_image
from src.discord_post import post_to_discord
from src.track import load_track_profile
from src.lap_details import export_weekend_lap_details
from src.tyres import infer_tyre_usage
from src.strategy import predict_tyre_strategies, make_strategy_table_image
from src.strategy_history import apply_historical_strategy_adjustment_to_outputs
from src.report_card import build_report_outputs
from src.simulation_viz import make_simulated_race_time_chart

try:
    from src.backtest import save_prediction_snapshot
except Exception:
    # Backtesting is optional for live runs; keep the prediction pipeline usable
    # even if a local backtest dependency/import is temporarily broken.
    save_prediction_snapshot = None


YEAR = 2026
TARGET_EVENT: str | int = "latest"
TARGET_SESSION = "Q"

N_BASELINE_RACES = 5
N_SIMS = 50000
DEFAULT_OVERTAKING_DIFFICULTY = 0.55
SAVE_RAW_RESULTS = True
HISTORICAL_STRATEGY_LOOKBACK_YEARS = 5


def _ensure_output_dirs() -> None:
    folders = [
        "outputs",
        "outputs/report",
        "outputs/strategy",
        "outputs/tyres",
        "outputs/lap_details",
        "outputs/history",
        "outputs/debug",
        "outputs/backtest",
    ]

    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None

    return float(number)


def _fmt_percent(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.1%}"


def _fmt_number(value: Any, decimals: int = 2) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.{decimals}f}"


def _fmt_weather_value(value: Any, decimals: int = 1, suffix: str = "") -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.{decimals}f}{suffix}"


def _fmt_grid_position(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"P{int(round(number))}"


def _fmt_price(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.1f}"


def _fmt_xppm(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.2f}"


def _safe_read_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()

    file_path = Path(path)

    if not file_path.exists():
        return pd.DataFrame()

    if file_path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        return pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:
        print(f"Could not read CSV {path}: {exc}")
        return pd.DataFrame()


def _get_lap_detail_path(lap_detail_files: dict[str, str]) -> str | None:
    # Support older/newer lap export key names so downstream tyre logic can run
    # across partial refactors without requiring every module to change at once.
    candidates = [
        "lap_details",
        "weekend_lap_details",
        "details",
    ]

    for key in candidates:
        if key in lap_detail_files:
            return lap_detail_files[key]

    fallback = Path("outputs/lap_details/weekend_lap_details.csv")

    if fallback.exists():
        # Reuse the latest generated lap file when this run skipped export; this
        # keeps report-only reruns possible but can be stale if the target event changed.
        return str(fallback)

    return None


def _get_long_run_summary_path(lap_detail_files: dict[str, str]) -> str | None:
    # Keep strategy generation tolerant of historical lap-detail return shapes.
    candidates = [
        "long_run_summary",
        "practice_long_run_summary",
    ]

    for key in candidates:
        if key in lap_detail_files:
            return lap_detail_files[key]

    fallback = Path("outputs/lap_details/practice_long_run_summary.csv")

    if fallback.exists():
        return str(fallback)

    return None


def _detect_sprint_weekend(lap_detail_files: dict[str, str]) -> bool:
    lap_details_path = _get_lap_detail_path(lap_detail_files)
    laps = _safe_read_csv(lap_details_path)

    if laps.empty or "Session" not in laps.columns:
        return False

    has_sprint_session = laps["Session"].astype(str).isin(["SQ", "S"]).any()

    return bool(has_sprint_session)


def _build_baseline_features(
    recent_races: list[tuple[Any, dict]],
) -> pd.DataFrame:
    baseline_frames: list[pd.DataFrame] = []

    for baseline_age, item in enumerate(recent_races):
        try:
            race_session, race_metadata = item
        except ValueError:
            print(f"Skipping unexpected recent race item: {item}")
            continue

        event_name = race_metadata.get("event", "Unknown")
        round_number = race_metadata.get("round", "Unknown")

        print(f"- baseline race: Round {round_number} {event_name}")

        try:
            race_features = build_driver_features(race_session.laps)
        except Exception as exc:
            print(f"  skipped: could not build features: {exc}")
            continue

        if race_features.empty:
            print("  skipped: no feature rows")
            continue

        race_features["source_year"] = race_metadata.get("year")
        race_features["source_event"] = race_metadata.get("event")
        race_features["source_round"] = race_metadata.get("round")
        race_features["baseline_age"] = baseline_age

        baseline_frames.append(race_features)

    if not baseline_frames:
        return pd.DataFrame()

    return pd.concat(baseline_frames, ignore_index=True)


def build_tyre_csv_outputs(
    lap_detail_files: dict[str, str],
    sprint_weekend: bool,
) -> dict[str, str]:
    output_files: dict[str, str] = {}

    lap_details_path = _get_lap_detail_path(lap_detail_files)
    lap_details = _safe_read_csv(lap_details_path)

    if lap_details.empty:
        print("Tyre CSV outputs skipped: no lap detail data available.")
        return output_files

    print("Building estimated tyre usage CSVs...")

    try:
        set_ledger, inventory = infer_tyre_usage(
            lap_details,
            sprint_weekend=sprint_weekend,
        )
    except TypeError:
        set_ledger, inventory = infer_tyre_usage(lap_details)

    Path("outputs/tyres").mkdir(parents=True, exist_ok=True)

    ledger_path = "outputs/tyres/tyre_set_ledger_estimated.csv"
    inventory_path = "outputs/tyres/tyre_inventory_estimated.csv"

    set_ledger.to_csv(ledger_path, index=False)
    inventory.to_csv(inventory_path, index=False)

    output_files["tyre_set_ledger"] = ledger_path
    output_files["tyre_inventory"] = inventory_path

    print(f"- tyre_set_ledger: {ledger_path}")
    print(f"- tyre_inventory: {inventory_path}")

    return output_files


def _call_predict_tyre_strategies(
    summary: pd.DataFrame,
    tyre_inventory: pd.DataFrame,
    long_run_summary: pd.DataFrame,
    weather_summary: dict,
    track_profile: dict,
) -> pd.DataFrame:
    # Strategy module signatures have changed during development; try the richer
    # weather/track-aware call first, then fall back to older call shapes.
    try:
        return predict_tyre_strategies(
            summary=summary,
            tyre_inventory=tyre_inventory,
            long_run_summary=long_run_summary,
            weather_summary=weather_summary,
            track_profile=track_profile,
        )
    except TypeError:
        pass

    try:
        return predict_tyre_strategies(
            summary,
            tyre_inventory,
            long_run_summary,
            weather_summary,
            track_profile,
        )
    except TypeError:
        pass

    try:
        return predict_tyre_strategies(
            summary=summary,
            tyre_inventory=tyre_inventory,
            long_run_summary=long_run_summary,
        )
    except TypeError:
        pass

    return predict_tyre_strategies(summary, tyre_inventory, long_run_summary)


def build_clean_strategy_outputs(
    summary: pd.DataFrame,
    tyre_inventory_path: str | None,
    long_run_summary_path: str | None,
    weather_summary: dict,
    track_profile: dict,
    session: Any | None = None,
) -> dict[str, str]:
    output_files: dict[str, str] = {}

    tyre_inventory = _safe_read_csv(tyre_inventory_path)
    long_run_summary = _safe_read_csv(long_run_summary_path)

    if summary.empty:
        print("Strategy outputs skipped: summary is empty.")
        return output_files

    print("Building predicted tyre strategy outputs...")

    try:
        strategies = _call_predict_tyre_strategies(
            summary=summary,
            tyre_inventory=tyre_inventory,
            long_run_summary=long_run_summary,
            weather_summary=weather_summary,
            track_profile=track_profile,
        )
    except Exception as exc:
        print(f"Strategy outputs skipped: {exc}")
        return output_files

    if strategies.empty:
        print("Strategy outputs skipped: no strategy rows generated.")
        return output_files

    Path("outputs/strategy").mkdir(parents=True, exist_ok=True)

    strategy_csv = "outputs/strategy/predicted_tyre_strategy.csv"
    strategy_image = "outputs/strategy/predicted_tyre_strategy.png"

    strategies.to_csv(strategy_csv, index=False)

    try:
        make_strategy_table_image(
            strategies,
            output_path=strategy_image,
            session=session,
        )
    except TypeError:
        # Older chart builders do not accept FastF1 session context for team colours.
        make_strategy_table_image(
            strategies,
            output_path=strategy_image,
        )

    output_files["predicted_tyre_strategy_csv"] = strategy_csv
    output_files["predicted_tyre_strategy_chart"] = strategy_image

    print(f"- predicted_tyre_strategy_csv: {strategy_csv}")
    print(f"- predicted_tyre_strategy_chart: {strategy_image}")

    return output_files


def build_model_commentary(
    summary: pd.DataFrame,
    model_features: pd.DataFrame,
    metadata: dict,
    weather_summary: dict,
    track_profile: dict,
) -> list[str]:
    lines: list[str] = []

    if summary.empty:
        return ["No simulation summary available."]

    top = summary.sort_values("avg_fantasy_points", ascending=False).head(5)
    winner = summary.sort_values("win_chance", ascending=False).iloc[0]
    podium = summary.sort_values("podium_chance", ascending=False).head(3)

    lines.append(
        f"Model read: {metadata.get('year')} {metadata.get('event')} "
        f"using {metadata.get('session')} data."
    )

    lines.append(
        "Weather modifiers: "
        f"chaos {float(weather_summary.get('chaos_factor', 1.0)):.2f}x, "
        f"strategy {float(weather_summary.get('strategy_factor', 1.0)):.2f}x, "
        f"DNF {float(weather_summary.get('dnf_factor', 1.0)):.2f}x, "
        f"tyre deg {float(weather_summary.get('degradation_factor', 1.0)):.2f}x."
    )

    lines.append(
        "Track profile: "
        f"{track_profile.get('event', metadata.get('event'))}; "
        f"overtaking difficulty "
        f"{float(track_profile.get('overtaking_difficulty', DEFAULT_OVERTAKING_DIFFICULTY)):.2f}."
    )

    lines.append(
        f"Highest win chance: {winner['Driver']} "
        f"({_fmt_percent(winner.get('win_chance'))})."
    )

    podium_text = ", ".join(
        f"{row['Driver']} {_fmt_percent(row.get('podium_chance'))}"
        for _, row in podium.iterrows()
    )
    lines.append(f"Strongest podium profile: {podium_text}.")

    value_candidates = pd.DataFrame()

    if "fantasy_xppm" in summary.columns:
        value_candidates = summary[summary["fantasy_xppm"].notna()].copy()

    if not value_candidates.empty:
        best_value = value_candidates.sort_values(
            ["fantasy_xppm", "avg_fantasy_points"],
            ascending=[False, False],
        ).iloc[0]

        lines.append(
            f"Best value pick: {best_value['Driver']} "
            f"at xPPM {_fmt_xppm(best_value.get('fantasy_xppm'))}."
        )

    top_text = ", ".join(
        f"{row['Driver']} {_fmt_number(row.get('avg_fantasy_points'), 2)}"
        for _, row in top.iterrows()
    )
    lines.append(f"Top fantasy projections: {top_text}.")

    if "grid_source" in summary.columns:
        grid_source_counts = summary["grid_source"].astype(str).value_counts()
        grid_source_text = ", ".join(
            f"{source}: {count}"
            for source, count in grid_source_counts.items()
        )
        lines.append(f"Grid source mix: {grid_source_text}.")

    if "current_pace_outlier_flag" in model_features.columns:
        outliers = model_features[
            model_features["current_pace_outlier_flag"].astype(bool)
        ]

        if not outliers.empty:
            outlier_drivers = ", ".join(outliers["Driver"].astype(str).tolist())
            lines.append(
                "Practice outlier handling active for: "
                f"{outlier_drivers}."
            )

    return lines


def save_model_commentary(lines: list[str]) -> str:
    Path("outputs/report").mkdir(parents=True, exist_ok=True)

    output_path = "outputs/report/model_commentary.txt"

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")

    return output_path


def build_discord_summary(
    summary: pd.DataFrame,
    metadata: dict,
    weather_summary: dict,
    track_profile: dict,
    commentary_lines: list[str] | None = None,
) -> str:
    lines: list[str] = []

    lines.append(
        f"🏁 **F1 Fantasy Simulation — {metadata.get('year')} {metadata.get('event')}**"
    )
    lines.append(f"Session used: **{metadata.get('session')}**")

    lines.append(
        "Weather: "
        f"Air {_fmt_weather_value(weather_summary.get('air_temp_avg'), 1, '°C')} | "
        f"Track {_fmt_weather_value(weather_summary.get('track_temp_avg'), 1, '°C')} | "
        f"Rain {'Yes' if weather_summary.get('rainfall_flag') else 'No'}"
    )

    lines.append(
        "Modifiers: "
        f"Chaos {float(weather_summary.get('chaos_factor', 1.0)):.2f}x | "
        f"Strategy {float(weather_summary.get('strategy_factor', 1.0)):.2f}x | "
        f"DNF {float(weather_summary.get('dnf_factor', 1.0)):.2f}x | "
        f"Tyre Deg {float(weather_summary.get('degradation_factor', 1.0)):.2f}x"
    )

    lines.append(
        "Track: "
        f"{track_profile.get('event', metadata.get('event'))} | "
        f"Overtaking difficulty "
        f"{float(track_profile.get('overtaking_difficulty', DEFAULT_OVERTAKING_DIFFICULTY)):.2f}"
    )

    lines.append("")

    if not summary.empty:
        top_fantasy = summary.sort_values(
            "avg_fantasy_points",
            ascending=False,
        ).head(5)

        lines.append("**Top fantasy projections**")

        for _, row in top_fantasy.iterrows():
            lines.append(
                f"- **{row['Driver']}** "
                f"Grid {_fmt_grid_position(row.get('grid_position', row.get('avg_grid')))} | "
                f"xFant {_fmt_number(row.get('avg_fantasy_points'), 2)} | "
                f"xRace {_fmt_number(row.get('avg_points'), 2)} | "
                f"Win {_fmt_percent(row.get('win_chance'))} | "
                f"Pod {_fmt_percent(row.get('podium_chance'))} | "
                f"Price {_fmt_price(row.get('fantasy_price'))} | "
                f"xPPM {_fmt_xppm(row.get('fantasy_xppm'))}"
            )

        lines.append("")

        top_winners = summary.sort_values("win_chance", ascending=False).head(5)

        lines.append("**Highest win chance**")

        for _, row in top_winners.iterrows():
            lines.append(
                f"- **{row['Driver']}** "
                f"{_fmt_percent(row.get('win_chance'))} "
                f"(avg finish {_fmt_number(row.get('avg_finish'), 2)})"
            )

    if commentary_lines:
        lines.append("")
        lines.append("**Model notes**")

        for note in commentary_lines[:6]:
            lines.append(f"- {note}")

    return "\n".join(lines)


def _call_build_report_outputs(
    summary: pd.DataFrame,
    metadata: dict,
    weather_summary: dict,
    track_profile: dict,
    overtaking_difficulty: float,
    strategy_csv_path: str | None,
    current_session: Any | None,
) -> dict[str, str]:
    # Prefer session-aware report colours when available, but preserve compatibility
    # with older report_card implementations that only accept static inputs.
    try:
        return build_report_outputs(
            summary=summary,
            metadata=metadata,
            weather_summary=weather_summary,
            track_profile=track_profile,
            overtaking_difficulty=overtaking_difficulty,
            strategy_csv_path=strategy_csv_path,
            session=current_session,
        )
    except TypeError as exc:
        print(
            "build_report_outputs does not accept session yet. "
            "Falling back without session. Update src/report_card.py for FastF1 team colours."
        )
        print(f"- {exc}")

        return build_report_outputs(
            summary=summary,
            metadata=metadata,
            weather_summary=weather_summary,
            track_profile=track_profile,
            overtaking_difficulty=overtaking_difficulty,
            strategy_csv_path=strategy_csv_path,
        )


def _post_to_discord_safe(
    message: str,
    files: list[str],
) -> None:
    # Discord helper signatures have varied; this wrapper keeps the main pipeline
    # independent from minor posting API changes.
    try:
        post_to_discord(content=message, files=files)
        return
    except TypeError:
        pass

    try:
        post_to_discord(message=message, files=files)
        return
    except TypeError:
        pass

    post_to_discord(message, files)


def main() -> None:
    load_dotenv()
    _ensure_output_dirs()

    enable_fastf1_cache()

    print("=" * 80)
    print("F1 race / fantasy simulation")
    print("=" * 80)

    print()
    print("Loading target session...")

    if str(TARGET_EVENT).lower() == "latest":
        current_session, metadata = load_latest_predictor_session(YEAR)
    else:
        current_session, metadata = load_session(
            YEAR,
            TARGET_EVENT,
            TARGET_SESSION,
        )

    print(
        f"- session: {metadata.get('year')} "
        f"{metadata.get('event')} "
        f"{metadata.get('session')}"
    )
    print(f"- round: {metadata.get('round')}")

    print()
    print("Exporting weekend lap details...")

    try:
        lap_detail_files = export_weekend_lap_details(
            year=metadata["year"],
            event_identifier=metadata["event"],
            sessions=["FP1", "FP2", "FP3", "Q", "SQ", "S"],
        )
    except TypeError:
        lap_detail_files = export_weekend_lap_details(
            metadata["year"],
            metadata["event"],
        )
    except Exception as exc:
        print(f"Lap detail export skipped: {exc}")
        lap_detail_files = {}

    for name, path in lap_detail_files.items():
        print(f"- {name}: {path}")

    sprint_weekend = _detect_sprint_weekend(lap_detail_files)
    print(f"- sprint weekend detected: {sprint_weekend}")

    tyre_output_files = build_tyre_csv_outputs(
        lap_detail_files=lap_detail_files,
        sprint_weekend=sprint_weekend,
    )

    print()
    print("Loading track profile...")

    track_profile = load_track_profile(metadata["event"])
    overtaking_difficulty = float(
        track_profile.get(
            "overtaking_difficulty",
            DEFAULT_OVERTAKING_DIFFICULTY,
        )
    )

    print(f"- track profile: {track_profile.get('event', metadata['event'])}")
    print(f"- overtaking difficulty: {overtaking_difficulty:.2f}")

    print()
    print("Summarising weather...")

    weather_summary = summarize_weather(current_session)

    print(
        "- weather: "
        f"air {_fmt_weather_value(weather_summary.get('air_temp_avg'), 1, '°C')}, "
        f"track {_fmt_weather_value(weather_summary.get('track_temp_avg'), 1, '°C')}, "
        f"rain {'yes' if weather_summary.get('rainfall_flag') else 'no'}"
    )

    print()
    print("Building current session driver features...")

    current_features = build_driver_features(current_session.laps)
    current_features.to_csv("outputs/current_session_features.csv", index=False)

    print(f"- current feature rows: {len(current_features)}")
    print("- saved: outputs/current_session_features.csv")

    print()
    print("Loading recent race baseline sessions...")

    recent_races = load_recent_race_sessions(
        target_year=metadata["year"],
        target_round=metadata["round"],
        count=N_BASELINE_RACES,
    )

    print(f"- recent races loaded: {len(recent_races)}")

    baseline_features = _build_baseline_features(recent_races)
    baseline_features.to_csv("outputs/baseline_race_features.csv", index=False)

    print(f"- baseline feature rows: {len(baseline_features)}")
    print("- saved: outputs/baseline_race_features.csv")

    print()
    print("Blending model features...")

    model_features = build_model_features(
        current_features=current_features,
        baseline_features=baseline_features,
        current_session_type=metadata["session"],
    )

    print("Adding grid features...")

    try:
        model_features = build_grid_features(
            model_features=model_features,
            current_features=current_features,
            current_session_type=metadata["session"],
            current_session=current_session,
        )
    except TypeError:
        model_features = build_grid_features(
            model_features,
            current_features,
            metadata["session"],
        )

    print("Adding separated performance profile...")

    # Split pace into quali/race/strategy/reliability signals before simulation
    # so a single practice pace number does not drive every race outcome dimension.
    model_features = add_performance_profile(
        model_features=model_features,
        current_features=current_features,
        baseline_features=baseline_features,
        current_session_type=metadata["session"],
        metadata=metadata,
    )

    model_features.to_csv("outputs/driver_model_features.csv", index=False)

    print(f"- model feature rows: {len(model_features)}")
    print("- saved: outputs/driver_model_features.csv")

    print()
    print("Ensuring fantasy price template...")

    try:
        price_template_path = ensure_price_template(model_features)
        print(f"- price template: {price_template_path}")
    except Exception as exc:
        print(f"Fantasy price template warning: {exc}")

    print()
    print(f"Running Monte Carlo simulation: {N_SIMS:,} races...")

    race_summary, position_matrix, results = simulate_races(
        features=model_features,
        n_sims=N_SIMS,
        seed=42,
        overtaking_difficulty=overtaking_difficulty,
        weather_modifiers=weather_summary,
    )

    print("- simulation complete")

    print()
    print("Calculating fantasy summary...")

    summary, fantasy_results = calculate_fantasy_summary(
        results=results,
        race_summary=race_summary,
    )

    summary.to_csv("outputs/simulation_summary.csv", index=False)
    position_matrix.to_csv("outputs/position_matrix.csv", index=False)

    if SAVE_RAW_RESULTS:
        results.to_csv("outputs/raw_simulation_results.csv", index=False)
        fantasy_results.to_csv("outputs/raw_fantasy_results.csv", index=False)

    print("- saved: outputs/simulation_summary.csv")
    print("- saved: outputs/position_matrix.csv")

    if SAVE_RAW_RESULTS:
        print("- saved: outputs/raw_simulation_results.csv")
        print("- saved: outputs/raw_fantasy_results.csv")

    if save_prediction_snapshot is not None:
        print()
        print("Saving prediction snapshot for future backtesting...")

        try:
            # Snapshot the fantasy-enriched summary, not the raw race summary, so
            # later backtests compare the exact posted prediction set.
            prediction_snapshot_path = save_prediction_snapshot(
                race_summary=summary,
                metadata=metadata,
                weather_summary=weather_summary,
                track_profile=track_profile,
                model_parameters={
                    "n_sims": N_SIMS,
                    "n_baseline_races": N_BASELINE_RACES,
                    "overtaking_difficulty": overtaking_difficulty,
                    "target_event": TARGET_EVENT,
                    "target_session": TARGET_SESSION,
                    "save_raw_results": SAVE_RAW_RESULTS,
                },
            )

            print(f"- prediction snapshot: {prediction_snapshot_path}")
        except Exception as exc:
            print(f"Prediction snapshot skipped: {exc}")

    print()
    print("Building strategy outputs...")

    strategy_output_files = build_clean_strategy_outputs(
        summary=summary,
        tyre_inventory_path=tyre_output_files.get("tyre_inventory"),
        long_run_summary_path=_get_long_run_summary_path(lap_detail_files),
        weather_summary=weather_summary,
        track_profile=track_profile,
        session=current_session,
    )

    historical_strategy_files: dict[str, str] = {}

    if "predicted_tyre_strategy_csv" in strategy_output_files:
        print()
        print("Applying historical strategy adjustment...")

        try:
            historical_strategy_files = apply_historical_strategy_adjustment_to_outputs(
                strategy_csv_path=strategy_output_files["predicted_tyre_strategy_csv"],
                current_year=metadata["year"],
                event_name=metadata["event"],
                lookback_years=HISTORICAL_STRATEGY_LOOKBACK_YEARS,
                session=current_session,
            )
        except TypeError:
            historical_strategy_files = apply_historical_strategy_adjustment_to_outputs(
                strategy_csv_path=strategy_output_files["predicted_tyre_strategy_csv"],
                current_year=metadata["year"],
                event_name=metadata["event"],
                lookback_years=HISTORICAL_STRATEGY_LOOKBACK_YEARS,
            )
        except Exception as exc:
            print(f"Historical strategy adjustment skipped: {exc}")

        for name, path in historical_strategy_files.items():
            print(f"- {name}: {path}")

    print()
    print("Building model commentary...")

    commentary_lines = build_model_commentary(
        summary=summary,
        model_features=model_features,
        metadata=metadata,
        weather_summary=weather_summary,
        track_profile=track_profile,
    )

    commentary_path = save_model_commentary(commentary_lines)

    print(f"- commentary: {commentary_path}")

    print()
    print("Building polished report images...")

    report_output_files = _call_build_report_outputs(
        summary=summary,
        metadata=metadata,
        weather_summary=weather_summary,
        track_profile=track_profile,
        overtaking_difficulty=overtaking_difficulty,
        strategy_csv_path=strategy_output_files.get("predicted_tyre_strategy_csv"),
        current_session=current_session,
    )

    for name, path in report_output_files.items():
        print(f"- {name}: {path}")

    print()
    print("Creating clean Discord chart bundle...")

    files: list[str] = []

    print("Creating simulated race time distribution chart...")

    sim_race_time_chart: str | None = None

    try:
        # The chart can derive race-time curves from explicit race-time columns,
        # performance scores, or finishing positions depending on simulator output.
        sim_race_time_chart = make_simulated_race_time_chart(
            results=results,
            session=current_session,
            metadata=metadata,
        )

        print(f"- simulated_race_times: {sim_race_time_chart}")
    except Exception as exc:
        print(f"Simulated race time chart skipped: {exc}")

    for key in ["dashboard", "tyre_timeline", "risk_reward"]:
        if key in report_output_files:
            files.append(report_output_files[key])

    if sim_race_time_chart:
        files.append(sim_race_time_chart)

    try:
        fantasy_points_chart = make_fantasy_points_chart(summary)
        files.append(fantasy_points_chart)
        print(f"- fantasy_points: {fantasy_points_chart}")
    except Exception as exc:
        print(f"Fantasy points chart skipped: {exc}")

    if "fantasy_xppm" in summary.columns and summary["fantasy_xppm"].notna().any():
        try:
            fantasy_value_chart = make_fantasy_value_chart(summary)
            files.append(fantasy_value_chart)
            print(f"- fantasy_value: {fantasy_value_chart}")
        except Exception as exc:
            print(f"Fantasy value chart skipped: {exc}")
    else:
        print("Fantasy value chart skipped: no fantasy_xppm values available.")

    try:
        probability_chart = make_probability_chart(summary)
        files.append(probability_chart)
        print(f"- probability_chart: {probability_chart}")
    except Exception as exc:
        print(f"Probability chart skipped: {exc}")

    try:
        text_report_image = make_text_report_image(
            summary,
            position_matrix,
            metadata,
            weather_summary,
        )
        files.append(text_report_image)
        print(f"- text_report: {text_report_image}")
    except Exception as exc:
        print(f"Text report image skipped: {exc}")

    if "predicted_tyre_strategy_chart" in strategy_output_files:
        strategy_chart = strategy_output_files["predicted_tyre_strategy_chart"]

        if strategy_chart not in files:
            files.append(strategy_chart)

    print()
    print("Final image bundle:")

    for file_path in files:
        print(f"- {file_path}")

    summary_text = build_discord_summary(
        summary=summary,
        metadata=metadata,
        weather_summary=weather_summary,
        track_profile=track_profile,
        commentary_lines=commentary_lines,
    )

    post_to_discord_flag = os.getenv("POST_TO_DISCORD", "false").strip().lower()

    if post_to_discord_flag in {"1", "true", "yes", "y"}:
        print()
        print("Posting to Discord...")

        try:
            _post_to_discord_safe(summary_text, files)
            print("- Discord post complete")
        except Exception as exc:
            print(f"Discord post failed: {exc}")
    else:
        print()
        print("POST_TO_DISCORD is false, so Discord posting was skipped.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()