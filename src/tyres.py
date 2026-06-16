from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DRY_COMPOUNDS = ["HARD", "MEDIUM", "SOFT"]

NORMAL_DRY_ALLOCATION = {
    "HARD": 2,
    "MEDIUM": 3,
    "SOFT": 8,
}

SPRINT_DRY_ALLOCATION = {
    "HARD": 2,
    "MEDIUM": 4,
    "SOFT": 6,
}

COMPOUND_COLOURS = {
    "HARD": "#f8fafc",
    "MEDIUM": "#facc15",
    "SOFT": "#ef4444",
    "INTERMEDIATE": "#22c55e",
    "WET": "#3b82f6",
}

STATUS_ORDER = {
    "new": 1,
    "scrubbed": 2,
    "used": 3,
    "unknown": 4,
}

RISK_ORDER = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}


def _ensure_outputs() -> None:
    Path("outputs/tyres").mkdir(parents=True, exist_ok=True)


def _compound_colour(compound: str) -> str:
    return COMPOUND_COLOURS.get(str(compound), "#d1d5db")


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _to_float_or_nan(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan

    if not np.isfinite(number):
        return np.nan

    return number


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.45:
        return "Medium"
    return "Low"


def _risk_label(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 35:
        return "Medium"
    return "Low"


def _status_source_group(set_status_source: str) -> str:
    if set_status_source.startswith("observed"):
        return "observed"
    if set_status_source.startswith("inferred"):
        return "inferred"
    if set_status_source.startswith("estimated"):
        return "estimated"
    return "unknown"


def _classify_tyre_set(
    fresh_flag: bool,
    start_tyre_life: float,
    end_tyre_life: float,
    observed_laps: int,
) -> dict[str, Any]:
    """
    Classifies an observed FastF1 stint into a readable tyre-set status.

    This is still an estimate. FastF1 tells us useful stint/lap attributes, but it
    does not provide official FIA/Pirelli barcode-level set allocation in this
    pipeline. The classification therefore separates what was directly observed
    from what was inferred or estimated.
    """

    start_known = np.isfinite(start_tyre_life)
    end_known = np.isfinite(end_tyre_life)

    confidence_score = 0.40

    if observed_laps >= 1:
        confidence_score += 0.08
    if observed_laps >= 3:
        confidence_score += 0.07
    if start_known:
        confidence_score += 0.14
    if end_known:
        confidence_score += 0.06
    if fresh_flag:
        confidence_score += 0.18

    if fresh_flag:
        tyre_status = "new"
        set_status_source = "observed_fastf1_fresh_tyre"
        reason = (
            "FastF1 FreshTyre indicates this stint started on a fresh set. "
            "This is observed from FastF1 data, but not official FIA/Pirelli barcode data."
        )
    elif start_known and start_tyre_life <= 2:
        tyre_status = "new"
        set_status_source = "inferred_from_low_start_tyre_life"
        confidence_score += 0.08
        reason = (
            f"Start TyreLife is {start_tyre_life:.0f}, so the set is inferred as new or near-new. "
            "This is inferred from FastF1 lap/stint data."
        )
    elif start_known and start_tyre_life <= 5:
        tyre_status = "scrubbed"
        set_status_source = "inferred_scrubbed_from_start_tyre_life"
        confidence_score += 0.04
        reason = (
            f"Start TyreLife is {start_tyre_life:.0f}, so the set is likely scrubbed rather than brand new. "
            "This is inferred from FastF1 lap/stint data."
        )
    elif start_known and start_tyre_life > 5:
        tyre_status = "used"
        set_status_source = "inferred_used_from_start_tyre_life"
        confidence_score += 0.02
        reason = (
            f"Start TyreLife is {start_tyre_life:.0f}, so the set is likely already used. "
            "This is inferred from FastF1 lap/stint data."
        )
    elif observed_laps > 0:
        tyre_status = "unknown"
        set_status_source = "estimated_unknown_from_observed_stint"
        reason = (
            "The stint is observed in FastF1, but FreshTyre/TyreLife was not enough to classify the set. "
            "Treat this as unknown for strategy confidence."
        )
    else:
        tyre_status = "unknown"
        set_status_source = "unknown"
        confidence_score = 0.20
        reason = "No usable stint evidence was available for this tyre-set estimate."

    # Estimated classifications are deliberately capped below 1.0 because this is
    # not official FIA/Pirelli allocation data.
    confidence_score = float(min(confidence_score, 0.90 if fresh_flag else 0.82))
    confidence = _confidence_label(confidence_score)

    if tyre_status == "unknown" or confidence == "Low":
        strategy_relevance = "High strategy uncertainty"
    elif tyre_status in {"used", "scrubbed"}:
        strategy_relevance = "May reduce available fresh race sets"
    else:
        strategy_relevance = "Useful for estimating fresh-set consumption"

    return {
        "tyre_status": tyre_status,
        "set_status_estimate": tyre_status,
        "set_status_source": set_status_source,
        "set_status_source_group": _status_source_group(set_status_source),
        "tyre_confidence_score": confidence_score,
        "tyre_confidence": confidence,
        "inventory_confidence": confidence,
        "tyre_confidence_reason": reason,
        "strategy_relevance": strategy_relevance,
    }


def _inventory_confidence_reason(
    compound: str,
    observed_stints: int,
    unknown_stints: int,
    confidence: str,
) -> str:
    if observed_stints <= 0:
        return (
            f"{compound} inventory has no observed dry stint for this driver. "
            "Remaining sets are allocation-based estimates, not official FIA/Pirelli data."
        )

    if unknown_stints > 0:
        return (
            f"{compound} inventory includes {unknown_stints} unknown stint(s). "
            f"Overall confidence is {confidence}. Not official FIA/Pirelli barcode data."
        )

    return (
        f"{compound} inventory is estimated from {observed_stints} observed FastF1 dry stint(s) "
        f"with {confidence.lower()} confidence. Not official FIA/Pirelli barcode data."
    )


def _build_driver_inventory_summary(inventory: pd.DataFrame) -> pd.Series:
    parts: list[str] = []

    for compound in DRY_COMPOUNDS:
        rows = inventory[inventory["Compound"].astype(str).str.upper() == compound]

        if rows.empty:
            parts.append(f"{compound[0]}: N/A")
            continue

        row = rows.iloc[0]
        remaining = int(_to_float_or_nan(row.get("estimated_new_sets_remaining")) or 0)
        status_mix = str(row.get("status_mix", ""))
        confidence = str(row.get("inventory_confidence", "N/A"))
        risk = str(row.get("inventory_risk_level", "N/A"))

        parts.append(
            f"{compound[0]}:{remaining} new est | {confidence} conf | {risk} risk | {status_mix}"
        )

    return pd.Series(
        {
            "driver_race_tyre_summary": " ; ".join(parts),
            "driver_inventory_risk_level": _risk_label(
                float(inventory.get("inventory_risk_score", pd.Series([0])).max())
            ),
            "driver_min_inventory_confidence_score": float(
                inventory.get("tyre_confidence_score", pd.Series([np.nan])).min()
            ),
        }
    )


def infer_tyre_usage(
    lap_details: pd.DataFrame,
    sprint_weekend: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Builds an estimated tyre usage ledger and inventory.

    This is an estimate, not the official Pirelli/FIA set ledger. We infer likely
    new/scrubbed/used/unknown set status from FastF1 FreshTyre and TyreLife.
    """

    allocation = SPRINT_DRY_ALLOCATION if sprint_weekend else NORMAL_DRY_ALLOCATION

    laps = lap_details.copy()

    required_columns = {"Driver", "Team", "Session", "Stint", "Compound", "LapNumber"}
    missing_columns = required_columns.difference(laps.columns)

    if missing_columns:
        raise ValueError(
            "Tyre usage cannot be inferred because lap details are missing columns: "
            f"{sorted(missing_columns)}"
        )

    laps["Compound"] = laps["Compound"].astype(str).str.upper()
    laps = laps[laps["Compound"].isin(DRY_COMPOUNDS)].copy()

    if laps.empty:
        return pd.DataFrame(), pd.DataFrame()

    laps["LapNumber"] = pd.to_numeric(laps["LapNumber"], errors="coerce")
    laps["TyreLife"] = pd.to_numeric(laps.get("TyreLife"), errors="coerce")
    laps["Stint"] = pd.to_numeric(laps["Stint"], errors="coerce")

    if "FreshTyre" in laps.columns:
        laps["FreshTyreBool"] = laps["FreshTyre"].map(_boolish)
    else:
        laps["FreshTyreBool"] = False

    group_cols = ["Driver", "Team", "Session", "Stint", "Compound"]

    rows: list[dict[str, Any]] = []

    for keys, group in laps.groupby(group_cols, dropna=False):
        driver, team, session, stint, compound = keys

        group = group.sort_values("LapNumber").copy()

        tyre_life_non_null = group["TyreLife"].dropna()

        start_tyre_life = (
            float(tyre_life_non_null.iloc[0])
            if not tyre_life_non_null.empty
            else np.nan
        )

        end_tyre_life = (
            float(tyre_life_non_null.iloc[-1])
            if not tyre_life_non_null.empty
            else np.nan
        )

        fresh_flag = bool(group["FreshTyreBool"].any())
        observed_laps = int(len(group))
        clean_push_laps = (
            int(group["CleanPushLap"].fillna(False).astype(bool).sum())
            if "CleanPushLap" in group.columns
            else observed_laps
        )

        classification = _classify_tyre_set(
            fresh_flag=fresh_flag,
            start_tyre_life=start_tyre_life,
            end_tyre_life=end_tyre_life,
            observed_laps=observed_laps,
        )

        tyre_status = classification["tyre_status"]
        likely_new_set = tyre_status == "new"
        likely_scrubbed_set = tyre_status == "scrubbed"
        likely_used_set = tyre_status == "used"
        unknown_set = tyre_status == "unknown"

        rows.append(
            {
                "Driver": driver,
                "Team": team,
                "Session": session,
                "Stint": stint,
                "Compound": compound,
                "observed_laps": observed_laps,
                "clean_push_laps": clean_push_laps,
                "first_lap_number": group["LapNumber"].min(),
                "last_lap_number": group["LapNumber"].max(),
                "start_tyre_life": start_tyre_life,
                "end_tyre_life": end_tyre_life,
                "fresh_tyre_flag": fresh_flag,
                "likely_new_set": likely_new_set,
                "likely_scrubbed_set": likely_scrubbed_set,
                "likely_used_set": likely_used_set,
                "unknown_set": unknown_set,
                "tyre_status": tyre_status,
                "set_status_estimate": classification["set_status_estimate"],
                "tyre_data_source": "fastf1_lap_stint_data",
                "usage_observation_source": "observed_fastf1_lap_stint",
                "set_status_source": classification["set_status_source"],
                "set_status_source_group": classification["set_status_source_group"],
                "tyre_confidence_score": classification["tyre_confidence_score"],
                "tyre_confidence": classification["tyre_confidence"],
                "inventory_confidence": classification["inventory_confidence"],
                "tyre_confidence_reason": classification["tyre_confidence_reason"],
                "classification_reason": classification["tyre_confidence_reason"],
                "strategy_relevance": classification["strategy_relevance"],
                "official_data_available": False,
                "official_data_note": "No official FIA/Pirelli barcode-level tyre allocation data is used in this pipeline.",
            }
        )

    set_ledger = pd.DataFrame(rows)

    set_ledger["status_order"] = set_ledger["tyre_status"].map(STATUS_ORDER).fillna(99).astype(int)
    set_ledger = set_ledger.sort_values(
        ["Driver", "Session", "Stint", "status_order", "Compound"],
        ascending=[True, True, True, True, True],
    ).drop(columns=["status_order"]).reset_index(drop=True)

    usage = (
        set_ledger.groupby(["Driver", "Team", "Compound"], dropna=False)
        .agg(
            observed_stints=("Stint", "count"),
            observed_laps=("observed_laps", "sum"),
            clean_push_laps=("clean_push_laps", "sum"),
            likely_new_sets_used=("likely_new_set", "sum"),
            scrubbed_stints=("likely_scrubbed_set", "sum"),
            used_stints=("likely_used_set", "sum"),
            unknown_stints=("unknown_set", "sum"),
            reused_or_unknown_stints=("likely_new_set", lambda x: (~x.astype(bool)).sum()),
            max_tyre_life_seen=("end_tyre_life", "max"),
            min_tyre_confidence_score=("tyre_confidence_score", "min"),
            avg_tyre_confidence_score=("tyre_confidence_score", "mean"),
            source_mix=("set_status_source_group", lambda values: ",".join(sorted(set(map(str, values))))),
        )
        .reset_index()
    )

    drivers = (
        set_ledger[["Driver", "Team"]]
        .drop_duplicates()
        .sort_values(["Team", "Driver"])
        .reset_index(drop=True)
    )

    inventory_rows: list[dict[str, Any]] = []

    for _, driver_row in drivers.iterrows():
        for compound in DRY_COMPOUNDS:
            compound_usage = usage[
                (usage["Driver"] == driver_row["Driver"])
                & (usage["Compound"] == compound)
            ]

            likely_new_used = 0
            scrubbed_stints = 0
            used_stints = 0
            unknown_stints = 0
            observed_stints = 0
            observed_laps = 0
            clean_laps = 0
            max_tyre_life = np.nan
            min_confidence_score = 0.35
            avg_confidence_score = 0.35
            source_mix = "estimated"

            if not compound_usage.empty:
                row = compound_usage.iloc[0]
                likely_new_used = int(row["likely_new_sets_used"])
                scrubbed_stints = int(row["scrubbed_stints"])
                used_stints = int(row["used_stints"])
                unknown_stints = int(row["unknown_stints"])
                observed_stints = int(row["observed_stints"])
                observed_laps = int(row["observed_laps"])
                clean_laps = int(row["clean_push_laps"])
                max_tyre_life = row["max_tyre_life_seen"]
                min_confidence_score = float(row["min_tyre_confidence_score"])
                avg_confidence_score = float(row["avg_tyre_confidence_score"])
                source_mix = str(row["source_mix"])

            starting_sets = allocation[compound]
            estimated_new_remaining = max(starting_sets - likely_new_used, 0)
            estimated_non_new_sets_seen = scrubbed_stints + used_stints + unknown_stints
            estimated_sets_accounted_for = min(
                starting_sets,
                likely_new_used + estimated_non_new_sets_seen,
            )

            unknown_pressure = min(35, unknown_stints * 18)
            shortage_pressure = 0

            if estimated_new_remaining <= 0:
                shortage_pressure += 35
            elif estimated_new_remaining == 1:
                shortage_pressure += 18

            low_confidence_pressure = max(0.0, (0.65 - min_confidence_score) * 70)
            inventory_risk_score = float(
                min(
                    100,
                    shortage_pressure
                    + unknown_pressure
                    + low_confidence_pressure
                    + max(0, scrubbed_stints + used_stints - 1) * 5,
                )
            )
            inventory_risk_level = _risk_label(inventory_risk_score)

            confidence_score = float(min(avg_confidence_score, 0.85))
            confidence = _confidence_label(confidence_score)
            status_mix = (
                f"new={likely_new_used}; scrubbed={scrubbed_stints}; "
                f"used={used_stints}; unknown={unknown_stints}"
            )

            if unknown_stints > 0:
                risk_reason = (
                    f"{compound} has {unknown_stints} unknown stint(s), so strategy assumptions are less reliable."
                )
            elif estimated_new_remaining <= 0:
                risk_reason = (
                    f"{compound} has no estimated fresh sets remaining; strategy may need used/scrubbed sets."
                )
            elif confidence == "Low":
                risk_reason = (
                    f"{compound} inventory confidence is low because available data is incomplete."
                )
            else:
                risk_reason = (
                    f"{compound} inventory has {estimated_new_remaining} estimated fresh set(s) remaining."
                )

            inventory_rows.append(
                {
                    "Driver": driver_row["Driver"],
                    "Team": driver_row["Team"],
                    "Compound": compound,
                    "starting_sets_assumed": starting_sets,
                    "likely_new_sets_used": likely_new_used,
                    "scrubbed_stints_inferred": scrubbed_stints,
                    "used_stints_inferred": used_stints,
                    "unknown_stints": unknown_stints,
                    "estimated_non_new_sets_seen": estimated_non_new_sets_seen,
                    "estimated_sets_accounted_for": estimated_sets_accounted_for,
                    "estimated_new_sets_remaining": estimated_new_remaining,
                    "observed_stints": observed_stints,
                    "observed_laps": observed_laps,
                    "clean_push_laps": clean_laps,
                    "max_tyre_life_seen": max_tyre_life,
                    "status_mix": status_mix,
                    "readable_compound_summary": (
                        f"{compound}: {estimated_new_remaining} estimated fresh set(s) remaining; "
                        f"{status_mix}; confidence={confidence}; risk={inventory_risk_level}"
                    ),
                    "note": "Estimated from FastF1 laps, not official tyre barcode data.",
                    "tyre_data_source": "fastf1_lap_stint_data",
                    "inventory_source": "estimated_from_fastf1_lap_stints_and_assumed_allocation",
                    "set_status_source": source_mix,
                    "set_status_source_group": source_mix,
                    "tyre_confidence_score": confidence_score,
                    "min_tyre_confidence_score": min_confidence_score,
                    "tyre_confidence": confidence,
                    "inventory_confidence": confidence,
                    "tyre_confidence_reason": _inventory_confidence_reason(
                        compound=compound,
                        observed_stints=observed_stints,
                        unknown_stints=unknown_stints,
                        confidence=confidence,
                    ),
                    "inventory_risk_score": inventory_risk_score,
                    "inventory_risk_level": inventory_risk_level,
                    "inventory_risk_reason": risk_reason,
                    "tyre_availability_risk": inventory_risk_level,
                    "official_data_available": False,
                    "official_data_note": "No official FIA/Pirelli barcode-level tyre allocation data is used in this pipeline.",
                }
            )

    inventory = pd.DataFrame(inventory_rows)

    if not inventory.empty:
        summary_rows: list[dict[str, Any]] = []

        for (driver, team), driver_inventory in inventory.groupby(["Driver", "Team"], dropna=False):
            summary = _build_driver_inventory_summary(driver_inventory).to_dict()
            summary["Driver"] = driver
            summary["Team"] = team
            summary_rows.append(summary)

        driver_summaries = pd.DataFrame(summary_rows)

        inventory = inventory.merge(
            driver_summaries,
            on=["Driver", "Team"],
            how="left",
        )

    return set_ledger, inventory


def make_tyre_usage_chart(
    inventory: pd.DataFrame,
    output_path: str = "outputs/tyres/tyre_new_sets_used.png",
) -> str:
    _ensure_outputs()

    if inventory.empty:
        raise ValueError("Tyre inventory is empty")

    pivot = inventory.pivot_table(
        index="Driver",
        columns="Compound",
        values="likely_new_sets_used",
        aggfunc="sum",
        fill_value=0,
    )

    pivot = pivot.reindex(columns=DRY_COMPOUNDS, fill_value=0)
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=True).drop(columns=["total"])

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    left = np.zeros(len(pivot))

    for compound in DRY_COMPOUNDS:
        values = pivot[compound].to_numpy()
        ax.barh(
            pivot.index,
            values,
            left=left,
            label=compound,
            color=_compound_colour(compound),
        )
        left += values

    ax.set_title(
        "Estimated new dry tyre sets used",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Likely new sets used", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def make_tyre_remaining_chart(
    inventory: pd.DataFrame,
    output_path: str = "outputs/tyres/tyre_new_sets_remaining.png",
) -> str:
    _ensure_outputs()

    if inventory.empty:
        raise ValueError("Tyre inventory is empty")

    pivot = inventory.pivot_table(
        index="Driver",
        columns="Compound",
        values="estimated_new_sets_remaining",
        aggfunc="sum",
        fill_value=0,
    )

    pivot = pivot.reindex(columns=DRY_COMPOUNDS, fill_value=0)
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=True).drop(columns=["total"])

    fig, ax = plt.subplots(figsize=(12, 9))
    fig.patch.set_facecolor("#30343b")
    ax.set_facecolor("#30343b")

    left = np.zeros(len(pivot))

    for compound in DRY_COMPOUNDS:
        values = pivot[compound].to_numpy()
        ax.barh(
            pivot.index,
            values,
            left=left,
            label=compound,
            color=_compound_colour(compound),
        )
        left += values

    ax.set_title(
        "Estimated new dry tyre sets remaining",
        color="white",
        fontsize=16,
        weight="bold",
    )
    ax.set_xlabel("Estimated new sets remaining", color="white")
    ax.tick_params(colors="white")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(facecolor="#30343b", edgecolor="#6b7280", labelcolor="white")

    for spine in ax.spines.values():
        spine.set_color("#6b7280")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)

    return output_path


def build_tyre_outputs(
    lap_details_path: str,
    sprint_weekend: bool = False,
) -> dict[str, str]:
    _ensure_outputs()

    lap_details = pd.read_csv(lap_details_path)

    set_ledger, inventory = infer_tyre_usage(
        lap_details=lap_details,
        sprint_weekend=sprint_weekend,
    )

    if set_ledger.empty or inventory.empty:
        return {}

    set_ledger_path = "outputs/tyres/tyre_set_ledger_estimated.csv"
    inventory_path = "outputs/tyres/tyre_inventory_estimated.csv"
    driver_summary_path = "outputs/tyres/tyre_inventory_driver_summary_estimated.csv"

    set_ledger.to_csv(set_ledger_path, index=False)
    inventory.to_csv(inventory_path, index=False)

    driver_summary_columns = [
        "Driver",
        "Team",
        "driver_race_tyre_summary",
        "driver_inventory_risk_level",
        "driver_min_inventory_confidence_score",
    ]

    driver_summary = (
        inventory[driver_summary_columns]
        .drop_duplicates(subset=["Driver", "Team"])
        .sort_values(["Team", "Driver"])
        .reset_index(drop=True)
    )
    driver_summary.to_csv(driver_summary_path, index=False)

    usage_chart = make_tyre_usage_chart(inventory)
    remaining_chart = make_tyre_remaining_chart(inventory)

    return {
        "tyre_set_ledger": set_ledger_path,
        "tyre_inventory": inventory_path,
        "tyre_inventory_driver_summary": driver_summary_path,
        "tyre_usage_chart": usage_chart,
        "tyre_remaining_chart": remaining_chart,
    }