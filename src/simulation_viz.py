from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.colours import get_team_colour


BACKGROUND_COLOUR = "#30343b"
TEXT_COLOUR = "#f8fafc"
MUTED_TEXT_COLOUR = "#d1d5db"


RACE_LAPS_BY_EVENT_KEYWORD = {
    "bahrain": 57,
    "saudi": 50,
    "australian": 58,
    "japanese": 53,
    "chinese": 56,
    "miami": 57,
    "emilia": 63,
    "monaco": 78,
    "spanish": 66,
    "canadian": 70,
    "austrian": 71,
    "british": 52,
    "hungarian": 70,
    "belgian": 44,
    "dutch": 72,
    "italian": 53,
    "azerbaijan": 51,
    "singapore": 62,
    "united states": 56,
    "mexico": 71,
    "brazil": 71,
    "las vegas": 50,
    "qatar": 57,
    "abu dhabi": 58,
}


def _ensure_outputs() -> None:
    Path("outputs/report").mkdir(parents=True, exist_ok=True)


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


def _find_first_existing_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col

    return None


def _add_sim_id_if_missing(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()

    sim_id_col = _find_first_existing_column(
        output,
        [
            "sim_id",
            "simulation_id",
            "SimulationId",
            "simulation",
            "Simulation",
            "race_id",
            "race_sim",
        ],
    )

    if sim_id_col:
        output["sim_id"] = output[sim_id_col]
        return output

    if "Driver" not in output.columns:
        raise ValueError("Cannot infer sim_id because Driver column is missing.")

    # Assumption: raw results have one row per driver per sim.
    # Each driver's nth row belongs to simulation n.
    output["sim_id"] = output.groupby("Driver").cumcount()

    return output


def _format_race_time(seconds: Any) -> str:
    value = _to_float_or_none(seconds)

    if value is None:
        return "N/A"

    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    return f"{minutes}:{secs:05.2f}"


def _estimate_race_laps(metadata: dict | None) -> int:
    if not metadata:
        return 57

    event_name = str(metadata.get("event", "")).lower()

    for keyword, laps in RACE_LAPS_BY_EVENT_KEYWORD.items():
        if keyword in event_name:
            return laps

    return 57


def _estimate_base_winner_time_seconds(
    df: pd.DataFrame,
    metadata: dict | None,
) -> float:
    """
    Estimates a realistic total winner race time.

    Priority:
    1. Use race_pace × race laps if race_pace exists.
    2. Otherwise use a neutral 90-minute race anchor.

    This only anchors the visual to total race time.
    The spread/order still comes from the simulation.
    """

    race_laps = _estimate_race_laps(metadata)

    race_pace_col = _find_first_existing_column(
        df,
        [
            "race_pace",
            "RacePace",
            "sim_race_pace",
            "projected_lap_time",
            "lap_time_seconds",
        ],
    )

    if race_pace_col:
        lap_times = pd.to_numeric(df[race_pace_col], errors="coerce")
        lap_times = lap_times.dropna()

        lap_times = lap_times[
            (lap_times >= 45)
            & (lap_times <= 160)
        ]

        if not lap_times.empty:
            # Use a strong but not extreme winner estimate.
            base_lap_time = float(lap_times.quantile(0.15))

            # Add a small race operations allowance for stops, traffic,
            # safety-car variance etc. This keeps the time realistic.
            pit_and_race_allowance = 28.0

            return float(base_lap_time * race_laps + pit_and_race_allowance)

    # Fallback: 90 minutes.
    return 90 * 60.0


def _prepare_total_race_time_distribution(
    results: pd.DataFrame,
    metadata: dict | None = None,
) -> tuple[pd.DataFrame, str]:
    df = results.copy()

    if df.empty:
        raise ValueError("Simulation results are empty.")

    if "Driver" not in df.columns:
        raise ValueError(
            "Simulation results must contain Driver. "
            f"Available columns: {', '.join(df.columns)}"
        )

    if "Team" not in df.columns:
        df["Team"] = "Unknown"

    df["Driver"] = df["Driver"].astype(str)
    df["Team"] = df["Team"].astype(str)

    race_time_col = _find_first_existing_column(
        df,
        [
            "race_time_seconds",
            "RaceTimeSeconds",
            "total_race_time_seconds",
            "total_time_seconds",
            "sim_race_time_seconds",
            "race_time",
            "total_race_time",
            "projected_race_time",
            "projected_race_time_seconds",
        ],
    )

    if race_time_col:
        df["ProjectedRaceTimeSeconds"] = pd.to_numeric(
            df[race_time_col],
            errors="coerce",
        )
        df = df.dropna(subset=["ProjectedRaceTimeSeconds"]).copy()

        return df, f"using {race_time_col}"

    score_col = _find_first_existing_column(
        df,
        [
            "performance_score",
            "PerformanceScore",
            "score",
            "sim_score",
            "race_score",
        ],
    )

    if score_col:
        df = _add_sim_id_if_missing(df)

        df[score_col] = pd.to_numeric(
            df[score_col],
            errors="coerce",
        )

        df = df.dropna(subset=[score_col]).copy()

        if df.empty:
            raise ValueError(f"No valid numeric values found in {score_col}.")

        base_winner_time = _estimate_base_winner_time_seconds(
            df=df,
            metadata=metadata,
        )

        # Lower score is better. Convert each sim into total projected time.
        df["SimBestScore"] = df.groupby("sim_id")[score_col].transform("min")
        df["TimeDeltaToSimWinner"] = df[score_col] - df["SimBestScore"]

        # Keep the spread sensible. A simulation score can include noise that
        # is not literally seconds. This cap keeps the visual race-like.
        df["TimeDeltaToSimWinner"] = df["TimeDeltaToSimWinner"].clip(
            lower=0.0,
            upper=180.0,
        )

        df["ProjectedRaceTimeSeconds"] = (
            base_winner_time + df["TimeDeltaToSimWinner"]
        )

        source_note = (
            f"estimated from {score_col}; "
            f"winner anchor {_format_race_time(base_winner_time)}"
        )

        return df, source_note

    position_col = _find_first_existing_column(
        df,
        [
            "finish_position",
            "finishing_position",
            "position",
            "Position",
            "finish",
            "Finish",
            "classified_position",
        ],
    )

    if position_col:
        df = _add_sim_id_if_missing(df)

        df[position_col] = pd.to_numeric(
            df[position_col],
            errors="coerce",
        )

        df = df.dropna(subset=[position_col]).copy()

        base_winner_time = _estimate_base_winner_time_seconds(
            df=df,
            metadata=metadata,
        )

        # Very rough fallback: each finishing position is about 4 seconds apart.
        df["ProjectedRaceTimeSeconds"] = (
            base_winner_time + (df[position_col] - 1).clip(lower=0) * 4.0
        )

        source_note = (
            f"estimated from {position_col}; "
            f"winner anchor {_format_race_time(base_winner_time)}"
        )

        return df, source_note

    raise ValueError(
        "Could not build total projected race time chart. "
        "No race-time, performance-score, or finish-position column found. "
        f"Available columns: {', '.join(results.columns)}"
    )


def make_simulated_race_time_chart(
    results: pd.DataFrame,
    output_path: str = "outputs/report/simulated_race_times.png",
    session: Any | None = None,
    metadata: dict | None = None,
    max_drivers: int = 20,
) -> str:
    _ensure_outputs()

    plot_data, source_note = _prepare_total_race_time_distribution(
        results=results,
        metadata=metadata,
    )

    if plot_data.empty:
        raise ValueError("No valid simulation data available for chart.")

    team_map = (
        plot_data.groupby("Driver")["Team"]
        .agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else "Unknown")
        .to_dict()
    )

    driver_order = (
        plot_data.groupby("Driver")["ProjectedRaceTimeSeconds"]
        .median()
        .sort_values()
        .index
        .tolist()
    )

    if max_drivers > 0:
        driver_order = driver_order[:max_drivers]

    percentiles = np.linspace(0, 100, 401)

    fig, ax = plt.subplots(figsize=(16, 10))
    fig.patch.set_facecolor(BACKGROUND_COLOUR)
    ax.set_facecolor(BACKGROUND_COLOUR)

    plotted_count = 0

    for driver in driver_order:
        driver_values = plot_data.loc[
            plot_data["Driver"] == driver,
            "ProjectedRaceTimeSeconds",
        ].dropna()

        if len(driver_values) < 3:
            continue

        values = driver_values.to_numpy(dtype=float)
        curve = np.percentile(values, percentiles)

        team = team_map.get(driver, "Unknown")
        colour = get_team_colour(team, session=session)

        ax.plot(
            percentiles,
            curve,
            linewidth=2.0,
            color=colour,
            alpha=0.95,
            label=f"{driver} ({team})",
        )

        p50 = float(np.percentile(values, 50))

        ax.scatter(
            [50],
            [p50],
            s=30,
            color=colour,
            edgecolors="white",
            linewidths=0.6,
            zorder=5,
        )

        ax.text(
            100.8,
            curve[-1],
            driver,
            color=colour,
            fontsize=8.5,
            va="center",
            ha="left",
            weight="bold",
        )

        plotted_count += 1

    if plotted_count == 0:
        raise ValueError("No drivers had enough simulation rows to plot.")

    ax.set_title(
        "Simulation Distribution — Total Projected Race Time",
        color=TEXT_COLOUR,
        fontsize=17,
        weight="bold",
        pad=14,
    )

    ax.set_xlabel("Simulation percentile", color=TEXT_COLOUR, fontsize=12)
    ax.set_ylabel("Total projected race time", color=TEXT_COLOUR, fontsize=12)

    ax.tick_params(colors=TEXT_COLOUR)
    ax.grid(alpha=0.20, color="#9ca3af")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    ax.set_xlim(0, 108)

    yticks = ax.get_yticks()
    ax.set_yticks(yticks)
    ax.set_yticklabels(
        [_format_race_time(tick) for tick in yticks],
        color=TEXT_COLOUR,
    )

    handles, labels = ax.get_legend_handles_labels()

    if handles:
        ax.legend(
            handles,
            labels,
            facecolor=BACKGROUND_COLOUR,
            edgecolor="#6b7280",
            labelcolor=TEXT_COLOUR,
            fontsize=8.0,
            ncol=2,
            loc="upper left",
        )

    ax.text(
        0.01,
        -0.08,
        f"Each line uses all simulations. Lower race time is better. Source: {source_note}.",
        transform=ax.transAxes,
        color=MUTED_TEXT_COLOUR,
        fontsize=9,
        ha="left",
        va="top",
    )

    plt.tight_layout()
    plt.savefig(
        output_path,
        dpi=200,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.25,
    )
    plt.close(fig)

    return output_path