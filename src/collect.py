from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import fastf1
import pandas as pd


PRE_FP1_SESSION = "PRE"
PRE_FP1_SESSION_ALIASES = {
    "PRE",
    "PRETEST",
    "PRE-TEST",
    "PRE_TEST",
    "PRE TEST",
    "BEFORE_FP1",
}

PREDICTOR_SESSION_PRIORITY = ["Q", "SQ", "S", "FP3", "FP2", "FP1"]
ANY_SESSION_PRIORITY = ["R", "Q", "SQ", "S", "FP3", "FP2", "FP1"]


def enable_fastf1_cache() -> None:
    Path("data/cache").mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache("data/cache")


def _load_fastf1_session(year: int, event_identifier, session_type: str):
    session = fastf1.get_session(year, event_identifier, session_type)

    try:
        session.load(laps=True, telemetry=False, weather=True, messages=False)
    except TypeError:
        session.load()

    if session.laps is None or len(session.laps) == 0:
        raise ValueError(f"No laps found for {year} {event_identifier} {session_type}")

    return session


def _normalise_schedule(year: int) -> pd.DataFrame:
    schedule = fastf1.get_event_schedule(year).copy()

    if "EventDate" not in schedule.columns:
        raise ValueError("FastF1 schedule did not include EventDate")

    schedule["EventDateParsed"] = pd.to_datetime(
        schedule["EventDate"],
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)

    schedule = schedule[schedule["RoundNumber"] > 0].copy()
    return schedule


def is_pre_fp1_session(session_type: str | None) -> bool:
    return str(session_type or "").strip().upper() in PRE_FP1_SESSION_ALIASES


def _select_event_row(
    schedule: pd.DataFrame,
    event: str | int,
    year: int,
) -> pd.Series:
    if str(event).lower() == "latest":
        now = datetime.utcnow()
        upcoming = schedule[schedule["EventDateParsed"] >= now - timedelta(days=2)].copy()

        if not upcoming.empty:
            return upcoming.sort_values("EventDateParsed", ascending=True).iloc[0]

        return schedule.sort_values("EventDateParsed", ascending=False).iloc[0]

    if isinstance(event, int) or str(event).isdigit():
        round_number = int(event)
        matches = schedule[schedule["RoundNumber"] == round_number]
    else:
        event_key = str(event).strip().lower()
        event_name_match = schedule["EventName"].astype(str).str.lower().eq(event_key)

        if "OfficialEventName" in schedule.columns:
            official_name_match = (
                schedule["OfficialEventName"]
                .astype(str)
                .str.lower()
                .str.contains(event_key, regex=False, na=False)
            )
        else:
            official_name_match = pd.Series(False, index=schedule.index)

        matches = schedule[event_name_match | official_name_match]

    if matches.empty:
        raise ValueError(f"Could not find event in {year} schedule: {event}")

    return matches.iloc[0]


def load_session(year: int, event: str | int, session_type: str):
    enable_fastf1_cache()
    session = _load_fastf1_session(year, event, session_type)

    metadata = {
        "year": year,
        "event": str(session.event.get("EventName", event)),
        "round": int(session.event.get("RoundNumber", 0)),
        "session": session_type,
    }

    return session, metadata


def load_pre_fp1_session(year: int, event: str | int = "latest"):
    """
    Creates event context for a pre-FP1 simulation without loading target laps.

    The rest of the model can then use recent race baselines, track profile,
    forecast weather, FIA context, and fantasy prices before weekend running exists.
    """
    enable_fastf1_cache()
    schedule = _normalise_schedule(year)
    row = _select_event_row(schedule, event, year)

    event_name = str(row["EventName"])
    round_number = int(row["RoundNumber"])
    event_date = row.get("EventDateParsed")

    session = SimpleNamespace(
        event={
            "EventName": event_name,
            "RoundNumber": round_number,
        },
        laps=pd.DataFrame(),
        weather_data=pd.DataFrame(),
        track_status=pd.DataFrame(),
        race_control_messages=pd.DataFrame(),
        date=event_date,
        name=PRE_FP1_SESSION,
    )

    metadata = {
        "year": year,
        "event": event_name,
        "round": round_number,
        "session": PRE_FP1_SESSION,
    }

    return session, metadata


def load_latest_available_session(
    year: int,
    session_priority: list[str] | None = None,
):
    enable_fastf1_cache()

    if session_priority is None:
        session_priority = ANY_SESSION_PRIORITY

    schedule = _normalise_schedule(year)

    now = datetime.utcnow()
    cutoff = now + timedelta(days=2)

    candidates = (
        schedule[
            schedule["EventDateParsed"].notna()
            & (schedule["EventDateParsed"] <= cutoff)
        ]
        .sort_values("EventDateParsed", ascending=False)
        .copy()
    )

    errors: list[str] = []

    for _, row in candidates.iterrows():
        round_number = int(row["RoundNumber"])
        event_name = str(row["EventName"])

        for session_type in session_priority:
            try:
                session = _load_fastf1_session(year, round_number, session_type)

                metadata = {
                    "year": year,
                    "event": str(session.event.get("EventName", event_name)),
                    "round": round_number,
                    "session": session_type,
                }

                return session, metadata

            except Exception as exc:
                errors.append(f"{event_name} {session_type}: {exc}")

    error_text = "\n".join(errors[-10:])
    raise RuntimeError(
        "Could not find a usable latest session.\n"
        f"Last errors:\n{error_text}"
    )


def load_latest_predictor_session(year: int):
    """
    Loads the latest useful session for prediction.

    This intentionally excludes the Race session because using the completed
    race to predict the same race gives misleadingly good-looking output.
    """
    return load_latest_available_session(
        year=year,
        session_priority=PREDICTOR_SESSION_PRIORITY,
    )


def load_recent_race_sessions(
    target_year: int,
    target_round: int,
    count: int = 5,
):
    """
    Loads recent completed Race sessions before the target round.

    Uses current year previous rounds first, then falls back to previous year
    if there are not enough completed current-year races.
    """
    enable_fastf1_cache()

    candidates = []

    for year in [target_year, target_year - 1]:
        try:
            schedule = _normalise_schedule(year)
        except Exception:
            continue

        if year == target_year:
            schedule = schedule[schedule["RoundNumber"] < target_round].copy()

        schedule = schedule.sort_values("RoundNumber", ascending=False)

        for _, row in schedule.iterrows():
            candidates.append(
                {
                    "year": year,
                    "round": int(row["RoundNumber"]),
                    "event": str(row["EventName"]),
                }
            )

    loaded = []
    errors = []

    for candidate in candidates:
        if len(loaded) >= count:
            break

        try:
            session = _load_fastf1_session(
                candidate["year"],
                candidate["round"],
                "R",
            )

            metadata = {
                "year": candidate["year"],
                "event": str(session.event.get("EventName", candidate["event"])),
                "round": candidate["round"],
                "session": "R",
            }

            loaded.append((session, metadata))

        except Exception as exc:
            errors.append(
                f"{candidate['year']} round {candidate['round']} R: {exc}"
            )

    if not loaded:
        error_text = "\n".join(errors[-10:])
        raise RuntimeError(
            "Could not load any recent race sessions for baseline.\n"
            f"Last errors:\n{error_text}"
        )

    return loaded
