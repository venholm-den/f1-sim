from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any, Iterable

import pandas as pd

from src.actual_strategy import extract_actual_strategy_from_session
from src.collect import _normalise_schedule, enable_fastf1_cache, load_session
from src.data_sources.openf1 import OpenF1Client
from src.lap_details import extract_lap_details
from src.race_control import summarise_race_control
from src.weather import summarize_weather


DEFAULT_SESSIONS = ["FP1", "FP2", "FP3", "Q", "R"]
OPENF1_ENDPOINTS = ["weather", "stints", "race_control", "pit"]


@dataclass(frozen=True)
class HistoricalBuildConfig:
    start_year: int
    end_year: int
    output_dir: str = "data/historical_model"
    sessions: tuple[str, ...] = tuple(DEFAULT_SESSIONS)
    include_openf1: bool = True
    max_events: int | None = None
    skip_existing: bool = True
    sleep_seconds: float = 0.0


def _safe_slug(value: Any) -> str:
    text = str(value).strip().lower()
    output = []

    for char in text:
        if char.isalnum():
            output.append(char)
        elif output and output[-1] != "_":
            output.append("_")

    return "".join(output).strip("_") or "unknown"


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _merge_and_write_frame(
    path: Path,
    frame: pd.DataFrame,
    subset: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and path.stat().st_size > 0:
        try:
            existing = pd.read_csv(path)
        except Exception:
            existing = pd.DataFrame()
    else:
        existing = pd.DataFrame()

    combined = _concat_or_empty([existing, frame])

    if subset and not combined.empty and all(column in combined.columns for column in subset):
        combined = combined.drop_duplicates(subset=subset, keep="last")
    elif not combined.empty:
        combined = combined.drop_duplicates(keep="last")

    _write_frame(path, combined)


def _metadata_columns(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "Year": metadata.get("year"),
        "Event": metadata.get("event"),
        "Round": metadata.get("round"),
        "Session": metadata.get("session"),
    }


def _with_metadata(frame: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame

    output = frame.copy()
    columns = _metadata_columns(metadata)

    for column, value in reversed(list(columns.items())):
        if column not in output.columns:
            output.insert(0, column, value)

    return output


def _extract_results(session: Any, metadata: dict[str, Any]) -> pd.DataFrame:
    results = getattr(session, "results", None)

    if results is None:
        return pd.DataFrame()

    try:
        frame = results.copy()
    except Exception:
        return pd.DataFrame()

    if frame.empty:
        return pd.DataFrame()

    keep = [
        "DriverNumber",
        "BroadcastName",
        "Abbreviation",
        "TeamName",
        "Position",
        "ClassifiedPosition",
        "Status",
        "Points",
        "GridPosition",
        "Time",
    ]
    selected = [column for column in keep if column in frame.columns]
    output = frame[selected].copy() if selected else frame.copy()
    return _with_metadata(output, metadata)


def _extract_weather(session: Any, metadata: dict[str, Any]) -> pd.DataFrame:
    weather_data = getattr(session, "weather_data", None)

    try:
        weather_frame = weather_data.copy() if weather_data is not None else pd.DataFrame()
    except Exception:
        weather_frame = pd.DataFrame()

    summary = pd.DataFrame([summarize_weather(session)])
    summary = _with_metadata(summary, metadata)

    if not weather_frame.empty:
        weather_frame = _with_metadata(weather_frame, metadata)

    summary["WeatherRows"] = len(weather_frame)
    return summary


def _extract_race_control(session: Any, metadata: dict[str, Any]) -> pd.DataFrame:
    try:
        summary = summarise_race_control(session)
    except Exception:
        summary = {}

    if not summary:
        return pd.DataFrame()

    return _with_metadata(pd.DataFrame([summary]), metadata)


def _event_candidates(start_year: int, end_year: int, max_events: int | None = None) -> list[dict[str, Any]]:
    enable_fastf1_cache()
    rows: list[dict[str, Any]] = []

    for year in range(start_year, end_year + 1):
        schedule = _normalise_schedule(year)
        now = pd.Timestamp.utcnow().tz_localize(None)

        if "EventDateParsed" in schedule.columns:
            schedule = schedule[schedule["EventDateParsed"].notna() & schedule["EventDateParsed"].le(now)]

        for _, row in schedule.sort_values("RoundNumber").iterrows():
            rows.append(
                {
                    "year": year,
                    "round": int(row["RoundNumber"]),
                    "event": str(row["EventName"]),
                    "event_date": str(row.get("EventDate", "")),
                }
            )

            if max_events is not None and len(rows) >= max_events:
                return rows

    return rows


def _openf1_session_key(
    client: OpenF1Client,
    year: int,
    event_name: str,
    session_name: str,
) -> int | None:
    try:
        sessions = client.sessions(year=year, session_name=session_name)
    except Exception:
        return None

    if sessions.empty or "session_key" not in sessions.columns:
        return None

    event_key = _safe_slug(event_name).replace("_grand_prix", "")
    candidates = sessions.copy()

    def score(row: pd.Series) -> int:
        text = " ".join(
            str(row.get(column, ""))
            for column in ["meeting_name", "location", "country_name", "circuit_short_name"]
        ).lower()
        tokens = [token for token in event_key.split("_") if len(token) > 2]
        return sum(1 for token in tokens if token in text)

    candidates["_match_score"] = candidates.apply(score, axis=1)
    candidates = candidates.sort_values(["_match_score", "date_start"], ascending=[False, True])

    if int(candidates["_match_score"].iloc[0]) <= 0:
        return None

    return int(candidates["session_key"].iloc[0])


def _extract_openf1(
    client: OpenF1Client,
    metadata: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    session_key = _openf1_session_key(
        client,
        int(metadata["year"]),
        str(metadata["event"]),
        str(metadata["session"]),
    )

    if session_key is None:
        return {}

    try:
        snapshot = client.session_snapshot(session_key=session_key, endpoints=OPENF1_ENDPOINTS)
    except Exception:
        return {}

    output: dict[str, pd.DataFrame] = {}

    for name, frame in snapshot.items():
        if frame.empty:
            continue

        enriched = _with_metadata(frame, metadata)
        enriched.insert(4, "OpenF1SessionKey", session_key)
        output[name] = enriched

    return output


def _concat_or_empty(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    return pd.concat(usable, ignore_index=True) if usable else pd.DataFrame()


def build_historical_dataset(config: HistoricalBuildConfig) -> dict[str, str]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    openf1_client = OpenF1Client() if config.include_openf1 else None

    if config.skip_existing and manifest_path.exists():
        manifest = pd.read_csv(manifest_path)
        completed_keys = set(
            manifest[manifest["status"].eq("ok")]["dataset_key"].astype(str)
        )
    else:
        manifest = pd.DataFrame()
        completed_keys = set()

    lap_frames: list[pd.DataFrame] = []
    result_frames: list[pd.DataFrame] = []
    strategy_frames: list[pd.DataFrame] = []
    weather_frames: list[pd.DataFrame] = []
    race_control_frames: list[pd.DataFrame] = []
    openf1_frames: dict[str, list[pd.DataFrame]] = (
        {endpoint: [] for endpoint in OPENF1_ENDPOINTS} if config.include_openf1 else {}
    )
    manifest_rows: list[dict[str, Any]] = []

    for event in _event_candidates(config.start_year, config.end_year, config.max_events):
        for session_name in config.sessions:
            dataset_key = f"{event['year']}_{event['round']:02d}_{_safe_slug(event['event'])}_{session_name}"

            if dataset_key in completed_keys:
                continue

            row = {
                "dataset_key": dataset_key,
                "year": event["year"],
                "round": event["round"],
                "event": event["event"],
                "session": session_name,
                "status": "ok",
                "message": "",
            }

            try:
                session, metadata = load_session(event["year"], event["round"], session_name)
                metadata["event"] = event["event"]

                lap_frames.append(extract_lap_details(session, metadata))
                weather_frames.append(_extract_weather(session, metadata))

                if session_name == "R":
                    result_frames.append(_extract_results(session, metadata))
                    strategy_frames.append(extract_actual_strategy_from_session(session, metadata))
                    race_control_frames.append(_extract_race_control(session, metadata))

                if openf1_client is not None:
                    for endpoint, frame in _extract_openf1(openf1_client, metadata).items():
                        openf1_frames.setdefault(endpoint, []).append(frame)

            except Exception as exc:
                row["status"] = "error"
                row["message"] = str(exc)

            manifest_rows.append(row)

            if config.sleep_seconds > 0:
                sleep(config.sleep_seconds)

    outputs = {
        "laps": output_dir / "fastf1_laps.csv",
        "race_results": output_dir / "fastf1_race_results.csv",
        "actual_strategy": output_dir / "fastf1_actual_strategy.csv",
        "weather": output_dir / "fastf1_weather_summary.csv",
        "race_control": output_dir / "fastf1_race_control_summary.csv",
        "manifest": manifest_path,
    }

    merged_manifest = pd.concat([manifest, pd.DataFrame(manifest_rows)], ignore_index=True)
    merged_manifest = merged_manifest.drop_duplicates(subset=["dataset_key"], keep="last")

    _merge_and_write_frame(
        outputs["laps"],
        _concat_or_empty(lap_frames),
        subset=["Year", "Event", "Session", "Driver", "LapNumber"],
    )
    _merge_and_write_frame(
        outputs["race_results"],
        _concat_or_empty(result_frames),
        subset=["Year", "Event", "Session", "DriverNumber"],
    )
    _merge_and_write_frame(
        outputs["actual_strategy"],
        _concat_or_empty(strategy_frames),
        subset=["year", "event", "Driver"],
    )
    _merge_and_write_frame(
        outputs["weather"],
        _concat_or_empty(weather_frames),
        subset=["Year", "Event", "Session"],
    )
    _merge_and_write_frame(
        outputs["race_control"],
        _concat_or_empty(race_control_frames),
        subset=["Year", "Event", "Session"],
    )
    _write_frame(outputs["manifest"], merged_manifest)

    for endpoint, frames in openf1_frames.items():
        path = output_dir / f"openf1_{endpoint}.csv"
        _merge_and_write_frame(path, _concat_or_empty(frames))
        outputs[f"openf1_{endpoint}"] = path

    return {key: str(path) for key, path in outputs.items()}
