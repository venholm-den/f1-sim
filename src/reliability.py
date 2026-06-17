from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MECHANICAL_STATUS_KEYWORDS = {
    "brake",
    "brakes",
    "clutch",
    "electrical",
    "electronics",
    "engine",
    "gearbox",
    "hydraulic",
    "hydraulics",
    "mechanical",
    "oil",
    "overheating",
    "power unit",
    "powerunit",
    "puncture",
    "radiator",
    "suspension",
    "transmission",
    "water leak",
}

NON_MECHANICAL_STATUS_KEYWORDS = {
    "accident",
    "collision",
    "crash",
    "damage",
    "disqualified",
    "excluded",
    "illness",
    "spun off",
    "withdrawn",
}

FINISHED_STATUS_KEYWORDS = {
    "finished",
    "+",
    "lap",
}

DEFAULT_MECHANICAL_DNF_RATE = 0.045
DEFAULT_PRIOR_WEIGHT = 8.0


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    return None


def classify_result_status(status: Any) -> str:
    text = _normalise_text(status)

    if not text:
        return "unknown"

    if any(keyword in text for keyword in NON_MECHANICAL_STATUS_KEYWORDS):
        return "non_mechanical_dnf"

    if any(keyword in text for keyword in MECHANICAL_STATUS_KEYWORDS):
        return "mechanical_dnf"

    if text.isdigit() or any(keyword in text for keyword in FINISHED_STATUS_KEYWORDS):
        return "finished"

    return "unknown"


def load_team_power_units(path: str | Path = "data/team_power_units.csv") -> pd.DataFrame:
    file_path = Path(path)

    if not file_path.exists():
        return pd.DataFrame(columns=["Year", "Team", "PowerUnitSupplier"])

    mapping = pd.read_csv(file_path)

    required = {"Year", "Team", "PowerUnitSupplier"}

    if not required.issubset(mapping.columns):
        missing = ", ".join(sorted(required - set(mapping.columns)))
        raise ValueError(f"Team power-unit mapping is missing required column(s): {missing}")

    mapping = mapping.copy()
    mapping["Year"] = pd.to_numeric(mapping["Year"], errors="coerce").astype("Int64")
    mapping["team_key"] = mapping["Team"].map(_normalise_text)
    mapping["PowerUnitSupplier"] = mapping["PowerUnitSupplier"].fillna("Unknown").astype(str)

    return mapping


def _power_unit_for_team(
    team: Any,
    year: Any,
    team_power_units: pd.DataFrame,
) -> str:
    if team_power_units.empty:
        return "Unknown"

    team_key = _normalise_text(team)
    year_number = pd.to_numeric(pd.Series([year]), errors="coerce").iloc[0]
    candidates = team_power_units[team_power_units["team_key"] == team_key].copy()

    if candidates.empty:
        return "Unknown"

    if pd.notna(year_number):
        exact = candidates[candidates["Year"] == int(year_number)]

        if not exact.empty:
            return str(exact.iloc[0]["PowerUnitSupplier"])

        prior = candidates[candidates["Year"] <= int(year_number)]

        if not prior.empty:
            return str(prior.sort_values("Year").iloc[-1]["PowerUnitSupplier"])

    return str(candidates.sort_values("Year").iloc[-1]["PowerUnitSupplier"])


def _extract_results(session: Any) -> pd.DataFrame:
    results = getattr(session, "results", None)

    if results is None:
        return pd.DataFrame()

    try:
        results = results.copy()
    except Exception:
        return pd.DataFrame()

    if not isinstance(results, pd.DataFrame):
        return pd.DataFrame()

    return results


def _weighted_rate(flags: pd.Series, weights: pd.Series) -> tuple[float, float, float]:
    valid = flags.notna()

    if valid.sum() == 0:
        return DEFAULT_MECHANICAL_DNF_RATE, 0.0, 0.0

    valid_flags = flags.loc[valid].astype(float)
    valid_weights = weights.loc[valid].astype(float)
    weighted_events = float((valid_flags * valid_weights).sum())
    weighted_entries = float(valid_weights.sum())
    smoothed = (
        weighted_events + DEFAULT_MECHANICAL_DNF_RATE * DEFAULT_PRIOR_WEIGHT
    ) / (weighted_entries + DEFAULT_PRIOR_WEIGHT)

    return float(np.clip(smoothed, 0.005, 0.30)), weighted_events, weighted_entries


def infer_reliability_profile(
    recent_races: list[tuple[Any, dict]],
    team_power_units: pd.DataFrame | None = None,
) -> pd.DataFrame:
    team_power_units = team_power_units if team_power_units is not None else pd.DataFrame()
    rows: list[dict[str, Any]] = []

    for race_age, item in enumerate(recent_races):
        try:
            session, metadata = item
        except ValueError:
            continue

        results = _extract_results(session)

        if results.empty:
            continue

        team_col = _first_existing_column(results, ["TeamName", "Team", "ConstructorName"])
        driver_col = _first_existing_column(results, ["Abbreviation", "Driver", "FullName"])
        status_col = _first_existing_column(results, ["Status", "ClassifiedPosition", "PositionText"])

        if team_col is None or status_col is None:
            continue

        year = metadata.get("year") if isinstance(metadata, dict) else None
        event = metadata.get("event") if isinstance(metadata, dict) else ""
        weight = 1 / (1 + race_age * 0.35)

        for _, result_row in results.iterrows():
            team = str(result_row.get(team_col, "Unknown"))
            status = result_row.get(status_col)
            status_class = classify_result_status(status)

            rows.append(
                {
                    "Driver": str(result_row.get(driver_col, "")) if driver_col else "",
                    "Team": team,
                    "team_key": _normalise_text(team),
                    "Year": year,
                    "Event": event,
                    "PowerUnitSupplier": _power_unit_for_team(team, year, team_power_units),
                    "Status": status,
                    "status_class": status_class,
                    "mechanical_dnf": status_class == "mechanical_dnf",
                    "weight": weight,
                }
            )

    observations = pd.DataFrame(rows)

    if observations.empty:
        return pd.DataFrame(
            columns=[
                "Team",
                "PowerUnitSupplier",
                "team_mechanical_dnf_rate",
                "power_unit_mechanical_dnf_rate",
                "engine_reliability_score",
                "reliability_observations",
                "reliability_profile_source",
            ]
        )

    team_rows: list[dict[str, Any]] = []

    for team_key, team_group in observations.groupby("team_key", dropna=False):
        team_rate, team_events, team_entries = _weighted_rate(
            team_group["mechanical_dnf"],
            team_group["weight"],
        )
        team_rows.append(
            {
                "team_key": team_key,
                "Team": str(team_group["Team"].iloc[-1]),
                "PowerUnitSupplier": str(team_group["PowerUnitSupplier"].iloc[-1]),
                "team_mechanical_dnf_rate": team_rate,
                "team_mechanical_dnf_events_weighted": team_events,
                "team_reliability_entries_weighted": team_entries,
            }
        )

    supplier_rows: list[dict[str, Any]] = []

    for supplier, supplier_group in observations.groupby("PowerUnitSupplier", dropna=False):
        supplier_rate, supplier_events, supplier_entries = _weighted_rate(
            supplier_group["mechanical_dnf"],
            supplier_group["weight"],
        )
        supplier_rows.append(
            {
                "PowerUnitSupplier": supplier,
                "power_unit_mechanical_dnf_rate": supplier_rate,
                "power_unit_mechanical_dnf_events_weighted": supplier_events,
                "power_unit_reliability_entries_weighted": supplier_entries,
            }
        )

    team_profile = pd.DataFrame(team_rows)
    supplier_profile = pd.DataFrame(supplier_rows)
    profile = team_profile.merge(supplier_profile, on="PowerUnitSupplier", how="left")

    profile["engine_reliability_score"] = (
        1.0 - pd.to_numeric(profile["power_unit_mechanical_dnf_rate"], errors="coerce")
    ).clip(0.0, 1.0)
    observation_counts = observations.groupby("team_key")["Team"].count().rename(
        "reliability_observations"
    )
    profile = profile.merge(observation_counts, on="team_key", how="left")
    profile["reliability_profile_source"] = "recent_race_result_status_inference"

    return profile


def apply_reliability_profile(
    model_features: pd.DataFrame,
    reliability_profile: pd.DataFrame,
) -> pd.DataFrame:
    output = model_features.copy()

    if output.empty:
        return output

    output["team_key"] = output["Team"].map(_normalise_text) if "Team" in output.columns else ""
    output["base_dnf_prob"] = pd.to_numeric(
        output.get("dnf_prob", DEFAULT_MECHANICAL_DNF_RATE),
        errors="coerce",
    ).fillna(DEFAULT_MECHANICAL_DNF_RATE)

    if reliability_profile.empty:
        output["PowerUnitSupplier"] = "Unknown"
        output["team_mechanical_dnf_rate"] = DEFAULT_MECHANICAL_DNF_RATE
        output["power_unit_mechanical_dnf_rate"] = DEFAULT_MECHANICAL_DNF_RATE
        output["engine_reliability_score"] = 1.0 - DEFAULT_MECHANICAL_DNF_RATE
        output["reliability_profile_source"] = "default_reliability_prior"
    else:
        merge_cols = [
            "team_key",
            "PowerUnitSupplier",
            "team_mechanical_dnf_rate",
            "power_unit_mechanical_dnf_rate",
            "engine_reliability_score",
            "reliability_profile_source",
        ]
        output = output.merge(
            reliability_profile[merge_cols],
            on="team_key",
            how="left",
        )
        output["PowerUnitSupplier"] = output["PowerUnitSupplier"].fillna("Unknown")
        output["team_mechanical_dnf_rate"] = pd.to_numeric(
            output["team_mechanical_dnf_rate"],
            errors="coerce",
        ).fillna(DEFAULT_MECHANICAL_DNF_RATE)
        output["power_unit_mechanical_dnf_rate"] = pd.to_numeric(
            output["power_unit_mechanical_dnf_rate"],
            errors="coerce",
        ).fillna(DEFAULT_MECHANICAL_DNF_RATE)
        output["engine_reliability_score"] = pd.to_numeric(
            output["engine_reliability_score"],
            errors="coerce",
        ).fillna(1.0 - DEFAULT_MECHANICAL_DNF_RATE)
        output["reliability_profile_source"] = output["reliability_profile_source"].fillna(
            "default_reliability_prior"
        )

    output["dnf_prob"] = (
        output["base_dnf_prob"] * 0.65
        + output["team_mechanical_dnf_rate"] * 0.25
        + output["power_unit_mechanical_dnf_rate"] * 0.10
    ).clip(0.005, 0.30)

    output = output.drop(columns=["team_key"])

    return output
