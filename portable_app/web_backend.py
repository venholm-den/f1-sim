from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from src.app_services.config_service import (
    DEFAULT_CONFIG_PATH,
    PortableRunSettings,
    build_run_config,
    load_json_config,
    settings_from_config,
    write_temp_run_config,
)
from src.app_services.data_health import validate_data_sources
from src.app_services.model_signals import load_model_signals
from src.app_services.output_index import list_core_outputs, read_output_table
from src.app_services.run_service import run_pipeline_with_config
from src.track import load_track_profile


SESSION_OPTIONS = ["PRE", "Q", "SQ", "S", "FP3", "FP2", "FP1", "R"]
SESSION_PRIORITY = ["R", "Q", "SQ", "S", "FP3", "FP2", "FP1"]
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
TRACK_LAYOUT_CACHE: dict[tuple[int, str, str], list[dict[str, float]]] = {}
PRE_SESSIONS = {"PRE"}
PRACTICE_SESSIONS = {"FP1", "FP2", "FP3"}
QUALI_SESSIONS = {"Q", "SQ"}
RACE_SESSIONS = {"R", "S"}


def project_root() -> Path:
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

        fastf1.Cache.enable_cache(str(project_root() / "data" / "cache"))
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
        return SESSION_PRIORITY.copy()

    scheduled: set[str] = set()

    for index in range(1, 6):
        session_code = _session_code(row.get(f"Session{index}"))

        if session_code is None:
            continue

        scheduled.add(session_code)

    if event_text.lower() != "latest":
        sessions = [session for session in SESSION_PRIORITY if session in scheduled]
        return sessions or SESSION_OPTIONS.copy()

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

    return [session for session in SESSION_PRIORITY if session in available]


def setup_options_payload(
    year: int,
    event: str,
    track_profiles_path: str,
) -> dict[str, Any]:
    schedule = _event_schedule(year)
    row = _event_row(schedule, event)
    event_name = str(row.get("EventName", event)) if row is not None else str(event)
    track_profile = load_track_profile(event_name, path=track_profiles_path)

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
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=5_000)

    if not laps.empty:
        year_value = pd.to_numeric(laps.get("Year", pd.Series(dtype="float64")), errors="coerce").dropna()
        event_value = laps.get("Event", pd.Series(dtype="object")).dropna()
        session_value = laps.get("Session", pd.Series(dtype="object")).dropna()

        if year is None and not year_value.empty:
            year = int(year_value.iloc[0])
        if not event_name and not event_value.empty:
            event_name = str(event_value.iloc[0])
        if not session_name and not session_value.empty:
            session_name = str(session_value.iloc[0])

    if year is None or not event_name or event_name == "latest":
        return []

    session_name = session_name or "Q"
    cache_key = (year, event_name, session_name)

    if cache_key in TRACK_LAYOUT_CACHE:
        return TRACK_LAYOUT_CACHE[cache_key]

    try:
        import fastf1

        fastf1.Cache.enable_cache(str(project_root() / "data" / "cache"))
        session = fastf1.get_session(year, event_name, session_name)
        session.load(laps=True, telemetry=True, weather=False, messages=False)
        telemetry = session.laps.pick_fastest().get_telemetry().add_distance()
    except Exception:
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    if telemetry.empty or not {"X", "Y", "Distance"}.issubset(set(telemetry.columns)):
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    frame = telemetry[["X", "Y", "Distance"]].dropna().copy()
    max_distance = pd.to_numeric(frame["Distance"], errors="coerce").max()

    if frame.empty or not pd.notna(max_distance) or float(max_distance) <= 0:
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

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
    TRACK_LAYOUT_CACHE[cache_key] = points
    return points


def weather_summary(output_dir: str | Path) -> dict[str, Any]:
    summary = read_output_table(output_dir, "simulation_summary.csv", max_rows=100)
    commentary_path = Path(output_dir) / "report" / "model_commentary.txt"
    commentary = commentary_path.read_text(encoding="utf-8") if commentary_path.exists() else ""
    values = {
        "rain": 0.0,
        "chaos": 0.0,
        "dnf": 0.0,
        "degradation": 0.0,
        "uncertainty": 0.0,
        "source": "No weather output found yet",
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
                values[key] = 0.0 if not pd.notna(value) else float(value) * 100

    for line in commentary.splitlines():
        if line.lower().startswith("weather modifiers:"):
            values["source"] = line
            break

    if "rain" in commentary.lower() or "wet" in commentary.lower():
        values["rain"] = max(float(values["rain"]), 55.0)

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
        self.window = None
        self.run_lock = threading.Lock()
        self.run_state: dict[str, Any] = {"running": False, "exitCode": None, "log": ""}

    def set_window(self, window: Any) -> None:
        self.window = window

    def initial_state(self) -> dict[str, Any]:
        settings = settings_to_dict(self.default_settings)
        setup_options = self.setup_options(settings["year"], settings["event"])
        sessions = setup_options["sessions"]
        event_names = self.events_for_year(self.default_settings.year)

        if settings["session"] not in sessions:
            settings["session"] = sessions[0] if sessions else "PRE"

        return {
            "settings": settings,
            "seasons": season_options(self.default_settings.year),
            "events": event_names,
            "sessions": sessions,
            "setupOptions": setup_options,
            "outputs": self.outputs(settings),
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

    def outputs(self, settings_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = settings_from_payload(settings_payload or {}, self.default_settings)
        output_dir = settings.output_dir
        summary = read_output_table(output_dir, "simulation_summary.csv", max_rows=100)
        reliability = read_output_table(output_dir, "debug/reliability_profile.csv", max_rows=100)
        strategy = read_output_table(output_dir, "strategy/predicted_tyre_strategy.csv", max_rows=100)
        fantasy = fantasy_driver_summary(read_output_table(output_dir, "raw_fantasy_results.csv", max_rows=5_000))
        signals = load_model_signals(output_dir)
        files = list_core_outputs(output_dir)
        health = validate_data_sources(build_run_config(self.base_config, settings))

        return {
            "outputDir": output_dir,
            "sessionMode": session_mode(settings.session),
            "files": [item.__dict__ for item in files],
            "dataHealth": [item.__dict__ for item in health],
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
            "track": {
                "points": track_layout_points(output_dir, settings.year, settings.event, settings.session),
                "sectors": sector_leaders(output_dir, settings.session),
                "fastestLap": fastest_lap(output_dir, settings.session),
                "session": settings.session,
            },
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
            if self.run_state.get("running"):
                return {"ok": False, "message": "A simulation is already running."}

            settings = settings_from_payload(settings_payload, self.default_settings)
            config = build_run_config(self.base_config, settings)
            config_path = write_temp_run_config(config)
            self.run_state = {
                "running": True,
                "exitCode": None,
                "log": f"Starting run with config: {config_path}\n",
                "outputDir": settings.output_dir,
            }

        thread = threading.Thread(target=self._run_pipeline, args=(config_path,), daemon=True)
        thread.start()
        return {"ok": True, "message": "Simulation started.", "configPath": str(config_path)}

    def _run_pipeline(self, config_path: Path) -> None:
        def log(text: str) -> None:
            with self.run_lock:
                self.run_state["log"] = str(self.run_state.get("log", "")) + text

        try:
            exit_code = run_pipeline_with_config(config_path, log)
        except Exception:
            log(traceback.format_exc())
            exit_code = 1

        with self.run_lock:
            self.run_state["running"] = False
            self.run_state["exitCode"] = exit_code

    def run_status(self) -> dict[str, Any]:
        with self.run_lock:
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
