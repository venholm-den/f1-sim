from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}
WET_COMPOUNDS = {"INTERMEDIATE", "WET"}
KNOWN_COMPOUNDS = DRY_COMPOUNDS | WET_COMPOUNDS


def _series_or_default(
    df: pd.DataFrame,
    column: str,
    default: Any,
) -> pd.Series:
    if column in df.columns:
        return df[column]

    return pd.Series([default] * len(df), index=df.index)


def _timedelta_to_seconds(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def _bool_series(
    df: pd.DataFrame,
    column: str,
    default: bool = False,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index)

    series = df[column]

    if str(series.dtype) == "bool":
        return series.fillna(default).astype(bool)

    text = series.astype(str).str.strip().str.lower()

    return text.isin({"true", "1", "yes", "y"})


def _weighted_quantile(
    values: pd.Series,
    quantile: float,
    weights: pd.Series | None = None,
) -> float:
    value_array = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)

    if weights is None:
        valid = np.isfinite(value_array)

        if valid.sum() == 0:
            return float("nan")

        return float(np.quantile(value_array[valid], quantile))

    weight_array = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float)

    valid = (
        np.isfinite(value_array)
        & np.isfinite(weight_array)
        & (weight_array > 0)
    )

    if valid.sum() == 0:
        return float("nan")

    value_array = value_array[valid]
    weight_array = weight_array[valid]

    sorter = np.argsort(value_array)
    value_array = value_array[sorter]
    weight_array = weight_array[sorter]

    weighted_cdf = np.cumsum(weight_array) - 0.5 * weight_array
    weighted_cdf = weighted_cdf / np.sum(weight_array)

    return float(np.interp(quantile, weighted_cdf, value_array))


def _weighted_std(
    values: pd.Series,
    weights: pd.Series | None = None,
) -> float:
    value_array = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)

    if weights is None:
        valid = np.isfinite(value_array)

        if valid.sum() <= 1:
            return 0.0

        return float(np.std(value_array[valid]))

    weight_array = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float)

    valid = (
        np.isfinite(value_array)
        & np.isfinite(weight_array)
        & (weight_array > 0)
    )

    if valid.sum() <= 1:
        return 0.0

    value_array = value_array[valid]
    weight_array = weight_array[valid]

    mean = np.average(value_array, weights=weight_array)
    variance = np.average((value_array - mean) ** 2, weights=weight_array)

    return float(np.sqrt(variance))


def _prepare_laps(laps: pd.DataFrame) -> pd.DataFrame:
    df = laps.copy()

    if df.empty:
        return df

    if "Driver" not in df.columns:
        raise ValueError("Lap data must include Driver")

    if "Team" not in df.columns:
        df["Team"] = "Unknown"

    df["Driver"] = df["Driver"].astype(str)
    df["Team"] = df["Team"].astype(str)

    if "Compound" in df.columns:
        df["Compound"] = df["Compound"].astype(str).str.upper()
    else:
        df["Compound"] = "UNKNOWN"

    if "LapTimeSeconds" in df.columns:
        df["LapTimeSeconds"] = pd.to_numeric(
            df["LapTimeSeconds"],
            errors="coerce",
        )
    elif "LapTime" in df.columns:
        df["LapTimeSeconds"] = _timedelta_to_seconds(df["LapTime"])
    else:
        df["LapTimeSeconds"] = np.nan

    df["LapNumber"] = pd.to_numeric(
        _series_or_default(df, "LapNumber", np.nan),
        errors="coerce",
    )

    df["Stint"] = pd.to_numeric(
        _series_or_default(df, "Stint", np.nan),
        errors="coerce",
    )

    df["TyreLife"] = pd.to_numeric(
        _series_or_default(df, "TyreLife", np.nan),
        errors="coerce",
    )

    df["FreshTyreBool"] = _bool_series(df, "FreshTyre", default=False)

    if "PitOutTime" in df.columns:
        df["PitOut"] = df["PitOutTime"].notna()
    else:
        df["PitOut"] = _bool_series(df, "PitOut", default=False)

    if "PitInTime" in df.columns:
        df["PitIn"] = df["PitInTime"].notna()
    else:
        df["PitIn"] = _bool_series(df, "PitIn", default=False)

    is_accurate = _bool_series(df, "IsAccurate", default=True)
    deleted = _bool_series(df, "Deleted", default=False)

    if "TrackStatus" in df.columns:
        track_status = df["TrackStatus"].astype(str)
        clean_track = ~track_status.str.contains("[24567]", regex=True, na=False)
    else:
        clean_track = pd.Series([True] * len(df), index=df.index)

    valid_lap_time = (
        df["LapTimeSeconds"].notna()
        & np.isfinite(df["LapTimeSeconds"])
        & (df["LapTimeSeconds"] >= 45)
        & (df["LapTimeSeconds"] <= 240)
    )

    if "CleanPushLap" in df.columns:
        provided_clean_push = _bool_series(df, "CleanPushLap", default=False)
    else:
        provided_clean_push = pd.Series([True] * len(df), index=df.index)

    df["CleanPushLap"] = (
        provided_clean_push
        & is_accurate
        & valid_lap_time
        & clean_track
        & ~deleted
        & ~df["PitOut"]
        & ~df["PitIn"]
    )

    # If dry running exists, use dry compounds only for true dry pace.
    dry_lap_count = int(df["Compound"].isin(DRY_COMPOUNDS).sum())

    if dry_lap_count >= 5:
        compound_ok = df["Compound"].isin(DRY_COMPOUNDS)
    else:
        compound_ok = df["Compound"].isin(KNOWN_COMPOUNDS) | df["Compound"].eq("UNKNOWN")

    df["TruePaceEligible"] = df["CleanPushLap"] & compound_ok

    return df


def _estimate_compound_offsets(laps: pd.DataFrame) -> dict[str, float]:
    eligible = laps[laps["TruePaceEligible"]].copy()

    if eligible.empty:
        return {}

    if eligible["Compound"].isin(DRY_COMPOUNDS).sum() >= 5:
        eligible = eligible[eligible["Compound"].isin(DRY_COMPOUNDS)].copy()

    compound_summary = (
        eligible.groupby("Compound", dropna=False)
        .agg(
            lap_count=("LapTimeSeconds", "count"),
            median_lap=("LapTimeSeconds", "median"),
        )
        .reset_index()
    )

    compound_summary = compound_summary[
        compound_summary["lap_count"] >= 3
    ].copy()

    if compound_summary.empty:
        return {}

    fastest_median = float(compound_summary["median_lap"].min())

    offsets: dict[str, float] = {}

    for _, row in compound_summary.iterrows():
        compound = str(row["Compound"]).upper()
        offset = float(row["median_lap"] - fastest_median)

        # Keep correction sensible. This avoids one strange compound sample
        # overcorrecting the whole model.
        offsets[compound] = float(np.clip(offset, -0.50, 2.50))

    return offsets


def _estimate_global_tyre_deg(laps: pd.DataFrame) -> float:
    eligible = laps[
        laps["TruePaceEligible"]
        & laps["TyreLife"].notna()
        & (laps["TyreLife"] >= 1)
        & (laps["TyreLife"] <= 45)
    ].copy()

    if eligible.empty:
        return 0.0

    slopes: list[float] = []

    group_cols = ["Driver", "Compound", "Stint"]

    for _, group in eligible.groupby(group_cols, dropna=False):
        group = group.sort_values("TyreLife").copy()

        if len(group) < 3:
            continue

        x = pd.to_numeric(group["TyreLife"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(group["LapTimeSeconds"], errors="coerce").to_numpy(dtype=float)

        valid = np.isfinite(x) & np.isfinite(y)

        if valid.sum() < 3:
            continue

        try:
            slope = float(np.polyfit(x[valid], y[valid], 1)[0])
        except Exception:
            continue

        if -0.10 <= slope <= 0.35:
            slopes.append(slope)

    if not slopes:
        return 0.0

    # Negative degradation can happen in practice because fuel burns off.
    # For tyre-age normalisation, only use positive degradation.
    return float(np.clip(np.median(slopes), 0.0, 0.12))


def _estimate_driver_deg(driver_laps: pd.DataFrame) -> float:
    eligible = driver_laps[
        driver_laps["TruePaceEligible"]
        & driver_laps["TyreLife"].notna()
        & (driver_laps["TyreLife"] >= 1)
        & (driver_laps["TyreLife"] <= 45)
    ].copy()

    if eligible.empty:
        return 0.0

    slopes: list[float] = []

    for _, group in eligible.groupby(["Compound", "Stint"], dropna=False):
        group = group.sort_values("TyreLife").copy()

        if len(group) < 3:
            continue

        x = pd.to_numeric(group["TyreLife"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(group["LapTimeSeconds"], errors="coerce").to_numpy(dtype=float)

        valid = np.isfinite(x) & np.isfinite(y)

        if valid.sum() < 3:
            continue

        try:
            slope = float(np.polyfit(x[valid], y[valid], 1)[0])
        except Exception:
            continue

        if -0.12 <= slope <= 0.40:
            slopes.append(slope)

    if not slopes:
        return 0.0

    return float(np.clip(np.median(slopes), -0.10, 0.18))


def _lap_quality_weights(laps: pd.DataFrame) -> pd.Series:
    weights = pd.Series([1.0] * len(laps), index=laps.index)

    tyre_life = pd.to_numeric(laps["TyreLife"], errors="coerce")

    tyre_age_factor = 1 / (1 + (tyre_life.fillna(1).clip(lower=1) - 1) * 0.035)
    tyre_age_factor = tyre_age_factor.clip(0.45, 1.0)

    weights = weights * tyre_age_factor

    fresh_factor = np.where(laps["FreshTyreBool"].fillna(False), 1.0, 0.82)
    weights = weights * fresh_factor

    compound = laps["Compound"].astype(str).str.upper()

    compound_factor = np.select(
        [
            compound.eq("SOFT"),
            compound.eq("MEDIUM"),
            compound.eq("HARD"),
            compound.isin(WET_COMPOUNDS),
        ],
        [
            1.00,
            0.94,
            0.90,
            0.80,
        ],
        default=0.85,
    )

    weights = weights * pd.Series(compound_factor, index=laps.index)

    return weights.clip(0.20, 1.25)


def _remove_driver_outlier_laps(driver_laps: pd.DataFrame) -> pd.DataFrame:
    if driver_laps.empty:
        return driver_laps

    best_true_lap = driver_laps["TrueLapTime"].min()

    if not np.isfinite(best_true_lap):
        return driver_laps

    # Keep representative push/race-pace laps, but remove obvious slow
    # practice outliers that would wreck pace.
    filtered = driver_laps[
        driver_laps["TrueLapTime"] <= best_true_lap + 4.0
    ].copy()

    if len(filtered) >= max(2, int(len(driver_laps) * 0.35)):
        return filtered

    return driver_laps


def build_driver_features(laps: pd.DataFrame) -> pd.DataFrame:
    prepared = _prepare_laps(laps)

    if prepared.empty:
        return pd.DataFrame()

    compound_offsets = _estimate_compound_offsets(prepared)
    global_tyre_deg = _estimate_global_tyre_deg(prepared)

    prepared["CompoundOffset"] = (
        prepared["Compound"]
        .astype(str)
        .str.upper()
        .map(compound_offsets)
        .fillna(0.0)
    )

    tyre_age = (
        pd.to_numeric(prepared["TyreLife"], errors="coerce")
        .fillna(1)
        .clip(lower=1)
        - 1
    )

    prepared["TyreAgeCorrection"] = (
        tyre_age * global_tyre_deg
    ).clip(lower=0.0, upper=1.80)

    # Normalise laps towards a fresh, fastest-observed-compound equivalent.
    # This lets a used Hard lap be compared more fairly with a fresh Soft lap.
    prepared["TrueLapTime"] = (
        prepared["LapTimeSeconds"]
        - prepared["CompoundOffset"]
        - prepared["TyreAgeCorrection"]
    )

    rows: list[dict[str, Any]] = []

    for driver, group in prepared.groupby("Driver", dropna=False):
        group = group.copy()

        team = (
            str(group["Team"].dropna().iloc[0])
            if not group["Team"].dropna().empty
            else "Unknown"
        )

        valid_laps = group[group["LapTimeSeconds"].notna()].copy()
        true_laps = group[group["TruePaceEligible"]].copy()

        clean_laps_before_outlier_filter = int(len(true_laps))

        true_laps = _remove_driver_outlier_laps(true_laps)

        clean_laps = int(len(true_laps))
        raw_laps = int(len(valid_laps))

        if clean_laps == 0:
            continue

        weights = _lap_quality_weights(true_laps)

        true_pace = _weighted_quantile(
            true_laps["TrueLapTime"],
            0.40,
            weights,
        )

        race_pace = _weighted_quantile(
            true_laps["LapTimeSeconds"],
            0.50,
            weights,
        )

        best_lap = float(true_laps["LapTimeSeconds"].min())

        pace_p25 = _weighted_quantile(
            true_laps["TrueLapTime"],
            0.25,
            weights,
        )

        pace_p75 = _weighted_quantile(
            true_laps["TrueLapTime"],
            0.75,
            weights,
        )

        lap_std = _weighted_std(
            true_laps["TrueLapTime"],
            weights,
        )

        deg_per_lap = _estimate_driver_deg(group)

        low_lap_penalty = max(0, 5 - clean_laps) * 0.006
        noisy_lap_penalty = min(lap_std / 100, 0.025)

        dnf_prob = float(np.clip(0.035 + low_lap_penalty + noisy_lap_penalty, 0.015, 0.20))

        model_uncertainty = float(
            np.clip(
                0.85
                + min(lap_std / 2.8, 1.20)
                + max(0, 6 - clean_laps) * 0.10,
                0.85,
                3.25,
            )
        )

        rows.append(
            {
                "Driver": str(driver),
                "Team": team,
                "race_pace": race_pace,
                "true_pace": true_pace,
                "best_lap": best_lap,
                "pace_p25": pace_p25,
                "pace_p75": pace_p75,
                "lap_std": lap_std,
                "deg_per_lap": deg_per_lap,
                "clean_laps": clean_laps,
                "raw_laps": raw_laps,
                "clean_laps_before_outlier_filter": clean_laps_before_outlier_filter,
                "dnf_prob": dnf_prob,
                "model_uncertainty": model_uncertainty,
                "compound_offsets_used": str(compound_offsets),
                "global_tyre_deg_used": global_tyre_deg,
            }
        )

    output = pd.DataFrame(rows)

    if output.empty:
        return output

    output["true_pace"] = pd.to_numeric(output["true_pace"], errors="coerce")
    output["race_pace"] = pd.to_numeric(output["race_pace"], errors="coerce")

    output = output.dropna(subset=["true_pace"]).copy()

    if output.empty:
        return output

    output["relative_pace"] = output["true_pace"] - output["true_pace"].min()

    # Downstream model uses model_pace/relative_pace. This is now true-pace based.
    output["model_pace"] = output["relative_pace"]

    output = output.sort_values("relative_pace").reset_index(drop=True)

    return output