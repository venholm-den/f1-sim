from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


CURRENT_SESSION_WEIGHTS = {
    "Q": 0.35,
    "SQ": 0.30,
    "S": 0.28,
    "FP3": 0.22,
    "FP2": 0.18,
    "FP1": 0.10,
    "R": 0.40,
}

PRACTICE_SESSIONS = {"FP1", "FP2", "FP3"}


def _to_numeric(series: pd.Series, default: float = np.nan) -> pd.Series:
    output = pd.to_numeric(series, errors="coerce")

    if not np.isnan(default):
        output = output.fillna(default)

    return output


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    values_numeric = pd.to_numeric(values, errors="coerce")
    weights_numeric = pd.to_numeric(weights, errors="coerce")

    valid = values_numeric.notna() & weights_numeric.notna() & (weights_numeric > 0)

    if valid.sum() == 0:
        return float("nan")

    return float(
        np.average(
            values_numeric.loc[valid],
            weights=weights_numeric.loc[valid],
        )
    )


def _weighted_std(values: pd.Series, weights: pd.Series) -> float:
    values_numeric = pd.to_numeric(values, errors="coerce")
    weights_numeric = pd.to_numeric(weights, errors="coerce")

    valid = values_numeric.notna() & weights_numeric.notna() & (weights_numeric > 0)

    if valid.sum() <= 1:
        return 0.0

    valid_values = values_numeric.loc[valid]
    valid_weights = weights_numeric.loc[valid]

    mean = np.average(valid_values, weights=valid_weights)
    variance = np.average((valid_values - mean) ** 2, weights=valid_weights)

    return float(np.sqrt(variance))


def _first_valid(series: pd.Series, default: Any = None) -> Any:
    valid = series.dropna()

    if valid.empty:
        return default

    return valid.iloc[0]


def _prepare_current_features(current_features: pd.DataFrame) -> pd.DataFrame:
    current = current_features.copy()

    rename_map = {
        "Team": "current_team",
        "relative_pace": "current_relative_pace",
        "race_pace": "current_race_pace",
        "best_lap": "current_best_lap",
        "lap_std": "current_lap_std",
        "deg_per_lap": "current_deg_per_lap",
        "clean_laps": "current_clean_laps",
        "raw_laps": "current_raw_laps",
        "dnf_prob": "current_dnf_prob",
    }

    keep_cols = ["Driver"] + [
        col for col in rename_map.keys()
        if col in current.columns
    ]

    current = current[keep_cols].rename(columns=rename_map)

    return current


def _prepare_baseline_features(baseline_features: pd.DataFrame) -> pd.DataFrame:
    baseline = baseline_features.copy()

    if baseline.empty:
        return pd.DataFrame(
            columns=[
                "Driver",
                "baseline_team",
                "baseline_relative_pace",
                "baseline_race_pace",
                "baseline_best_lap",
                "baseline_lap_std",
                "baseline_deg_per_lap",
                "baseline_clean_laps",
                "baseline_raw_laps",
                "baseline_dnf_prob",
                "baseline_pace_std",
                "baseline_rounds",
            ]
        )

    if "baseline_age" not in baseline.columns:
        baseline["baseline_age"] = 0

    baseline["baseline_age"] = pd.to_numeric(
        baseline["baseline_age"],
        errors="coerce",
    ).fillna(0)

    # Recent races get more weight, but older races still matter.
    baseline["baseline_weight"] = 1 / (1 + baseline["baseline_age"] * 0.45)

    numeric_cols = [
        "relative_pace",
        "race_pace",
        "best_lap",
        "lap_std",
        "deg_per_lap",
        "clean_laps",
        "raw_laps",
        "dnf_prob",
    ]

    for col in numeric_cols:
        if col not in baseline.columns:
            baseline[col] = np.nan

        baseline[col] = pd.to_numeric(baseline[col], errors="coerce")

    if "Team" not in baseline.columns:
        baseline["Team"] = ""

    rows: list[dict[str, Any]] = []

    for driver, group in baseline.groupby("Driver", dropna=False):
        weights = group["baseline_weight"]

        if "source_round" in group.columns:
            baseline_rounds = int(group["source_round"].nunique())
        else:
            baseline_rounds = int(len(group))

        rows.append(
            {
                "Driver": str(driver),
                "baseline_team": str(_first_valid(group["Team"], "")),
                "baseline_relative_pace": _weighted_mean(group["relative_pace"], weights),
                "baseline_race_pace": _weighted_mean(group["race_pace"], weights),
                "baseline_best_lap": _weighted_mean(group["best_lap"], weights),
                "baseline_lap_std": _weighted_mean(group["lap_std"], weights),
                "baseline_deg_per_lap": _weighted_mean(group["deg_per_lap"], weights),
                "baseline_clean_laps": _weighted_mean(group["clean_laps"], weights),
                "baseline_raw_laps": _weighted_mean(group["raw_laps"], weights),
                "baseline_dnf_prob": _weighted_mean(group["dnf_prob"], weights),
                "baseline_pace_std": _weighted_std(group["relative_pace"], weights),
                "baseline_rounds": baseline_rounds,
            }
        )

    return pd.DataFrame(rows)


def _calculate_current_signal_quality(
    model: pd.DataFrame,
    current_session_type: str,
) -> pd.Series:
    session = current_session_type.upper()

    current_pace = pd.to_numeric(
        model.get("current_relative_pace", np.nan),
        errors="coerce",
    )

    clean_laps = pd.to_numeric(
        model.get("current_clean_laps", 0),
        errors="coerce",
    ).fillna(0)

    lap_std = pd.to_numeric(
        model.get("current_lap_std", np.nan),
        errors="coerce",
    ).fillna(99)

    laps_factor = (clean_laps / 8).clip(0.05, 1.0)

    # High lap standard deviation usually means mixed runs, traffic,
    # in/out laps, or unreliable practice sampling.
    std_factor = (1 - ((lap_std - 1.5) / 5.0)).clip(0.05, 1.0)

    outlier_factor = pd.Series(1.0, index=model.index)

    if session in PRACTICE_SESSIONS:
        outlier_factor = np.select(
            [
                current_pace > 8.0,
                current_pace > 5.0,
                current_pace > 3.0,
            ],
            [
                0.05,
                0.15,
                0.45,
            ],
            default=1.0,
        )

        outlier_factor = pd.Series(outlier_factor, index=model.index)
    else:
        outlier_factor = np.select(
            [
                current_pace > 6.0,
                current_pace > 4.0,
            ],
            [
                0.25,
                0.55,
            ],
            default=1.0,
        )

        outlier_factor = pd.Series(outlier_factor, index=model.index)

    quality = laps_factor * std_factor * outlier_factor

    quality = quality.where(current_pace.notna(), 0.0)

    return quality.clip(0.0, 1.0)


def _cap_current_practice_pace(
    current_pace: pd.Series,
    current_session_type: str,
) -> pd.Series:
    session = current_session_type.upper()

    pace = pd.to_numeric(current_pace, errors="coerce")

    if session in PRACTICE_SESSIONS:
        # Practice can contain heavy fuel, traffic, bad run plans, used tyres,
        # or incomplete push laps. Cap its negative influence.
        return pace.clip(lower=-0.75, upper=3.00)

    if session in {"Q", "SQ"}:
        return pace.clip(lower=-0.50, upper=5.00)

    return pace.clip(lower=-1.00, upper=5.50)


def build_model_features(
    current_features: pd.DataFrame,
    baseline_features: pd.DataFrame,
    current_session_type: str,
) -> pd.DataFrame:
    session = current_session_type.upper()

    current = _prepare_current_features(current_features)
    baseline = _prepare_baseline_features(baseline_features)

    model = current.merge(
        baseline,
        on="Driver",
        how="outer",
    )

    model["Team"] = model["current_team"].fillna(model["baseline_team"]).fillna("Unknown")

    base_current_weight = CURRENT_SESSION_WEIGHTS.get(session, 0.15)

    model["base_current_weight"] = base_current_weight

    model["current_signal_quality"] = _calculate_current_signal_quality(
        model,
        current_session_type=session,
    )

    model["current_pace_outlier_flag"] = (
        pd.to_numeric(model["current_relative_pace"], errors="coerce") > 5.0
    )

    model["current_weight"] = (
        model["base_current_weight"] * model["current_signal_quality"]
    ).clip(0.0, base_current_weight)

    model["current_relative_pace_capped"] = _cap_current_practice_pace(
        model["current_relative_pace"],
        current_session_type=session,
    )

    current_pace = pd.to_numeric(
        model["current_relative_pace_capped"],
        errors="coerce",
    )

    baseline_pace = pd.to_numeric(
        model["baseline_relative_pace"],
        errors="coerce",
    )

    # If there is no baseline, trust the current capped value.
    # If there is no current value, trust baseline.
    model["blend_current_pace"] = current_pace
    model["blend_baseline_pace"] = baseline_pace

    model["effective_current_weight"] = model["current_weight"]

    model.loc[baseline_pace.isna() & current_pace.notna(), "effective_current_weight"] = 1.0
    model.loc[current_pace.isna() & baseline_pace.notna(), "effective_current_weight"] = 0.0

    fallback_pace = current_pace.fillna(baseline_pace).fillna(0.0)
    fallback_baseline = baseline_pace.fillna(current_pace).fillna(0.0)

    model["model_pace"] = (
        model["effective_current_weight"] * fallback_pace
        + (1 - model["effective_current_weight"]) * fallback_baseline
    )

    model["model_pace"] = model["model_pace"] - model["model_pace"].min()
    model["relative_pace"] = model["model_pace"]

    current_race_pace = pd.to_numeric(
        model["current_race_pace"],
        errors="coerce",
    )

    baseline_race_pace = pd.to_numeric(
        model["baseline_race_pace"],
        errors="coerce",
    )

    model["race_pace"] = (
        model["effective_current_weight"] * current_race_pace.fillna(baseline_race_pace)
        + (1 - model["effective_current_weight"]) * baseline_race_pace.fillna(current_race_pace)
    )

    model["best_lap"] = pd.to_numeric(
        model["current_best_lap"],
        errors="coerce",
    ).fillna(model["baseline_best_lap"])

    baseline_std = pd.to_numeric(
        model["baseline_pace_std"],
        errors="coerce",
    ).fillna(0.35)

    baseline_rounds = pd.to_numeric(
        model["baseline_rounds"],
        errors="coerce",
    ).fillna(0)

    current_lap_std = pd.to_numeric(
        model["current_lap_std"],
        errors="coerce",
    ).fillna(3.0)

    low_baseline_penalty = ((5 - baseline_rounds).clip(lower=0) / 5) * 0.35
    practice_quality_penalty = (1 - model["current_signal_quality"]) * 0.65

    if session in PRACTICE_SESSIONS:
        practice_session_penalty = 0.30
    else:
        practice_session_penalty = 0.05

    model["model_uncertainty"] = (
        0.85
        + baseline_std * 0.85
        + low_baseline_penalty
        + practice_quality_penalty
        + practice_session_penalty
    ).clip(0.90, 3.25)

    current_deg = pd.to_numeric(
        model["current_deg_per_lap"],
        errors="coerce",
    ).clip(-0.08, 0.12)

    baseline_deg = pd.to_numeric(
        model["baseline_deg_per_lap"],
        errors="coerce",
    ).clip(-0.10, 0.18)

    model["deg_per_lap"] = (
        model["effective_current_weight"] * current_deg.fillna(baseline_deg).fillna(0.0)
        + (1 - model["effective_current_weight"]) * baseline_deg.fillna(current_deg).fillna(0.0)
    ).clip(-0.10, 0.18)

    model["lap_std"] = current_lap_std.fillna(model["baseline_lap_std"]).fillna(1.5)

    model["clean_laps"] = pd.to_numeric(
        model["current_clean_laps"],
        errors="coerce",
    ).fillna(0).astype(int)

    model["raw_laps"] = pd.to_numeric(
        model["current_raw_laps"],
        errors="coerce",
    ).fillna(model["clean_laps"]).fillna(0).astype(int)

    current_dnf = pd.to_numeric(
        model["current_dnf_prob"],
        errors="coerce",
    )

    baseline_dnf = pd.to_numeric(
        model["baseline_dnf_prob"],
        errors="coerce",
    )

    model["dnf_prob"] = (
        model["effective_current_weight"] * current_dnf.fillna(baseline_dnf).fillna(0.045)
        + (1 - model["effective_current_weight"]) * baseline_dnf.fillna(current_dnf).fillna(0.045)
    ).clip(0.015, 0.20)

    output_cols = [
        "Driver",
        "Team",
        "model_pace",
        "model_uncertainty",
        "relative_pace",
        "race_pace",
        "best_lap",
        "lap_std",
        "deg_per_lap",
        "clean_laps",
        "raw_laps",
        "dnf_prob",
        "current_relative_pace",
        "current_relative_pace_capped",
        "baseline_relative_pace",
        "baseline_pace_std",
        "baseline_rounds",
        "base_current_weight",
        "current_signal_quality",
        "current_weight",
        "effective_current_weight",
        "current_pace_outlier_flag",
    ]

    existing_cols = [col for col in output_cols if col in model.columns]

    output = model[existing_cols].copy()

    output = output.sort_values("model_pace").reset_index(drop=True)

    return output