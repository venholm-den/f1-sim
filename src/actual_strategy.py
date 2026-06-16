from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import re

import numpy as np
import pandas as pd


DRY_COMPOUNDS = ["HARD", "MEDIUM", "SOFT"]
WET_COMPOUNDS = ["INTERMEDIATE", "WET"]
ALL_COMPOUNDS = DRY_COMPOUNDS + WET_COMPOUNDS

_COMPOUND_ALIASES = {
    "H": "HARD",
    "HN": "HARD",
    "HU": "HARD",
    "HARD": "HARD",
    "HARDS": "HARD",
    "M": "MEDIUM",
    "MN": "MEDIUM",
    "MU": "MEDIUM",
    "MED": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "MEDIUMS": "MEDIUM",
    "S": "SOFT",
    "SN": "SOFT",
    "SU": "SOFT",
    "SOFT": "SOFT",
    "SOFTS": "SOFT",
    "I": "INTERMEDIATE",
    "IN": "INTERMEDIATE",
    "INTER": "INTERMEDIATE",
    "INTERS": "INTERMEDIATE",
    "INTERMEDIATE": "INTERMEDIATE",
    "INTERMEDIATES": "INTERMEDIATE",
    "W": "WET",
    "WN": "WET",
    "WET": "WET",
    "WETS": "WET",
}


def normalise_driver(value: Any) -> str:
    return str(value or "").strip().upper()


def normalise_compound(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text).strip()

    if not text or text in {"NAN", "NONE", "UNKNOWN"}:
        return "UNKNOWN"

    parts = text.split()

    for part in parts:
        if part in _COMPOUND_ALIASES:
            return _COMPOUND_ALIASES[part]

    for compound in ALL_COMPOUNDS:
        if compound in text:
            return compound

    return "UNKNOWN"


def format_strategy_sequence(compounds: list[str]) -> str:
    return " → ".join(compound.title() for compound in compounds if compound in ALL_COMPOUNDS)


def parse_strategy_sequence(value: Any) -> list[str]:
    """Parses model or FastF1 strategy strings into normalised compound names."""

    if value is None:
        return []

    if isinstance(value, float) and not np.isfinite(value):
        return []

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none"}:
        return []

    # Keep stint separators while removing status labels such as (new) and
    # (used/unknown). The CSV normally uses arrows, but older outputs sometimes
    # use hyphens or abbreviated visual labels.
    cleaned = re.sub(r"\([^)]*\)", "", text)
    cleaned = cleaned.replace("→", "|").replace("->", "|").replace("—", "|")

    # Treat hyphens as separators only when they appear between compound words,
    # not inside arbitrary text.
    cleaned = re.sub(r"\s+-\s+", "|", cleaned)

    raw_parts = [part.strip() for part in cleaned.split("|") if part.strip()]

    if len(raw_parts) <= 1:
        # Fallback for compact labels such as "Mn Hn Hn".
        raw_parts = re.split(r"[,;/\s]+", cleaned)

    compounds: list[str] = []

    for part in raw_parts:
        compound = normalise_compound(part)
        if compound in ALL_COMPOUNDS:
            compounds.append(compound)

    return compounds


def _dominant_compound(stint: pd.DataFrame) -> str:
    if "Compound" not in stint.columns:
        return "UNKNOWN"

    compounds = stint["Compound"].map(normalise_compound)
    compounds = compounds[compounds.isin(ALL_COMPOUNDS)]

    if compounds.empty:
        return "UNKNOWN"

    return str(compounds.value_counts().index[0])


def _prepare_laps(laps: pd.DataFrame) -> pd.DataFrame:
    required = {"Driver", "LapNumber", "Compound"}
    missing = required.difference(laps.columns)

    if missing:
        raise ValueError(
            "FastF1 race lap data is missing required columns for actual tyre "
            f"strategy extraction: {sorted(missing)}"
        )

    df = laps.copy()
    df["Driver"] = df["Driver"].map(normalise_driver)
    df["Team"] = df["Team"].astype(str) if "Team" in df.columns else ""
    df["LapNumber"] = pd.to_numeric(df["LapNumber"], errors="coerce")
    df["Compound"] = df["Compound"].map(normalise_compound)

    df = df.dropna(subset=["Driver", "LapNumber"]).copy()
    df = df[df["Compound"].isin(ALL_COMPOUNDS)].copy()

    if df.empty:
        return df

    df = df.sort_values(["Driver", "LapNumber"]).reset_index(drop=True)

    if "Stint" in df.columns:
        df["Stint"] = pd.to_numeric(df["Stint"], errors="coerce")

        # Fill missing stint numbers by compound changes so partial FastF1 data
        # can still be used.
        if df["Stint"].isna().any():
            inferred = (
                df.groupby("Driver")["Compound"]
                .transform(lambda series: series.ne(series.shift()).cumsum())
            )
            df["Stint"] = df["Stint"].fillna(inferred)
    else:
        df["Stint"] = (
            df.groupby("Driver")["Compound"]
            .transform(lambda series: series.ne(series.shift()).cumsum())
        )

    return df


def extract_actual_tyre_strategy_from_session(
    race_session: Any,
    metadata: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Extracts actual race tyre strategy from completed FastF1 race laps.

    This is not FIA/Pirelli barcode allocation data. It is the actual compound
    sequence observed in FastF1 race lap/stint data and is intended for
    post-race backtesting.
    """

    metadata = metadata or {}
    laps = getattr(race_session, "laps", pd.DataFrame())

    if laps is None or laps.empty:
        return pd.DataFrame()

    df = _prepare_laps(laps)

    if df.empty:
        return pd.DataFrame()

    race_lap_count = int(pd.to_numeric(df["LapNumber"], errors="coerce").max())
    rows: list[dict[str, Any]] = []

    for driver, driver_laps in df.groupby("Driver"):
        driver_laps = driver_laps.sort_values(["LapNumber"]).copy()

        if driver_laps.empty:
            continue

        team = (
            str(driver_laps["Team"].dropna().iloc[0])
            if "Team" in driver_laps.columns and not driver_laps["Team"].dropna().empty
            else ""
        )

        max_driver_lap = int(driver_laps["LapNumber"].max())
        completed_likely = max_driver_lap >= max(1, int(race_lap_count * 0.85))

        stint_rows: list[dict[str, Any]] = []

        for stint_number, stint in driver_laps.groupby("Stint", dropna=False):
            if stint.empty:
                continue

            compound = _dominant_compound(stint)

            if compound == "UNKNOWN":
                continue

            stint_rows.append(
                {
                    "Stint": stint_number,
                    "Compound": compound,
                    "Laps": int(len(stint)),
                    "FirstLap": int(stint["LapNumber"].min()),
                    "LastLap": int(stint["LapNumber"].max()),
                }
            )

        if not stint_rows:
            continue

        stint_df = pd.DataFrame(stint_rows).sort_values("FirstLap").reset_index(drop=True)

        # Remove isolated 1-lap compound anomalies if the driver has other real
        # stints. This avoids a single in/out lap distorting the stop count.
        if len(stint_df) > 1:
            filtered = stint_df[stint_df["Laps"] >= 2].copy()
            if not filtered.empty:
                stint_df = filtered.reset_index(drop=True)

        sequence = stint_df["Compound"].astype(str).tolist()
        dry_sequence = [compound for compound in sequence if compound in DRY_COMPOUNDS]
        had_wet = any(compound in WET_COMPOUNDS for compound in sequence)

        if not sequence:
            continue

        rows.append(
            {
                "year": metadata.get("year", ""),
                "event": metadata.get("event", ""),
                "round": metadata.get("round", ""),
                "Driver": driver,
                "Team": team,
                "race_laps": race_lap_count,
                "driver_max_lap": max_driver_lap,
                "completed_likely": bool(completed_likely),
                "had_wet_compound": bool(had_wet),
                "actual_stint_count": int(len(sequence)),
                "actual_stops": int(max(len(sequence) - 1, 0)),
                "actual_strategy_sequence": "-".join(sequence),
                "actual_strategy": format_strategy_sequence(sequence),
                "actual_first_compound": sequence[0] if sequence else "",
                "actual_dry_stint_count": int(len(dry_sequence)),
                "actual_dry_stops": int(max(len(dry_sequence) - 1, 0)),
                "actual_dry_strategy_sequence": "-".join(dry_sequence),
                "actual_dry_strategy": format_strategy_sequence(dry_sequence),
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            }
        )

    return pd.DataFrame(rows)


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _counter_match(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False
    return Counter(left) == Counter(right)


def compare_predicted_to_actual_strategy(
    predicted: pd.DataFrame,
    actual: pd.DataFrame,
) -> pd.DataFrame:
    """Compares predicted strategy CSV output against actual FastF1 strategy."""

    if predicted.empty or actual.empty:
        return pd.DataFrame()

    predicted_strategy_col = _first_existing_column(
        predicted,
        [
            "PredictedStrategy",
            "predicted_strategy",
            "history_adjusted_strategy",
            "HistoryAdjustedStrategy",
            "primary_strategy",
            "PrimaryStrategy",
        ],
    )

    if predicted_strategy_col is None:
        return pd.DataFrame()

    pred = predicted.copy()
    act = actual.copy()

    pred["Driver"] = pred["Driver"].map(normalise_driver)
    act["Driver"] = act["Driver"].map(normalise_driver)

    pred["predicted_strategy"] = pred[predicted_strategy_col].astype(str)
    pred["predicted_strategy_source_column"] = predicted_strategy_col
    pred["predicted_compounds"] = pred["predicted_strategy"].map(parse_strategy_sequence)
    pred["predicted_strategy_compact"] = pred["predicted_compounds"].map(lambda seq: "-".join(seq))
    pred["predicted_stops"] = pred["predicted_compounds"].map(lambda seq: max(len(seq) - 1, 0) if seq else np.nan)
    pred["predicted_first_compound"] = pred["predicted_compounds"].map(lambda seq: seq[0] if seq else "")

    if "actual_strategy" not in act.columns and "actual_strategy_sequence" in act.columns:
        act["actual_strategy"] = act["actual_strategy_sequence"].map(
            lambda value: format_strategy_sequence(parse_strategy_sequence(value))
        )

    act["actual_compounds"] = act["actual_strategy"].map(parse_strategy_sequence)
    act["actual_strategy_compact"] = act["actual_compounds"].map(lambda seq: "-".join(seq))

    if "actual_stops" not in act.columns:
        act["actual_stops"] = act["actual_compounds"].map(lambda seq: max(len(seq) - 1, 0) if seq else np.nan)

    if "actual_first_compound" not in act.columns:
        act["actual_first_compound"] = act["actual_compounds"].map(lambda seq: seq[0] if seq else "")

    keep_pred_cols = [
        "Driver",
        "Team" if "Team" in pred.columns else None,
        "predicted_strategy",
        "predicted_strategy_source_column",
        "predicted_strategy_compact",
        "predicted_stops",
        "predicted_first_compound",
    ]
    keep_pred_cols = [col for col in keep_pred_cols if col is not None and col in pred.columns]

    keep_actual_cols = [
        "Driver",
        "Team" if "Team" in act.columns else None,
        "actual_strategy",
        "actual_strategy_compact",
        "actual_stops",
        "actual_first_compound",
        "actual_dry_strategy",
        "actual_dry_stops",
        "completed_likely",
        "had_wet_compound",
        "actual_strategy_source",
    ]
    keep_actual_cols = [col for col in keep_actual_cols if col is not None and col in act.columns]

    comparison = pred[keep_pred_cols].merge(
        act[keep_actual_cols],
        on="Driver",
        how="left",
        suffixes=("_predicted", "_actual"),
    )

    def _pred_seq(row: pd.Series) -> list[str]:
        return parse_strategy_sequence(row.get("predicted_strategy_compact", ""))

    def _actual_seq(row: pd.Series) -> list[str]:
        return parse_strategy_sequence(row.get("actual_strategy_compact", ""))

    predicted_sequences = comparison.apply(_pred_seq, axis=1)
    actual_sequences = comparison.apply(_actual_seq, axis=1)

    comparison["exact_strategy_match"] = [
        bool(pred_seq and act_seq and pred_seq == act_seq)
        for pred_seq, act_seq in zip(predicted_sequences, actual_sequences)
    ]
    comparison["stop_count_match"] = (
        pd.to_numeric(comparison["predicted_stops"], errors="coerce")
        == pd.to_numeric(comparison["actual_stops"], errors="coerce")
    )
    comparison["first_compound_match"] = (
        comparison["predicted_first_compound"].astype(str)
        == comparison["actual_first_compound"].astype(str)
    ) & comparison["actual_first_compound"].astype(str).ne("")
    comparison["same_compounds_any_order"] = [
        _counter_match(pred_seq, act_seq)
        for pred_seq, act_seq in zip(predicted_sequences, actual_sequences)
    ]
    comparison["strategy_stop_error"] = (
        pd.to_numeric(comparison["predicted_stops"], errors="coerce")
        - pd.to_numeric(comparison["actual_stops"], errors="coerce")
    )
    comparison["strategy_abs_stop_error"] = comparison["strategy_stop_error"].abs()

    comparison["strategy_match_score"] = (
        comparison["stop_count_match"].astype(float) * 0.45
        + comparison["first_compound_match"].astype(float) * 0.20
        + comparison["same_compounds_any_order"].astype(float) * 0.20
        + comparison["exact_strategy_match"].astype(float) * 0.15
    )

    return comparison


def summarise_strategy_comparison(comparison: pd.DataFrame) -> pd.DataFrame:
    if comparison.empty:
        return pd.DataFrame()

    valid = comparison.dropna(subset=["actual_strategy"]).copy()

    if valid.empty:
        return pd.DataFrame()

    metrics = {
        "drivers_compared": int(len(valid)),
        "exact_strategy_match_rate": float(valid["exact_strategy_match"].mean()),
        "stop_count_match_rate": float(valid["stop_count_match"].mean()),
        "first_compound_match_rate": float(valid["first_compound_match"].mean()),
        "same_compounds_any_order_rate": float(valid["same_compounds_any_order"].mean()),
        "average_abs_stop_error": float(pd.to_numeric(valid["strategy_abs_stop_error"], errors="coerce").mean()),
        "average_strategy_match_score": float(pd.to_numeric(valid["strategy_match_score"], errors="coerce").mean()),
        "actual_strategy_source": str(valid["actual_strategy_source"].dropna().iloc[0]) if "actual_strategy_source" in valid.columns and not valid["actual_strategy_source"].dropna().empty else "fastf1_race_lap_stint_data",
    }

    return pd.DataFrame([metrics])


def make_strategy_comparison_image(
    comparison: pd.DataFrame,
    output_path: str | Path,
    title: str = "Predicted vs Actual Tyre Strategy",
) -> str:
    """Creates a compact PNG table for backtest strategy comparison."""

    if comparison.empty:
        return ""

    try:
        import matplotlib.pyplot as plt
    except Exception:
        return ""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    display = comparison.copy().head(24)

    cols = [
        "Driver",
        "predicted_strategy_compact",
        "actual_strategy_compact",
        "predicted_stops",
        "actual_stops",
        "stop_count_match",
        "exact_strategy_match",
        "strategy_match_score",
    ]

    for col in cols:
        if col not in display.columns:
            display[col] = ""

    display = display[cols].copy()
    display.columns = ["Driver", "Predicted", "Actual", "Pred stops", "Actual stops", "Stops OK", "Exact", "Score"]

    display["Stops OK"] = display["Stops OK"].map(lambda value: "Yes" if bool(value) else "No")
    display["Exact"] = display["Exact"].map(lambda value: "Yes" if bool(value) else "No")
    display["Score"] = pd.to_numeric(display["Score"], errors="coerce").map(lambda value: f"{value:.0%}" if pd.notna(value) else "")

    fig_height = max(4.0, min(14.0, 1.2 + 0.34 * len(display)))
    fig, ax = plt.subplots(figsize=(16, fig_height))
    ax.axis("off")
    ax.set_title(title, fontsize=16, fontweight="bold", loc="left", pad=14)

    table = ax.table(
        cellText=display.values,
        colLabels=display.columns,
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.35)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#e5e7eb")
        elif row % 2 == 0:
            cell.set_facecolor("#f8fafc")

        if row > 0 and col in {5, 6}:
            text = cell.get_text().get_text()
            if text == "Yes":
                cell.set_facecolor("#dcfce7")
            elif text == "No":
                cell.set_facecolor("#fee2e2")

    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)

    return str(output_path)
