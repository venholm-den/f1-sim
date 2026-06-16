from __future__ import annotations

from pathlib import Path
from typing import Any
from src.colours import get_team_colour

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch


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


def _confidence_from_risk(risk: str, rainfall_flag: bool = False) -> str:
    if rainfall_flag:
        return "Low"
    if risk == "Low":
        return "High"
    if risk == "High":
        return "Medium"
    return "Medium"


def _strategy_risk_reason(
    old_tyre_count: int,
    old_tyre_risk: str,
    rainfall_flag: bool,
) -> str:
    if rainfall_flag:
        return (
            "Weather/rain flag is active, so dry tyre strategy is uncertain. "
            "Tyre availability remains estimated rather than official FIA/Pirelli data."
        )

    if old_tyre_count > 0:
        return (
            f"Strategy likely uses {old_tyre_count} old/unknown dry set(s). "
            "Tyre availability is estimated from FastF1 lap/stint data, not official FIA/Pirelli allocation data."
        )

    if old_tyre_risk == "Low":
        return (
            "Model found enough estimated fresh dry tyre availability for the selected strategy. "
            "Confidence is still capped because inventory is not official FIA/Pirelli barcode data."
        )

    return (
        "Strategy depends on estimated tyre inventory and modelled degradation assumptions. "
        "It is not based on official FIA/Pirelli tyre allocation data."
    )



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
            "tyre_data_source": "unknown",
            "tyre_confidence": "Low",
            "inventory_confidence": "Low",
            "tyre_confidence_reason": "No tyre inventory row was available for this driver/compound.",
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
        "tyre_data_source": row.get("tyre_data_source", "fastf1_lap_stint_data"),
        "tyre_confidence": row.get("tyre_confidence", "Medium"),
        "inventory_confidence": row.get("inventory_confidence", row.get("tyre_confidence", "Medium")),
        "tyre_confidence_reason": row.get(
            "tyre_confidence_reason",
            "Estimated from FastF1 lap/stint data, not official FIA/Pirelli allocation data.",
        ),
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


def _strategy_type_from_reason(
    base_reason: str,
    grid_position: float | None,
    degradation_signal: float,
    rainfall_flag: bool,
) -> str:
    reason = str(base_reason).lower()
    grid = grid_position if grid_position is not None else 12

    if rainfall_flag or "weather" in reason:
        return "weather_dependent"
    if "aggressive" in reason or "recovery" in reason:
        return "aggressive_recovery"
    if "alternate" in reason or grid >= 13:
        return "alternate"
    if "conservative" in reason or "track position" in reason:
        return "conservative"
    if "2-stop" in reason or degradation_signal >= 0.085:
        return "high_degradation_two_stop"
    if "limited" in reason or "tyre-limited" in reason:
        return "tyre_limited"
    if grid <= 10:
        return "front_field_standard"
    return "balanced"


def _allocate_compound_sequence(
    compounds: list[str],
    fresh_hard: int,
    fresh_medium: int,
    fresh_soft: int,
    observed_stints: dict[str, int],
) -> tuple[str, int]:
    available_new_sets = {
        "HARD": int(max(fresh_hard, 0)),
        "MEDIUM": int(max(fresh_medium, 0)),
        "SOFT": int(max(fresh_soft, 0)),
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

    return " → ".join(legs), int(sum(old_flags))


def _alternative_compounds(
    primary_compounds: list[str],
    grid_position: float | None,
    degradation_signal: float,
    fresh_hard: int,
    fresh_medium: int,
    fresh_soft: int,
    overtaking_difficulty: float,
    rainfall_flag: bool,
) -> list[str]:
    if rainfall_flag:
        return []

    primary = [compound.upper() for compound in primary_compounds]
    grid = grid_position if grid_position is not None else 12

    if len(primary) >= 3:
        if fresh_medium > 0 and fresh_hard > 0:
            return ["MEDIUM", "HARD"]
        return ["HARD", "MEDIUM"]

    if degradation_signal >= 0.075:
        if fresh_soft > 0 and fresh_medium > 0 and fresh_hard > 0:
            return ["SOFT", "MEDIUM", "HARD"]
        if fresh_medium >= 2 and fresh_hard > 0:
            return ["MEDIUM", "HARD", "MEDIUM"]

    if primary == ["MEDIUM", "HARD"]:
        if grid >= 13 and fresh_hard > 0:
            return ["HARD", "MEDIUM"]
        if fresh_soft > 0 and fresh_hard > 0 and overtaking_difficulty <= 0.55:
            return ["SOFT", "HARD"]
        return ["HARD", "MEDIUM"]

    if primary == ["HARD", "MEDIUM"]:
        if fresh_medium > 0 and fresh_hard > 0:
            return ["MEDIUM", "HARD"]
        if fresh_soft > 0 and fresh_hard > 0:
            return ["SOFT", "HARD"]

    if fresh_medium > 0 and fresh_hard > 0:
        return ["MEDIUM", "HARD"]

    if fresh_soft > 0 and fresh_hard > 0:
        return ["SOFT", "HARD"]

    return ["HARD", "MEDIUM"]


def _expected_stops(compounds: list[str], rainfall_flag: bool) -> int | None:
    if rainfall_flag:
        return None
    return int(max(len(compounds) - 1, 0))


def _order_strategy_columns(strategies: pd.DataFrame) -> pd.DataFrame:
    if strategies is None or strategies.empty:
        return strategies

    preferred = [
        "Driver",
        "Team",
        "Grid",
        "GridPosition",
        "PredictedStrategy",
        "primary_strategy",
        "alternative_strategy",
        "expected_stops",
        "strategy_type",
        "strategy_source",
        "strategy_confidence",
        "confidence_reason",
        "risk_level",
        "strategy_risk_level",
        "strategy_risk_reason",
        "tyre_availability_risk",
        "strategy_reason",
        "LikelyOldTyreUse",
        "OldTyreRiskScore",
        "OldTyreRisk",
        "FreshHardRemaining",
        "FreshMediumRemaining",
        "FreshSoftRemaining",
        "ObservedHardStints",
        "ObservedMediumStints",
        "ObservedSoftStints",
        "EstimatedDegPerLap",
        "inventory_confidence",
        "tyre_data_source",
        "tyre_confidence_reason",
        "AvgFantasyPoints",
        "AvgRacePoints",
        "WinChance",
        "PodiumChance",
        "Notes",
    ]

    ordered = [column for column in preferred if column in strategies.columns]
    remaining = [column for column in strategies.columns if column not in ordered]

    return strategies[ordered + remaining].copy()


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

    inventory_confidences = [
        str(compound_inventory[compound].get("inventory_confidence", "Medium"))
        for compound in DRY_COMPOUNDS
    ]

    if "Low" in inventory_confidences:
        inventory_confidence = "Low"
    elif "Medium" in inventory_confidences:
        inventory_confidence = "Medium"
    else:
        inventory_confidence = "High"

    tyre_data_source = "fastf1_lap_stint_data"
    tyre_confidence_reason = (
        "Tyre inventory is estimated from FastF1 lap/stint data, not official FIA/Pirelli allocation data."
    )

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

    strategy_type = _strategy_type_from_reason(
        base_reason=base_reason,
        grid_position=grid_position,
        degradation_signal=degradation_signal,
        rainfall_flag=rainfall_flag,
    )
    expected_stops = _expected_stops(compounds, rainfall_flag=rainfall_flag)

    if rainfall_flag:
        predicted_strategy = "Weather-dependent: Intermediate/Wet as required"
        old_tyre_count = 0
        old_tyre_risk_score = 20
        old_tyre_risk = "Low"
        confidence = "Low"
        notes = "Wet or rain-affected session. Dry tyre strategy is less reliable."
        alternative_strategy = "Dry fallback unavailable until weather is clearer"
        strategy_reason = notes
    else:
        predicted_strategy, old_tyre_count = _allocate_compound_sequence(
            compounds=compounds,
            fresh_hard=fresh_hard,
            fresh_medium=fresh_medium,
            fresh_soft=fresh_soft,
            observed_stints=observed_stints,
        )

        alternative_compounds = _alternative_compounds(
            primary_compounds=compounds,
            grid_position=grid_position,
            degradation_signal=degradation_signal,
            fresh_hard=fresh_hard,
            fresh_medium=fresh_medium,
            fresh_soft=fresh_soft,
            overtaking_difficulty=overtaking_difficulty,
            rainfall_flag=rainfall_flag,
        )
        alternative_strategy, _ = _allocate_compound_sequence(
            compounds=alternative_compounds,
            fresh_hard=fresh_hard,
            fresh_medium=fresh_medium,
            fresh_soft=fresh_soft,
            observed_stints=observed_stints,
        )

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

        strategy_reason = (
            f"{base_reason}. {degradation_note}. "
            f"Estimated fresh sets remaining: H{fresh_hard}/M{fresh_medium}/S{fresh_soft}."
        )

    strategy_risk_reason = _strategy_risk_reason(
        old_tyre_count=old_tyre_count,
        old_tyre_risk=old_tyre_risk,
        rainfall_flag=rainfall_flag,
    )

    confidence_reason = (
        f"Strategy confidence is {confidence}. "
        f"Inventory confidence is {inventory_confidence}. "
        f"{strategy_risk_reason}"
    )

    return {
        "Driver": driver,
        "Team": team,
        "Grid": _fmt_grid(grid_position),
        "GridPosition": grid_position,
        "PredictedStrategy": predicted_strategy,
        "primary_strategy": predicted_strategy,
        "PrimaryStrategy": predicted_strategy,
        "alternative_strategy": alternative_strategy,
        "AlternativeStrategy": alternative_strategy,
        "expected_stops": expected_stops,
        "ExpectedStops": expected_stops,
        "strategy_type": strategy_type,
        "StrategyType": strategy_type,
        "strategy_reason": strategy_reason,
        "StrategyReason": strategy_reason,
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
        "strategy_source": "model_estimate",
        "StrategySource": "model_estimate",
        "tyre_data_source": tyre_data_source,
        "TyreDataSource": tyre_data_source,
        "inventory_confidence": inventory_confidence,
        "InventoryConfidence": inventory_confidence,
        "strategy_confidence": confidence,
        "StrategyConfidenceLabel": confidence,
        "confidence_reason": confidence_reason,
        "ConfidenceReason": confidence_reason,
        "risk_level": old_tyre_risk,
        "RiskLevel": old_tyre_risk,
        "strategy_risk_level": old_tyre_risk,
        "StrategyRiskLevel": old_tyre_risk,
        "strategy_risk_reason": strategy_risk_reason,
        "StrategyRiskReason": strategy_risk_reason,
        "tyre_availability_risk": old_tyre_risk,
        "TyreAvailabilityRisk": old_tyre_risk,
        "tyre_confidence_reason": tyre_confidence_reason,
        "TyreConfidenceReason": tyre_confidence_reason,
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

    return _order_strategy_columns(output.reset_index(drop=True))



def make_strategy_table_image(
    strategies: pd.DataFrame,
    output_path: str = "outputs/strategy/predicted_tyre_strategy.png",
    session: Any | None = None,
) -> str:
    """
    Builds a visual tyre-strategy report image.

    The image is designed to be readable in Discord/GitHub without opening the CSV:
    - compound-coloured stint blocks
    - expected stop count
    - confidence and risk labels
    - history-adjustment marker where available
    - short strategy caveat/notes
    """
    _ensure_outputs()

    if strategies.empty:
        raise ValueError("No predicted tyre strategy data available")

    compound_colours = {
        "SOFT": "#ef4444",
        "MEDIUM": "#facc15",
        "HARD": "#f8fafc",
        "INTERMEDIATE": "#22c55e",
        "WET": "#3b82f6",
        "UNKNOWN": "#9ca3af",
    }

    def compound_colour(compound: str) -> str:
        return compound_colours.get(str(compound).upper(), compound_colours["UNKNOWN"])

    def compound_from_segment(segment: Any) -> str:
        text = str(segment).upper()
        if "SOFT" in text or text.strip() == "S":
            return "SOFT"
        if "MEDIUM" in text or text.strip() == "M":
            return "MEDIUM"
        if "HARD" in text or text.strip() == "H":
            return "HARD"
        if "INTER" in text or text.strip() in {"I", "INT"}:
            return "INTERMEDIATE"
        if "WET" in text or text.strip() == "W":
            return "WET"
        return "UNKNOWN"

    def segment_label(segment: Any) -> str:
        compound = compound_from_segment(segment)
        short = {
            "SOFT": "S",
            "MEDIUM": "M",
            "HARD": "H",
            "INTERMEDIATE": "I",
            "WET": "W",
            "UNKNOWN": "?",
        }.get(compound, "?")

        text = str(segment).lower()
        if "used/unknown" in text:
            return f"{short}?"
        if "used" in text:
            return f"{short}u"
        if "new" in text:
            return f"{short}n"
        return short

    def parse_strategy(strategy_text: Any) -> list[str]:
        text = str(strategy_text).strip()

        if not text or text.lower() in {"nan", "none"}:
            return ["Unknown"]

        for separator in ["→", "->", ">"]:
            if separator in text:
                return [part.strip() for part in text.split(separator) if part.strip()]

        if "-" in text and any(compound in text.upper() for compound in ["SOFT", "MEDIUM", "HARD", "INTER", "WET"]):
            return [part.strip() for part in text.split("-") if part.strip()]

        return [text]

    def first_text(row: pd.Series, columns: list[str], default: str = "") -> str:
        for column in columns:
            if column in row.index and pd.notna(row.get(column)):
                value = str(row.get(column)).strip()
                if value and value.lower() not in {"nan", "none"}:
                    return value
        return default

    def boolish(value: Any) -> bool:
        return str(value).strip().lower() in {"true", "1", "yes", "y"}

    def history_changed(row: pd.Series) -> bool:
        explicit = first_text(
            row,
            ["strategy_changed_by_history", "history_adjustment_applied"],
            default="",
        )

        if explicit:
            return boolish(explicit)

        original = first_text(row, ["original_predicted_strategy"], default="")
        adjusted = first_text(row, ["history_adjusted_strategy", "PredictedStrategy"], default="")

        return bool(original and adjusted and original != adjusted)

    def truncate(text: Any, max_len: int) -> str:
        value = " ".join(str(text).replace(chr(10), " ").split())
        if len(value) <= max_len:
            return value
        return value[: max_len - 1].rstrip() + "…"

    def stops_text(row: pd.Series, segments: list[str]) -> str:
        explicit = _to_float_or_none(row.get("expected_stops"))

        if explicit is None:
            explicit = _to_float_or_none(row.get("ExpectedStops"))

        if explicit is None:
            stop_count = max(len(segments) - 1, 0)
        else:
            stop_count = int(round(explicit))

        return "1 stop" if stop_count == 1 else f"{stop_count} stops"

    display = strategies.copy()

    display["GridPosition"] = pd.to_numeric(
        display.get("GridPosition"),
        errors="coerce",
    )

    if display["GridPosition"].notna().any():
        display = display.sort_values("GridPosition", ascending=True).copy()

    display = display.head(22).reset_index(drop=True)

    strategy_segments = [
        parse_strategy(
            first_text(
                row,
                ["history_adjusted_strategy", "PredictedStrategy", "primary_strategy", "PrimaryStrategy"],
                default="Unknown",
            )
        )
        for _, row in display.iterrows()
    ]

    max_segments = max([len(segments) for segments in strategy_segments] + [2])
    n_rows = len(display)

    fig_width = 22
    fig_height = max(8.2, 2.4 + n_rows * 0.58)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")
    ax.axis("off")

    segment_width = 1.10
    segment_gap = 0.08
    timeline_width = max_segments * (segment_width + segment_gap)

    x_driver = -4.25
    x_grid = -3.10
    x_timeline = -2.35
    x_stops = x_timeline + timeline_width + 0.35
    x_conf = x_stops + 1.25
    x_risk = x_conf + 1.35
    x_hist = x_risk + 1.25
    x_notes = x_hist + 1.10

    y_top = n_rows + 1.25

    ax.text(
        0.01,
        0.985,
        "Predicted Tyre Strategies",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#f8fafc",
        fontsize=18,
        fontweight="bold",
    )
    ax.text(
        0.01,
        0.945,
        "Colour blocks show predicted stint sequence. Tyre availability is estimated from FastF1 lap/stint data, not official FIA/Pirelli barcode data.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#d1d5db",
        fontsize=10.5,
    )

    headers = [
        (x_driver, "Driver"),
        (x_grid, "Grid"),
        (x_timeline, "Stints"),
        (x_stops, "Stops"),
        (x_conf, "Conf"),
        (x_risk, "Risk"),
        (x_hist, "Hist"),
        (x_notes, "Key assumption"),
    ]

    for x, text in headers:
        ax.text(
            x,
            y_top,
            text,
            ha="left",
            va="center",
            color="#f8fafc",
            fontsize=10.5,
            fontweight="bold",
        )

    ax.hlines(y_top - 0.36, x_driver, x_notes + 6.5, color="#6b7280", linewidth=1.0, alpha=0.7)

    for idx, (_, row) in enumerate(display.iterrows()):
        y = n_rows - idx
        team = str(row.get("Team", ""))
        driver = str(row.get("Driver", ""))
        team_colour = get_team_colour(team, session=session)

        if idx % 2 == 0:
            ax.axhspan(y - 0.33, y + 0.33, color="#252932", alpha=0.55, linewidth=0)

        grid_value = _to_float_or_none(row.get("GridPosition"))
        grid = f"P{int(round(grid_value))}" if grid_value is not None else str(row.get("Grid", "N/A"))

        segments = strategy_segments[idx]

        ax.text(
            x_driver,
            y,
            driver,
            ha="left",
            va="center",
            color=team_colour,
            fontsize=10.5,
            fontweight="bold",
        )
        ax.text(
            x_grid,
            y,
            grid,
            ha="left",
            va="center",
            color="#d1d5db",
            fontsize=9.7,
        )

        x = x_timeline

        for segment in segments:
            compound = compound_from_segment(segment)
            colour = compound_colour(compound)
            label = segment_label(segment)
            text_colour = "#111827" if compound in {"MEDIUM", "HARD"} else "white"

            ax.barh(
                y,
                segment_width,
                left=x,
                height=0.46,
                color=colour,
                edgecolor="#111827",
                linewidth=1.0,
            )
            ax.text(
                x + segment_width / 2,
                y,
                label,
                ha="center",
                va="center",
                color=text_colour,
                fontsize=9.0,
                fontweight="bold",
            )

            x += segment_width + segment_gap

        stops = stops_text(row, segments)
        confidence = first_text(
            row,
            ["strategy_confidence", "StrategyConfidenceLabel", "StrategyConfidence"],
            default="N/A",
        )
        risk = first_text(
            row,
            ["strategy_risk_level", "RiskLevel", "OldTyreRisk", "risk_level"],
            default="N/A",
        )
        hist = "Yes" if history_changed(row) else "No"

        note = first_text(
            row,
            [
                "visual_key_assumption",
                "history_adjustment_blocked_reason",
                "history_adjustment_reason",
                "strategy_reason",
                "StrategyReason",
                "strategy_risk_reason",
                "confidence_reason",
                "Notes",
            ],
            default="Estimated tyre strategy.",
        )

        risk_colour = {
            "Low": "#22c55e",
            "Medium": "#facc15",
            "High": "#ef4444",
        }.get(risk, "#d1d5db")
        confidence_colour = {
            "High": "#22c55e",
            "Medium": "#facc15",
            "Low": "#ef4444",
        }.get(confidence, "#d1d5db")
        hist_colour = "#facc15" if hist == "Yes" else "#d1d5db"

        ax.text(x_stops, y, stops, ha="left", va="center", color="#f8fafc", fontsize=9.3)
        ax.text(x_conf, y, confidence, ha="left", va="center", color=confidence_colour, fontsize=9.3, fontweight="bold")
        ax.text(x_risk, y, risk, ha="left", va="center", color=risk_colour, fontsize=9.3, fontweight="bold")
        ax.text(x_hist, y, hist, ha="left", va="center", color=hist_colour, fontsize=9.3, fontweight="bold")
        ax.text(x_notes, y, truncate(note, 70), ha="left", va="center", color="#d1d5db", fontsize=8.6)

    legend_handles = [
        Patch(facecolor=compound_colour("SOFT"), edgecolor="#111827", label="Soft"),
        Patch(facecolor=compound_colour("MEDIUM"), edgecolor="#111827", label="Medium"),
        Patch(facecolor=compound_colour("HARD"), edgecolor="#111827", label="Hard"),
        Patch(facecolor=compound_colour("INTERMEDIATE"), edgecolor="#111827", label="Inter"),
        Patch(facecolor=compound_colour("WET"), edgecolor="#111827", label="Wet"),
        Patch(facecolor=compound_colour("UNKNOWN"), edgecolor="#111827", label="Unknown"),
    ]

    ax.legend(
        handles=legend_handles,
        facecolor="#30343b",
        edgecolor="#6b7280",
        labelcolor="#f8fafc",
        loc="lower left",
        bbox_to_anchor=(0.01, -0.035),
        ncol=6,
        framealpha=1.0,
        fontsize=9.0,
    )

    ax.text(
        0.99,
        -0.025,
        "Labels: n=new, u=used, ?=used/unknown",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#d1d5db",
        fontsize=9.0,
    )

    ax.set_xlim(x_driver - 0.15, x_notes + 7.2)
    ax.set_ylim(-0.35, n_rows + 2.05)

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

    strategies = _order_strategy_columns(strategies)

    strategy_csv = "outputs/strategy/predicted_tyre_strategy.csv"
    strategies.to_csv(strategy_csv, index=False)

    strategy_image = make_strategy_table_image(strategies)
    risk_chart = make_old_tyre_risk_chart(strategies)

    return {
        "predicted_tyre_strategy_csv": strategy_csv,
        "predicted_tyre_strategy_chart": strategy_image,
        "old_tyre_risk_chart": risk_chart,
    }