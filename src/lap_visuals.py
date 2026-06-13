from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COMPOUND_COLOURS = {
    "HARD": "#f8fafc",
    "MEDIUM": "#facc15",
    "SOFT": "#ef4444",
    "INTERMEDIATE": "#22c55e",
    "WET": "#3b82f6",
}


def _ensure_outputs() -> None:
    Path("outputs/lap_visuals").mkdir(parents=True, exist_ok=True)


def _compound_colour(compound: str) -> str:
    return COMPOUND_COLOURS.get(str(compound).upper(), "#d1d5db")


def make_quali_gap_chart(
    quali_summary_path: str,
    output_path: str = "outputs/lap_visuals/quali_gap_to_fastest.png",
) -> str:
    _ensure_outputs()

    quali = pd.read_csv(quali_summary_path)

    if quali.empty or "gap_to_fastest" not in quali.columns:
        raise ValueError("No qualifying summary data available")

    chart_data = quali.sort_values("gap_to_fastest", ascending=True).copy()

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(chart_data["Driver"], chart_data["gap_to_fastest"])
    ax.invert_yaxis()

    ax.set_title(
        "Qualifying lap gap to fastest",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Gap to fastest lap, seconds", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_ideal_vs_actual_quali_chart(
    quali_summary_path: str,
    output_path: str = "outputs/lap_visuals/quali_ideal_vs_actual.png",
) -> str:
    _ensure_outputs()

    quali = pd.read_csv(quali_summary_path)

    if quali.empty or "ideal_lap" not in quali.columns:
        raise ValueError("No qualifying ideal lap data available")

    chart_data = quali.sort_values("best_lap", ascending=True).copy()
    y = np.arange(len(chart_data))

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(y - 0.18, chart_data["best_lap"], height=0.35, label="Best lap")
    ax.barh(y + 0.18, chart_data["ideal_lap"], height=0.35, label="Ideal lap")

    ax.set_yticks(y)
    ax.set_yticklabels(chart_data["Driver"])
    ax.invert_yaxis()

    ax.set_title(
        "Qualifying best lap vs ideal lap",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Lap time, seconds", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_practice_compound_pace_chart(
    practice_summary_path: str,
    output_path: str = "outputs/lap_visuals/practice_best_lap_by_compound.png",
) -> str:
    _ensure_outputs()

    practice = pd.read_csv(practice_summary_path)

    if practice.empty:
        raise ValueError("No practice summary data available")

    chart_data = practice[
        practice["Compound"].astype(str).str.upper().isin(["HARD", "MEDIUM", "SOFT"])
    ].copy()

    if chart_data.empty:
        raise ValueError("No dry compound practice data available")

    chart_data["Compound"] = chart_data["Compound"].astype(str).str.upper()

    best_by_driver_compound = (
        chart_data.groupby(["Driver", "Team", "Compound"], dropna=False)
        .agg(best_lap=("best_lap", "min"))
        .reset_index()
    )

    fastest_drivers = (
        best_by_driver_compound.groupby("Driver")
        .agg(driver_best=("best_lap", "min"))
        .sort_values("driver_best")
        .head(20)
        .index
        .tolist()
    )

    plot_data = best_by_driver_compound[
        best_by_driver_compound["Driver"].isin(fastest_drivers)
    ].copy()

    plot_data["driver_order"] = plot_data["Driver"].map(
        {driver: index for index, driver in enumerate(fastest_drivers)}
    )

    fig, ax = plt.subplots(figsize=(13, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    for compound in ["HARD", "MEDIUM", "SOFT"]:
        subset = plot_data[plot_data["Compound"] == compound]

        ax.scatter(
            subset["best_lap"],
            subset["driver_order"],
            label=compound,
            color=_compound_colour(compound),
            s=70,
            alpha=0.9,
        )

    ax.set_yticks(np.arange(len(fastest_drivers)))
    ax.set_yticklabels(fastest_drivers)
    ax.invert_yaxis()

    ax.set_title(
        "Practice best lap by compound",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Best lap, seconds", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_long_run_degradation_chart(
    long_run_summary_path: str,
    output_path: str = "outputs/lap_visuals/long_run_degradation.png",
) -> str:
    _ensure_outputs()

    long_run = pd.read_csv(long_run_summary_path)

    if long_run.empty or "degradation_per_lap" not in long_run.columns:
        raise ValueError("No long-run summary data available")

    chart_data = long_run[
        pd.to_numeric(long_run["laps_in_run"], errors="coerce") >= 5
    ].copy()

    if chart_data.empty:
        raise ValueError("No long runs with at least 5 laps available")

    chart_data["label"] = (
        chart_data["Driver"].astype(str)
        + " "
        + chart_data["Session"].astype(str)
        + " "
        + chart_data["Compound"].astype(str)
        + " stint "
        + chart_data["Stint"].astype(str)
    )

    chart_data = chart_data.sort_values("degradation_per_lap", ascending=True).tail(25)

    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    colours = [_compound_colour(compound) for compound in chart_data["Compound"]]

    ax.barh(
        chart_data["label"],
        chart_data["degradation_per_lap"],
        color=colours,
    )

    ax.set_title(
        "Practice long-run degradation estimate",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Estimated seconds per lap", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_lap_time_evolution_chart(
    all_laps_path: str,
    output_path: str = "outputs/lap_visuals/lap_time_evolution_top_drivers.png",
) -> str:
    _ensure_outputs()

    laps = pd.read_csv(all_laps_path)

    if laps.empty:
        raise ValueError("No lap details available")

    laps = laps[
        laps["CleanPushLap"].fillna(False).astype(bool)
        & laps["LapTimeSeconds"].notna()
        & laps["Session"].isin(["FP1", "FP2", "FP3", "Q"])
    ].copy()

    if laps.empty:
        raise ValueError("No clean push laps available")

    driver_order = (
        laps.groupby("Driver")
        .agg(best=("LapTimeSeconds", "min"))
        .sort_values("best")
        .head(8)
        .index
        .tolist()
    )

    plot_data = laps[laps["Driver"].isin(driver_order)].copy()

    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    for driver in driver_order:
        subset = plot_data[plot_data["Driver"] == driver].sort_values(
            ["Session", "LapNumber"]
        )

        ax.scatter(
            subset["LapNumber"],
            subset["LapTimeSeconds"],
            label=driver,
            s=35,
            alpha=0.75,
        )

    ax.set_title(
        "Lap time evolution — top clean-lap drivers",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Lap number within session", color="white")
    ax.set_ylabel("Lap time, seconds", color="white")
    ax.tick_params(colors="white")
    ax.grid(alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def create_lap_detail_visuals(lap_detail_files: dict[str, str]) -> list[str]:
    files: list[str] = []

    all_laps_path = lap_detail_files.get("all_laps")
    practice_summary_path = lap_detail_files.get("practice_summary")
    long_run_summary_path = lap_detail_files.get("long_run_summary")
    quali_summary_path = lap_detail_files.get("quali_summary")

    attempts = [
        (make_lap_time_evolution_chart, all_laps_path),
        (make_practice_compound_pace_chart, practice_summary_path),
        (make_long_run_degradation_chart, long_run_summary_path),
        (make_quali_gap_chart, quali_summary_path),
        (make_ideal_vs_actual_quali_chart, quali_summary_path),
    ]

    for func, path in attempts:
        if not path:
            continue

        try:
            files.append(func(path))
        except Exception as exc:
            print(f"Lap visual skipped: {func.__name__}: {exc}")

    return files