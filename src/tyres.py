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


def infer_tyre_usage(
    lap_details: pd.DataFrame,
    sprint_weekend: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Builds an estimated tyre usage ledger.

    This is an estimate, not the official Pirelli/FIA set ledger.
    We infer likely new sets from FreshTyre and TyreLife.
    """

    allocation = SPRINT_DRY_ALLOCATION if sprint_weekend else NORMAL_DRY_ALLOCATION

    laps = lap_details.copy()
    laps["Compound"] = laps["Compound"].astype(str).str.upper()
    laps = laps[laps["Compound"].isin(DRY_COMPOUNDS)].copy()

    if laps.empty:
        return pd.DataFrame(), pd.DataFrame()

    laps["LapNumber"] = pd.to_numeric(laps["LapNumber"], errors="coerce")
    laps["TyreLife"] = pd.to_numeric(laps["TyreLife"], errors="coerce")
    laps["Stint"] = pd.to_numeric(laps["Stint"], errors="coerce")
    laps["FreshTyreBool"] = laps["FreshTyre"].map(_boolish)

    group_cols = ["Driver", "Team", "Session", "Stint", "Compound"]

    rows = []

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

        likely_new_set = fresh_flag

        if np.isfinite(start_tyre_life) and start_tyre_life <= 2:
            likely_new_set = True

        rows.append(
            {
                "Driver": driver,
                "Team": team,
                "Session": session,
                "Stint": stint,
                "Compound": compound,
                "observed_laps": int(len(group)),
                "clean_push_laps": int(group["CleanPushLap"].fillna(False).astype(bool).sum())
                if "CleanPushLap" in group.columns
                else int(len(group)),
                "first_lap_number": group["LapNumber"].min(),
                "last_lap_number": group["LapNumber"].max(),
                "start_tyre_life": start_tyre_life,
                "end_tyre_life": end_tyre_life,
                "fresh_tyre_flag": fresh_flag,
                "likely_new_set": likely_new_set,
                "set_status_estimate": "new" if likely_new_set else "reused/unknown",
            }
        )

    set_ledger = pd.DataFrame(rows)

    usage = (
        set_ledger.groupby(["Driver", "Team", "Compound"], dropna=False)
        .agg(
            observed_stints=("Stint", "count"),
            observed_laps=("observed_laps", "sum"),
            clean_push_laps=("clean_push_laps", "sum"),
            likely_new_sets_used=("likely_new_set", "sum"),
            reused_or_unknown_stints=("likely_new_set", lambda x: (~x.astype(bool)).sum()),
            max_tyre_life_seen=("end_tyre_life", "max"),
        )
        .reset_index()
    )

    drivers = (
        set_ledger[["Driver", "Team"]]
        .drop_duplicates()
        .sort_values(["Team", "Driver"])
        .reset_index(drop=True)
    )

    inventory_rows = []

    for _, driver_row in drivers.iterrows():
        for compound in DRY_COMPOUNDS:
            compound_usage = usage[
                (usage["Driver"] == driver_row["Driver"])
                & (usage["Compound"] == compound)
            ]

            likely_new_used = 0
            observed_stints = 0
            observed_laps = 0
            clean_laps = 0
            max_tyre_life = np.nan

            if not compound_usage.empty:
                row = compound_usage.iloc[0]
                likely_new_used = int(row["likely_new_sets_used"])
                observed_stints = int(row["observed_stints"])
                observed_laps = int(row["observed_laps"])
                clean_laps = int(row["clean_push_laps"])
                max_tyre_life = row["max_tyre_life_seen"]

            starting_sets = allocation[compound]
            estimated_new_remaining = max(starting_sets - likely_new_used, 0)

            inventory_rows.append(
                {
                    "Driver": driver_row["Driver"],
                    "Team": driver_row["Team"],
                    "Compound": compound,
                    "starting_sets_assumed": starting_sets,
                    "likely_new_sets_used": likely_new_used,
                    "estimated_new_sets_remaining": estimated_new_remaining,
                    "observed_stints": observed_stints,
                    "observed_laps": observed_laps,
                    "clean_push_laps": clean_laps,
                    "max_tyre_life_seen": max_tyre_life,
                    "note": "Estimated from FastF1 laps, not official tyre barcode data.",
                }
            )

    inventory = pd.DataFrame(inventory_rows)

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

    set_ledger.to_csv(set_ledger_path, index=False)
    inventory.to_csv(inventory_path, index=False)

    usage_chart = make_tyre_usage_chart(inventory)
    remaining_chart = make_tyre_remaining_chart(inventory)

    return {
        "tyre_set_ledger": set_ledger_path,
        "tyre_inventory": inventory_path,
        "tyre_usage_chart": usage_chart,
        "tyre_remaining_chart": remaining_chart,
    }