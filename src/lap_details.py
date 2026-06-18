from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.collect import load_session


DETAIL_SESSIONS = ["FP1", "FP2", "FP3", "Q"]


def _td_to_seconds(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    try:
        seconds = pd.to_timedelta(value).total_seconds()
    except (TypeError, ValueError):
        return None

    if not np.isfinite(seconds):
        return None

    return float(seconds)


def _series_to_seconds(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def _safe_col(df: pd.DataFrame, col: str, default: Any = None) -> pd.Series:
    if col in df.columns:
        return df[col]

    return pd.Series([default] * len(df), index=df.index)


def extract_lap_details(session: Any, metadata: dict) -> pd.DataFrame:
    laps = session.laps.copy()

    detail = pd.DataFrame(index=laps.index)

    detail["Year"] = metadata["year"]
    detail["Event"] = metadata["event"]
    detail["Round"] = metadata["round"]
    detail["Session"] = metadata["session"]

    detail["Driver"] = _safe_col(laps, "Driver").astype(str)
    detail["DriverNumber"] = _safe_col(laps, "DriverNumber")
    detail["Team"] = _safe_col(laps, "Team").astype(str)

    detail["LapNumber"] = pd.to_numeric(_safe_col(laps, "LapNumber"), errors="coerce")
    detail["Stint"] = pd.to_numeric(_safe_col(laps, "Stint"), errors="coerce")

    detail["Compound"] = _safe_col(laps, "Compound").astype(str)
    detail["TyreLife"] = pd.to_numeric(_safe_col(laps, "TyreLife"), errors="coerce")
    detail["FreshTyre"] = _safe_col(laps, "FreshTyre")

    detail["LapTimeSeconds"] = _series_to_seconds(_safe_col(laps, "LapTime"))
    detail["Sector1Seconds"] = _series_to_seconds(_safe_col(laps, "Sector1Time"))
    detail["Sector2Seconds"] = _series_to_seconds(_safe_col(laps, "Sector2Time"))
    detail["Sector3Seconds"] = _series_to_seconds(_safe_col(laps, "Sector3Time"))

    detail["SpeedI1"] = pd.to_numeric(_safe_col(laps, "SpeedI1"), errors="coerce")
    detail["SpeedI2"] = pd.to_numeric(_safe_col(laps, "SpeedI2"), errors="coerce")
    detail["SpeedFL"] = pd.to_numeric(_safe_col(laps, "SpeedFL"), errors="coerce")
    detail["SpeedST"] = pd.to_numeric(_safe_col(laps, "SpeedST"), errors="coerce")

    detail["IsPersonalBest"] = _safe_col(laps, "IsPersonalBest", False).fillna(False).astype(bool)
    detail["IsAccurate"] = _safe_col(laps, "IsAccurate", False).fillna(False).astype(bool)
    detail["TrackStatus"] = _safe_col(laps, "TrackStatus").astype(str)
    detail["Deleted"] = _safe_col(laps, "Deleted", False).fillna(False).astype(bool)

    pit_out = _safe_col(laps, "PitOutTime")
    pit_in = _safe_col(laps, "PitInTime")

    detail["PitOut"] = pit_out.notna()
    detail["PitIn"] = pit_in.notna()

    detail["LapStartTimeSeconds"] = _series_to_seconds(_safe_col(laps, "LapStartTime"))

    detail["CleanPushLap"] = (
        detail["IsAccurate"]
        & detail["LapTimeSeconds"].notna()
        & ~detail["PitOut"]
        & ~detail["PitIn"]
        & ~detail["Deleted"]
    )

    return detail


def build_practice_lap_summary(lap_details: pd.DataFrame) -> pd.DataFrame:
    practice = lap_details[
        lap_details["Session"].isin(["FP1", "FP2", "FP3"])
        & lap_details["CleanPushLap"]
    ].copy()

    if practice.empty:
        return pd.DataFrame()

    summary = (
        practice.groupby(["Session", "Driver", "Team", "Compound"], dropna=False)
        .agg(
            clean_laps=("LapTimeSeconds", "count"),
            best_lap=("LapTimeSeconds", "min"),
            median_lap=("LapTimeSeconds", "median"),
            avg_lap=("LapTimeSeconds", "mean"),
            best_s1=("Sector1Seconds", "min"),
            best_s2=("Sector2Seconds", "min"),
            best_s3=("Sector3Seconds", "min"),
            avg_speed_trap=("SpeedST", "mean"),
        )
        .reset_index()
    )

    summary["ideal_lap"] = (
        summary["best_s1"] + summary["best_s2"] + summary["best_s3"]
    )

    summary = summary.sort_values(
        ["Session", "best_lap"],
        ascending=[True, True],
    ).reset_index(drop=True)

    return summary


def build_long_run_summary(lap_details: pd.DataFrame) -> pd.DataFrame:
    practice = lap_details[
        lap_details["Session"].isin(["FP1", "FP2", "FP3"])
        & lap_details["CleanPushLap"]
    ].copy()

    if practice.empty:
        return pd.DataFrame()

    rows = []

    group_cols = ["Session", "Driver", "Team", "Stint", "Compound"]

    for keys, group in practice.groupby(group_cols, dropna=False):
        group = group.sort_values("LapNumber").copy()

        if len(group) < 3:
            continue

        x = np.arange(len(group), dtype=float)
        y = group["LapTimeSeconds"].astype(float).to_numpy()

        try:
            degradation_per_lap = float(np.polyfit(x, y, 1)[0])
        except Exception:
            degradation_per_lap = 0.0

        session, driver, team, stint, compound = keys

        rows.append(
            {
                "Session": session,
                "Driver": driver,
                "Team": team,
                "Stint": stint,
                "Compound": compound,
                "laps_in_run": len(group),
                "run_start_lap": group["LapNumber"].min(),
                "run_end_lap": group["LapNumber"].max(),
                "best_lap": group["LapTimeSeconds"].min(),
                "median_lap": group["LapTimeSeconds"].median(),
                "avg_lap": group["LapTimeSeconds"].mean(),
                "degradation_per_lap": degradation_per_lap,
                "avg_tyre_life": group["TyreLife"].mean(),
            }
        )

    output = pd.DataFrame(rows)

    if output.empty:
        return output

    return output.sort_values(
        ["Session", "median_lap"],
        ascending=[True, True],
    ).reset_index(drop=True)


def build_quali_lap_summary(lap_details: pd.DataFrame) -> pd.DataFrame:
    quali = lap_details[
        (lap_details["Session"] == "Q")
        & lap_details["CleanPushLap"]
    ].copy()

    if quali.empty:
        return pd.DataFrame()

    summary = (
        quali.groupby(["Driver", "Team"], dropna=False)
        .agg(
            clean_laps=("LapTimeSeconds", "count"),
            best_lap=("LapTimeSeconds", "min"),
            median_lap=("LapTimeSeconds", "median"),
            best_s1=("Sector1Seconds", "min"),
            best_s2=("Sector2Seconds", "min"),
            best_s3=("Sector3Seconds", "min"),
            best_speed_trap=("SpeedST", "max"),
        )
        .reset_index()
    )

    summary["ideal_lap"] = (
        summary["best_s1"] + summary["best_s2"] + summary["best_s3"]
    )

    fastest = summary["best_lap"].min()
    summary["gap_to_fastest"] = summary["best_lap"] - fastest
    summary["ideal_gap_to_fastest"] = summary["ideal_lap"] - fastest

    summary = summary.sort_values("best_lap").reset_index(drop=True)
    summary["quali_rank_from_laps"] = summary.index + 1

    return summary


def extract_quali_results(session: Any, metadata: dict) -> pd.DataFrame:
    results = getattr(session, "results", None)

    if results is None or len(results) == 0:
        return pd.DataFrame()

    df = results.copy()

    if "Abbreviation" in df.columns:
        driver_col = "Abbreviation"
    elif "Driver" in df.columns:
        driver_col = "Driver"
    else:
        return pd.DataFrame()

    team_col = "TeamName" if "TeamName" in df.columns else None

    output = pd.DataFrame()
    output["Year"] = metadata["year"]
    output["Event"] = metadata["event"]
    output["Round"] = metadata["round"]
    output["Driver"] = df[driver_col].astype(str)

    if team_col:
        output["Team"] = df[team_col].astype(str)
    else:
        output["Team"] = ""

    if "Position" in df.columns:
        output["Position"] = pd.to_numeric(df["Position"], errors="coerce")
    else:
        output["Position"] = np.nan

    for q_col in ["Q1", "Q2", "Q3"]:
        if q_col in df.columns:
            output[f"{q_col}Seconds"] = _series_to_seconds(df[q_col])
        else:
            output[f"{q_col}Seconds"] = np.nan

    output["BestQualiSegmentTime"] = output[
        ["Q1Seconds", "Q2Seconds", "Q3Seconds"]
    ].min(axis=1)

    fastest = output["BestQualiSegmentTime"].min()

    if pd.notna(fastest):
        output["GapToBestQualiSegment"] = output["BestQualiSegmentTime"] - fastest
    else:
        output["GapToBestQualiSegment"] = np.nan

    return output.sort_values("Position").reset_index(drop=True)


def export_weekend_lap_details(
    year: int,
    event_identifier: int | str,
    sessions: list[str] | None = None,
    output_dir: str | Path = "outputs/lap_details",
) -> dict[str, str]:
    if sessions is None:
        sessions = DETAIL_SESSIONS

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    detail_frames = []
    quali_results_frames = []

    for session_type in sessions:
        try:
            session, metadata = load_session(year, event_identifier, session_type)
        except Exception as exc:
            print(f"Skipping {session_type}: {exc}")
            continue

        lap_details = extract_lap_details(session, metadata)
        detail_frames.append(lap_details)

        safe_event = str(metadata["event"]).replace(" ", "_").replace("/", "_").replace("\\", "_")
        safe_session_file = str(output_path / f"{safe_event}_{session_type}_laps.csv")
        lap_details.to_csv(safe_session_file, index=False)

        if session_type == "Q":
            quali_results = extract_quali_results(session, metadata)

            if not quali_results.empty:
                quali_results_frames.append(quali_results)

    if not detail_frames:
        raise RuntimeError("No lap detail data could be exported")

    all_laps = pd.concat(detail_frames, ignore_index=True)

    all_laps_path = str(output_path / "weekend_lap_details.csv")
    practice_summary_path = str(output_path / "practice_lap_summary.csv")
    long_run_summary_path = str(output_path / "practice_long_run_summary.csv")
    quali_summary_path = str(output_path / "quali_lap_summary.csv")
    quali_results_path = str(output_path / "quali_results_segments.csv")

    all_laps.to_csv(all_laps_path, index=False)

    practice_summary = build_practice_lap_summary(all_laps)
    practice_summary.to_csv(practice_summary_path, index=False)

    long_run_summary = build_long_run_summary(all_laps)
    long_run_summary.to_csv(long_run_summary_path, index=False)

    quali_summary = build_quali_lap_summary(all_laps)
    quali_summary.to_csv(quali_summary_path, index=False)

    if quali_results_frames:
        quali_results = pd.concat(quali_results_frames, ignore_index=True)
        quali_results.to_csv(quali_results_path, index=False)

    return {
        "all_laps": all_laps_path,
        "practice_summary": practice_summary_path,
        "long_run_summary": long_run_summary_path,
        "quali_summary": quali_summary_path,
        "quali_results": quali_results_path,
    }
