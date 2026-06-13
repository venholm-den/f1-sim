from __future__ import annotations

from pathlib import Path
from typing import Any
from src.colours import get_team_colour

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DRY_COMPOUNDS = ["HARD", "MEDIUM", "SOFT"]

COMPOUND_DISPLAY = {
    "HARD": "Hard",
    "MEDIUM": "Medium",
    "SOFT": "Soft",
    "INTERMEDIATE": "Intermediate",
    "WET": "Wet",
}

RISK_ORDER = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}


def _ensure_outputs() -> None:
    Path("outputs/strategy").mkdir(parents=True, exist_ok=True)


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


def _fmt_grid(value: Any) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"P{int(round(number))}"


def _fmt_number(value: Any, decimals: int = 2) -> str:
    number = _to_float_or_none(value)

    if number is None:
        return "N/A"

    return f"{number:.{decimals}f}"


def _get_driver_compound_inventory(
    inventory: pd.DataFrame,
    driver: str,
    compound: str,
) -> dict[str, Any]:
    rows = inventory[
        (inventory["Driver"].astype(str) == str(driver))
        & (inventory["Compound"].astype(str).str.upper() == compound)
    ]

    if rows.empty:
        return {
            "estimated_new_sets_remaining": 0,
            "observed_stints": 0,
            "observed_laps": 0,
            "likely_new_sets_used": 0,
            "max_tyre_life_seen": np.nan,
        }

    row = rows.iloc[0]

    return {
        "estimated_new_sets_remaining": int(
            max(_to_float_or_none(row.get("estimated_new_sets_remaining")) or 0, 0)
        ),
        "observed_stints": int(max(_to_float_or_none(row.get("observed_stints")) or 0, 0)),
        "observed_laps": int(max(_to_float_or_none(row.get("observed_laps")) or 0, 0)),
        "likely_new_sets_used": int(max(_to_float_or_none(row.get("likely_new_sets_used")) or 0, 0)),
        "max_tyre_life_seen": row.get("max_tyre_life_seen"),
    }


def _driver_long_run_degradation(
    long_run_summary: pd.DataFrame,
    driver: str,
) -> float | None:
    if long_run_summary.empty:
        return None

    if "Driver" not in long_run_summary.columns:
        return None

    driver_runs = long_run_summary[
        long_run_summary["Driver"].astype(str) == str(driver)
    ].copy()

    if driver_runs.empty:
        return None

    if "degradation_per_lap" not in driver_runs.columns:
        return None

    driver_runs["degradation_per_lap"] = pd.to_numeric(
        driver_runs["degradation_per_lap"],
        errors="coerce",
    )

    if "laps_in_run" in driver_runs.columns:
        driver_runs["laps_in_run"] = pd.to_numeric(
            driver_runs["laps_in_run"],
            errors="coerce",
        ).fillna(1)

        valid = driver_runs["degradation_per_lap"].notna()

        if valid.sum() == 0:
            return None

        return float(
            np.average(
                driver_runs.loc[valid, "degradation_per_lap"],
                weights=driver_runs.loc[valid, "laps_in_run"],
            )
        )

    value = driver_runs["degradation_per_lap"].mean()

    if pd.isna(value):
        return None

    return float(value)


def _select_tyre_leg(
    compound: str,
    available_new_sets: dict[str, int],
    observed_stints: dict[str, int],
) -> tuple[str, bool]:
    display = COMPOUND_DISPLAY.get(compound, compound.title())

    if available_new_sets.get(compound, 0) > 0:
        available_new_sets[compound] -= 1
        return f"{display}(new)", False

    if observed_stints.get(compound, 0) > 0:
        return f"{display}(used)", True

    return f"{display}(used/unknown)", True


def _choose_base_strategy(
    grid_position: float | None,
    overtaking_difficulty: float,
    degradation_signal: float,
    fresh_hard: int,
    fresh_medium: int,
    fresh_soft: int,
    rainfall_flag: bool,
) -> tuple[list[str], str]:
    if rainfall_flag:
        return ["INTERMEDIATE", "WET"], "Weather-dependent wet/inter strategy"

    grid = grid_position if grid_position is not None else 12

    high_deg = degradation_signal >= 0.085
    hard_to_overtake = overtaking_difficulty >= 0.68
    easy_to_overtake = overtaking_difficulty <= 0.48

    if high_deg:
        if grid >= 13 and fresh_soft > 0 and easy_to_overtake:
            return ["SOFT", "MEDIUM", "HARD"], "High degradation; aggressive recovery 2-stop"
        if fresh_medium >= 2 and fresh_hard > 0:
            return ["MEDIUM", "HARD", "MEDIUM"], "High degradation; medium-hard-medium 2-stop"
        return ["SOFT", "MEDIUM", "HARD"], "High degradation; likely 2-stop"

    if grid <= 10:
        if fresh_medium > 0 and fresh_hard > 0:
            return ["MEDIUM", "HARD"], "Standard front/midfield 1-stop"
        if fresh_hard > 0 and fresh_medium == 0:
            return ["HARD", "MEDIUM"], "Medium-limited; likely hard-medium"
        return ["SOFT", "HARD"], "Limited fresh medium availability"

    if hard_to_overtake:
        if fresh_medium > 0 and fresh_hard > 0:
            return ["MEDIUM", "HARD"], "Track position important; conservative 1-stop"
        return ["SOFT", "HARD"], "Track position important; tyre-limited 1-stop"

    if grid >= 13:
        if fresh_hard > 0 and fresh_medium > 0:
            return ["HARD", "MEDIUM"], "Alternate strategy from lower grid"
        if fresh_soft > 0 and fresh_hard > 0:
            return ["SOFT", "HARD"], "Soft-start recovery attempt"
        return ["MEDIUM", "HARD"], "Default lower-grid 1-stop"

    return ["MEDIUM", "HARD"], "Default balanced 1-stop"


def _risk_label(score: float) -> str:
    if score >= 70:
        return "High"

    if score >= 35:
        return "Medium"

    return "Low"


def predict_driver_strategy(
    driver_row: pd.Series,
    inventory: pd.DataFrame,
    long_run_summary: pd.DataFrame,
    weather_summary: dict,
    track_profile: dict,
) -> dict[str, Any]:
    driver = str(driver_row["Driver"])
    team = str(driver_row.get("Team", "Unknown"))

    grid_position = _to_float_or_none(driver_row.get("grid_position"))
    avg_fantasy_points = _to_float_or_none(driver_row.get("avg_fantasy_points"))
    avg_race_points = _to_float_or_none(driver_row.get("avg_points"))
    win_chance = _to_float_or_none(driver_row.get("win_chance"))
    podium_chance = _to_float_or_none(driver_row.get("podium_chance"))

    overtaking_difficulty = float(track_profile.get("overtaking_difficulty", 0.55))
    rainfall_flag = bool(weather_summary.get("rainfall_flag", False))
    degradation_factor = float(weather_summary.get("degradation_factor", 1.0))

    compound_inventory = {
        compound: _get_driver_compound_inventory(inventory, driver, compound)
        for compound in DRY_COMPOUNDS
    }

    fresh_hard = compound_inventory["HARD"]["estimated_new_sets_remaining"]
    fresh_medium = compound_inventory["MEDIUM"]["estimated_new_sets_remaining"]
    fresh_soft = compound_inventory["SOFT"]["estimated_new_sets_remaining"]

    observed_stints = {
        compound: compound_inventory[compound]["observed_stints"]
        for compound in DRY_COMPOUNDS
    }

    degradation = _driver_long_run_degradation(long_run_summary, driver)

    if degradation is None:
        degradation_signal = 0.055 * degradation_factor
        degradation_note = "No reliable long-run degradation; using weather-adjusted default"
    else:
        degradation_signal = degradation * degradation_factor
        degradation_note = f"Long-run deg {_fmt_number(degradation_signal, 3)}s/lap"

    compounds, base_reason = _choose_base_strategy(
        grid_position=grid_position,
        overtaking_difficulty=overtaking_difficulty,
        degradation_signal=degradation_signal,
        fresh_hard=fresh_hard,
        fresh_medium=fresh_medium,
        fresh_soft=fresh_soft,
        rainfall_flag=rainfall_flag,
    )

    if rainfall_flag:
        predicted_strategy = "Weather-dependent: Intermediate/Wet as required"
        old_tyre_count = 0
        old_tyre_risk_score = 20
        old_tyre_risk = "Low"
        confidence = "Low"
        notes = "Wet or rain-affected session. Dry tyre strategy is less reliable."
    else:
        available_new_sets = {
            "HARD": fresh_hard,
            "MEDIUM": fresh_medium,
            "SOFT": fresh_soft,
        }

        legs: list[str] = []
        old_flags: list[bool] = []

        for compound in compounds:
            leg, is_old = _select_tyre_leg(
                compound=compound,
                available_new_sets=available_new_sets,
                observed_stints=observed_stints,
            )
            legs.append(leg)
            old_flags.append(is_old)

        predicted_strategy = " → ".join(legs)

        old_tyre_count = int(sum(old_flags))

        soft_quali_pressure = 0

        if fresh_soft <= 1:
            soft_quali_pressure = 20
        elif fresh_soft <= 2:
            soft_quali_pressure = 10

        hard_medium_shortage = 0

        if fresh_hard <= 0:
            hard_medium_shortage += 20

        if fresh_medium <= 0:
            hard_medium_shortage += 25

        old_tyre_risk_score = min(
            100,
            old_tyre_count * 38
            + soft_quali_pressure
            + hard_medium_shortage,
        )

        old_tyre_risk = _risk_label(old_tyre_risk_score)

        if old_tyre_risk == "Low" and fresh_hard > 0 and fresh_medium > 0:
            confidence = "High"
        elif old_tyre_risk == "High":
            confidence = "Medium"
        else:
            confidence = "Medium"

        notes = f"{base_reason}. {degradation_note}."

        if old_tyre_count > 0:
            notes += f" Strategy likely uses {old_tyre_count} old/unknown dry set(s)."

        if fresh_soft <= 1:
            notes += " Low fresh-soft buffer for quali/late race."

    return {
        "Driver": driver,
        "Team": team,
        "Grid": _fmt_grid(grid_position),
        "GridPosition": grid_position,
        "PredictedStrategy": predicted_strategy,
        "LikelyOldTyreUse": old_tyre_count,
        "OldTyreRiskScore": old_tyre_risk_score,
        "OldTyreRisk": old_tyre_risk,
        "FreshHardRemaining": fresh_hard,
        "FreshMediumRemaining": fresh_medium,
        "FreshSoftRemaining": fresh_soft,
        "ObservedHardStints": observed_stints["HARD"],
        "ObservedMediumStints": observed_stints["MEDIUM"],
        "ObservedSoftStints": observed_stints["SOFT"],
        "EstimatedDegPerLap": degradation_signal,
        "StrategyConfidence": confidence,
        "AvgFantasyPoints": avg_fantasy_points,
        "AvgRacePoints": avg_race_points,
        "WinChance": win_chance,
        "PodiumChance": podium_chance,
        "Notes": notes,
    }


def predict_tyre_strategies(
    summary: pd.DataFrame,
    inventory: pd.DataFrame,
    long_run_summary: pd.DataFrame,
    weather_summary: dict,
    track_profile: dict,
) -> pd.DataFrame:
    rows = []

    sorted_summary = summary.sort_values(
        ["grid_position", "avg_fantasy_points"],
        ascending=[True, False],
    ).copy()

    for _, row in sorted_summary.iterrows():
        rows.append(
            predict_driver_strategy(
                driver_row=row,
                inventory=inventory,
                long_run_summary=long_run_summary,
                weather_summary=weather_summary,
                track_profile=track_profile,
            )
        )

    output = pd.DataFrame(rows)

    if output.empty:
        return output

    output["RiskOrder"] = output["OldTyreRisk"].map(RISK_ORDER).fillna(99)

    output = output.sort_values(
        ["RiskOrder", "GridPosition"],
        ascending=[False, True],
    ).drop(columns=["RiskOrder"])

    return output.reset_index(drop=True)


def make_strategy_table_image(
    strategies: pd.DataFrame,
    output_path: str = "outputs/strategy/predicted_tyre_strategy.png",
    session: Any | None = None,
) -> str:
    _ensure_outputs()

    if strategies.empty:
        raise ValueError("No predicted tyre strategy data available")

    display = strategies.copy()
    display["GridPosition"] = pd.to_numeric(
        display.get("GridPosition"),
        errors="coerce",
    )
    display = display.sort_values("GridPosition", ascending=True).copy()

    def _int_or_zero(value: Any) -> int:
        number = _to_float_or_none(value)
        return int(number) if number is not None else 0

    title = "Predicted tyre strategy and old-tyre risk"
    subtitle_1 = "H/M/S = estimated fresh dry sets remaining."
    subtitle_2 = "Tyre availability is estimated, not official barcode data."

    header = (
        f"{'DR':<4} "
        f"{'Team':<12} "
        f"{'Grid':<5} "
        f"{'Strategy':<42} "
        f"{'Risk':<6} "
        f"{'H':>2} {'M':>2} {'S':>2} "
        f"{'Conf':<6}"
    )

    rows: list[tuple[str, str]] = []

    for _, row in display.iterrows():
        driver = str(row.get("Driver", ""))
        team = str(row.get("Team", ""))
        grid_value = _to_float_or_none(row.get("GridPosition"))
        grid = f"P{int(round(grid_value))}" if grid_value is not None else str(row.get("Grid", "N/A"))

        strategy = str(row.get("PredictedStrategy", "N/A"))
        risk = str(row.get("OldTyreRisk", "N/A"))
        confidence = str(row.get("StrategyConfidence", "N/A"))

        h = _int_or_zero(row.get("FreshHardRemaining"))
        m = _int_or_zero(row.get("FreshMediumRemaining"))
        s = _int_or_zero(row.get("FreshSoftRemaining"))

        line = (
            f"{driver:<4} "
            f"{team:<12.12} "
            f"{grid:<5} "
            f"{strategy:<42.42} "
            f"{risk:<6} "
            f"{h:>2} {m:>2} {s:>2} "
            f"{confidence:<6}"
        )

        rows.append((line, get_team_colour(team, session=session)))

    line_count = len(rows) + 7
    fig_height = max(7.0, line_count * 0.34)
    fig_width = 18

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")
    ax.axis("off")

    y = 0.98
    line_gap = 0.035

    def draw_line(
        text: str,
        colour: str = "#f8fafc",
        fontsize: float = 12.0,
        weight: str = "normal",
        extra_gap: float = 0.0,
    ) -> None:
        nonlocal y

        ax.text(
            0.015,
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

    draw_line(title, fontsize=15, weight="bold")
    draw_line("=" * len(title), fontsize=12, extra_gap=0.012)
    draw_line(header, fontsize=11.5, weight="bold")

    for line, colour in rows:
        draw_line(line, colour=colour, fontsize=11.5)

    y -= 0.015
    draw_line(subtitle_1, fontsize=10.5)
    draw_line(subtitle_2, fontsize=10.5)

    plt.savefig(
        output_path,
        dpi=200,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.25,
    )
    plt.close(fig)

    return output_path


def make_old_tyre_risk_chart(
    strategies: pd.DataFrame,
    output_path: str = "outputs/strategy/old_tyre_risk.png",
) -> str:
    _ensure_outputs()

    if strategies.empty:
        raise ValueError("No predicted tyre strategy data available")

    chart_data = strategies.sort_values("OldTyreRiskScore", ascending=True).copy()

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    ax.barh(chart_data["Driver"], chart_data["OldTyreRiskScore"])

    for _, row in chart_data.iterrows():
        ax.text(
            row["OldTyreRiskScore"] + 1,
            row["Driver"],
            str(row["OldTyreRisk"]),
            va="center",
            color="white",
            fontsize=9,
        )

    ax.set_title(
        "Predicted old-tyre usage risk",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Risk score", color="white")
    ax.set_xlim(0, 105)
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


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


def build_strategy_outputs(
    summary: pd.DataFrame,
    tyre_inventory_path: str,
    long_run_summary_path: str | None,
    weather_summary: dict,
    track_profile: dict,
) -> dict[str, str]:
    _ensure_outputs()

    if not tyre_inventory_path:
        print("Strategy skipped: no tyre inventory path available.")
        return {}

    inventory = _safe_read_csv(tyre_inventory_path)

    if inventory.empty:
        print("Strategy skipped: tyre inventory is empty.")
        return {}

    long_run_summary = _safe_read_csv(long_run_summary_path)

    if long_run_summary.empty:
        print(
            "Long-run summary is empty. "
            "Strategy model will use default degradation assumptions."
        )

    strategies = predict_tyre_strategies(
        summary=summary,
        inventory=inventory,
        long_run_summary=long_run_summary,
        weather_summary=weather_summary,
        track_profile=track_profile,
    )

    if strategies.empty:
        print("Strategy skipped: no strategy rows were generated.")
        return {}

    strategy_csv = "outputs/strategy/predicted_tyre_strategy.csv"
    strategies.to_csv(strategy_csv, index=False)

    strategy_image = make_strategy_table_image(strategies)
    risk_chart = make_old_tyre_risk_chart(strategies)

    return {
        "predicted_tyre_strategy_csv": strategy_csv,
        "predicted_tyre_strategy_chart": strategy_image,
        "old_tyre_risk_chart": risk_chart,
    }