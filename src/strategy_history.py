from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.collect import load_session
from src.strategy import make_strategy_table_image


DRY_COMPOUNDS = ["HARD", "MEDIUM", "SOFT"]
WET_COMPOUNDS = ["INTERMEDIATE", "WET"]
ALL_COMPOUNDS = DRY_COMPOUNDS + WET_COMPOUNDS

EVENT_STOP_WORDS = {
    "grand",
    "prix",
    "gp",
    "the",
    "of",
    "formula",
    "1",
    "f1",
}


def _ensure_outputs() -> None:
    Path("outputs/history").mkdir(parents=True, exist_ok=True)
    Path("outputs/strategy").mkdir(parents=True, exist_ok=True)


def _ensure_output_dirs(output_dir: str | Path) -> tuple[Path, Path]:
    root = Path(output_dir)
    history_dir = root / "history"
    strategy_dir = root / "strategy"

    history_dir.mkdir(parents=True, exist_ok=True)
    strategy_dir.mkdir(parents=True, exist_ok=True)

    return history_dir, strategy_dir


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


def _clean_text(value: Any) -> str:
    text = str(value).lower()
    text = text.replace("-", " ").replace("_", " ").replace("/", " ")

    cleaned = "".join(char if char.isalnum() or char.isspace() else " " for char in text)
    cleaned = " ".join(cleaned.split())

    return cleaned


def _event_tokens(event_name: str) -> list[str]:
    clean = _clean_text(event_name)

    return [
        token
        for token in clean.split()
        if token and token not in EVENT_STOP_WORDS and len(token) > 2
    ]


def _score_schedule_row(row: pd.Series, event_name: str) -> int:
    target = _clean_text(event_name)
    tokens = _event_tokens(event_name)

    fields = []

    for col in ["EventName", "OfficialEventName", "Location", "Country"]:
        if col in row.index:
            fields.append(str(row.get(col, "")))

    haystack = _clean_text(" ".join(fields))

    score = 0

    if target and target in haystack:
        score += 100

    for token in tokens:
        if token in haystack:
            score += 12

    # Common naming mismatch: Barcelona GP vs Spanish GP.
    if "barcelona" in target and ("spanish" in haystack or "spain" in haystack):
        score += 40

    if "spanish" in target and "barcelona" in haystack:
        score += 30

    return score


def _find_round_for_event(year: int, event_name: str) -> int | None:
    try:
        import fastf1

        schedule = fastf1.get_event_schedule(year)
    except Exception as exc:
        print(f"Could not load event schedule for {year}: {exc}")
        return None

    if schedule.empty or "RoundNumber" not in schedule.columns:
        return None

    scored = schedule.copy()
    scored["match_score"] = scored.apply(
        lambda row: _score_schedule_row(row, event_name),
        axis=1,
    )

    scored = scored.sort_values("match_score", ascending=False)

    if scored.empty:
        return None

    best = scored.iloc[0]
    score = int(best["match_score"])

    if score < 12:
        return None

    round_number = _to_float_or_none(best.get("RoundNumber"))

    if round_number is None:
        return None

    return int(round(round_number))


def _load_historical_race(year: int, event_name: str) -> tuple[Any, dict] | None:
    """
    Tries to load a previous race for the same event.

    First tries the event name directly. If FastF1 cannot match it, it searches
    the schedule for that year and loads by round number.
    """

    try:
        return load_session(year, event_name, "R")
    except Exception:
        pass

    round_number = _find_round_for_event(year, event_name)

    if round_number is None:
        print(f"Historical strategy skipped {year}: could not match event {event_name}")
        return None

    try:
        return load_session(year, round_number, "R")
    except Exception as exc:
        print(f"Historical strategy skipped {year}: {exc}")
        return None


def _dominant_compound(stint: pd.DataFrame) -> str:
    if "Compound" not in stint.columns:
        return "UNKNOWN"

    compounds = (
        stint["Compound"]
        .astype(str)
        .str.upper()
        .replace({"NAN": "UNKNOWN", "NONE": "UNKNOWN"})
    )

    compounds = compounds[compounds.isin(ALL_COMPOUNDS)]

    if compounds.empty:
        return "UNKNOWN"

    counts = compounds.value_counts()

    return str(counts.index[0])


def extract_race_strategy_from_session(
    race_session: Any,
    metadata: dict,
) -> pd.DataFrame:
    """
    Extracts actual race tyre strategy sequences from FastF1 race laps.

    Output is driver-level:
    - StrategySequence, e.g. MEDIUM-HARD-MEDIUM
    - Stops
    - HadWetCompound
    - CompletedLikely
    """

    laps = race_session.laps.copy()

    required = {"Driver", "LapNumber", "Compound"}

    if not required.issubset(set(laps.columns)):
        return pd.DataFrame()

    if "Stint" not in laps.columns:
        return pd.DataFrame()

    df = laps.copy()

    df["Driver"] = df["Driver"].astype(str)
    df["Team"] = df["Team"].astype(str) if "Team" in df.columns else ""
    df["LapNumber"] = pd.to_numeric(df["LapNumber"], errors="coerce")
    df["Stint"] = pd.to_numeric(df["Stint"], errors="coerce")
    df["Compound"] = df["Compound"].astype(str).str.upper()

    df = df.dropna(subset=["Driver", "LapNumber"])
    df = df[df["Compound"].isin(ALL_COMPOUNDS)].copy()

    if df.empty:
        return pd.DataFrame()

    race_lap_count = int(df["LapNumber"].max())

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

        stint_rows = []

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

        # Remove tiny 1-lap anomaly stints where possible.
        if len(stint_df) > 1:
            filtered = stint_df[stint_df["Laps"] >= 2].copy()

            if not filtered.empty:
                stint_df = filtered.reset_index(drop=True)

        sequence = stint_df["Compound"].astype(str).tolist()

        if not sequence:
            continue

        had_wet = any(compound in WET_COMPOUNDS for compound in sequence)
        dry_sequence = [compound for compound in sequence if compound in DRY_COMPOUNDS]

        rows.append(
            {
                "Year": metadata.get("year"),
                "Event": metadata.get("event"),
                "Round": metadata.get("round"),
                "Driver": driver,
                "Team": team,
                "RaceLaps": race_lap_count,
                "DriverMaxLap": max_driver_lap,
                "CompletedLikely": bool(completed_likely),
                "HadWetCompound": bool(had_wet),
                "StintCount": int(len(sequence)),
                "Stops": int(max(len(sequence) - 1, 0)),
                "StrategySequence": "-".join(sequence),
                "DryStintCount": int(len(dry_sequence)),
                "DryStops": int(max(len(dry_sequence) - 1, 0)),
                "DryStrategySequence": "-".join(dry_sequence),
            }
        )

    return pd.DataFrame(rows)


def build_historical_strategy_baseline(
    current_year: int,
    event_name: str,
    lookback_years: int = 5,
    output_dir: str | Path = "outputs",
) -> dict[str, Any]:
    history_dir, _ = _ensure_output_dirs(output_dir)

    frames: list[pd.DataFrame] = []
    years_used: list[int] = []

    start_year = current_year - 1
    end_year = max(current_year - lookback_years, 2018)

    for year in range(start_year, end_year - 1, -1):
        loaded = _load_historical_race(year, event_name)

        if loaded is None:
            continue

        race_session, metadata = loaded

        extracted = extract_race_strategy_from_session(race_session, metadata)

        if extracted.empty:
            print(f"Historical strategy skipped {year}: no strategy rows extracted")
            continue

        frames.append(extracted)
        years_used.append(year)

    if not frames:
        return {
            "driver_runs_path": "",
            "summary_path": "",
            "summary_data": {},
        }

    all_runs = pd.concat(frames, ignore_index=True)

    driver_runs_path = str(history_dir / "historical_strategy_driver_runs.csv")
    all_runs.to_csv(driver_runs_path, index=False)

    valid = all_runs[
        all_runs["CompletedLikely"].astype(bool)
        & ~all_runs["HadWetCompound"].astype(bool)
        & (pd.to_numeric(all_runs["DryStintCount"], errors="coerce") >= 2)
    ].copy()

    if valid.empty:
        return {
            "driver_runs_path": driver_runs_path,
            "summary_path": "",
            "summary_data": {},
        }

    valid["DryStops"] = pd.to_numeric(valid["DryStops"], errors="coerce").fillna(0).astype(int)
    valid["DryStrategySequence"] = valid["DryStrategySequence"].astype(str)

    strategy_counts = (
        valid.groupby(["DryStops", "DryStrategySequence"], dropna=False)
        .size()
        .reset_index(name="Count")
        .sort_values(["Count", "DryStops"], ascending=[False, False])
        .reset_index(drop=True)
    )

    strategy_counts_path = str(history_dir / "historical_strategy_summary.csv")
    strategy_counts.to_csv(strategy_counts_path, index=False)

    stop_counts = valid["DryStops"].value_counts(normalize=True)
    sample_drivers = int(len(valid))

    dominant = strategy_counts.iloc[0]

    two_stop = strategy_counts[strategy_counts["DryStops"] == 2].copy()

    if not two_stop.empty:
        dominant_two_stop_strategy = str(two_stop.iloc[0]["DryStrategySequence"])
    else:
        dominant_two_stop_strategy = ""

    three_stop = strategy_counts[strategy_counts["DryStops"] >= 3].copy()

    if not three_stop.empty:
        dominant_three_stop_strategy = str(three_stop.iloc[0]["DryStrategySequence"])
    else:
        dominant_three_stop_strategy = ""

    summary_data = {
        "years_used": ",".join(str(year) for year in sorted(years_used)),
        "sample_drivers": sample_drivers,
        "average_stops": float(valid["DryStops"].mean()),
        "dominant_stops": int(dominant["DryStops"]),
        "dominant_strategy": str(dominant["DryStrategySequence"]),
        "dominant_strategy_count": int(dominant["Count"]),
        "one_stop_rate": float(stop_counts.get(1, 0.0)),
        "two_stop_rate": float(stop_counts.get(2, 0.0)),
        "three_plus_stop_rate": float(valid["DryStops"].ge(3).mean()),
        "dominant_two_stop_strategy": dominant_two_stop_strategy,
        "dominant_three_stop_strategy": dominant_three_stop_strategy,
        "driver_runs_path": driver_runs_path,
        "summary_path": strategy_counts_path,
    }

    baseline_path = str(history_dir / "historical_strategy_baseline.csv")
    pd.DataFrame([summary_data]).to_csv(baseline_path, index=False)

    return {
        "driver_runs_path": driver_runs_path,
        "summary_path": strategy_counts_path,
        "baseline_path": baseline_path,
        "summary_data": summary_data,
    }


def _strategy_stint_count(strategy_text: Any) -> int:
    text = str(strategy_text)

    if "→" in text:
        return len([part for part in text.split("→") if part.strip()])

    if "->" in text:
        return len([part for part in text.split("->") if part.strip()])

    return 1 if text.strip() else 0


def _parse_historical_sequence(sequence: str) -> list[str]:
    compounds = [
        part.strip().upper()
        for part in str(sequence).replace("→", "-").replace(">", "-").split("-")
    ]

    return [compound for compound in compounds if compound in DRY_COMPOUNDS]


def _fallback_two_stop_sequence(row: pd.Series, grid_position: float | None) -> list[str]:
    fresh_hard = int(_to_float_or_none(row.get("FreshHardRemaining")) or 0)
    fresh_medium = int(_to_float_or_none(row.get("FreshMediumRemaining")) or 0)
    fresh_soft = int(_to_float_or_none(row.get("FreshSoftRemaining")) or 0)

    grid = grid_position if grid_position is not None else 12

    if fresh_medium >= 2 and fresh_hard >= 1:
        return ["MEDIUM", "HARD", "MEDIUM"]

    if fresh_soft >= 1 and fresh_medium >= 1 and fresh_hard >= 1:
        if grid >= 13:
            return ["HARD", "MEDIUM", "SOFT"]

        return ["SOFT", "MEDIUM", "HARD"]

    if fresh_hard >= 1 and fresh_medium >= 1:
        return ["MEDIUM", "HARD", "MEDIUM"]

    return ["SOFT", "MEDIUM", "HARD"]


def _fallback_three_stop_sequence(row: pd.Series) -> list[str]:
    fresh_hard = int(_to_float_or_none(row.get("FreshHardRemaining")) or 0)
    fresh_medium = int(_to_float_or_none(row.get("FreshMediumRemaining")) or 0)
    fresh_soft = int(_to_float_or_none(row.get("FreshSoftRemaining")) or 0)

    if fresh_medium >= 2 and fresh_soft >= 1 and fresh_hard >= 1:
        return ["SOFT", "MEDIUM", "HARD", "MEDIUM"]

    if fresh_medium >= 2 and fresh_hard >= 1:
        return ["MEDIUM", "HARD", "MEDIUM", "SOFT"]

    return ["SOFT", "MEDIUM", "HARD", "SOFT"]


def _driver_specific_two_stop_sequence(row: pd.Series, grid_position: float | None) -> list[str]:
    """
    Chooses a two-stop compound sequence per driver.

    Historical data is used as a stop-count signal, not as a field-wide compound
    template. This avoids giving every driver the same historical sequence.
    Compound choice remains driven by grid position, estimated tyre inventory,
    and tyre-risk information.
    """

    fresh_hard = int(_to_float_or_none(row.get("FreshHardRemaining")) or 0)
    fresh_medium = int(_to_float_or_none(row.get("FreshMediumRemaining")) or 0)
    fresh_soft = int(_to_float_or_none(row.get("FreshSoftRemaining")) or 0)

    grid = grid_position if grid_position is not None else 12
    risk = str(row.get("OldTyreRisk", row.get("strategy_risk_level", "Medium")))

    # Front runners: prefer medium/hard based two-stops, closer to a
    # tyre-management race than an all-out soft-heavy plan.
    if grid <= 5:
        if fresh_medium >= 1 and fresh_hard >= 2:
            return ["MEDIUM", "HARD", "HARD"]
        if fresh_medium >= 2 and fresh_hard >= 1:
            return ["MEDIUM", "HARD", "MEDIUM"]
        if fresh_medium >= 1 and fresh_hard >= 1 and fresh_soft >= 1:
            return ["MEDIUM", "HARD", "SOFT"]

    # Upper midfield: default to a medium-hard-medium style two-stop where
    # possible. This avoids a soft-heavy field-wide override.
    if grid <= 10:
        if fresh_medium >= 2 and fresh_hard >= 1:
            return ["MEDIUM", "HARD", "MEDIUM"]
        if fresh_medium >= 1 and fresh_hard >= 1 and fresh_soft >= 1:
            return ["MEDIUM", "HARD", "SOFT"]

    # Lower midfield: alternate strategy is more plausible, especially if the
    # base model put them on a simple one-stop.
    if grid <= 16:
        if fresh_hard >= 1 and fresh_medium >= 1 and fresh_soft >= 1:
            return ["HARD", "MEDIUM", "SOFT"]
        if fresh_medium >= 2 and fresh_hard >= 1:
            return ["MEDIUM", "HARD", "MEDIUM"]

    # Back of the field can justify a more aggressive offset, but avoid soft
    # starts if the tyre-risk model is already warning.
    if grid >= 17:
        if risk != "High" and fresh_soft >= 1 and fresh_medium >= 1 and fresh_hard >= 1:
            return ["SOFT", "MEDIUM", "HARD"]
        if fresh_hard >= 1 and fresh_medium >= 1 and fresh_soft >= 1:
            return ["HARD", "MEDIUM", "SOFT"]
        if fresh_medium >= 2 and fresh_hard >= 1:
            return ["MEDIUM", "HARD", "MEDIUM"]

    # Safe fallbacks.
    if fresh_medium >= 2 and fresh_hard >= 1:
        return ["MEDIUM", "HARD", "MEDIUM"]

    if fresh_medium >= 1 and fresh_hard >= 1:
        return ["MEDIUM", "HARD", "MEDIUM"]

    if fresh_soft >= 1 and fresh_medium >= 1 and fresh_hard >= 1:
        return ["SOFT", "MEDIUM", "HARD"]

    return ["MEDIUM", "HARD"]


def _historical_two_stop_sequence(row: pd.Series, history: dict[str, Any], grid_position: float | None) -> list[str]:
    """
    Builds a two-stop history candidate.

    History is used to say "this event usually needs more than a one-stop".
    It should not copy the dominant historical compound sequence onto every
    driver, because that creates unrealistic field-wide uniformity.
    """

    return _driver_specific_two_stop_sequence(row, grid_position)


def _target_sequence_for_row(
    row: pd.Series,
    history: dict[str, Any],
) -> list[str] | None:
    sample_drivers = int(history.get("sample_drivers", 0))
    average_stops = float(history.get("average_stops", 1.0))
    dominant_stops = int(history.get("dominant_stops", 1))
    two_stop_rate = float(history.get("two_stop_rate", 0.0))
    three_plus_rate = float(history.get("three_plus_stop_rate", 0.0))
    multi_stop_rate = two_stop_rate + three_plus_rate

    if sample_drivers < 6:
        return None

    current_stints = _strategy_stint_count(row.get("PredictedStrategy"))
    current_stops = max(current_stints - 1, 0)
    grid_position = _to_float_or_none(row.get("GridPosition"))
    estimated_deg = _to_float_or_none(row.get("EstimatedDegPerLap")) or 0.055

    strong_multi_stop = (
        dominant_stops >= 2
        or multi_stop_rate >= 0.45
        or average_stops >= 1.65
    )

    very_strong_three_stop = (
        dominant_stops >= 3
        and three_plus_rate >= 0.45
        and average_stops >= 2.25
        and estimated_deg >= 0.075
    )

    force_two_stop = (
        dominant_stops == 2
        or two_stop_rate >= 0.35
        or average_stops >= 1.45
        or strong_multi_stop
    )

    mixed_two_stop = (
        multi_stop_rate >= 0.35
        and estimated_deg >= 0.055
    )

    # Most important correction: if the base model is one-stop but history says
    # this event is usually multi-stop, promote to a two-stop candidate first.
    # Do not jump straight to a three-stop pattern for the whole field.
    if current_stops <= 1 and (force_two_stop or mixed_two_stop):
        return _historical_two_stop_sequence(row, history, grid_position)

    if very_strong_three_stop and current_stints < 4:
        historical = _parse_historical_sequence(
            str(history.get("dominant_three_stop_strategy") or history.get("dominant_strategy", ""))
        )

        if len(historical) >= 4:
            return historical[:4]

        return _fallback_three_stop_sequence(row)

    return None


def _compound_display(compound: str) -> str:
    lookup = {
        "HARD": "Hard",
        "MEDIUM": "Medium",
        "SOFT": "Soft",
    }

    return lookup.get(compound.upper(), compound.title())


def _allocate_sequence(
    sequence: list[str],
    row: pd.Series,
) -> tuple[str, int]:
    available = {
        "HARD": int(_to_float_or_none(row.get("FreshHardRemaining")) or 0),
        "MEDIUM": int(_to_float_or_none(row.get("FreshMediumRemaining")) or 0),
        "SOFT": int(_to_float_or_none(row.get("FreshSoftRemaining")) or 0),
    }

    legs: list[str] = []
    old_count = 0

    for compound in sequence:
        display = _compound_display(compound)

        if available.get(compound, 0) > 0:
            available[compound] -= 1
            legs.append(f"{display}(new)")
        else:
            old_count += 1
            legs.append(f"{display}(used/unknown)")

    return " → ".join(legs), old_count


def _risk_label(score: float) -> str:
    if score >= 70:
        return "High"

    if score >= 35:
        return "Medium"

    return "Low"



def _history_adjustment_reason(history: dict[str, Any], sequence: list[str] | None) -> str:
    if sequence is None:
        return "No historical adjustment applied."

    return (
        f"Adjusted using historical strategy baseline {history.get('years_used', 'N/A')}; "
        f"average stops {float(history.get('average_stops', 0.0)):.2f}, "
        f"dominant strategy {history.get('dominant_strategy', 'N/A')}."
    )


def _history_strategy_type(sequence: list[str] | None) -> str:
    if not sequence:
        return "model_estimate"

    stops = max(len(sequence) - 1, 0)

    if stops >= 3:
        return "history_adjusted_three_stop"
    if stops == 2:
        return "history_adjusted_two_stop"
    if stops == 1:
        return "history_adjusted_one_stop"
    return "history_adjusted"


def _ensure_history_comparison_columns(output: pd.DataFrame) -> pd.DataFrame:
    if output is None or output.empty:
        return output

    output = output.copy()

    predicted = output.get("PredictedStrategy", "")

    if "original_predicted_strategy" not in output.columns:
        output["original_predicted_strategy"] = predicted

    if "OriginalPredictedStrategy" not in output.columns:
        output["OriginalPredictedStrategy"] = output["original_predicted_strategy"]

    if "history_adjusted_strategy" not in output.columns:
        output["history_adjusted_strategy"] = output.get("PredictedStrategy", "")

    if "HistoryAdjustedStrategy" not in output.columns:
        output["HistoryAdjustedStrategy"] = output["history_adjusted_strategy"]

    if "history_adjustment_applied" not in output.columns:
        output["history_adjustment_applied"] = False

    if "HistoryAdjustmentApplied" not in output.columns:
        output["HistoryAdjustmentApplied"] = output["history_adjustment_applied"]

    if "history_adjustment_reason" not in output.columns:
        output["history_adjustment_reason"] = "No historical adjustment applied."

    if "HistoryAdjustmentReason" not in output.columns:
        output["HistoryAdjustmentReason"] = output["history_adjustment_reason"]

    if "strategy_changed_by_history" not in output.columns:
        output["strategy_changed_by_history"] = False

    if "StrategyChangedByHistory" not in output.columns:
        output["StrategyChangedByHistory"] = output["strategy_changed_by_history"]

    if "original_strategy_confidence" not in output.columns:
        output["original_strategy_confidence"] = output.get(
            "strategy_confidence",
            output.get("StrategyConfidence", "Medium"),
        )

    if "OriginalStrategyConfidence" not in output.columns:
        output["OriginalStrategyConfidence"] = output["original_strategy_confidence"]

    if "original_strategy_risk_level" not in output.columns:
        output["original_strategy_risk_level"] = output.get(
            "strategy_risk_level",
            output.get("OldTyreRisk", "Medium"),
        )

    if "OriginalStrategyRiskLevel" not in output.columns:
        output["OriginalStrategyRiskLevel"] = output["original_strategy_risk_level"]

    if "strategy_source" not in output.columns:
        output["strategy_source"] = "model_estimate"

    if "StrategySource" not in output.columns:
        output["StrategySource"] = output["strategy_source"]

    if "primary_strategy" not in output.columns:
        output["primary_strategy"] = output.get("PredictedStrategy", "")

    if "PrimaryStrategy" not in output.columns:
        output["PrimaryStrategy"] = output["primary_strategy"]

    if "alternative_strategy" not in output.columns:
        output["alternative_strategy"] = output.get("original_predicted_strategy", "")

    if "AlternativeStrategy" not in output.columns:
        output["AlternativeStrategy"] = output["alternative_strategy"]

    if "expected_stops" not in output.columns:
        output["expected_stops"] = output.get("PredictedStrategy", "").map(_strategy_stint_count) - 1

    if "ExpectedStops" not in output.columns:
        output["ExpectedStops"] = output["expected_stops"]

    if "strategy_type" not in output.columns:
        output["strategy_type"] = "model_estimate"

    if "StrategyType" not in output.columns:
        output["StrategyType"] = output["strategy_type"]

    if "risk_level" not in output.columns and "OldTyreRisk" in output.columns:
        output["risk_level"] = output["OldTyreRisk"]

    if "RiskLevel" not in output.columns and "risk_level" in output.columns:
        output["RiskLevel"] = output["risk_level"]

    if "strategy_risk_level" not in output.columns and "OldTyreRisk" in output.columns:
        output["strategy_risk_level"] = output["OldTyreRisk"]

    if "StrategyRiskLevel" not in output.columns and "strategy_risk_level" in output.columns:
        output["StrategyRiskLevel"] = output["strategy_risk_level"]

    if "strategy_risk_reason" not in output.columns:
        output["strategy_risk_reason"] = (
            "Strategy depends on estimated tyre availability and modelled degradation assumptions."
        )

    if "StrategyRiskReason" not in output.columns:
        output["StrategyRiskReason"] = output["strategy_risk_reason"]

    if "tyre_availability_risk" not in output.columns and "OldTyreRisk" in output.columns:
        output["tyre_availability_risk"] = output["OldTyreRisk"]

    if "TyreAvailabilityRisk" not in output.columns and "tyre_availability_risk" in output.columns:
        output["TyreAvailabilityRisk"] = output["tyre_availability_risk"]

    if "confidence_reason" not in output.columns:
        output["confidence_reason"] = output["strategy_risk_reason"]

    if "ConfidenceReason" not in output.columns:
        output["ConfidenceReason"] = output["confidence_reason"]

    if "history_candidate_strategy" not in output.columns:
        output["history_candidate_strategy"] = ""

    if "HistoryCandidateStrategy" not in output.columns:
        output["HistoryCandidateStrategy"] = output["history_candidate_strategy"]

    if "history_adjustment_confidence" not in output.columns:
        output["history_adjustment_confidence"] = "Low"

    if "HistoryAdjustmentConfidence" not in output.columns:
        output["HistoryAdjustmentConfidence"] = output["history_adjustment_confidence"]

    if "history_adjustment_strength" not in output.columns:
        output["history_adjustment_strength"] = "Low"

    if "HistoryAdjustmentStrength" not in output.columns:
        output["HistoryAdjustmentStrength"] = output["history_adjustment_strength"]

    if "history_adjustment_blocked_reason" not in output.columns:
        output["history_adjustment_blocked_reason"] = ""

    if "HistoryAdjustmentBlockedReason" not in output.columns:
        output["HistoryAdjustmentBlockedReason"] = output["history_adjustment_blocked_reason"]

    if "strategy_display_source" not in output.columns:
        output["strategy_display_source"] = output.get("strategy_source", "model_estimate")

    if "StrategyDisplaySource" not in output.columns:
        output["StrategyDisplaySource"] = output["strategy_display_source"]

    if "visual_key_assumption" not in output.columns:
        output["visual_key_assumption"] = output.get("strategy_reason", output.get("Notes", "Model estimate."))

    if "VisualKeyAssumption" not in output.columns:
        output["VisualKeyAssumption"] = output["visual_key_assumption"]

    return output


def _order_history_strategy_columns(output: pd.DataFrame) -> pd.DataFrame:
    if output is None or output.empty:
        return output

    preferred = [
        "Driver",
        "Team",
        "Grid",
        "GridPosition",
        "original_predicted_strategy",
        "history_candidate_strategy",
        "history_adjusted_strategy",
        "PredictedStrategy",
        "history_adjustment_applied",
        "strategy_changed_by_history",
        "history_adjustment_confidence",
        "history_adjustment_strength",
        "history_adjustment_blocked_reason",
        "history_adjustment_reason",
        "strategy_display_source",
        "visual_key_assumption",
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
        "LikelyOldTyreUse",
        "OldTyreRiskScore",
        "OldTyreRisk",
        "FreshHardRemaining",
        "FreshMediumRemaining",
        "FreshSoftRemaining",
        "EstimatedDegPerLap",
        "inventory_confidence",
        "tyre_data_source",
        "Notes",
    ]

    ordered = [column for column in preferred if column in output.columns]
    remaining = [column for column in output.columns if column not in ordered]

    return output[ordered + remaining].copy()



def _history_signal_metrics(history: dict[str, Any]) -> dict[str, Any]:
    sample_drivers = int(history.get("sample_drivers", 0) or 0)
    dominant_count = int(history.get("dominant_strategy_count", 0) or 0)
    dominant_share = dominant_count / sample_drivers if sample_drivers > 0 else 0.0

    two_stop_rate = float(history.get("two_stop_rate", 0.0) or 0.0)
    three_plus_stop_rate = float(history.get("three_plus_stop_rate", 0.0) or 0.0)

    return {
        "sample_drivers": sample_drivers,
        "average_stops": float(history.get("average_stops", 1.0) or 1.0),
        "dominant_stops": int(history.get("dominant_stops", 1) or 1),
        "dominant_strategy": str(history.get("dominant_strategy", "")),
        "dominant_strategy_count": dominant_count,
        "dominant_share": float(dominant_share),
        "two_stop_rate": two_stop_rate,
        "three_plus_stop_rate": three_plus_stop_rate,
        "multi_stop_rate": two_stop_rate + three_plus_stop_rate,
        "years_used": str(history.get("years_used", "N/A")),
    }


def _history_adjustment_strength(metrics: dict[str, Any], target_stops: int) -> str:
    sample_drivers = int(metrics.get("sample_drivers", 0))
    dominant_share = float(metrics.get("dominant_share", 0.0))
    two_stop_rate = float(metrics.get("two_stop_rate", 0.0))
    three_plus_rate = float(metrics.get("three_plus_stop_rate", 0.0))

    if sample_drivers < 12:
        return "Low"

    if target_stops >= 3:
        if sample_drivers >= 16 and (three_plus_rate >= 0.55 or dominant_share >= 0.55):
            return "High"
        if three_plus_rate >= 0.35 or dominant_share >= 0.40:
            return "Medium"
        return "Low"

    if target_stops == 2:
        average_stops = float(metrics.get("average_stops", 1.0))
        multi_stop_rate = float(metrics.get("multi_stop_rate", two_stop_rate + three_plus_rate))

        if sample_drivers >= 16 and (
            two_stop_rate >= 0.55
            or multi_stop_rate >= 0.65
            or dominant_share >= 0.55
            or average_stops >= 1.85
        ):
            return "High"
        if (
            two_stop_rate >= 0.30
            or multi_stop_rate >= 0.45
            or dominant_share >= 0.40
            or average_stops >= 1.55
        ):
            return "Medium"
        return "Low"

    if dominant_share >= 0.55:
        return "Medium"

    return "Low"


def _history_adjustment_decision(
    row: pd.Series,
    history: dict[str, Any],
    sequence: list[str] | None,
    candidate_strategy: str,
    old_count: int,
    risk_score: float,
) -> tuple[bool, str, str, str]:
    """
    Decides whether history should override the base model strategy.

    History is intentionally conservative here. Historical races can be a useful
    warning that a modelled one-stop is too simple, but it should not force the
    whole field into the same strategy unless the signal is strong and tyre
    availability supports it.

    Returns:
    - applied
    - confidence label
    - strength label
    - reason/blocking explanation
    """

    if not sequence:
        return False, "Low", "Low", "No history-based strategy candidate was generated."

    metrics = _history_signal_metrics(history)
    target_stops = max(len(sequence) - 1, 0)
    current_stops = max(_strategy_stint_count(row.get("PredictedStrategy")) - 1, 0)
    stop_delta = target_stops - current_stops
    estimated_deg = _to_float_or_none(row.get("EstimatedDegPerLap")) or 0.055
    original_strategy = str(row.get("original_predicted_strategy", row.get("PredictedStrategy", "")))
    strength = _history_adjustment_strength(metrics, target_stops)

    if candidate_strategy == original_strategy:
        return False, "Low", strength, "Historical candidate matches the base model strategy."

    if metrics["sample_drivers"] < 12:
        return (
            False,
            "Low",
            strength,
            f"Historical sample is too small ({metrics['sample_drivers']} driver-runs).",
        )

    if stop_delta <= 0:
        return (
            False,
            "Low",
            strength,
            "Historical candidate does not add a materially different stop profile.",
        )

    if stop_delta > 1:
        return (
            False,
            "Low",
            strength,
            f"Historical candidate would add {stop_delta} extra stops, which is too aggressive for an automatic override.",
        )

    if old_count > 1:
        return (
            False,
            "Low",
            strength,
            f"Historical candidate would require {old_count} old/unknown sets, so it remains an alternative only.",
        )

    if risk_score >= 70:
        return (
            False,
            "Low",
            strength,
            f"Historical candidate risk is High ({risk_score:.0f}/100), so it remains an alternative only.",
        )

    if target_stops >= 3:
        if strength != "High":
            return (
                False,
                "Low",
                strength,
                "Three-stop historical signal is not strong enough for an automatic override.",
            )

        if estimated_deg < 0.075:
            return (
                False,
                "Medium",
                strength,
                f"Three-stop candidate needs stronger current degradation evidence; estimated deg is {estimated_deg:.3f}s/lap.",
            )

        return True, "High", strength, "Strong historical three-stop signal and current degradation support an override."

    if target_stops == 2:
        average_stops = float(metrics.get("average_stops", 1.0))
        multi_stop_rate = float(metrics.get("multi_stop_rate", 0.0))

        if strength == "Low":
            return (
                False,
                "Low",
                strength,
                "Two-stop historical signal is too weak for an automatic override.",
            )

        # If current long-run data is weak/defaulted, allow a strong historical
        # multi-stop signal to correct an over-simple one-stop prediction.
        if estimated_deg < 0.060 and strength != "High" and average_stops < 1.75 and multi_stop_rate < 0.60:
            return (
                False,
                "Medium",
                strength,
                f"Two-stop candidate needs stronger degradation/history evidence; estimated deg is {estimated_deg:.3f}s/lap.",
            )

        return (
            True,
            "Medium",
            strength,
            "Historical multi-stop signal supports promoting the base one-stop to a driver-specific two-stop strategy.",
        )

    return False, "Low", strength, "History candidate is not useful enough to override the base model."


def _history_candidate_note(
    history: dict[str, Any],
    candidate_strategy: str,
    applied: bool,
    confidence: str,
    strength: str,
    decision_reason: str,
) -> str:
    metrics = _history_signal_metrics(history)

    if not candidate_strategy:
        return "No usable historical strategy candidate."

    if applied:
        return (
            f"History stop-count adjusted from baseline {metrics['years_used']} to {candidate_strategy}; "
            f"signal={strength}, confidence={confidence}."
        )

    return (
        f"Kept base strategy. History suggested {candidate_strategy}, but not applied: "
        f"{decision_reason}"
    )


def _apply_history_to_strategies(
    strategies: pd.DataFrame,
    history: dict[str, Any],
) -> pd.DataFrame:
    output = _ensure_history_comparison_columns(strategies)

    if output.empty:
        return output

    if not history:
        output["strategy_display_source"] = output.get("strategy_source", "model_estimate")
        output["visual_key_assumption"] = output.get("strategy_reason", output.get("Notes", "Model estimate."))
        return _order_history_strategy_columns(output)

    metrics = _history_signal_metrics(history)

    for index, row in output.iterrows():
        original_strategy = str(row.get("original_predicted_strategy", row.get("PredictedStrategy", "")))
        sequence = _target_sequence_for_row(row, history)

        if sequence is None:
            output.at[index, "history_candidate_strategy"] = ""
            output.at[index, "HistoryCandidateStrategy"] = ""
            output.at[index, "history_adjusted_strategy"] = original_strategy
            output.at[index, "HistoryAdjustedStrategy"] = original_strategy
            output.at[index, "history_adjustment_applied"] = False
            output.at[index, "HistoryAdjustmentApplied"] = False
            output.at[index, "strategy_changed_by_history"] = False
            output.at[index, "StrategyChangedByHistory"] = False
            output.at[index, "history_adjustment_confidence"] = "Low"
            output.at[index, "history_adjustment_strength"] = "Low"
            output.at[index, "history_adjustment_blocked_reason"] = "No strong historical adjustment signal for this row."
            output.at[index, "history_adjustment_reason"] = "No historical adjustment applied."
            output.at[index, "HistoryAdjustmentReason"] = "No historical adjustment applied."
            output.at[index, "strategy_display_source"] = str(row.get("strategy_source", "model_estimate"))
            output.at[index, "visual_key_assumption"] = str(row.get("strategy_reason", row.get("Notes", "Model estimate.")))
            continue

        candidate_strategy, old_count = _allocate_sequence(sequence, row)

        soft_remaining = int(_to_float_or_none(row.get("FreshSoftRemaining")) or 0)
        medium_remaining = int(_to_float_or_none(row.get("FreshMediumRemaining")) or 0)
        hard_remaining = int(_to_float_or_none(row.get("FreshHardRemaining")) or 0)

        shortage_score = 0

        if medium_remaining <= 0:
            shortage_score += 18

        if hard_remaining <= 0:
            shortage_score += 15

        if soft_remaining <= 1:
            shortage_score += 8

        risk_score = min(100.0, old_count * 38.0 + shortage_score)
        risk = _risk_label(risk_score)
        expected_stops = int(max(len(sequence) - 1, 0))
        strategy_type = _history_strategy_type(sequence)

        applied, confidence, strength, decision_reason = _history_adjustment_decision(
            row=row,
            history=history,
            sequence=sequence,
            candidate_strategy=candidate_strategy,
            old_count=old_count,
            risk_score=risk_score,
        )

        candidate_reason = (
            f"Historical baseline {metrics['years_used']}: avg stops {metrics['average_stops']:.2f}, "
            f"multi-stop {metrics.get('multi_stop_rate', metrics['two_stop_rate'] + metrics['three_plus_stop_rate']):.0%}, "
            f"2-stop {metrics['two_stop_rate']:.0%}, 3+ stop {metrics['three_plus_stop_rate']:.0%}, "
            f"dominant {metrics['dominant_strategy']}."
        )
        visual_note = _history_candidate_note(
            history=history,
            candidate_strategy=candidate_strategy,
            applied=applied,
            confidence=confidence,
            strength=strength,
            decision_reason=decision_reason,
        )

        existing_notes = str(row.get("Notes", "")).strip()
        notes = f"{existing_notes} {candidate_reason}".strip() if existing_notes else candidate_reason

        if applied:
            final_strategy = candidate_strategy
            final_source = "history_adjusted_model_estimate"
            final_risk = risk
            final_risk_score = risk_score
            final_confidence = confidence
            final_reason = (
                f"{_history_adjustment_reason(history, sequence)} "
                "Tyre availability is still estimated from FastF1 lap/stint data, not official FIA/Pirelli allocation data."
            )
            changed = final_strategy != original_strategy
            alternative_strategy = original_strategy
        else:
            final_strategy = original_strategy
            final_source = str(row.get("strategy_source", "model_estimate"))
            final_risk = str(row.get("OldTyreRisk", row.get("strategy_risk_level", "Medium")))
            final_risk_score = _to_float_or_none(row.get("OldTyreRiskScore")) or 0.0
            final_confidence = str(row.get("strategy_confidence", row.get("StrategyConfidence", "Medium")))
            final_reason = (
                f"Historical candidate kept as alternative only. {decision_reason} "
                "Final strategy remains the base model estimate."
            )
            changed = False
            alternative_strategy = candidate_strategy

        output.at[index, "PredictedStrategy"] = final_strategy
        output.at[index, "history_candidate_strategy"] = candidate_strategy
        output.at[index, "HistoryCandidateStrategy"] = candidate_strategy
        output.at[index, "history_candidate_expected_stops"] = expected_stops
        output.at[index, "HistoryCandidateExpectedStops"] = expected_stops
        output.at[index, "history_adjusted_strategy"] = final_strategy
        output.at[index, "HistoryAdjustedStrategy"] = final_strategy
        output.at[index, "primary_strategy"] = final_strategy
        output.at[index, "PrimaryStrategy"] = final_strategy
        output.at[index, "alternative_strategy"] = alternative_strategy
        output.at[index, "AlternativeStrategy"] = alternative_strategy
        output.at[index, "expected_stops"] = int(max(_strategy_stint_count(final_strategy) - 1, 0))
        output.at[index, "ExpectedStops"] = int(max(_strategy_stint_count(final_strategy) - 1, 0))
        output.at[index, "strategy_type"] = strategy_type if applied else str(row.get("strategy_type", "model_estimate"))
        output.at[index, "StrategyType"] = output.at[index, "strategy_type"]
        output.at[index, "LikelyOldTyreUse"] = old_count if applied else row.get("LikelyOldTyreUse", 0)
        output.at[index, "OldTyreRiskScore"] = final_risk_score
        output.at[index, "OldTyreRisk"] = final_risk
        output.at[index, "StrategyConfidence"] = final_confidence
        output.at[index, "strategy_confidence"] = final_confidence
        output.at[index, "StrategyConfidenceLabel"] = final_confidence
        output.at[index, "strategy_source"] = final_source
        output.at[index, "StrategySource"] = final_source
        output.at[index, "risk_level"] = final_risk
        output.at[index, "RiskLevel"] = final_risk
        output.at[index, "strategy_risk_level"] = final_risk
        output.at[index, "StrategyRiskLevel"] = final_risk
        output.at[index, "strategy_risk_reason"] = final_reason
        output.at[index, "StrategyRiskReason"] = final_reason
        output.at[index, "tyre_availability_risk"] = final_risk
        output.at[index, "TyreAvailabilityRisk"] = final_risk
        output.at[index, "confidence_reason"] = final_reason
        output.at[index, "ConfidenceReason"] = final_reason
        output.at[index, "history_adjustment_applied"] = bool(applied)
        output.at[index, "HistoryAdjustmentApplied"] = bool(applied)
        output.at[index, "strategy_changed_by_history"] = bool(changed)
        output.at[index, "StrategyChangedByHistory"] = bool(changed)
        output.at[index, "history_adjustment_confidence"] = confidence
        output.at[index, "HistoryAdjustmentConfidence"] = confidence
        output.at[index, "history_adjustment_strength"] = strength
        output.at[index, "HistoryAdjustmentStrength"] = strength
        output.at[index, "history_adjustment_blocked_reason"] = "" if applied else decision_reason
        output.at[index, "HistoryAdjustmentBlockedReason"] = "" if applied else decision_reason
        output.at[index, "history_adjustment_reason"] = visual_note
        output.at[index, "HistoryAdjustmentReason"] = visual_note
        output.at[index, "strategy_display_source"] = final_source
        output.at[index, "StrategyDisplaySource"] = final_source
        output.at[index, "visual_key_assumption"] = visual_note
        output.at[index, "VisualKeyAssumption"] = visual_note
        output.at[index, "Notes"] = notes

    return _order_history_strategy_columns(output)

def apply_historical_strategy_adjustment_to_outputs(
    strategy_csv_path: str,
    current_year: int,
    event_name: str,
    lookback_years: int = 5,
    session: Any | None = None,
    output_dir: str | Path = "outputs",
) -> dict[str, str]:
    """
    Builds a historical strategy baseline and rewrites predicted strategies
    if historical races suggest that the current 1-stop default is too simple.
    """

    history_dir, strategy_dir = _ensure_output_dirs(output_dir)

    strategies = _safe_read_csv(strategy_csv_path)

    if strategies.empty:
        print("Historical strategy adjustment skipped: strategy CSV is empty.")
        return {}

    historical = build_historical_strategy_baseline(
        current_year=current_year,
        event_name=event_name,
        lookback_years=lookback_years,
        output_dir=output_dir,
    )

    history_data = historical.get("summary_data", {})

    if not history_data:
        print("Historical strategy adjustment skipped: no usable historical baseline.")
        return {
            "historical_strategy_runs": historical.get("driver_runs_path", ""),
            "historical_strategy_summary": historical.get("summary_path", ""),
        }

    adjusted = _apply_history_to_strategies(strategies, history_data)
    adjusted = _order_history_strategy_columns(adjusted)

    adjusted_csv = str(strategy_dir / "predicted_tyre_strategy_history_adjusted.csv")
    adjusted.to_csv(adjusted_csv, index=False)

    chart_path = make_strategy_table_image(
        adjusted,
        output_path=str(strategy_dir / "predicted_tyre_strategy.png"),
        session=session,
    )

    print(
        "Historical strategy baseline: "
        f"years={history_data.get('years_used', 'N/A')} | "
        f"sample={history_data.get('sample_drivers', 0)} | "
        f"avg_stops={float(history_data.get('average_stops', 0.0)):.2f} | "
        f"dominant={history_data.get('dominant_strategy', 'N/A')} | "
        f"two_stop_rate={float(history_data.get('two_stop_rate', 0.0)):.0%}"
    )

    return {
        "predicted_tyre_strategy_csv": adjusted_csv,
        "predicted_tyre_strategy_chart": chart_path,
        "historical_strategy_runs": historical.get("driver_runs_path", ""),
        "historical_strategy_summary": historical.get("summary_path", ""),
        "historical_strategy_baseline": historical.get("baseline_path", ""),
    }
