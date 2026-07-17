from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import fastf1
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.charts import TEAM_COLOURS


ProjectionLoader = Callable[[int, Path], pd.DataFrame]
ActualResultsLoader = Callable[[int, int], pd.DataFrame]


def _safe_slug(value: Any) -> str:
    text = str(value or "unknown").strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _normalise_driver(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return float(number)


def _team_colour(team: Any) -> str:
    return TEAM_COLOURS.get(str(team), "#d1d5db")


def _normalise_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule is None or schedule.empty:
        return pd.DataFrame(columns=["RoundNumber", "EventName", "EventDateParsed"])

    output = schedule.copy()

    if "RoundNumber" not in output.columns:
        return pd.DataFrame(columns=["RoundNumber", "EventName", "EventDateParsed"])

    output["RoundNumber"] = pd.to_numeric(output["RoundNumber"], errors="coerce")
    output = output[output["RoundNumber"].notna() & output["RoundNumber"].gt(0)].copy()
    output["RoundNumber"] = output["RoundNumber"].astype(int)

    if "EventName" not in output.columns:
        output["EventName"] = output["RoundNumber"].map(lambda value: f"Round {value}")

    if "EventDateParsed" not in output.columns:
        event_date = output["EventDate"] if "EventDate" in output.columns else pd.NaT
        output["EventDateParsed"] = pd.to_datetime(event_date, errors="coerce", utc=True).dt.tz_convert(None)

    return output.sort_values("RoundNumber").reset_index(drop=True)


def _load_schedule(year: int) -> pd.DataFrame:
    return _normalise_schedule(fastf1.get_event_schedule(year))


def _load_race_results(year: int, round_number: int) -> pd.DataFrame:
    session = fastf1.get_session(year, round_number, "R")

    try:
        session.load(laps=False, telemetry=False, weather=False, messages=False)
    except TypeError:
        session.load()

    results = getattr(session, "results", None)
    if results is None:
        return pd.DataFrame()

    try:
        return results.copy()
    except Exception:
        return pd.DataFrame()


def _points_column(frame: pd.DataFrame) -> str | None:
    for column in ["Points", "points", "race_points", "avg_points"]:
        if column in frame.columns:
            return column
    return None


def _driver_column(frame: pd.DataFrame) -> str | None:
    for column in ["Driver", "Abbreviation", "DriverCode", "BroadcastName"]:
        if column in frame.columns:
            return column
    return None


def _team_column(frame: pd.DataFrame) -> str | None:
    for column in ["Team", "TeamName", "team"]:
        if column in frame.columns:
            return column
    return None


def _projection_from_frame(
    frame: pd.DataFrame,
    default_source: str,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Driver", "Team", "projected_points", "projection_source"])

    driver_col = _driver_column(frame)
    points_col = _points_column(frame)
    if driver_col is None or points_col is None:
        return pd.DataFrame(columns=["Driver", "Team", "projected_points", "projection_source"])

    team_col = _team_column(frame)
    output = pd.DataFrame(
        {
            "Driver": frame[driver_col].map(_normalise_driver),
            "Team": frame[team_col].astype(str) if team_col else "",
            "projected_points": pd.to_numeric(frame[points_col], errors="coerce").fillna(0.0),
            "projection_source": default_source,
        }
    )
    output = output[output["Driver"].ne("")]
    return output.groupby(["Driver", "Team", "projection_source"], as_index=False)["projected_points"].mean()


def _actual_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Driver", "Team", "race_points"])

    driver_col = _driver_column(frame)
    points_col = _points_column(frame)
    if driver_col is None or points_col is None:
        return pd.DataFrame(columns=["Driver", "Team", "race_points"])

    team_col = _team_column(frame)
    output = pd.DataFrame(
        {
            "Driver": frame[driver_col].map(_normalise_driver),
            "Team": frame[team_col].astype(str) if team_col else "",
            "race_points": pd.to_numeric(frame[points_col], errors="coerce").fillna(0.0),
        }
    )
    output = output[output["Driver"].ne("")]
    return output.groupby(["Driver", "Team"], as_index=False)["race_points"].sum()


def load_latest_snapshot_projection(
    round_number: int,
    history_dir: str | Path,
) -> pd.DataFrame:
    history_path = Path(history_dir)
    if not history_path.exists():
        return pd.DataFrame()

    matches: list[tuple[float, Path]] = []
    for path in history_path.glob("*prediction_snapshot*.csv"):
        if path.name == "latest_prediction_snapshot.csv":
            continue

        try:
            sample = pd.read_csv(path, nrows=1)
        except Exception:
            continue

        if "round" not in sample.columns:
            continue

        sample_round = pd.to_numeric(sample["round"], errors="coerce").iloc[0]
        if pd.isna(sample_round) or int(sample_round) != int(round_number):
            continue

        matches.append((path.stat().st_mtime, path))

    if not matches:
        return pd.DataFrame()

    _, latest_path = max(matches, key=lambda item: item[0])

    try:
        frame = pd.read_csv(latest_path)
    except Exception:
        return pd.DataFrame()

    projection = _projection_from_frame(
        frame,
        default_source=f"snapshot:{latest_path.name}",
    )
    return projection


def build_season_projection_table(
    schedule: pd.DataFrame,
    current_projection: pd.DataFrame,
    year: int,
    target_round: int,
    history_dir: str | Path,
    now: datetime | None = None,
    actual_results_loader: ActualResultsLoader | None = None,
    projection_loader: ProjectionLoader | None = None,
) -> pd.DataFrame:
    schedule = _normalise_schedule(schedule)
    now = now or datetime.utcnow()
    actual_results_loader = actual_results_loader or _load_race_results
    projection_loader = projection_loader or load_latest_snapshot_projection
    default_projection = _projection_from_frame(current_projection, "current_run")

    if schedule.empty or default_projection.empty:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    cumulative: dict[str, float] = {}
    team_by_driver: dict[str, str] = {
        str(row.Driver): str(row.Team)
        for row in default_projection.itertuples(index=False)
    }

    for row in schedule.itertuples(index=False):
        round_number = int(getattr(row, "RoundNumber"))
        event = str(getattr(row, "EventName", f"Round {round_number}"))
        event_date = getattr(row, "EventDateParsed", pd.NaT)
        event_datetime = pd.to_datetime(event_date, errors="coerce")

        race_has_happened = bool(pd.notna(event_datetime) and event_datetime.to_pydatetime() < now)
        use_actual = race_has_happened and round_number < int(target_round)

        if use_actual:
            try:
                actual = _actual_from_frame(actual_results_loader(int(year), round_number))
            except Exception:
                actual = pd.DataFrame()

            if not actual.empty:
                for actual_row in actual.itertuples(index=False):
                    driver = str(actual_row.Driver)
                    team = str(actual_row.Team)
                    points = _to_float(actual_row.race_points)
                    team_by_driver[driver] = team or team_by_driver.get(driver, "")
                    cumulative[driver] = cumulative.get(driver, 0.0) + points
                    records.append(
                        {
                            "year": year,
                            "round": round_number,
                            "event": event,
                            "status": "actual",
                            "Driver": driver,
                            "Team": team_by_driver.get(driver, ""),
                            "race_points": points,
                            "cumulative_points": cumulative[driver],
                            "projection_source": "fastf1_race_results",
                        }
                    )
                continue

        if round_number == int(target_round):
            projection = default_projection
        else:
            projection = projection_loader(round_number, Path(history_dir))
            if projection.empty:
                projection = default_projection

        for projected_row in projection.itertuples(index=False):
            driver = str(projected_row.Driver)
            team = str(projected_row.Team)
            points = _to_float(projected_row.projected_points)
            team_by_driver[driver] = team or team_by_driver.get(driver, "")
            cumulative[driver] = cumulative.get(driver, 0.0) + points
            records.append(
                {
                    "year": year,
                    "round": round_number,
                    "event": event,
                    "status": "projected",
                    "Driver": driver,
                    "Team": team_by_driver.get(driver, ""),
                    "race_points": points,
                    "cumulative_points": cumulative[driver],
                    "projection_source": str(projected_row.projection_source),
                }
            )

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


def make_season_projection_chart(
    projection: pd.DataFrame,
    output_path: str | Path,
    title: str,
    top_n: int = 10,
) -> str:
    if projection is None or projection.empty:
        raise ValueError("Season projection dataframe is empty.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    chart_data = projection.copy()
    chart_data["round"] = pd.to_numeric(chart_data["round"], errors="coerce")
    chart_data["cumulative_points"] = pd.to_numeric(chart_data["cumulative_points"], errors="coerce")
    chart_data = chart_data.dropna(subset=["round", "cumulative_points"])

    final_order = (
        chart_data.sort_values(["round", "cumulative_points"])
        .groupby("Driver", as_index=False)
        .tail(1)
        .sort_values("cumulative_points", ascending=False)
    )
    drivers = final_order["Driver"].head(top_n).tolist()
    chart_data = chart_data[chart_data["Driver"].isin(drivers)].copy()

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    for driver in drivers:
        driver_data = chart_data[chart_data["Driver"].eq(driver)].sort_values("round")
        if driver_data.empty:
            continue

        team = str(driver_data["Team"].dropna().iloc[-1]) if driver_data["Team"].notna().any() else ""
        colour = _team_colour(team)
        actual = driver_data[driver_data["status"].eq("actual")]
        projected = driver_data[driver_data["status"].eq("projected")]

        if not actual.empty:
            ax.plot(
                actual["round"],
                actual["cumulative_points"],
                color=colour,
                linewidth=2.2,
                marker="o",
            )

        if not projected.empty:
            bridge = pd.concat([actual.tail(1), projected], ignore_index=True) if not actual.empty else projected
            ax.plot(
                bridge["round"],
                bridge["cumulative_points"],
                color=colour,
                linewidth=2.2,
                linestyle="--",
                marker="o",
                label=driver,
            )
        elif not actual.empty:
            ax.plot([], [], color=colour, linewidth=2.2, label=driver)

        last = driver_data.iloc[-1]
        ax.text(
            float(last["round"]) + 0.08,
            float(last["cumulative_points"]),
            driver,
            color=colour,
            fontsize=9,
            va="center",
        )

    ax.set_title(title, color="white", fontsize=16, weight="bold")
    ax.set_xlabel("Round", color="white")
    ax.set_ylabel("Driver championship points", color="white")
    ax.tick_params(colors="white")
    ax.grid(alpha=0.22)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white", ncols=2)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    return str(output)


def build_season_projection_outputs(
    summary: pd.DataFrame,
    metadata: dict[str, Any],
    output_dir: str | Path = "outputs",
    schedule: pd.DataFrame | None = None,
) -> dict[str, str]:
    year = int(metadata.get("year", metadata.get("season")))
    target_round = int(metadata.get("round", metadata.get("round_number", 1)))
    event = str(metadata.get("event", "Season"))
    root = Path(output_dir)
    season_dir = root / "season"
    season_dir.mkdir(parents=True, exist_ok=True)

    season_schedule = _load_schedule(year) if schedule is None else schedule
    projection = build_season_projection_table(
        schedule=season_schedule,
        current_projection=summary,
        year=year,
        target_round=target_round,
        history_dir=root / "history",
    )

    if projection.empty:
        raise ValueError("No season projection rows were produced.")

    slug = f"{year}_season_projection_after_R{target_round:02d}_{_safe_slug(event)}"
    csv_path = season_dir / f"{slug}.csv"
    png_path = season_dir / f"{slug}.png"
    latest_csv = season_dir / "latest_season_projection.csv"
    latest_png = season_dir / "latest_season_projection.png"

    projection.to_csv(csv_path, index=False)
    projection.to_csv(latest_csv, index=False)

    chart_title = f"{year} Driver Points - Actuals and Rest-of-Season Projection"
    make_season_projection_chart(projection, png_path, chart_title)
    make_season_projection_chart(projection, latest_png, chart_title)

    return {
        "season_projection_csv": str(csv_path),
        "season_projection_chart": str(png_path),
        "latest_season_projection_csv": str(latest_csv),
        "latest_season_projection_chart": str(latest_png),
    }
