from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
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


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None

    return number


def _fmt_weather(value: Any, suffix: str = "") -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.1f}{suffix}"


def _fmt_grid(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"P{int(round(number))}"


def _fmt_signed_3(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:+.3f}"


def _fmt_2(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.2f}"


def _fmt_percent_1(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number * 100:.1f}"


def make_expected_points_chart(
    summary: pd.DataFrame,
    output_path: str = "outputs/expected_points.png",
) -> str:
    _ensure_outputs()

    chart_data = summary.sort_values("avg_points", ascending=True).copy()
    colours = [_team_colour(team) for team in chart_data["Team"]]

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(chart_data["Driver"], chart_data["avg_points"], color=colours)

    ax.set_title(
        "F1 Simulation — Expected Race Points",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Expected points", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_probability_chart(
    summary: pd.DataFrame,
    output_path: str = "outputs/probabilities.png",
) -> str:
    _ensure_outputs()

    chart_data = summary.sort_values("avg_points", ascending=True).copy()
    y = np.arange(len(chart_data))

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(
        y - 0.25,
        chart_data["win_chance"] * 100,
        height=0.22,
        label="Win %",
    )
    ax.barh(
        y,
        chart_data["podium_chance"] * 100,
        height=0.22,
        label="Podium %",
    )
    ax.barh(
        y + 0.25,
        chart_data["points_chance"] * 100,
        height=0.22,
        label="Points %",
    )

    ax.set_yticks(y)
    ax.set_yticklabels(chart_data["Driver"])
    ax.set_xlabel("Probability %", color="white")
    ax.set_title(
        "F1 Simulation — Result Probabilities",
        color="white",
        fontsize=16,
        weight="bold",
    )

    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_position_matrix_chart(
    position_matrix: pd.DataFrame,
    output_path: str = "outputs/position_matrix.png",
) -> str:
    _ensure_outputs()

    matrix = position_matrix.copy()
    drivers = matrix["Driver"].astype(str).tolist()
    values = matrix.drop(columns=["Driver"]).astype(float).to_numpy()

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    image = ax.imshow(values, aspect="auto")

    ax.set_title(
        "F1 Simulation — Finishing Position Probability Matrix",
        color="white",
        fontsize=16,
        weight="bold",
    )

    ax.set_yticks(np.arange(len(drivers)))
    ax.set_yticklabels(drivers, color="white")

    position_cols = matrix.drop(columns=["Driver"]).columns.astype(str).tolist()
    ax.set_xticks(np.arange(values.shape[1]))
    ax.set_xticklabels(position_cols, color="white", rotation=45)

    ax.tick_params(colors="white")

    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            val = values[i, j]

            if val >= 8:
                text = f"{val:.0f}"
            elif val >= 1:
                text = f"{val:.1f}"
            else:
                text = ""

            if text:
                ax.text(
                    j,
                    i,
                    text,
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=7,
                )

    cbar = fig.colorbar(image, ax=ax)
    cbar.ax.tick_params(colors="white")
    cbar.set_label("Probability %", color="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_finish_distribution_chart(
    results: pd.DataFrame,
    summary: pd.DataFrame,
    output_path: str = "outputs/finish_distribution.png",
) -> str:
    _ensure_outputs()

    driver_order = (
        summary.sort_values("avg_points", ascending=False)["Driver"]
        .astype(str)
        .tolist()
    )

    data: list[np.ndarray] = []
    labels: list[str] = []

    for driver in driver_order:
        driver_rows = results.loc[
            results["Driver"].astype(str).eq(driver),
            ["position"],
        ].copy()

        positions = pd.to_numeric(
            driver_rows["position"],
            errors="coerce",
        ).dropna()

        if not positions.empty:
            data.append(positions.astype(float).to_numpy())
            labels.append(driver)

    if not data:
        raise ValueError("No finish position data available for distribution chart")

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    parts = ax.violinplot(
        data,
        showmeans=True,
        showmedians=True,
        showextrema=True,
    )

    bodies = cast(list[Any], parts.get("bodies", []))

    for body in bodies:
        body.set_alpha(0.65)

    ax.set_title(
        "F1 Simulation — Finish Position Distributions",
        color="white",
        fontsize=16,
        weight="bold",
    )

    ax.set_ylabel("Finishing position", color="white")
    ax.set_xticks(np.arange(1, len(labels) + 1))
    ax.set_xticklabels(labels, rotation=45, ha="right", color="white")
    ax.invert_yaxis()

    ax.tick_params(colors="white")
    ax.grid(axis="y", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_text_report_image(
    summary: pd.DataFrame,
    position_matrix: pd.DataFrame,
    metadata: dict,
    weather_summary: dict | None = None,
    output_path: str = "outputs/detailed_report.png",
) -> str:
    _ensure_outputs()

    report = summary.copy()

    report = report.sort_values(
        ["avg_fantasy_points", "avg_points"]
        if "avg_fantasy_points" in report.columns
        else ["avg_points"],
        ascending=[False, False]
        if "avg_fantasy_points" in report.columns
        else [False],
    ).copy()

    top_report = report.head(20).copy()

    lines = []

    title = (
        f"F1 Simulation Report — {metadata['year']} "
        f"{metadata['event']} ({metadata['session']})"
    )

    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")

    if weather_summary:
        lines.append("Weather")
        lines.append("-------")
        lines.append(
            f"Air {_fmt_weather(weather_summary.get('air_temp_avg'), '°C')} | "
            f"Track {_fmt_weather(weather_summary.get('track_temp_avg'), '°C')} | "
            f"Humidity {_fmt_weather(weather_summary.get('humidity_avg'), '%')} | "
            f"Wind {_fmt_weather(weather_summary.get('wind_speed_avg'), ' m/s')} | "
            f"Rain {'Yes' if weather_summary.get('rainfall_flag') else 'No'}"
        )
        lines.append(
            f"Modifiers: Chaos {float(weather_summary.get('chaos_factor', 1.0)):.2f}x | "
            f"Strategy {float(weather_summary.get('strategy_factor', 1.0)):.2f}x | "
            f"DNF {float(weather_summary.get('dnf_factor', 1.0)):.2f}x | "
            f"Tyre Deg {float(weather_summary.get('degradation_factor', 1.0)):.2f}x | "
            f"Uncertainty {float(weather_summary.get('uncertainty_factor', 1.0)):.2f}x"
        )

        if weather_summary.get("notes"):
            lines.append(str(weather_summary["notes"]))

        lines.append("")

    table = pd.DataFrame()

    table["DR"] = top_report["Driver"].astype(str)
    table["Team"] = top_report["Team"].astype(str).str.slice(0, 11)

    if "grid_position" in top_report.columns:
        table["Grid"] = top_report["grid_position"].map(_fmt_grid)
    else:
        table["Grid"] = top_report["avg_grid"].map(_fmt_grid)

    if "model_pace" in top_report.columns:
        table["Pace"] = top_report["model_pace"].map(_fmt_signed_3)

    table["AvgFin"] = top_report["avg_finish"].map(lambda x: _fmt_2(x))
    table["xPts"] = top_report["avg_points"].map(lambda x: _fmt_2(x))

    if "avg_fantasy_points" in top_report.columns:
        table["xFant"] = top_report["avg_fantasy_points"].map(lambda x: _fmt_2(x))

    table["Win%"] = top_report["win_chance"].map(_fmt_percent_1)
    table["Pod%"] = top_report["podium_chance"].map(_fmt_percent_1)
    table["Pts%"] = top_report["points_chance"].map(_fmt_percent_1)
    table["DNF%"] = top_report["dnf_chance"].map(_fmt_percent_1)

    if "deg_per_lap" in top_report.columns:
        table["Deg"] = top_report["deg_per_lap"].map(_fmt_signed_3)

    lines.append("Driver summary")
    lines.append("--------------")
    lines.append(table.to_string(index=False))
    lines.append("")

    matrix = position_matrix.copy()

    if not matrix.empty:
        driver_order = top_report["Driver"].astype(str).tolist()
        matrix = matrix[matrix["Driver"].astype(str).isin(driver_order)].copy()

        matrix["sort_order"] = matrix["Driver"].astype(str).map(
            {driver: index for index, driver in enumerate(driver_order)}
        )

        matrix = matrix.sort_values("sort_order").drop(columns=["sort_order"])

        wanted_position_cols = [
            col for col in [f"p{i}" for i in range(1, 13)]
            if col in matrix.columns
        ]

        matrix_display = matrix[["Driver"] + wanted_position_cols].copy()

        for col in wanted_position_cols:
            matrix_display[col] = matrix_display[col].map(lambda x: f"{float(x):.1f}")

        lines.append("Finish position probability matrix, %")
        lines.append("-------------------------------------")
        lines.append(matrix_display.to_string(index=False))
        lines.append("")

    lines.append("Only P1–P12 probabilities are shown to keep the image readable.")

    text = "\n".join(lines)

    line_count = len(lines)
    max_line_length = max(len(line) for line in lines)

    fig_width = min(max(max_line_length * 0.078, 10.5), 18)
    fig_height = min(max(line_count * 0.24, 7.0), 14)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")
    ax.axis("off")

    ax.text(
        0.01,
        0.99,
        text,
        va="top",
        ha="left",
        family="DejaVu Sans Mono",
        fontsize=9.8,
        color="#f8fafc",
        transform=ax.transAxes,
    )

    plt.savefig(
        output_path,
        dpi=200,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.25,
    )
    plt.close(fig)

    return output_path