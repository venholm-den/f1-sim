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
) -> dict[str, Any]:
    _ensure_outputs()

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

    driver_runs_path = "outputs/history/historical_strategy_driver_runs.csv"
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

    strategy_counts_path = "outputs/history/historical_strategy_summary.csv"
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

    pd.DataFrame([summary_data]).to_csv(
        "outputs/history/historical_strategy_baseline.csv",
        index=False,
    )

    return {
        "driver_runs_path": driver_runs_path,
        "summary_path": strategy_counts_path,
        "baseline_path": "outputs/history/historical_strategy_baseline.csv",
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


def _target_sequence_for_row(
    row: pd.Series,
    history: dict[str, Any],
) -> list[str] | None:
    sample_drivers = int(history.get("sample_drivers", 0))
    average_stops = float(history.get("average_stops", 1.0))
    dominant_stops = int(history.get("dominant_stops", 1))
    two_stop_rate = float(history.get("two_stop_rate", 0.0))
    three_plus_rate = float(history.get("three_plus_stop_rate", 0.0))

    if sample_drivers < 6:
        return None

    current_stints = _strategy_stint_count(row.get("PredictedStrategy"))
    grid_position = _to_float_or_none(row.get("GridPosition"))
    estimated_deg = _to_float_or_none(row.get("EstimatedDegPerLap")) or 0.055

    force_three_stop = (
        dominant_stops >= 3
        or three_plus_rate >= 0.25
        or average_stops >= 2.45
    )

    force_two_stop = (
        dominant_stops == 2
        or two_stop_rate >= 0.40
        or average_stops >= 1.45
    )

    mixed_two_stop = (
        two_stop_rate >= 0.22
        and estimated_deg >= 0.060
    )

    if force_three_stop and current_stints < 4:
        historical = _parse_historical_sequence(
            str(history.get("dominant_three_stop_strategy") or history.get("dominant_strategy", ""))
        )

        if len(historical) >= 4:
            return historical[:4]

        return _fallback_three_stop_sequence(row)

    if (force_two_stop or mixed_two_stop) and current_stints < 3:
        historical = _parse_historical_sequence(
            str(history.get("dominant_two_stop_strategy") or history.get("dominant_strategy", ""))
        )

        if len(historical) >= 3:
            return historical[:3]

        return _fallback_two_stop_sequence(row, grid_position)

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


def _apply_history_to_strategies(
    strategies: pd.DataFrame,
    history: dict[str, Any],
) -> pd.DataFrame:
    output = strategies.copy()

    if output.empty or not history:
        return output

    for index, row in output.iterrows():
        sequence = _target_sequence_for_row(row, history)

        if sequence is None:
            continue

        strategy_text, old_count = _allocate_sequence(sequence, row)

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

        history_note = (
            f"Historical baseline {history.get('years_used', 'N/A')}: "
            f"avg stops {float(history.get('average_stops', 0.0)):.2f}, "
            f"2-stop rate {float(history.get('two_stop_rate', 0.0)):.0%}, "
            f"dominant {history.get('dominant_strategy', 'N/A')}."
        )

        existing_notes = str(row.get("Notes", "")).strip()

        if existing_notes:
            notes = f"{existing_notes} {history_note}"
        else:
            notes = history_note

        output.at[index, "PredictedStrategy"] = strategy_text
        output.at[index, "LikelyOldTyreUse"] = old_count
        output.at[index, "OldTyreRiskScore"] = risk_score
        output.at[index, "OldTyreRisk"] = risk
        output.at[index, "StrategyConfidence"] = "Medium" if old_count > 0 else "High"
        output.at[index, "Notes"] = notes

    return output


def apply_historical_strategy_adjustment_to_outputs(
    strategy_csv_path: str,
    current_year: int,
    event_name: str,
    lookback_years: int = 5,
    session: Any | None = None,
) -> dict[str, str]:
    """
    Builds a historical strategy baseline and rewrites predicted strategies
    if historical races suggest that the current 1-stop default is too simple.
    """

    _ensure_outputs()

    strategies = _safe_read_csv(strategy_csv_path)

    if strategies.empty:
        print("Historical strategy adjustment skipped: strategy CSV is empty.")
        return {}

    historical = build_historical_strategy_baseline(
        current_year=current_year,
        event_name=event_name,
        lookback_years=lookback_years,
    )

    history_data = historical.get("summary_data", {})

    if not history_data:
        print("Historical strategy adjustment skipped: no usable historical baseline.")
        return {
            "historical_strategy_runs": historical.get("driver_runs_path", ""),
            "historical_strategy_summary": historical.get("summary_path", ""),
        }

    adjusted = _apply_history_to_strategies(strategies, history_data)

    adjusted_csv = "outputs/strategy/predicted_tyre_strategy_history_adjusted.csv"
    adjusted.to_csv(adjusted_csv, index=False)

    chart_path = make_strategy_table_image(
        adjusted,
        output_path="outputs/strategy/predicted_tyre_strategy.png",
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