from __future__ import annotations

from typing import Any

import pandas as pd


TRACK_STATUS_LABELS = {
    "1": "All clear",
    "2": "Yellow flag",
    "3": "Unknown / sector condition",
    "4": "Safety car",
    "5": "Red flag",
    "6": "Virtual safety car",
    "7": "Virtual safety car ending",
}

SAFETY_CAR_CODES = {"4"}
RED_FLAG_CODES = {"5"}
VSC_CODES = {"6", "7"}
YELLOW_CODES = {"2", "3"}


def _safe_dataframe(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()

    if isinstance(value, pd.DataFrame):
        return value.copy()

    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


def _normalise_track_status(track_status: pd.DataFrame) -> pd.DataFrame:
    if track_status.empty:
        return pd.DataFrame(columns=["Time", "Status", "Message"])

    df = track_status.copy()

    if "Status" not in df.columns:
        return pd.DataFrame(columns=["Time", "Status", "Message"])

    df["Status"] = df["Status"].astype(str).str.strip()

    if "Message" not in df.columns:
        df["Message"] = df["Status"].map(TRACK_STATUS_LABELS).fillna("Unknown")

    if "Time" in df.columns:
        df["Time"] = pd.to_timedelta(df["Time"], errors="coerce")
        df = df.sort_values("Time").reset_index(drop=True)

    return df


def _normalise_race_control_messages(messages: pd.DataFrame) -> pd.DataFrame:
    if messages.empty:
        return pd.DataFrame()

    df = messages.copy()

    for col in ["Message", "Category", "Status", "Flag", "Scope", "Sector", "RacingNumber"]:
        if col not in df.columns:
            df[col] = pd.NA

    if "Time" in df.columns:
        df["Time"] = pd.to_timedelta(df["Time"], errors="coerce")
        df = df.sort_values("Time").reset_index(drop=True)

    df["message_text"] = df["Message"].fillna("").astype(str).str.lower()
    df["category_text"] = df["Category"].fillna("").astype(str).str.lower()
    df["status_text"] = df["Status"].fillna("").astype(str).str.lower()
    df["flag_text"] = df["Flag"].fillna("").astype(str).str.lower()

    return df


def _count_track_status_windows(track_status: pd.DataFrame, status_codes: set[str]) -> int:
    if track_status.empty or "Status" not in track_status.columns:
        return 0

    statuses = track_status["Status"].astype(str).tolist()

    count = 0
    previous_active = False

    for status in statuses:
        active = status in status_codes

        if active and not previous_active:
            count += 1

        previous_active = active

    return count


def _estimate_track_status_seconds(track_status: pd.DataFrame, status_codes: set[str]) -> float:
    if track_status.empty or "Time" not in track_status.columns or "Status" not in track_status.columns:
        return 0.0

    df = track_status.copy()
    df = df.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)

    if len(df) < 2:
        return 0.0

    total_seconds = 0.0

    for idx in range(len(df) - 1):
        status = str(df.loc[idx, "Status"])

        if status in status_codes:
            delta = df.loc[idx + 1, "Time"] - df.loc[idx, "Time"]
            total_seconds += max(delta.total_seconds(), 0.0)

    return float(total_seconds)


def _race_control_keyword_count(messages: pd.DataFrame, keywords: list[str]) -> int:
    if messages.empty or "message_text" not in messages.columns:
        return 0

    pattern = "|".join(keywords)
    return int(messages["message_text"].str.contains(pattern, case=False, na=False).sum())


def neutral_race_control_summary() -> dict[str, Any]:
    return {
        "race_control_available": False,
        "track_status_available": False,
        "track_status_rows": 0,
        "race_control_message_rows": 0,
        "safety_car_flag": False,
        "vsc_flag": False,
        "red_flag_flag": False,
        "yellow_flag_windows": 0,
        "safety_car_windows": 0,
        "vsc_windows": 0,
        "red_flag_windows": 0,
        "yellow_flag_seconds": 0.0,
        "safety_car_seconds": 0.0,
        "vsc_seconds": 0.0,
        "red_flag_seconds": 0.0,
        "race_control_incident_messages": 0,
        "race_control_safety_car_messages": 0,
        "race_control_vsc_messages": 0,
        "race_control_red_flag_messages": 0,
        "race_control_chaos_factor": 1.0,
        "race_control_strategy_factor": 1.0,
        "race_control_dnf_factor": 1.0,
        "race_control_uncertainty_factor": 1.0,
        "race_control_red_flag_probability_hint": 0.02,
        "race_control_notes": [
            "Race-control data unavailable; using neutral race-control modifiers."
        ],
    }


def summarise_race_control(session: Any | None = None) -> dict[str, Any]:
    """
    Summarise FastF1 race-control and TrackStatus context.

    The function is deliberately safe for all session types. If the session does
    not expose TrackStatus or race-control data, it returns neutral modifiers.
    """

    if session is None:
        return neutral_race_control_summary()

    raw_track_status = _safe_dataframe(getattr(session, "track_status", None))
    raw_messages = _safe_dataframe(getattr(session, "race_control_messages", None))

    track_status = _normalise_track_status(raw_track_status)
    messages = _normalise_race_control_messages(raw_messages)

    safety_car_windows = _count_track_status_windows(track_status, SAFETY_CAR_CODES)
    red_flag_windows = _count_track_status_windows(track_status, RED_FLAG_CODES)
    vsc_windows = _count_track_status_windows(track_status, VSC_CODES)
    yellow_windows = _count_track_status_windows(track_status, YELLOW_CODES)

    safety_car_seconds = _estimate_track_status_seconds(track_status, SAFETY_CAR_CODES)
    red_flag_seconds = _estimate_track_status_seconds(track_status, RED_FLAG_CODES)
    vsc_seconds = _estimate_track_status_seconds(track_status, VSC_CODES)
    yellow_seconds = _estimate_track_status_seconds(track_status, YELLOW_CODES)

    message_safety_car_count = _race_control_keyword_count(
        messages,
        ["safety car", "sc deployed", "sc in this lap"],
    )
    message_red_flag_count = _race_control_keyword_count(
        messages,
        ["red flag", "session suspended"],
    )
    message_vsc_count = _race_control_keyword_count(
        messages,
        ["virtual safety car", "vsc"],
    )
    message_incident_count = _race_control_keyword_count(
        messages,
        [
            "incident",
            "collision",
            "stopped",
            "spun",
            "off track",
            "debris",
            "investigation",
            "noted",
            "unsafe release",
        ],
    )

    safety_car_flag = safety_car_windows > 0 or message_safety_car_count > 0
    red_flag_flag = red_flag_windows > 0 or message_red_flag_count > 0
    vsc_flag = vsc_windows > 0 or message_vsc_count > 0

    chaos_points = 0.0
    chaos_points += safety_car_windows * 0.30
    chaos_points += vsc_windows * 0.18
    chaos_points += yellow_windows * 0.08
    chaos_points += red_flag_windows * 0.80
    chaos_points += min(message_incident_count * 0.04, 0.50)

    if safety_car_seconds > 0:
        chaos_points += min(safety_car_seconds / 900.0, 0.35)

    if vsc_seconds > 0:
        chaos_points += min(vsc_seconds / 900.0, 0.25)

    if red_flag_seconds > 0:
        chaos_points += min(red_flag_seconds / 1200.0, 0.70)

    chaos_factor = min(1.0 + chaos_points, 2.75)
    strategy_factor = min(
        1.0
        + safety_car_windows * 0.15
        + vsc_windows * 0.10
        + red_flag_windows * 0.30,
        2.20,
    )
    dnf_factor = min(
        1.0 + message_incident_count * 0.03 + red_flag_windows * 0.20,
        1.80,
    )
    uncertainty_factor = min(1.0 + chaos_points * 0.50, 2.00)

    if red_flag_flag:
        red_flag_probability_hint = 0.35
    elif safety_car_flag or vsc_flag:
        red_flag_probability_hint = 0.08
    else:
        red_flag_probability_hint = 0.02

    notes: list[str] = []

    if safety_car_flag:
        notes.append("Safety car context detected from FastF1 TrackStatus/race-control data.")

    if vsc_flag:
        notes.append("Virtual safety car context detected from FastF1 TrackStatus/race-control data.")

    if red_flag_flag:
        notes.append("Red flag context detected from FastF1 TrackStatus/race-control data.")

    if message_incident_count > 0:
        notes.append(f"{message_incident_count} race-control incident-style messages detected.")

    if not notes:
        notes.append("No major race-control disruption detected from available FastF1 data.")

    return {
        "race_control_available": not messages.empty,
        "track_status_available": not track_status.empty,
        "track_status_rows": int(len(track_status)),
        "race_control_message_rows": int(len(messages)),
        "safety_car_flag": bool(safety_car_flag),
        "vsc_flag": bool(vsc_flag),
        "red_flag_flag": bool(red_flag_flag),
        "yellow_flag_windows": int(yellow_windows),
        "safety_car_windows": int(safety_car_windows),
        "vsc_windows": int(vsc_windows),
        "red_flag_windows": int(red_flag_windows),
        "yellow_flag_seconds": float(yellow_seconds),
        "safety_car_seconds": float(safety_car_seconds),
        "vsc_seconds": float(vsc_seconds),
        "red_flag_seconds": float(red_flag_seconds),
        "race_control_incident_messages": int(message_incident_count),
        "race_control_safety_car_messages": int(message_safety_car_count),
        "race_control_vsc_messages": int(message_vsc_count),
        "race_control_red_flag_messages": int(message_red_flag_count),
        "race_control_chaos_factor": float(chaos_factor),
        "race_control_strategy_factor": float(strategy_factor),
        "race_control_dnf_factor": float(dnf_factor),
        "race_control_uncertainty_factor": float(uncertainty_factor),
        "race_control_red_flag_probability_hint": float(red_flag_probability_hint),
        "race_control_notes": notes,
    }


def summarize_race_control(session: Any | None = None) -> dict[str, Any]:
    return summarise_race_control(session)


def merge_race_control_into_weather_modifiers(
    weather_summary: dict[str, Any] | None,
    race_control_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge weather-driven and race-control-driven modifiers.

    Existing weather values remain the base. Race-control values can increase
    chaos, strategy, DNF and uncertainty factors.
    """

    merged = dict(weather_summary or {})
    race_control = race_control_summary or neutral_race_control_summary()

    merged["chaos_factor"] = max(
        float(merged.get("chaos_factor", 1.0)),
        float(race_control.get("race_control_chaos_factor", 1.0)),
    )
    merged["strategy_factor"] = max(
        float(merged.get("strategy_factor", 1.0)),
        float(race_control.get("race_control_strategy_factor", 1.0)),
    )
    merged["dnf_factor"] = max(
        float(merged.get("dnf_factor", 1.0)),
        float(race_control.get("race_control_dnf_factor", 1.0)),
    )
    merged["uncertainty_factor"] = max(
        float(merged.get("uncertainty_factor", 1.0)),
        float(race_control.get("race_control_uncertainty_factor", 1.0)),
    )

    merged["race_control_red_flag_probability_hint"] = float(
        race_control.get("race_control_red_flag_probability_hint", 0.02)
    )

    for key, value in race_control.items():
        merged[key] = value

    existing_notes = merged.get("notes", [])
    if isinstance(existing_notes, str):
        existing_notes = [existing_notes]

    race_control_notes = race_control.get("race_control_notes", [])
    if isinstance(race_control_notes, str):
        race_control_notes = [race_control_notes]

    merged["notes"] = list(existing_notes) + list(race_control_notes)

    return merged