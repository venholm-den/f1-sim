from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


TEAM_COLOURS = {
    "Ferrari": "#ef4444",
    "McLaren": "#fb923c",
    "Red Bull Racing": "#3b82f6",
    "Mercedes": "#2dd4bf",
    "Williams": "#60a5fa",
    "Aston Martin": "#14b8a6",
    "Haas F1 Team": "#f8fafc",
    "Alpine": "#f472b6",
    "RB": "#818cf8",
    "Racing Bulls": "#818cf8",
    "Kick Sauber": "#22c55e",
    "Sauber": "#22c55e",
}


def _ensure_outputs() -> None:
    Path("outputs").mkdir(parents=True, exist_ok=True)


def _team_colour(team: str) -> str:
    return TEAM_COLOURS.get(str(team), "#d1d5db")


def make_fantasy_points_chart(
    summary: pd.DataFrame,
    output_path: str = "outputs/fantasy_expected_points.png",
) -> str:
    _ensure_outputs()

    chart_data = summary.sort_values("avg_fantasy_points", ascending=True).copy()
    colours = [_team_colour(team) for team in chart_data["Team"]]

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(chart_data["Driver"], chart_data["avg_fantasy_points"], color=colours)

    ax.set_title(
        "F1 Fantasy Simulation — Expected Points",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Expected fantasy points", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_fantasy_value_chart(
    summary: pd.DataFrame,
    output_path: str = "outputs/fantasy_value.png",
) -> str:
    _ensure_outputs()

    chart_data = summary[
        summary["fantasy_xppm"].notna()
        & (summary["fantasy_xppm"] > 0)
    ].copy()

    if chart_data.empty:
        raise ValueError(
            "No fantasy value data available. Fill data/fantasy_prices.csv first."
        )

    chart_data = chart_data.sort_values("fantasy_xppm", ascending=True)
    colours = [_team_colour(team) for team in chart_data["Team"]]

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(chart_data["Driver"], chart_data["fantasy_xppm"], color=colours)

    ax.set_title(
        "F1 Fantasy Simulation — Value",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Expected fantasy points per price unit", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path