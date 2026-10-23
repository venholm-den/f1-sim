from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

import os
import json
import subprocess
import sys
import threading
import time
import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Any

import pandas as pd

from src.app_services.config_service import (
    DEFAULT_CONFIG_PATH,
    PortableRunSettings,
    build_run_config,
    load_json_config,
    settings_from_config,
)
from src.app_services.data_health import validate_data_sources
from src.app_services.model_signals import load_model_signals
from src.app_services.output_index import list_core_outputs, read_output_table
from src.track import load_track_profile
from src.app_services.simulation_jobs import SimulationJobs
from src.app_services.dashboard_health import output_context, saved_data_health
from src.app_services.workbench import model_reference, saved_details


SESSION_OPTIONS = ["PRE", "FP1", "FP2", "FP3", "SQ", "S", "Q", "R"]
SESSION_PRIORITY = SESSION_OPTIONS[1:]
SESSION_NAME_TO_CODE = {
    "PRACTICE 1": "FP1",
    "FREE PRACTICE 1": "FP1",
    "PRACTICE 2": "FP2",
    "FREE PRACTICE 2": "FP2",
    "PRACTICE 3": "FP3",
    "FREE PRACTICE 3": "FP3",
    "QUALIFYING": "Q",
    "SPRINT QUALIFYING": "SQ",
    "SPRINT SHOOTOUT": "SQ",
    "SPRINT": "S",
    "RACE": "R",
}
TRACK_LAYOUT_CACHE: dict[tuple[int, str, str], dict[str, Any]] = {}
PRE_SESSIONS = {"PRE"}
PRACTICE_SESSIONS = {"FP1", "FP2", "FP3"}
QUALI_SESSIONS = {"Q", "SQ"}
RACE_SESSIONS = {"R", "S"}


def project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path.cwd()
    return Path(__file__).resolve().parents[1]


def season_options(default_year: int) -> list[int]:
    current_year = pd.Timestamp.now().year
    first_year = min(2018, default_year)
    final_year = max(current_year + 1, default_year)
    return list(range(final_year, first_year - 1, -1))


def table_payload(frame: pd.DataFrame, max_rows: int = 100) -> dict[str, Any]:
    if frame.empty:
        return {"columns": [], "rows": []}

    preview = frame.head(max_rows).copy()
    preview = preview.where(pd.notna(preview), "")
    return {
        "columns": [str(column) for column in preview.columns],
        "rows": preview.astype(str).to_dict(orient="records"),
    }


def sorted_view(
    frame: pd.DataFrame,
    columns: list[str],
    sort_by: str | None = None,
    ascending: bool = False,
    max_rows: int = 30,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    selected = [column for column in columns if column in frame.columns]
    output = frame[selected].copy() if selected else frame.copy()

    if sort_by and sort_by in output.columns:
        output[sort_by] = pd.to_numeric(output[sort_by], errors="coerce")
        output = output.sort_values(sort_by, ascending=ascending)

    return output.head(max_rows)


def chart_points(
    frame: pd.DataFrame,
    label_column: str,
    value_column: str,
    multiplier: float = 1.0,
    max_points: int = 12,
) -> list[dict[str, float | str]]:
    if frame.empty or label_column not in frame.columns or value_column not in frame.columns:
        return []

    values = frame[[label_column, value_column]].copy()
    values[value_column] = pd.to_numeric(values[value_column], errors="coerce") * multiplier
    values = values.dropna(subset=[value_column]).sort_values(value_column, ascending=False).head(max_points)

    return [
        {"label": str(row[label_column]), "value": float(row[value_column])}
        for _, row in values.iterrows()
    ]


def _track_profile_event_names(track_profiles_path: str | Path | None) -> list[str]:
    if not track_profiles_path:
        return []

    try:
        profiles = pd.read_csv(track_profiles_path)
    except Exception:
        return []

    if "Event" not in profiles.columns:
        return []

    return [
        str(name)
        for name in profiles["Event"].dropna().astype(str).drop_duplicates().tolist()
        if str(name).strip()
    ]


def available_event_names(year: int, track_profiles_path: str | Path | None = None) -> list[str]:
    schedule = _event_schedule(year)

    if schedule.empty or "EventName" not in schedule.columns:
        return _track_profile_event_names(track_profiles_path)

    return [str(name) for name in schedule["EventName"].dropna().unique().tolist()]


def _event_schedule(year: int) -> pd.DataFrame:
    try:
        import fastf1

        cache = project_root() / "data" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        enable_cache(str(cache))
        schedule = fastf1.get_event_schedule(year).copy()
    except Exception:
        return pd.DataFrame()

    if schedule.empty:
        return pd.DataFrame()

    if "EventDate" in schedule.columns:
        schedule["EventDateParsed"] = pd.to_datetime(
            schedule["EventDate"],
            errors="coerce",
            utc=True,
        ).dt.tz_convert(None)

    if "RoundNumber" in schedule.columns:
        schedule = schedule[
            pd.to_numeric(schedule["RoundNumber"], errors="coerce").fillna(0).gt(0)
        ].copy()

    return schedule


def _event_row(schedule: pd.DataFrame, event: str) -> pd.Series | None:
    if schedule.empty or "EventName" not in schedule.columns:
        return None

    event_text = str(event or "latest").strip()

    if event_text.lower() == "latest":
        if "EventDateParsed" not in schedule.columns:
            return schedule.iloc[-1]

        now = pd.Timestamp.now(tz="UTC").tz_convert(None)
        upcoming = schedule[
            schedule["EventDateParsed"].notna()
            & (schedule["EventDateParsed"] >= now - pd.Timedelta(days=2))
        ].copy()

        if not upcoming.empty:
            return upcoming.sort_values("EventDateParsed", ascending=True).iloc[0]

        past = schedule[schedule["EventDateParsed"].notna()].copy()

        if not past.empty:
            return past.sort_values("EventDateParsed", ascending=False).iloc[0]

        return schedule.iloc[-1]

    event_key = event_text.lower()
    event_match = schedule["EventName"].astype(str).str.strip().str.lower().eq(event_key)

    if "OfficialEventName" in schedule.columns:
        official_match = (
            schedule["OfficialEventName"]
            .astype(str)
            .str.lower()
            .str.contains(event_key, regex=False, na=False)
        )
    else:
        official_match = pd.Series(False, index=schedule.index)

    matches = schedule[event_match | official_match]

    if matches.empty:
        return None

    return matches.iloc[0]


def _session_code(session_name: Any) -> str | None:
    name = str(session_name or "").strip().upper()

    if not name:
        return None

    return SESSION_NAME_TO_CODE.get(name)


def _session_date(value: Any) -> pd.Timestamp | None:
    date = pd.to_datetime(value, errors="coerce", utc=True)

    if pd.isna(date):
        return None

    return date.tz_convert(None)


def available_sessions_for_event(
    year: int,
    event: str,
    now: pd.Timestamp | None = None,
) -> list[str]:
    event_text = str(event or "latest").strip()
    schedule = _event_schedule(year)
    row = _event_row(schedule, event_text)

    if row is None:
        if event_text.lower() == "latest":
            return ["PRE"]
        return ['PRE', *SESSION_PRIORITY]

    scheduled: list[str] = []

    for index in range(1, 6):
        session_code = _session_code(row.get(f"Session{index}"))

        if session_code is None:
            continue

        if session_code not in scheduled:
            scheduled.append(session_code)

    if event_text.lower() != "latest":
        sessions = scheduled
        return ['PRE', *sessions] if sessions else SESSION_OPTIONS.copy()

    now = now or pd.Timestamp.now(tz="UTC").tz_convert(None)
    available: set[str] = set()

    for index in range(1, 6):
        session_code = _session_code(row.get(f"Session{index}"))

        if session_code is None:
            continue

        session_date = _session_date(row.get(f"Session{index}Date"))

        if session_date is not None and session_date <= now:
            available.add(session_code)

    if not available:
        return ["PRE"]

    return ['PRE', *[session for session in scheduled if session in available]]


def setup_options_payload(
    year: int,
    event: str,
    track_profiles_path: str,
) -> dict[str, Any]:
    schedule = _event_schedule(year)
    row = _event_row(schedule, event)
    event_name = str(row.get("EventName", event)) if row is not None else str(event)
    from src.venues import venue_for_context
    context = {'year': year, 'event': event_name}
    context['venue'] = venue_for_context(context, event_data=row if row is not None else {})
    track_profile = load_track_profile(event_name, path=track_profiles_path, metadata=context)

    return {
        "sessions": available_sessions_for_event(year, event),
        "trackProfile": track_profile,
    }


def settings_to_dict(settings: PortableRunSettings) -> dict[str, Any]:
    return {
        "year": settings.year,
        "event": settings.event,
        "session": settings.session,
        "n_sims": settings.n_sims,
        "random_seed": settings.random_seed,
        "n_baseline_races": settings.n_baseline_races,
        "historical_strategy_lookback_years": settings.historical_strategy_lookback_years,
        "default_overtaking_difficulty": settings.default_overtaking_difficulty,
        "output_dir": settings.output_dir,
        "save_prediction_snapshot": settings.save_prediction_snapshot,
        "save_report_images": settings.save_report_images,
        "save_raw_results": settings.save_raw_results,
        "post_to_discord": settings.post_to_discord,
        "use_weather_forecast": settings.use_weather_forecast,
        "use_race_control_context": settings.use_race_control_context,
        "use_track_red_flag_base_chance": settings.use_track_red_flag_base_chance,
        "use_historical_model_calibration": settings.use_historical_model_calibration,
        "historical_finish_weight": settings.historical_finish_weight,
        "historical_dnf_weight": settings.historical_dnf_weight,
    }


def settings_from_payload(payload: dict[str, Any], defaults: PortableRunSettings) -> PortableRunSettings:
    return PortableRunSettings(
        year=int(payload.get("year", defaults.year)),
        event=str(payload.get("event", defaults.event)).strip() or "latest",
        session=str(payload.get("session", defaults.session)).strip() or "Q",
        n_sims=int(payload.get("n_sims", defaults.n_sims)),
        random_seed=int(payload.get("random_seed", defaults.random_seed)),
        n_baseline_races=int(payload.get("n_baseline_races", defaults.n_baseline_races)),
        historical_strategy_lookback_years=int(
            payload.get("historical_strategy_lookback_years", defaults.historical_strategy_lookback_years)
        ),
        default_overtaking_difficulty=float(
            payload.get("default_overtaking_difficulty", defaults.default_overtaking_difficulty)
        ),
        output_dir=str(payload.get("output_dir", defaults.output_dir)).strip() or "outputs",
        save_prediction_snapshot=bool(payload.get("save_prediction_snapshot", defaults.save_prediction_snapshot)),
        save_report_images=bool(payload.get("save_report_images", defaults.save_report_images)),
        save_raw_results=bool(payload.get("save_raw_results", defaults.save_raw_results)),
        post_to_discord=bool(payload.get("post_to_discord", defaults.post_to_discord)),
        use_weather_forecast=bool(payload.get("use_weather_forecast", defaults.use_weather_forecast)),
        use_race_control_context=bool(payload.get("use_race_control_context", defaults.use_race_control_context)),
        use_track_red_flag_base_chance=bool(
            payload.get("use_track_red_flag_base_chance", defaults.use_track_red_flag_base_chance)
        ),
        use_historical_model_calibration=bool(
            payload.get(
                "use_historical_model_calibration",
                defaults.use_historical_model_calibration,
            )
        ),
        historical_finish_weight=float(
            payload.get("historical_finish_weight", defaults.historical_finish_weight)
        ),
        historical_dnf_weight=float(
            payload.get("historical_dnf_weight", defaults.historical_dnf_weight)
        ),
    )


def session_mode(session: str | None) -> str:
    code = str(session or "").upper()
    if code in PRE_SESSIONS:
        return "pre"
    if code in PRACTICE_SESSIONS:
        return "practice"
    if code in QUALI_SESSIONS:
        return "quali"
    if code in RACE_SESSIONS:
        return "race"
    return "race"


def _clean_push_laps(laps: pd.DataFrame) -> pd.DataFrame:
    if laps.empty:
        return laps

    if "CleanPushLap" not in laps.columns:
        return laps.copy()

    clean = laps["CleanPushLap"].astype(str).str.lower().isin(["true", "1"])
    return laps[clean].copy()


def _session_laps(laps: pd.DataFrame, session: str | None) -> pd.DataFrame:
    if laps.empty or not session or "Session" not in laps.columns:
        return laps.copy()

    code = str(session).upper()
    return laps[laps["Session"].astype(str).str.upper().eq(code)].copy()


def sector_times_table(laps: pd.DataFrame, sessions: set[str]) -> pd.DataFrame:
    if laps.empty or "Driver" not in laps.columns:
        return pd.DataFrame()

    scope = _clean_push_laps(laps)
    if "Session" in scope.columns:
        scope = scope[scope["Session"].astype(str).str.upper().isin(sessions)]

    rows: list[dict[str, Any]] = []
    base_columns = ["Driver", "Team", "Session", "LapNumber"]
    available_base = [column for column in base_columns if column in scope.columns]

    for label, column in [("S1", "Sector1Seconds"), ("S2", "Sector2Seconds"), ("S3", "Sector3Seconds")]:
        if column not in scope.columns:
            continue

        sector = scope[[*available_base, column]].copy()
        sector[column] = pd.to_numeric(sector[column], errors="coerce")
        sector = sector.dropna(subset=[column]).sort_values(column)

        if sector.empty:
            continue

        leader = sector.iloc[0]
        rows.append(
            {
                "Sector": label,
                "Driver": str(leader.get("Driver", "")),
                "Team": str(leader.get("Team", "")),
                "Session": str(leader.get("Session", "")),
                "Lap": "" if pd.isna(leader.get("LapNumber", "")) else str(leader.get("LapNumber", "")),
                "Best time": f"{float(leader[column]):.3f}s",
            }
        )

    return pd.DataFrame(rows)


def fastest_lap(output_dir: str | Path, session: str | None = None) -> dict[str, float | str]:
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=20_000)

    if laps.empty or "Driver" not in laps.columns or "LapTimeSeconds" not in laps.columns:
        return {}

    laps = _session_laps(_clean_push_laps(laps), session)
    lap_columns = [
        column
        for column in ["Driver", "Team", "Session", "LapNumber", "LapTimeSeconds"]
        if column in laps.columns
    ]
    values = laps[lap_columns].copy()
    values["LapTimeSeconds"] = pd.to_numeric(values["LapTimeSeconds"], errors="coerce")
    values = values.dropna(subset=["LapTimeSeconds"]).sort_values("LapTimeSeconds")

    if values.empty:
        return {}

    lap = values.iloc[0]
    return {
        "driver": str(lap.get("Driver", "")),
        "team": str(lap.get("Team", "")),
        "session": str(lap.get("Session", session or "")),
        "lap": "" if pd.isna(lap.get("LapNumber", "")) else str(lap.get("LapNumber", "")),
        "seconds": float(lap["LapTimeSeconds"]),
    }


def session_screen_payloads(output_dir: str | Path, summary: pd.DataFrame, strategy: pd.DataFrame) -> dict[str, Any]:
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=20_000)
    practice_summary = read_output_table(output_dir, "lap_details/practice_lap_summary.csv", max_rows=5_000)
    long_run_summary = read_output_table(output_dir, "lap_details/practice_long_run_summary.csv", max_rows=5_000)
    quali_summary = read_output_table(output_dir, "lap_details/quali_lap_summary.csv", max_rows=5_000)

    return {
        "practice": {
            "sectors": table_payload(sector_times_table(laps, PRACTICE_SESSIONS)),
            "pace": table_payload(
                sorted_view(
                    practice_summary,
                    [
                        "Session",
                        "Driver",
                        "Team",
                        "Compound",
                        "clean_laps",
                        "best_lap",
                        "median_lap",
                        "ideal_lap",
                        "avg_speed_trap",
                    ],
                    sort_by="best_lap",
                    ascending=True,
                    max_rows=30,
                )
            ),
            "longRun": table_payload(
                sorted_view(
                    long_run_summary,
                    [
                        "Session",
                        "Driver",
                        "Team",
                        "Compound",
                        "laps_in_run",
                        "run_start_lap",
                        "run_end_lap",
                        "avg_lap",
                        "median_lap",
                        "degradation_per_lap",
                    ],
                    sort_by="avg_lap",
                    ascending=True,
                    max_rows=30,
                )
            ),
        },
        "quali": {
            "sectors": table_payload(sector_times_table(laps, QUALI_SESSIONS)),
            "pace": table_payload(
                sorted_view(
                    quali_summary,
                    [
                        "Session",
                        "Driver",
                        "Team",
                        "quali_rank_from_laps",
                        "clean_laps",
                        "best_lap",
                        "gap_to_fastest",
                        "ideal_lap",
                        "ideal_gap_to_fastest",
                        "best_s1",
                        "best_s2",
                        "best_s3",
                    ],
                    sort_by="best_lap",
                    ascending=True,
                    max_rows=30,
                )
            ),
        },
        "race": {
            "summary": table_payload(
                sorted_view(
                    summary,
                    [
                        "Driver",
                        "Team",
                        "avg_finish",
                        "win_chance",
                        "podium_chance",
                        "dnf_chance",
                        "avg_points",
                    ],
                    sort_by="avg_finish",
                    ascending=True,
                    max_rows=30,
                )
            ),
            "strategy": table_payload(strategy),
        },
    }


def sector_leaders(output_dir: str | Path, session: str | None = None) -> dict[str, dict[str, float | str]]:
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=20_000)

    if laps.empty:
        return {}

    laps = _session_laps(_clean_push_laps(laps), session)

    leaders: dict[str, dict[str, float | str]] = {}

    for label, column in [("S1", "Sector1Seconds"), ("S2", "Sector2Seconds"), ("S3", "Sector3Seconds")]:
        if column not in laps.columns or "Driver" not in laps.columns:
            continue

        sector = laps[["Driver", column]].copy()
        sector[column] = pd.to_numeric(sector[column], errors="coerce")
        sector = sector.dropna(subset=[column]).sort_values(column)

        if not sector.empty:
            leaders[label] = {
                "driver": str(sector.iloc[0]["Driver"]),
                "seconds": float(sector.iloc[0][column]),
            }

    return leaders


def track_layout_points(
    output_dir: str | Path,
    year: int | None = None,
    event_name: str | None = None,
    session_name: str | None = None,
) -> list[dict[str, float]]:
    return track_layout_payload(output_dir, year, event_name, session_name)['points']


def track_layout_payload(output_dir, year=None, event_name=None, session_name=None):
    resolved = output_context(output_dir, year, event_name, session_name or 'Q')
    year, event_name, session_name = resolved['year'], resolved['event'], resolved['session']
    def result(status, message, points=None, completion='not_recorded'):
        return {'points': points or [], 'status': status, 'message': message,
                'completion': completion, 'event': event_name, 'year': year, 'session': session_name}
    if year is None or not event_name or event_name == "latest":
        return result('context_missing', 'No saved event context. Run a simulation or select a named race.')

    from src.app_services.archive_telemetry import layout
    from src.venues import resolve_venue
    archived = layout(project_root(), year, event_name, session_name, resolve_venue(year, event_name), allow_reference=True)
    if archived['status'] in ('available', 'archive_error'):
        return archived

    session_name = session_name or "Q"
    cache_key = (year, event_name, session_name)

    if cache_key in TRACK_LAYOUT_CACHE:
        return TRACK_LAYOUT_CACHE[cache_key]

    try:
        import fastf1

        enable_cache(str(project_root() / "data" / "cache"))
        session = fastf1.get_session(year, event_name, session_name)
        session.load(laps=True, telemetry=True, weather=False, messages=False)
        telemetry = session.laps.pick_fastest().get_telemetry().add_distance()
        states = session.session_status.Status.dropna()
        completion = str(states.iloc[-1]) if not states.empty else 'not_recorded'
    except Exception:
        # Never cache failures forever: Refresh outputs must be able to retry.
        return result('load_failed', 'Telemetry could not be loaded. Check the connection and Refresh outputs to retry.')

    if telemetry.empty or not {"X", "Y", "Distance"}.issubset(set(telemetry.columns)):
        return result('data_missing', 'Session loaded, but usable track coordinates are missing.', completion=completion)

    frame = telemetry[["X", "Y", "Distance"]].dropna().copy()
    max_distance = pd.to_numeric(frame["Distance"], errors="coerce").max()

    if frame.empty or not pd.notna(max_distance) or float(max_distance) <= 0:
        return result('data_missing', 'Session loaded, but its coordinate/distance data is incomplete.', completion=completion)

    step = max(1, len(frame) // 450)
    sampled = frame.iloc[::step].copy()
    points = [
        {
            "x": float(row["X"]),
            "y": float(row["Y"]),
            "progress": float(row["Distance"]) / float(max_distance),
        }
        for _, row in sampled.iterrows()
    ]
    payload = result('available', f'{len(points)} track points from {event_name} {session_name}.', points, completion)
    TRACK_LAYOUT_CACHE[cache_key] = payload
    return payload


def weather_summary(output_dir: str | Path) -> dict[str, Any]:
    summary = read_output_table(output_dir, "simulation_summary.csv", max_rows=100)
    commentary_path = Path(output_dir) / "report" / "model_commentary.txt"
    commentary = commentary_path.read_text(encoding="utf-8") if commentary_path.exists() else ""
    values = {
        "rain": None,
        "chaos": None,
        "dnf": None,
        "degradation": None,
        "uncertainty": None,
        "source": "Weather observations were not saved for this run; no rain probability inferred.",
        "observed": {}, "modifiers": {},
    }

    if not summary.empty:
        column_map = {
            "red_flag_chance": "chaos",
            "dnf_chance": "dnf",
            "performance_uncertainty": "uncertainty",
            "tyre_deg_score": "degradation",
        }
        for column, key in column_map.items():
            if column in summary.columns:
                value = pd.to_numeric(summary[column], errors="coerce").mean()
                values[key] = None if not pd.notna(value) else float(value) * (100 if key in {'chaos', 'dnf'} else 1)

    for line in commentary.splitlines():
        if line.lower().startswith("weather modifiers:"):
            values["source"] = line
            break

    path = Path(output_dir) / 'weather_context.json'
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            values['observed'] = ({key: saved.get(key) for key in ('air_temp_avg', 'track_temp_avg', 'rainfall_flag')}
                                  if saved.get('weather_source') == 'fastf1_session_weather' else {})
            values['modifiers'] = {key: saved.get(key) for key in ('chaos_factor', 'strategy_factor', 'dnf_factor', 'degradation_factor', 'uncertainty_factor')}
            values['source'] = saved.get('weather_source', 'unknown')
            probability = saved.get('rain_probability')
            values['rain'] = float(probability) if probability is not None else None
        except (ValueError, TypeError, OSError):
            values['source'] = 'Saved weather context could not be read; rain probability unknown.'

    return values


def fantasy_driver_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "Driver" not in frame.columns or "fantasy_points" not in frame.columns:
        return pd.DataFrame()

    output = frame[["Driver", "fantasy_points"]].copy()
    output["fantasy_points"] = pd.to_numeric(output["fantasy_points"], errors="coerce")
    output = output.dropna(subset=["fantasy_points"])

    if output.empty:
        return pd.DataFrame()

    return (
        output.groupby("Driver", as_index=False)["fantasy_points"]
        .mean()
        .rename(columns={"fantasy_points": "avg_fantasy_points"})
    )


def race_review_payload(output_dir: str | Path) -> dict[str, Any]:
    actual = read_output_table(output_dir, "backtest/latest_prediction_snapshot_actual_results.csv", max_rows=100)
    strategy = read_output_table(output_dir, "backtest/latest_prediction_snapshot_actual_strategy.csv", max_rows=100)
    comparison = read_output_table(output_dir, "backtest/latest_prediction_snapshot_comparison.csv", max_rows=100)
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=20_000)
    overview_rows: list[dict[str, str]] = []

    if not actual.empty and "actual_position" in actual.columns:
        winner = actual.copy()
        winner["actual_position"] = pd.to_numeric(winner["actual_position"], errors="coerce")
        winner = winner.sort_values("actual_position")
        if not winner.empty:
            overview_rows.append({"Metric": "Race winner", "Value": str(winner.iloc[0].get("Driver", ""))})

    lap_scope = laps[laps["Session"].astype(str).eq("R")] if "Session" in laps.columns else laps
    if lap_scope.empty:
        lap_scope = laps

    for metric, column in [
        ("Fastest lap", "LapTimeSeconds"),
        ("Best sector 1", "Sector1Seconds"),
        ("Best sector 2", "Sector2Seconds"),
        ("Best sector 3", "Sector3Seconds"),
    ]:
        if column in lap_scope.columns and "Driver" in lap_scope.columns:
            values = lap_scope[["Driver", column]].copy()
            values[column] = pd.to_numeric(values[column], errors="coerce")
            values = values.dropna(subset=[column]).sort_values(column)
            if not values.empty:
                overview_rows.append(
                    {"Metric": metric, "Value": f"{values.iloc[0]['Driver']} ({float(values.iloc[0][column]):.3f}s)"}
                )

    outliers = sorted_view(
        comparison,
        [
            "Driver",
            "Team",
            "predicted_finish",
            "actual_position",
            "finish_error",
            "finish_abs_error",
            "actual_status",
            "dnf_chance",
        ],
        sort_by="finish_abs_error",
        max_rows=20,
    )

    chart_frame = outliers.copy()
    if "finish_abs_error" in chart_frame.columns:
        chart_frame["outlier_score"] = pd.to_numeric(chart_frame["finish_abs_error"], errors="coerce").abs()

    return {
        "overview": table_payload(pd.DataFrame(overview_rows)),
        "strategy": table_payload(
            sorted_view(strategy, ["Driver", "Team", "actual_strategy", "actual_stops", "actual_race_laps"], max_rows=30)
        ),
        "outliers": table_payload(outliers),
        "outlierChart": chart_points(chart_frame, "Driver", "outlier_score"),
    }


class PortableWebApi:
    def __init__(self) -> None:
        self.base_config = load_json_config(DEFAULT_CONFIG_PATH)
        self.default_settings = settings_from_config(self.base_config)
        self._window = None
        from src.app_services.f1_account import F1Account
        self._f1_account = F1Account()
        self.run_lock = threading.Lock()
        self._fantasy_lock = threading.Lock()
        self._fantasy_progress = {'running': False, 'result': None}
        self._manual_job = None
        self.run_state: dict[str, Any] = {"running": False, "exitCode": None, "log": ""}
        self._jobs = SimulationJobs(Path.cwd())
        self._settings_path = self._jobs.root/'config/app_settings.json'
        self.ui_preferences = {'auto_reload': False, 'follow_pc_runs': True, 'pc_workspace': ''}
        self.last_output = self.default_settings.output_dir
        if self._settings_path.is_file():
            try:
                saved = json.loads(self._settings_path.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    raise ValueError('App settings must be an object.')
                candidate = settings_from_payload(saved.get('settings', {}), self.default_settings)
                from src.app_services.workbench import validate_settings
                validate_settings(candidate)
                self.default_settings = replace(candidate, post_to_discord=False)
                self.ui_preferences['auto_reload'] = bool(saved.get('auto_reload', False))
                self.ui_preferences['follow_pc_runs'] = bool(saved.get('follow_pc_runs', True))
                self.ui_preferences['pc_workspace'] = str(saved.get('pc_workspace', ''))
                self.last_output = saved.get('last_output', self.default_settings.output_dir)
                self.base_config['data'].update({key: value for key, value in saved.get('data_paths', {}).items()
                                                if key in self.base_config['data'] and str(value).lower().endswith('.csv')})
            except (ValueError, TypeError, KeyError):
                self.ui_preferences['settings_error'] = 'Saved app settings could not be loaded; project defaults are in use.'

    def lab_state(self, source_dir='outputs'):
        from src.app_services.discord_settings import local_webhook
        return {**self._jobs.state(source_dir), 'discord_configured': bool(local_webhook(self._jobs.root))}

    def lab_historical_events(self, year):
        from src.app_services.historical_runs import historical_events
        return historical_events(year, self._jobs.root)

    def historical_state(self):
        from src.app_services.historical_library import inventory
        history = [job for job in self._jobs.history() if job['kind'] == 'historical_download']
        active = self._jobs.active_id if self._jobs.process and self._jobs.process.poll() is None else None
        return {**inventory(self._jobs.root), 'jobs': history[:20], 'active_id': active,
                'active_kind': next((job['kind'] for job in self._jobs.history() if job['id'] == active), None)}

    def historical_start(self, payload):
        return self.lab_start({'kind': 'historical_download', 'archive': payload})

    def historical_auth_state(self):
        return self._f1_account.state()

    def historical_auth_start(self):
        return self._f1_account.start()

    def historical_auth_cancel(self):
        return self._f1_account.cancel()

    def training_state(self):
        from src.app_services.model_training import state
        active = self._jobs.active_id if self._jobs.process and self._jobs.process.poll() is None else None
        history = [job for job in self._jobs.history() if job['kind'] == 'historical_training']
        return {**state(self._jobs.root), 'jobs': history[:20], 'active_id': active}

    def training_start(self, payload):
        return self.lab_start({'kind': 'historical_training', 'training': payload})

    def historical_preview(self, year, mode, table='laps', page=1):
        from src.app_services.historical_library import preview
        return preview(self._jobs.root, year, mode, table, page)

    def historical_export(self, payload):
        from src.app_services.historical_library import export
        return export(self._jobs.root, payload)

    def historical_open(self):
        from src.app_services.historical_library import library_root
        path = library_root(self._jobs.root)
        path.mkdir(parents=True, exist_ok=True)
        return self.open_output_dir(str(path))

    def lab_next_race(self):
        from src.app_services.beta import next_race
        return next_race(self._jobs.root)

    def lab_share_export(self, job_id):
        from src.app_services.beta import sharing_export, dump_new
        from uuid import uuid4
        folder = self._jobs._folder(job_id)
        payload = sharing_export(folder)
        exports = folder/'exports'
        exports.mkdir(exist_ok=True)
        path = exports/f'sharing-preview-{uuid4().hex[:8]}.json'
        dump_new(path, payload)
        return {'filename':path.name, 'uploaded':False}

    def lab_start(self, payload):
        with self.run_lock:
            self._refresh_manual_run()
            if self.run_state.get('running'):
                raise ValueError('Race Setup is already running. Wait for it to finish first.')
            return self._jobs.start(payload)

    def lab_status(self, job_id):
        return self._jobs.status(job_id)

    def lab_results(self, job_id, driver='', scenario=''):
        return self._jobs.results(job_id, driver, scenario)

    def lab_cancel(self):
        return self._jobs.cancel()

    def lab_open_folder(self, job_id):
        return self._jobs.open_folder(job_id)

    def lab_export(self, job_id, driver='', scenario=''):
        return self._jobs.export(job_id, driver, scenario)

    def set_window(self, window: Any) -> None:
        self._window = window

    def initial_state(self) -> dict[str, Any]:
        settings = settings_to_dict(self.default_settings)
        automation = self.automation_state()
        latest = automation['latest'] if self.ui_preferences['follow_pc_runs'] else None
        if latest:
            settings.update(latest['context'])
        setup_options = self.setup_options(settings["year"], settings["event"])
        sessions = setup_options["sessions"]
        event_names = self.events_for_year(settings['year'])
        if latest:
            if settings['event'] not in event_names:
                event_names.append(settings['event'])
            if settings['session'] not in sessions:
                sessions.append(settings['session'])

        if settings["session"] not in sessions:
            settings["session"] = sessions[0] if sessions else "PRE"

        return {
            "settings": settings,
            "seasons": season_options(settings['year']),
            "events": event_names,
            "sessions": sessions,
            "setupOptions": setup_options,
            "outputs": self.automation_load(latest['id']) if latest else self.outputs({**settings, 'output_dir': self.last_output}),
            'automation': automation,
            'modelReference': model_reference(),
            'projectDefaults': settings_to_dict(settings_from_config(load_json_config(DEFAULT_CONFIG_PATH))),
            'preferences': self.ui_preferences,
            'discordConfigured': self.workbench_status()['discordConfigured'],
        }

    def events_for_year(self, year: int) -> list[str]:
        data_config = self.base_config.get("data", {})
        track_profiles_path = str(data_config.get("track_profiles_path", "data/track_profiles.csv"))
        return ["latest", *available_event_names(int(year), track_profiles_path=track_profiles_path)]

    def setup_options(self, year: int, event: str) -> dict[str, Any]:
        data_config = self.base_config.get("data", {})
        track_profiles_path = str(data_config.get("track_profiles_path", "data/track_profiles.csv"))

        return setup_options_payload(
            year=int(year),
            event=str(event or "latest"),
            track_profiles_path=track_profiles_path,
        )

    def setup_track(self, year: int, event: str, session: str = 'Q') -> dict[str, Any]:
        from src.app_services.archive_telemetry import layout
        if str(session).upper() not in SESSION_OPTIONS:
            raise ValueError('Choose a supported session.')
        options = self.setup_options(int(year), event)
        profile = options['trackProfile']
        return layout(self._jobs.root, int(year), profile['event'], session, profile, allow_reference=True)

    def outputs(self, settings_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._sync_fia_reference()
        settings = settings_from_payload(settings_payload or {}, self.default_settings)
        output_dir = settings.output_dir
        summary = read_output_table(output_dir, "simulation_summary.csv", max_rows=100)
        frozen_manifest = None
        folder = Path(output_dir).resolve()
        if folder.name == 'source' and (folder.parent / 'frozen/manifest.json').is_file():
            from src.app_services.beta import verified_snapshot
            frozen_manifest = verified_snapshot(folder.parent)
            summary = read_output_table(folder.parent / 'frozen', 'simulation_summary.csv', max_rows=100)
        reliability = read_output_table(output_dir, "debug/reliability_profile.csv", max_rows=100)
        strategy = read_output_table(output_dir, "strategy/predicted_tyre_strategy.csv", max_rows=100)
        fantasy = fantasy_driver_summary(read_output_table(output_dir, "raw_fantasy_results.csv", max_rows=5_000))
        signals = load_model_signals(output_dir)
        files = list_core_outputs(output_dir)
        health = validate_data_sources(build_run_config(self.base_config, settings))
        context = output_context(output_dir, settings.year, settings.event, settings.session)
        if frozen_manifest:
            context = {key: frozen_manifest['context'][key] for key in ('year', 'event', 'session')}
            context['source'] = 'verified_frozen_forecast'
        track = track_layout_payload(output_dir, context['year'], context['event'], context['session'])
        track.update(sectors=sector_leaders(output_dir, context['session']) or track.get('sectors', {}),
                     fastestLap=fastest_lap(output_dir, context['session']) or track.get('fastestLap', {}))

        from src.app_services.grid_updates import forecast_grid_status
        grid_context = frozen_manifest['context'] if frozen_manifest else context
        grid_freshness = forecast_grid_status(self._jobs.root, output_dir, grid_context,
            index_path=self.base_config.get('data', {}).get('fia_document_index_path'))

        return {
            'gridFreshness': grid_freshness,
            'details': saved_details(output_dir, summary_override=summary),
            "outputDir": output_dir,
            "sessionMode": session_mode(context['session']),
            "files": [item.__dict__ for item in files],
            "dataHealth": [item.__dict__ for item in health],
            "savedContext": context,
            "runHealth": saved_data_health(output_dir, context,
                {'year': settings.year, 'event': settings.event, 'session': settings.session}, track),
            "summaryTable": table_payload(
                sorted_view(
                    summary,
                    [
                        "Driver",
                        "Team",
                        "avg_finish",
                        "win_chance",
                        "podium_chance",
                        "dnf_chance",
                        "avg_points",
                        "avg_fantasy_points",
                    ],
                    sort_by="avg_finish",
                    ascending=True,
                    max_rows=30,
                )
            ),
            "resultsCharts": {
                "win": chart_points(summary, "Driver", "win_chance", multiplier=100),
                "podium": chart_points(summary, "Driver", "podium_chance", multiplier=100),
                "dnf": chart_points(summary, "Driver", "dnf_chance", multiplier=100),
                "fantasy": chart_points(fantasy, "Driver", "avg_fantasy_points"),
            },
            "signals": {
                "overview": table_payload(signals.overview),
                "drivers": table_payload(signals.driver_signals, max_rows=50),
                "commentary": signals.commentary,
                "featuresPath": signals.features_path,
                "featuresExist": signals.features_exist,
            },
            "track": track,
            "sessionScreens": session_screen_payloads(output_dir, summary, strategy),
            "weather": weather_summary(output_dir),
            "reliability": {
                "table": table_payload(reliability),
                "engineChart": chart_points(reliability, "Team", "engine_reliability_score", multiplier=100),
            },
            "strategy": table_payload(strategy),
            "raceReview": race_review_payload(output_dir),
        }

    def start_run(self, settings_payload: dict[str, Any]) -> dict[str, Any]:
        with self.run_lock:
            self._refresh_manual_run()
            self._sync_fia_reference()
            if self._jobs.process and self._jobs.process.poll() is None:
                return {'ok': False, 'message': 'A Simulation Centre job is running. Wait or cancel it first.'}
            if self.run_state.get("running"):
                return {"ok": False, "message": "A simulation is already running."}

            settings = settings_from_payload(settings_payload, self.default_settings)
            from src.app_services.workbench import validate_settings
            validate_settings(settings)
            if settings.post_to_discord:
                raise ValueError('Use Simulation Centre to upload a verified frozen forecast to Discord.')
            target = Path(settings.output_dir).resolve()
            if 'frozen' in {part.lower() for part in target.parts} or target.is_relative_to(self._jobs.run_root):
                raise ValueError('Choose a separate output directory; archived forecasts remain unchanged.')
            # Each manual run gets a fresh directory, preserving every prior result.
            output = target/'workbench_runs'/f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
            output.mkdir(parents=True, exist_ok=False)
            settings = replace(settings, output_dir=str(output))
            config = build_run_config(self.base_config, settings)
            config['ignore_environment_overrides'] = True
            launched = self._jobs.start_manual(config)
            self._manual_job = launched["id"]
            config_path = Path(launched["configPath"])
            self.run_state = {
                "running": True,
                "exitCode": None,
                "log": f"Starting run with config: {config_path}\n",
                "outputDir": settings.output_dir,
                'started': time.monotonic(),
            }

        return {"ok": True, "message": "Simulation started.", "configPath": str(config_path), 'outputDir': settings.output_dir}

    def _refresh_manual_run(self):
        # Caller holds run_lock. All execution/logging stays in the worker process.
        if not self._manual_job:
            return
        data = self._jobs.status(self._manual_job)
        running = data['status'] in {'running', 'cancelling'}
        self.run_state.update(running=running, log=data['log'], status=data['status'],
                              exitCode=data.get('exit_code'))
        if not running:
            self.run_state['elapsedSeconds'] = round(time.monotonic()-self.run_state['started'], 2)
            if data['status'] == 'completed':
                self.last_output = data['output_dir']
                try:
                    self._persist_preferences()
                except OSError as exc:
                    self.run_state['log'] += f'\nResults completed, but app settings could not be saved: {exc}\n'
            self._manual_job = None

    def _persist_preferences(self):
        from src.app_services.simulation_jobs import write_json
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self._settings_path, {'settings': {**settings_to_dict(self.default_settings), 'post_to_discord': False},
            'last_output': self.last_output, **self.ui_preferences,
            'data_paths': self.base_config['data']})

    def automation_state(self):
        from src.app_services.automation_feed import forecast_feed
        return {**forecast_feed(self._jobs.root, self.ui_preferences['pc_workspace']),
                'fia_reference_sync':self._sync_fia_reference(),
                'following': self.ui_preferences['follow_pc_runs']}

    def _sync_fia_reference(self):
        from src.app_services.automation_feed import DEFAULT_PC_WORKSPACE
        from src.app_services.fia_reference_sync import sync_pc_index
        return sync_pc_index(self._jobs.root,
            self.ui_preferences['pc_workspace'] or DEFAULT_PC_WORKSPACE,
            self.base_config.get('data',{}).get('fia_document_index_path','data/fia_documents/fia_document_index.csv'),
            following=self.ui_preferences['follow_pc_runs'])

    def _fantasy_workspace(self):
        from src.app_services.automation_feed import DEFAULT_PC_WORKSPACE
        pc = Path(self.ui_preferences['pc_workspace'] or DEFAULT_PC_WORKSPACE)
        return pc if pc.is_dir() else self._jobs.root

    def fantasy_state(self, year=None):
        from src.fantasy_market import history, FIRST_SEASON, archive_root
        root = self._fantasy_workspace()
        rows, index, errors = history(root)
        seasons = sorted({int(row['season']) for row in rows}, reverse=True)
        selected = int(year) if year else (seasons[0] if seasons else datetime.now().year)
        selected_rows = [r for r in rows if int(r['season']) == selected]
        events = {int(r['round']): r['event'] for r in selected_rows}
        market = [r for r in rows if r['source'] == 'official']
        if market:
            latest = max((int(r['season']), int(r['round']), r['captured_at']) for r in market)
            market = [r for r in market if (int(r['season']), int(r['round']), r['captured_at']) == latest
                      and r['is_active'].lower() in {'true', '1'}]
        with self._fantasy_lock:
            progress = dict(self._fantasy_progress)
        return {'year': selected, 'seasons': seasons,
                'supported_seasons': list(range(datetime.now().year, FIRST_SEASON - 1, -1)),
                'events': [{'round': n, 'event': e} for n, e in sorted(events.items())],
                'rows': selected_rows, 'market': market, 'errors': errors,
                'attempts': index.get('attempts', {}), 'progress': progress,
                'archive': str(archive_root(root)),
                'completed_weeks': len({(r['season'], r['round']) for r in rows if r['points_status'] == 'completed'}),
                'total_rows': len(rows)}

    def fantasy_refresh(self, years=None):
        from src.fantasy_market import collect, FIRST_SEASON
        selected = [int(y) for y in (years or [datetime.now().year])]
        if any(y < FIRST_SEASON or y > datetime.now().year for y in selected):
            raise ValueError('Select a supported Fantasy season.')
        root = self._fantasy_workspace()
        with self._fantasy_lock:
            if self._fantasy_progress['running']:
                return {'running': True}
            self._fantasy_progress = {'running': True, 'result': None}
        def run():
            try:
                result = collect(root, selected, force=True)
            except Exception as exc:
                result = {'status': 'error', 'error': type(exc).__name__}
            with self._fantasy_lock:
                self._fantasy_progress = {'running': False, 'result': result}
        threading.Thread(target=run, daemon=True).start()
        return {'running': True}

    def fantasy_open(self):
        from src.fantasy_market import archive_root
        path = archive_root(self._fantasy_workspace())
        path.mkdir(parents=True, exist_ok=True)
        return self.open_output_dir(str(path))

    def automation_load(self, identifier):
        from src.app_services.automation_feed import selected_forecast
        run = selected_forecast(self._jobs.root, self.ui_preferences['pc_workspace'], str(identifier))
        outputs = self.outputs({**run['context'], 'output_dir': run['output_dir']})
        outputs['automationRun'] = run
        return outputs

    def automation_preferences(self, following, pc_workspace=None):
        if pc_workspace is not None:
            directory = Path(str(pc_workspace)).expanduser().resolve()
            if not directory.is_dir():
                raise ValueError('The PC automation workspace must be an existing directory.')
            self.ui_preferences['pc_workspace'] = str(directory)
        self.ui_preferences['follow_pc_runs'] = bool(following)
        self._persist_preferences()
        return self.automation_state()

    def workbench_status(self):
        from src.app_services.discord_settings import local_webhook
        fia_sync = self._sync_fia_reference()
        return {'discordConfigured': bool(local_webhook(self._jobs.root)), 'workspace': str(self._jobs.root),
                'fiaReferenceSync':fia_sync,
                'dataHealth': [item.__dict__ for item in validate_data_sources(self.base_config)]}

    def workbench_data(self, key='track_profiles', page=1):
        from src.app_services.workbench import data_preview
        if key=='fia_document_index':
            self._sync_fia_reference()
        return data_preview(self.base_config, str(key), int(page))

    def workbench_open_data(self, key):
        if key == 'folder':
            return self.open_output_dir(str(Path(self.base_config['data']['track_profiles_path']).parent))
        from src.app_services.workbench import data_preview
        source = data_preview(self.base_config, str(key))['source']
        if not source['exists']:
            raise ValueError('The selected source file is missing.')
        return self.open_output_dir(source['path'])

    def workbench_save(self, payload, data_directory='', auto_reload=False):
        from src.app_services.workbench import validate_settings
        settings = settings_from_payload(payload, self.default_settings)
        validate_settings(settings)
        data_paths = dict(self.base_config['data'])
        if data_directory:
            directory = Path(str(data_directory)).resolve()
            if not directory.is_dir():
                raise ValueError('The data directory must exist.')
            names = {'fantasy_prices_path': 'fantasy_prices.csv', 'track_profiles_path': 'track_profiles.csv',
                     'team_power_units_path': 'team_power_units.csv', 'fia_document_index_path': 'fia_documents/fia_document_index.csv'}
            data_paths.update({key: str(directory/name) for key, name in names.items()})
        self.default_settings = replace(settings, post_to_discord=False)
        self.base_config['data'] = data_paths
        self.ui_preferences['auto_reload'] = bool(auto_reload)
        self._persist_preferences()
        return {'saved': True, **self.workbench_status()}

    def workbench_export(self, output_dir, kind):
        from src.app_services.workbench import export_results
        return export_results(output_dir, kind)

    def workbench_history(self):
        history = self._jobs.history()
        self._workbench_runs = {}
        for run in self.automation_state()['runs']:
            identifier = 'pc:' + hashlib.sha256(run['id'].encode()).hexdigest()[:16]
            self._workbench_runs[identifier] = Path(run['id'])
            history.append({'id': identifier, 'kind': 'forecast', 'status': 'completed',
                            'label': run['label'] + ' · PC forecast', 'created_at': run['created_at']})
        locations = {Path(self.default_settings.output_dir).resolve()/'workbench_runs',
                     Path(self.last_output).resolve().parent}
        for location in locations:
            for metadata in location.glob('*/ui_run.json'):
                try:
                    saved = json.loads(metadata.read_text(encoding='utf-8'))
                    context = output_context(metadata.parent, None, 'latest', 'PRE')
                    identifier = 'workbench:' + hashlib.sha256(str(metadata.parent).encode()).hexdigest()[:16]
                    self._workbench_runs[identifier] = metadata.parent
                    history.append({'id': identifier, 'kind': 'monte_carlo', 'status': 'completed',
                                    'label': f"{context['year']} {context['event']} · {context['session']}",
                                    'created_at': saved['completed_at_utc']})
                except (ValueError, TypeError, KeyError, OSError):
                    continue
        return {'history': sorted(history, key=lambda item: item['created_at'], reverse=True)}

    def workbench_compare(self, first_id, second_id):
        from src.app_services.workbench import compare_summaries
        frames = []
        for identifier in (first_id, second_id):
            folder = getattr(self, '_workbench_runs', {}).get(identifier)
            if folder is None:
                folder = self._jobs._folder(identifier)
            if (folder/'frozen/manifest.json').is_file():
                from src.app_services.beta import verified_snapshot
                verified_snapshot(folder)
                folder = folder/'frozen'
            frames.append(read_output_table(folder, 'simulation_summary.csv', max_rows=100))
        return compare_summaries(*frames)

    def workbench_weather(self, year, event):
        from src.app_services.race_weather_updates import capture_weather_update
        row = _event_row(_event_schedule(int(year)), str(event))
        if row is None:
            raise ValueError('No published event was found.')
        start = next((pd.to_datetime(row.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
                      for i in range(1, 6) if row.get(f'Session{i}') == 'Race'), None)
        if start is None or pd.isna(start):
            raise ValueError('Race UTC start is unavailable.')
        context = {'year': int(year), 'event': str(row.EventName), 'round': int(row.RoundNumber), 'race_start_utc': start.isoformat()}
        result = capture_weather_update(self._jobs.root, context)
        if not result.get('folder'):
            raise ValueError('Fresh weather is available only for a future race within 14 days. Past race weather remains historical.')
        return json.loads((Path(result['folder'])/'race_weather.json').read_text(encoding='utf-8'))

    def run_status(self) -> dict[str, Any]:
        with self.run_lock:
            self._refresh_manual_run()
            return dict(self.run_state)

    def open_output_dir(self, output_dir: str) -> bool:
        path = Path(output_dir or self.default_settings.output_dir).resolve()
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
            return True
        except Exception:
            return False
