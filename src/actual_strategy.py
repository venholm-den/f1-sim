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
    "M": "MEDIUM",
    "MN": "MEDIUM",
    "MU": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "S": "SOFT",
    "SN": "SOFT",
    "SU": "SOFT",
    "SOFT": "SOFT",
    "I": "INTERMEDIATE",
    "IN": "INTERMEDIATE",
    "INTER": "INTERMEDIATE",
    "INTERMEDIATE": "INTERMEDIATE",
    "W": "WET",
    "WN": "WET",
    "WET": "WET",
}


def normalise_driver(value: Any) -> str:
    return str(value or "").strip().upper()


def normalise_compound(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("(NEW)", "").replace("(USED)", "").replace("(UNKNOWN)", "")
    text = text.replace("USED/UNKNOWN", "").replace("UNKNOWN", "")
    text = "".join(char for char in text if char.isalpha())
    return _COMPOUND_ALIASES.get(text, text if text in ALL_COMPOUNDS else "UNKNOWN")


def _dominant_compound(stint: pd.DataFrame) -> str:
    """Return the most common compound for a stint.

    Prefer the pre-normalised CompoundNormalised column when available. Do not
    rename CompoundNormalised to Compound before calling this helper because
    that can create duplicate Compound columns in pandas, which makes
    stint["Compound"] return a DataFrame instead of a Series.
    """

    if "CompoundNormalised" in stint.columns:
        compounds = stint["CompoundNormalised"].map(normalise_compound)
    elif "Compound" in stint.columns:
        compounds = stint["Compound"].map(normalise_compound)
    else:
        return "UNKNOWN"

    compounds = compounds[compounds.isin(ALL_COMPOUNDS)]

    if compounds.empty:
        return "UNKNOWN"

    return str(compounds.value_counts().index[0])


def _strategy_string(sequence: list[str]) -> str:
    return "-".join(compound for compound in sequence if compound in ALL_COMPOUNDS)


def parse_strategy_sequence(value: Any) -> list[str]:
    """
    Parse the strategy formats used around the project into a list of compounds.

    Supported examples:
    - "Medium(new) → Hard(new) → Soft(used/unknown)"
    - "MEDIUM-HARD-MEDIUM"
    - "Mn Hn Sn"
    - "Soft -> Medium -> Hard"

    Important: do not split on the slash inside "used/unknown" before the
    compound has been extracted. Otherwise "Soft(used/unknown)" becomes two
    broken tokens and the soft stint is lost.
    """

    text = str(value or "").strip()

    if not text:
        return []

    # Remove project status suffixes before replacing separators. This keeps
    # Soft(used/unknown) as Soft instead of splitting on the slash.
    text = re.sub(
        r"\((?:new|used|unknown|used\s*/\s*unknown)\)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    replacements = {
        "→": "-",
        "->": "-",
        ">": "-",
        ",": "-",
        "|": "-",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # If a visual code string is space-separated, e.g. "Mn Hn Sn", split on spaces too.
    if "-" not in text and " " in text:
        parts = text.split()
    else:
        parts = text.split("-")

    sequence: list[str] = []

    for part in parts:
        compound = normalise_compound(part)
        if compound in ALL_COMPOUNDS:
            sequence.append(compound)

    return sequence


def strategy_stops(strategy: Any) -> int:
    sequence = parse_strategy_sequence(strategy)
    return max(len(sequence) - 1, 0) if sequence else 0


def strategy_first_compound(strategy: Any) -> str:
    sequence = parse_strategy_sequence(strategy)
    return sequence[0] if sequence else ""


def strategy_same_compounds_any_order(predicted: Any, actual: Any) -> bool:
    predicted_sequence = parse_strategy_sequence(predicted)
    actual_sequence = parse_strategy_sequence(actual)
    return bool(predicted_sequence and actual_sequence and Counter(predicted_sequence) == Counter(actual_sequence))


def strategy_overlap_score(predicted: Any, actual: Any) -> float:
    predicted_sequence = parse_strategy_sequence(predicted)
    actual_sequence = parse_strategy_sequence(actual)

    if not predicted_sequence or not actual_sequence:
        return 0.0

    if predicted_sequence == actual_sequence:
        return 1.0

    predicted_stops = max(len(predicted_sequence) - 1, 0)
    actual_stops = max(len(actual_sequence) - 1, 0)
    stops_match = predicted_stops == actual_stops
    first_match = predicted_sequence[0] == actual_sequence[0]

    predicted_counter = Counter(predicted_sequence)
    actual_counter = Counter(actual_sequence)
    overlap = sum((predicted_counter & actual_counter).values())
    denominator = max(len(predicted_sequence), len(actual_sequence), 1)
    compound_overlap = overlap / denominator

    score = 0.45 * float(stops_match) + 0.20 * float(first_match) + 0.35 * compound_overlap
    return float(np.clip(score, 0.0, 1.0))


def extract_actual_strategy_from_session(
    race_session: Any,
    metadata: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Reconstruct the completed race tyre strategy from FastF1 lap/stint data.

    This is actual race strategy inferred from FastF1 lap compound data. It is not
    FIA/Pirelli barcode-level tyre set allocation data.
    """

    metadata = metadata or {}
    laps = getattr(race_session, "laps", pd.DataFrame())

    if laps is None or laps.empty:
        return pd.DataFrame()

    required = {"Driver", "LapNumber", "Compound"}
    if not required.issubset(set(laps.columns)):
        return pd.DataFrame()

    df = laps.copy()

    if "Stint" not in df.columns:
        # FastF1 race laps normally include Stint. If it is missing, infer a new
        # stint when the compound changes for a driver.
        df = df.sort_values(["Driver", "LapNumber"]).copy()
        df["CompoundNormalised"] = df["Compound"].map(normalise_compound)
        df["Stint"] = (
            df.groupby("Driver")["CompoundNormalised"]
            .transform(lambda s: s.ne(s.shift()).cumsum())
            .astype(int)
        )
    else:
        df["CompoundNormalised"] = df["Compound"].map(normalise_compound)

    df["Driver"] = df["Driver"].map(normalise_driver)
    df["Team"] = df["Team"].astype(str) if "Team" in df.columns else ""
    df["LapNumber"] = pd.to_numeric(df["LapNumber"], errors="coerce")
    df["Stint"] = pd.to_numeric(df["Stint"], errors="coerce")

    df = df.dropna(subset=["Driver", "LapNumber"])
    df = df[df["CompoundNormalised"].isin(ALL_COMPOUNDS)].copy()

    if df.empty:
        return pd.DataFrame()

    race_lap_count = int(df["LapNumber"].max())
    rows: list[dict[str, Any]] = []

    for driver, driver_laps in df.groupby("Driver"):
        driver_laps = driver_laps.sort_values("LapNumber").copy()

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

        # Remove tiny one-lap anomaly stints where there are enough other stints.
        if len(stint_df) > 1:
            filtered = stint_df[stint_df["Laps"] >= 2].copy()
            if not filtered.empty:
                stint_df = filtered.reset_index(drop=True)

        sequence = stint_df["Compound"].astype(str).tolist()
        dry_sequence = [compound for compound in sequence if compound in DRY_COMPOUNDS]
        had_wet = any(compound in WET_COMPOUNDS for compound in sequence)

        if not sequence:
            continue

        actual_strategy = _strategy_string(dry_sequence or sequence)
        actual_stops = max(len(dry_sequence or sequence) - 1, 0)

        rows.append(
            {
                "year": metadata.get("year"),
                "event": metadata.get("event"),
                "round": metadata.get("round"),
                "Driver": driver,
                "Team": team,
                "actual_strategy": actual_strategy,
                "actual_strategy_sequence": actual_strategy,
                "actual_stops": int(actual_stops),
                "actual_stint_count": int(len(dry_sequence or sequence)),
                "actual_first_compound": (dry_sequence or sequence)[0] if (dry_sequence or sequence) else "",
                "actual_had_wet_compound": bool(had_wet),
                "actual_completed_likely": bool(completed_likely),
                "actual_race_laps": race_lap_count,
                "actual_driver_max_lap": max_driver_lap,
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Driver").reset_index(drop=True)


def _find_predicted_strategy_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "PredictedStrategy",
        "predicted_strategy",
        "history_adjusted_strategy",
        "HistoryAdjustedStrategy",
        "primary_strategy",
        "PrimaryStrategy",
        "strategy",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    return None


def build_strategy_comparison(
    predictions: pd.DataFrame,
    actual_strategy: pd.DataFrame,
) -> pd.DataFrame:
    if predictions is None or predictions.empty:
        raise ValueError("No prediction rows supplied for strategy comparison.")

    if actual_strategy is None or actual_strategy.empty:
        raise ValueError("No actual strategy rows supplied for strategy comparison.")

    predicted = predictions.copy()
    actual = actual_strategy.copy()

    if "Driver" not in predicted.columns:
        raise ValueError("Prediction dataframe must include a Driver column.")

    predicted["Driver"] = predicted["Driver"].map(normalise_driver)
    actual["Driver"] = actual["Driver"].map(normalise_driver)

    strategy_col = _find_predicted_strategy_column(predicted)

    if strategy_col is None:
        predicted["predicted_strategy"] = ""
    else:
        predicted["predicted_strategy"] = predicted[strategy_col].astype(str)

    if "Team" not in predicted.columns:
        predicted["Team"] = ""

    predicted["predicted_strategy_source_column"] = strategy_col or "missing"

    predicted_cols = [
        "Driver",
        "Team",
        "predicted_strategy",
        "predicted_strategy_source_column",
    ]

    if "Grid" in predicted.columns:
        predicted_cols.append("Grid")
    if "GridPosition" in predicted.columns:
        predicted_cols.append("GridPosition")
    if "grid_position" in predicted.columns:
        predicted_cols.append("grid_position")

    comparison = predicted[predicted_cols].merge(
        actual[
            [
                "Driver",
                "actual_strategy",
                "actual_stops",
                "actual_stint_count",
                "actual_first_compound",
                "actual_completed_likely",
                "actual_had_wet_compound",
                "actual_strategy_source",
            ]
        ],
        on="Driver",
        how="left",
    )

    comparison["predicted_strategy_sequence"] = comparison["predicted_strategy"].map(
        lambda value: _strategy_string(parse_strategy_sequence(value))
    )
    comparison["actual_strategy_sequence"] = comparison["actual_strategy"].fillna("").map(
        lambda value: _strategy_string(parse_strategy_sequence(value))
    )
    comparison["predicted_stops"] = comparison["predicted_strategy_sequence"].map(strategy_stops)
    comparison["actual_stops"] = pd.to_numeric(comparison["actual_stops"], errors="coerce")
    comparison["strategy_stop_error"] = comparison["predicted_stops"] - comparison["actual_stops"]
    comparison["strategy_stop_abs_error"] = comparison["strategy_stop_error"].abs()
    comparison["stops_match"] = comparison["strategy_stop_error"].fillna(999).eq(0)
    comparison["exact_strategy_match"] = (
        comparison["predicted_strategy_sequence"].astype(str)
        == comparison["actual_strategy_sequence"].astype(str)
    ) & comparison["actual_strategy_sequence"].astype(str).ne("")
    comparison["predicted_first_compound"] = comparison["predicted_strategy_sequence"].map(strategy_first_compound)
    comparison["first_compound_match"] = (
        comparison["predicted_first_compound"].astype(str)
        == comparison["actual_first_compound"].astype(str)
    ) & comparison["actual_first_compound"].astype(str).ne("")
    comparison["same_compounds_any_order"] = comparison.apply(
        lambda row: strategy_same_compounds_any_order(
            row.get("predicted_strategy_sequence", ""),
            row.get("actual_strategy_sequence", ""),
        ),
        axis=1,
    )
    comparison["strategy_score"] = comparison.apply(
        lambda row: strategy_overlap_score(
            row.get("predicted_strategy_sequence", ""),
            row.get("actual_strategy_sequence", ""),
        ),
        axis=1,
    )

    output_cols = [
        "Driver",
        "Team",
        "predicted_strategy_sequence",
        "actual_strategy_sequence",
        "predicted_stops",
        "actual_stops",
        "stops_match",
        "exact_strategy_match",
        "first_compound_match",
        "same_compounds_any_order",
        "strategy_score",
        "strategy_stop_error",
        "strategy_stop_abs_error",
        "predicted_strategy_source_column",
        "actual_strategy_source",
        "actual_completed_likely",
        "actual_had_wet_compound",
    ]

    extra = [col for col in comparison.columns if col not in output_cols]
    return comparison[output_cols + extra].reset_index(drop=True)


def build_strategy_metrics(
    strategy_comparison: pd.DataFrame,
    year: int | None = None,
    event: str | None = None,
) -> pd.DataFrame:
    if strategy_comparison is None or strategy_comparison.empty:
        return pd.DataFrame(
            [
                {
                    "year": year,
                    "event": event,
                    "drivers_compared": 0,
                    "exact_strategy_accuracy": np.nan,
                    "stop_count_accuracy": np.nan,
                    "first_compound_accuracy": np.nan,
                    "same_compounds_any_order_accuracy": np.nan,
                    "average_strategy_score": np.nan,
                    "average_stop_error": np.nan,
                    "average_abs_stop_error": np.nan,
                    "actual_strategy_source": "fastf1_race_lap_stint_data",
                }
            ]
        )

    valid = strategy_comparison.dropna(subset=["actual_strategy_sequence"]).copy()
    valid = valid[valid["actual_strategy_sequence"].astype(str).ne("")]

    if valid.empty:
        drivers_compared = 0
    else:
        drivers_compared = int(len(valid))

    def mean_bool(column: str) -> float:
        if drivers_compared == 0 or column not in valid.columns:
            return float("nan")
        return float(valid[column].astype(bool).mean())

    metrics = {
        "year": year,
        "event": event,
        "drivers_compared": drivers_compared,
        "exact_strategy_matches": int(valid["exact_strategy_match"].astype(bool).sum()) if drivers_compared else 0,
        "stop_count_matches": int(valid["stops_match"].astype(bool).sum()) if drivers_compared else 0,
        "exact_strategy_accuracy": mean_bool("exact_strategy_match"),
        "stop_count_accuracy": mean_bool("stops_match"),
        "first_compound_accuracy": mean_bool("first_compound_match"),
        "same_compounds_any_order_accuracy": mean_bool("same_compounds_any_order"),
        "average_strategy_score": float(pd.to_numeric(valid.get("strategy_score"), errors="coerce").mean()) if drivers_compared else float("nan"),
        "average_stop_error": float(pd.to_numeric(valid.get("strategy_stop_error"), errors="coerce").mean()) if drivers_compared else float("nan"),
        "average_abs_stop_error": float(pd.to_numeric(valid.get("strategy_stop_abs_error"), errors="coerce").mean()) if drivers_compared else float("nan"),
        "actual_strategy_source": "fastf1_race_lap_stint_data",
    }

    return pd.DataFrame([metrics])


def save_strategy_outputs(
    actual_strategy: pd.DataFrame,
    strategy_comparison: pd.DataFrame,
    strategy_metrics: pd.DataFrame,
    output_dir: str | Path,
    stem: str,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    actual_path = output_path / f"{stem}_actual_strategy.csv"
    comparison_path = output_path / f"{stem}_strategy_comparison.csv"
    metrics_path = output_path / f"{stem}_strategy_metrics.csv"

    actual_strategy.to_csv(actual_path, index=False)
    strategy_comparison.to_csv(comparison_path, index=False)
    strategy_metrics.to_csv(metrics_path, index=False)

    return {
        "actual_strategy": str(actual_path),
        "strategy_comparison": str(comparison_path),
        "strategy_metrics": str(metrics_path),
    }