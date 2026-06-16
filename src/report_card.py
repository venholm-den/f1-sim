from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from src.colours import get_team_colour


COMPOUND_COLOURS = {
    "HARD": "#f8fafc",
    "MEDIUM": "#facc15",
    "SOFT": "#ef4444",
    "INTERMEDIATE": "#22c55e",
    "WET": "#3b82f6",
    "UNKNOWN": "#9ca3af",
}

BACKGROUND_COLOUR = "#30343b"
TEXT_COLOUR = "#f8fafc"
MUTED_TEXT_COLOUR = "#d1d5db"


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


def _compound_colour(compound: str) -> str:
    return COMPOUND_COLOURS.get(str(compound).upper(), COMPOUND_COLOURS["UNKNOWN"])


def _fmt_number(value: Any, decimals: int = 2) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.{decimals}f}"


def _fmt_percent(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.1%}"


def _fmt_grid(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"P{int(round(number))}"


def _fmt_temp(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.1f}°C"


def _safe_read_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()

    file_path = Path(path)

    if not file_path.exists():
        return pd.DataFrame()

    if file_path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        return pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:
        print(f"Could not read CSV {path}: {exc}")
        return pd.DataFrame()


def _load_strategy_df(strategy_csv_path: str | None) -> pd.DataFrame:
    strategies = _safe_read_csv(strategy_csv_path)

    if strategies.empty:
        return strategies

    if "GridPosition" in strategies.columns:
        strategies["GridPosition"] = pd.to_numeric(
            strategies["GridPosition"],
            errors="coerce",
        )

    if "OldTyreRiskScore" in strategies.columns:
        strategies["OldTyreRiskScore"] = pd.to_numeric(
            strategies["OldTyreRiskScore"],
            errors="coerce",
        )

    return strategies



def _strategy_confidence_value(row: pd.Series) -> str:
    for column in ["strategy_confidence", "StrategyConfidenceLabel", "StrategyConfidence"]:
        if column in row.index and pd.notna(row.get(column)):
            text = str(row.get(column)).strip()
            if text:
                return text
    return "N/A"


def _strategy_source_value(row: pd.Series) -> str:
    for column in ["strategy_source", "StrategySource"]:
        if column in row.index and pd.notna(row.get(column)):
            text = str(row.get(column)).strip()
            if text:
                return text
    return "model_estimate"


def _strategy_risk_reason_value(row: pd.Series) -> str:
    for column in ["strategy_risk_reason", "StrategyRiskReason", "confidence_reason", "ConfidenceReason"]:
        if column in row.index and pd.notna(row.get(column)):
            text = str(row.get(column)).strip()
            if text:
                return text
    return "Tyre availability is estimated, not official FIA/Pirelli allocation data."


def _strategy_compound(segment: str) -> str:
    text = str(segment).strip().upper()

    if "SOFT" in text:
        return "SOFT"

    if "MEDIUM" in text:
        return "MEDIUM"

    if "HARD" in text:
        return "HARD"

    if "INTER" in text:
        return "INTERMEDIATE"

    if "WET" in text:
        return "WET"

    return "UNKNOWN"


def _parse_strategy(strategy_text: str) -> list[str]:
    text = str(strategy_text).strip()

    if not text:
        return ["Unknown"]

    if "→" in text:
        return [part.strip() for part in text.split("→") if part.strip()]

    if "->" in text:
        return [part.strip() for part in text.split("->") if part.strip()]

    return [text]


def _headline_notes(
    summary: pd.DataFrame,
    strategies: pd.DataFrame,
) -> list[str]:
    notes: list[str] = []

    if summary.empty:
        return ["No summary data available."]

    top_pick = summary.sort_values("avg_fantasy_points", ascending=False).iloc[0]
    notes.append(
        f"Top projection: {top_pick['Driver']} ({top_pick['Team']}) "
        f"— xFant {top_pick['avg_fantasy_points']:.2f}"
    )

    if "fantasy_xppm" in summary.columns and summary["fantasy_xppm"].notna().any():
        best_value = summary[summary["fantasy_xppm"].notna()].sort_values(
            "fantasy_xppm",
            ascending=False,
        ).iloc[0]

        notes.append(
            f"Best value: {best_value['Driver']} — "
            f"xPPM {best_value['fantasy_xppm']:.2f}"
        )

    if "dnf_chance" in summary.columns:
        safe_pool = summary.sort_values(
            ["dnf_chance", "avg_fantasy_points"],
            ascending=[True, False],
        )

        safe_pick = safe_pool.iloc[0]
        notes.append(
            f"Safest base: {safe_pick['Driver']} — "
            f"DNF {safe_pick['dnf_chance']:.1%}"
        )

    if not strategies.empty and "OldTyreRiskScore" in strategies.columns:
        high_risk = strategies.sort_values("OldTyreRiskScore", ascending=False).iloc[0]
        notes.append(
            f"Highest tyre risk: {high_risk['Driver']} — "
            f"{high_risk.get('OldTyreRisk', 'N/A')} "
            f"(confidence {_strategy_confidence_value(high_risk)})"
        )

    return notes


def _draw_text_block(
    ax: Any,
    lines: list[str],
    x: float = 0.01,
    y: float = 0.99,
    fontsize: float = 11.5,
    colour: str = TEXT_COLOUR,
) -> None:
    ax.text(
        x,
        y,
        "\n".join(lines),
        va="top",
        ha="left",
        family="DejaVu Sans Mono",
        fontsize=fontsize,
        color=colour,
        transform=ax.transAxes,
    )


def _draw_driver_table(
    ax: Any,
    title: str,
    header: str,
    rows: list[tuple[str, str]],
    session: Any | None = None,
    x: float = 0.01,
    y_start: float = 0.99,
    fontsize: float = 12.0,
    line_gap: float = 0.064,
) -> None:
    y = y_start

    def draw(
        text: str,
        colour: str = TEXT_COLOUR,
        weight: str = "normal",
        extra_gap: float = 0.0,
    ) -> None:
        nonlocal y

        ax.text(
            x,
            y,
            text,
            va="top",
            ha="left",
            family="DejaVu Sans Mono",
            fontsize=fontsize,
            color=colour,
            fontweight=weight,
            transform=ax.transAxes,
        )

        y -= line_gap + extra_gap

    draw(title, weight="bold", extra_gap=0.004)
    draw("-" * len(title), extra_gap=0.020)
    draw(header, weight="bold", extra_gap=0.006)

    for row_text, team in rows:
        colour = get_team_colour(team, session=session)
        draw(row_text, colour=colour)


def _build_top_rows(summary: pd.DataFrame) -> tuple[str, list[tuple[str, str]]]:
    top_display = summary.sort_values(
        "avg_fantasy_points",
        ascending=False,
    ).head(8).copy()

    header = (
        f"{'DR':<4} "
        f"{'Grid':<5} "
        f"{'xFant':>6} "
        f"{'xRace':>6} "
        f"{'Win%':>6} "
        f"{'Pod%':>6} "
        f"{'xPPM':>6}"
    )

    rows: list[tuple[str, str]] = []

    for _, row in top_display.iterrows():
        team = str(row.get("Team", ""))
        grid = _fmt_grid(row.get("grid_position", row.get("avg_grid")))
        xppm = _fmt_number(row.get("fantasy_xppm"), 2)

        line = (
            f"{str(row.get('Driver', '')):<4} "
            f"{grid:<5} "
            f"{_fmt_number(row.get('avg_fantasy_points'), 2):>6} "
            f"{_fmt_number(row.get('avg_points'), 2):>6} "
            f"{_fmt_percent(row.get('win_chance')):>6} "
            f"{_fmt_percent(row.get('podium_chance')):>6} "
            f"{xppm:>6}"
        )

        rows.append((line, team))

    return header, rows


def _build_value_rows(summary: pd.DataFrame) -> tuple[str, list[tuple[str, str]]]:
    if "fantasy_xppm" in summary.columns and summary["fantasy_xppm"].notna().any():
        value_display = summary[summary["fantasy_xppm"].notna()].copy()
        value_display = value_display.sort_values(
            ["fantasy_xppm", "avg_fantasy_points"],
            ascending=[False, False],
        ).head(6)
    else:
        value_display = summary.sort_values(
            "avg_fantasy_points",
            ascending=False,
        ).head(6).copy()

    header = (
        f"{'DR':<4} "
        f"{'Price':>6} "
        f"{'xFant':>6} "
        f"{'xPPM':>6} "
        f"{'Pts%':>6}"
    )

    rows: list[tuple[str, str]] = []

    for _, row in value_display.iterrows():
        team = str(row.get("Team", ""))

        line = (
            f"{str(row.get('Driver', '')):<4} "
            f"{_fmt_number(row.get('fantasy_price'), 1):>6} "
            f"{_fmt_number(row.get('avg_fantasy_points'), 2):>6} "
            f"{_fmt_number(row.get('fantasy_xppm'), 2):>6} "
            f"{_fmt_percent(row.get('points_chance')):>6}"
        )

        rows.append((line, team))

    return header, rows


def _build_strategy_rows(
    strategies: pd.DataFrame,
) -> tuple[str, list[tuple[str, str]]]:
    header = (
        f"{'DR':<4} "
        f"{'Grid':<5} "
        f"{'Risk':<6} "
        f"{'Conf':<6} "
        f"{'Strategy':<36}"
    )

    if strategies.empty:
        return header, [("No tyre strategy data available", "")]

    strategy_display = strategies.copy()

    if "OldTyreRiskScore" in strategy_display.columns:
        strategy_display = strategy_display.sort_values(
            ["OldTyreRiskScore", "GridPosition"],
            ascending=[False, True],
        )
    elif "GridPosition" in strategy_display.columns:
        strategy_display = strategy_display.sort_values("GridPosition")

    strategy_display = strategy_display.head(6)

    rows: list[tuple[str, str]] = []

    for _, row in strategy_display.iterrows():
        team = str(row.get("Team", ""))
        grid = str(row.get("Grid", _fmt_grid(row.get("GridPosition"))))
        risk = str(row.get("OldTyreRisk", "N/A"))
        confidence = _strategy_confidence_value(row)
        strategy = str(row.get("PredictedStrategy", "N/A"))

        line = (
            f"{str(row.get('Driver', '')):<4} "
            f"{grid:<5} "
            f"{risk:<6} "
            f"{confidence:<6} "
            f"{strategy:<36.36}"
        )

        rows.append((line, team))

    return header, rows


def make_race_dashboard(
    summary: pd.DataFrame,
    metadata: dict,
    weather_summary: dict,
    track_profile: dict,
    overtaking_difficulty: float,
    strategy_csv_path: str | None = None,
    output_path: str = "outputs/report/race_dashboard.png",
    session: Any | None = None,
) -> str:
    _ensure_outputs()

    strategies = _load_strategy_df(strategy_csv_path)
    notes = _headline_notes(summary, strategies)

    red_flag_chance = (
        float(summary["red_flag_chance"].mean())
        if "red_flag_chance" in summary.columns
        else 0.0
    )

    fig = plt.figure(figsize=(18, 10))
    fig.patch.set_facecolor(BACKGROUND_COLOUR)

    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[0.95, 1.25],
        height_ratios=[0.85, 1.15],
        hspace=0.16,
        wspace=0.08,
    )

    ax_meta = fig.add_subplot(gs[0, 0])
    ax_value = fig.add_subplot(gs[1, 0])
    ax_top = fig.add_subplot(gs[0, 1])
    ax_strategy = fig.add_subplot(gs[1, 1])

    for ax in [ax_meta, ax_value, ax_top, ax_strategy]:
        ax.set_facecolor(BACKGROUND_COLOUR)
        ax.axis("off")

    meta_lines = [
        f"F1 Fantasy Race Dashboard — {metadata['year']} {metadata['event']}",
        "=" * 72,
        "",
        f"Session Used: {metadata['session']}",
        f"Track Profile: {track_profile.get('event', metadata['event'])}",
        f"Overtaking Difficulty: {overtaking_difficulty:.2f}",
        f"Safety Car Base: {_fmt_percent(track_profile.get('safety_car_chance'))}",
        (
            "Red Flag Chance: "
            f"{red_flag_chance:.1%} "
            f"(base {_fmt_percent(track_profile.get('red_flag_base_chance'))})"
        ),
        "",
        "Weather",
        "-------",
        (
            f"Air {_fmt_temp(weather_summary.get('air_temp_avg'))} | "
            f"Track {_fmt_temp(weather_summary.get('track_temp_avg'))} | "
            f"Wind {_fmt_number(weather_summary.get('wind_speed_avg'), 1)} m/s | "
            f"Rain {'Yes' if weather_summary.get('rainfall_flag') else 'No'}"
        ),
        (
            f"Chaos {float(weather_summary.get('chaos_factor', 1.0)):.2f}x | "
            f"Strategy {float(weather_summary.get('strategy_factor', 1.0)):.2f}x | "
            f"DNF {float(weather_summary.get('dnf_factor', 1.0)):.2f}x | "
            f"Tyre Deg {float(weather_summary.get('degradation_factor', 1.0)):.2f}x"
        ),
        "",
        "Headlines",
        "---------",
    ]

    for note in notes:
        meta_lines.append(f"- {note}")

    if track_profile.get("notes"):
        meta_lines.append("")
        meta_lines.append(f"Track Note: {track_profile['notes']}")

    if weather_summary.get("notes"):
        meta_lines.append(f"Weather Note: {weather_summary['notes']}")

    _draw_text_block(
        ax=ax_meta,
        lines=meta_lines,
        fontsize=11.2,
    )

    top_header, top_rows = _build_top_rows(summary)
    _draw_driver_table(
        ax=ax_top,
        title="Top Projected Fantasy Picks",
        header=top_header,
        rows=top_rows,
        session=session,
        fontsize=12.0,
        line_gap=0.068,
    )

    value_header, value_rows = _build_value_rows(summary)
    _draw_driver_table(
        ax=ax_value,
        title="Value / Efficiency Watch",
        header=value_header,
        rows=value_rows,
        session=session,
        fontsize=11.6,
        line_gap=0.070,
    )

    ax_value.text(
        0.01,
        0.10,
        "xPPM = expected fantasy points per price unit.",
        va="top",
        ha="left",
        family="DejaVu Sans Mono",
        fontsize=10.8,
        color=MUTED_TEXT_COLOUR,
        transform=ax_value.transAxes,
    )

    strategy_header, strategy_rows = _build_strategy_rows(strategies)
    _draw_driver_table(
        ax=ax_strategy,
        title="Tyre Strategy Watchlist",
        header=strategy_header,
        rows=strategy_rows,
        session=session,
        fontsize=11.6,
        line_gap=0.070,
    )

    ax_strategy.text(
        0.01,
        0.10,
        "Tyre strategy and tyre availability are estimated from FastF1 stint/lap data, not official FIA/Pirelli allocation data.",
        va="top",
        ha="left",
        family="DejaVu Sans Mono",
        fontsize=10.8,
        color=MUTED_TEXT_COLOUR,
        transform=ax_strategy.transAxes,
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


def make_fantasy_risk_reward_chart(
    summary: pd.DataFrame,
    strategy_csv_path: str | None = None,
    output_path: str = "outputs/report/fantasy_risk_reward.png",
    session: Any | None = None,
) -> str:
    _ensure_outputs()

    chart_data = summary.copy()
    strategies = _load_strategy_df(strategy_csv_path)

    if not strategies.empty:
        merge_cols = [
            col
            for col in ["Driver", "OldTyreRiskScore", "OldTyreRisk"]
            if col in strategies.columns
        ]

        if "Driver" in merge_cols:
            chart_data = chart_data.merge(
                strategies[merge_cols].drop_duplicates(subset=["Driver"]),
                on="Driver",
                how="left",
            )

    if "OldTyreRiskScore" not in chart_data.columns:
        chart_data["OldTyreRiskScore"] = 0.0

    if "dnf_chance" not in chart_data.columns:
        chart_data["dnf_chance"] = 0.0

    if "points_chance" not in chart_data.columns:
        chart_data["points_chance"] = 0.0

    chart_data["OldTyreRiskScore"] = pd.to_numeric(
        chart_data["OldTyreRiskScore"],
        errors="coerce",
    ).fillna(0.0)

    chart_data["dnf_chance"] = pd.to_numeric(
        chart_data["dnf_chance"],
        errors="coerce",
    ).fillna(0.0)

    chart_data["points_chance"] = pd.to_numeric(
        chart_data["points_chance"],
        errors="coerce",
    ).fillna(0.0)

    chart_data["avg_fantasy_points"] = pd.to_numeric(
        chart_data["avg_fantasy_points"],
        errors="coerce",
    )

    if "win_chance" in chart_data.columns:
        chart_data["win_chance"] = pd.to_numeric(
            chart_data["win_chance"],
            errors="coerce",
        ).fillna(0.0)
    else:
        chart_data["win_chance"] = 0.0

    chart_data["RiskScore"] = (
        chart_data["OldTyreRiskScore"] * 0.55
        + chart_data["dnf_chance"] * 100 * 0.80
        + (1 - chart_data["points_chance"]) * 18
    )

    chart_data["BubbleSize"] = 140 + (chart_data["win_chance"] * 850)

    fig, ax = plt.subplots(figsize=(13, 9))
    fig.patch.set_facecolor(BACKGROUND_COLOUR)
    ax.set_facecolor(BACKGROUND_COLOUR)

    for _, row in chart_data.iterrows():
        team = str(row.get("Team", ""))

        ax.scatter(
            row["RiskScore"],
            row["avg_fantasy_points"],
            s=row["BubbleSize"],
            alpha=0.75,
            color=get_team_colour(team, session=session),
            edgecolors="white",
            linewidths=0.8,
        )

        ax.text(
            row["RiskScore"] + 0.8,
            row["avg_fantasy_points"] + 0.06,
            str(row["Driver"]),
            color=get_team_colour(team, session=session),
            fontsize=9,
            weight="bold",
        )

    ax.set_title(
        "Fantasy Risk / Reward Map",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Combined risk score", color="white")
    ax.set_ylabel("Expected fantasy points", color="white")
    ax.tick_params(colors="white")
    ax.grid(alpha=0.25)

    if not chart_data.empty:
        median_risk = float(chart_data["RiskScore"].median())
        median_reward = float(chart_data["avg_fantasy_points"].median())

        ax.axvline(median_risk, color="#9ca3af", linestyle="--", alpha=0.7)
        ax.axhline(median_reward, color="#9ca3af", linestyle="--", alpha=0.7)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_tyre_strategy_timeline(
    strategy_csv_path: str,
    output_path: str = "outputs/report/tyre_strategy_timeline.png",
    session: Any | None = None,
) -> str:
    _ensure_outputs()

    strategies = _load_strategy_df(strategy_csv_path)

    if strategies.empty:
        raise ValueError("No tyre strategy data available")

    if "GridPosition" in strategies.columns:
        plot_data = strategies.sort_values("GridPosition", ascending=True).copy()
    else:
        plot_data = strategies.copy()

    plot_data = plot_data.head(20).reset_index(drop=True)

    n_drivers = len(plot_data)
    fig_height = max(9, 0.52 * n_drivers + 2.0)

    fig, ax = plt.subplots(figsize=(16, fig_height))
    fig.patch.set_facecolor(BACKGROUND_COLOUR)
    ax.set_facecolor(BACKGROUND_COLOUR)

    legend_handles = [
        Patch(color=_compound_colour("SOFT"), label="Soft"),
        Patch(color=_compound_colour("MEDIUM"), label="Medium"),
        Patch(color=_compound_colour("HARD"), label="Hard"),
        Patch(color=_compound_colour("INTERMEDIATE"), label="Intermediate"),
        Patch(color=_compound_colour("WET"), label="Wet"),
    ]

    max_segments = 0

    for idx, row in plot_data.iterrows():
        strategy_text = str(row.get("PredictedStrategy", "Unknown"))
        segments = _parse_strategy(strategy_text)
        max_segments = max(max_segments, len(segments))

        y = idx
        x = 0.0
        segment_width = 1.6

        for segment in segments:
            compound = _strategy_compound(segment)

            ax.barh(
                y,
                segment_width,
                left=x,
                height=0.58,
                color=_compound_colour(compound),
                edgecolor="#111827",
                linewidth=1.0,
            )

            text_color = "#111827" if compound in {"MEDIUM", "HARD"} else "white"

            ax.text(
                x + segment_width / 2,
                y,
                segment,
                ha="center",
                va="center",
                fontsize=8.5,
                color=text_color,
            )

            x += segment_width + 0.18

        risk_text = str(row.get("OldTyreRisk", "N/A"))
        grid_text = str(row.get("Grid", "N/A"))

        ax.text(
            x + 0.22,
            y,
            f"Risk: {risk_text}",
            va="center",
            ha="left",
            fontsize=9,
            color=get_team_colour(str(row.get("Team", "")), session=session),
            weight="bold",
        )

        ax.text(
            -0.22,
            y,
            grid_text,
            va="center",
            ha="right",
            fontsize=9,
            color=MUTED_TEXT_COLOUR,
        )

    y_labels = [str(driver) for driver in plot_data["Driver"].tolist()]
    y_colours = [
        get_team_colour(str(team), session=session)
        for team in plot_data["Team"].tolist()
    ]

    ax.set_yticks(np.arange(n_drivers))
    ax.set_yticklabels(y_labels)
    ax.invert_yaxis()

    for tick_label, colour in zip(ax.get_yticklabels(), y_colours):
        tick_label.set_color(colour)
        tick_label.set_fontweight("bold")

    ax.set_xticks([])
    ax.tick_params(colors="white")
    ax.set_title(
        "Predicted Tyre Strategy Timeline",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Predicted stint sequence", color="white")

    ax.legend(
        handles=legend_handles,
        facecolor=BACKGROUND_COLOUR,
        edgecolor="#6b7280",
        labelcolor="white",
        loc="upper right",
    )

    ax.set_xlim(-0.9, max_segments * 1.85 + 3.2)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def build_report_outputs(
    summary: pd.DataFrame,
    metadata: dict,
    weather_summary: dict,
    track_profile: dict,
    overtaking_difficulty: float,
    strategy_csv_path: str | None = None,
    session: Any | None = None,
) -> dict[str, str]:
    _ensure_outputs()

    outputs: dict[str, str] = {}

    outputs["dashboard"] = make_race_dashboard(
        summary=summary,
        metadata=metadata,
        weather_summary=weather_summary,
        track_profile=track_profile,
        overtaking_difficulty=overtaking_difficulty,
        strategy_csv_path=strategy_csv_path,
        session=session,
    )

    outputs["risk_reward"] = make_fantasy_risk_reward_chart(
        summary=summary,
        strategy_csv_path=strategy_csv_path,
        session=session,
    )

    strategies = _load_strategy_df(strategy_csv_path)

    if not strategies.empty:
        outputs["tyre_timeline"] = make_tyre_strategy_timeline(
            strategy_csv_path,
            session=session,
        )

    return outputs