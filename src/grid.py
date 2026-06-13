from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


QUALI_SESSION_TYPES = {"Q", "SQ"}


def _to_numeric(series: pd.Series, default: float = np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _timedelta_to_seconds(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def _normalise_driver(value: Any) -> str:
    return str(value).strip().upper()


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col

    return None


def _get_session_results(current_session: Any | None) -> pd.DataFrame:
    if current_session is None:
        return pd.DataFrame()

    results = getattr(current_session, "results", None)

    if results is None:
        return pd.DataFrame()

    try:
        df = results.copy()
    except Exception:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    return df


def _extract_actual_quali_grid_from_results(
    current_session: Any | None,
) -> pd.DataFrame:
    """
    Extracts the actual Q/SQ classification from FastF1 session.results.

    For qualifying-style sessions, FastF1's Position column should represent the
    classification order. This should override estimated/model grid.
    """

    results = _get_session_results(current_session)

    if results.empty:
        return pd.DataFrame()

    driver_col = _first_existing_column(
        results,
        [
            "Abbreviation",
            "Driver",
            "BroadcastName",
            "FullName",
        ],
    )

    if driver_col is None:
        return pd.DataFrame()

    team_col = _first_existing_column(
        results,
        [
            "TeamName",
            "Team",
            "TeamId",
        ],
    )

    position_col = _first_existing_column(
        results,
        [
            "Position",
            "ClassifiedPosition",
        ],
    )

    if position_col is None:
        return pd.DataFrame()

    output = pd.DataFrame()
    output["Driver"] = results[driver_col].map(_normalise_driver)

    if team_col is not None:
        output["actual_grid_team"] = results[team_col].astype(str)
    else:
        output["actual_grid_team"] = ""

    output["actual_grid_position"] = pd.to_numeric(
        results[position_col],
        errors="coerce",
    )

    output = output.dropna(subset=["Driver", "actual_grid_position"]).copy()

    if output.empty:
        return output

    output["actual_grid_position"] = output["actual_grid_position"].astype(int)

    output = output.sort_values(
        "actual_grid_position",
        ascending=True,
    ).drop_duplicates(subset=["Driver"], keep="first")

    output["actual_grid_score"] = output["actual_grid_position"].astype(float)

    return output[
        [
            "Driver",
            "actual_grid_team",
            "actual_grid_position",
            "actual_grid_score",
        ]
    ].reset_index(drop=True)


def _extract_actual_quali_grid_from_laps(
    current_session: Any | None,
) -> pd.DataFrame:
    """
    Fallback if session.results is unavailable.

    Uses fastest valid lap in the current qualifying session.
    """

    if current_session is None:
        return pd.DataFrame()

    laps = getattr(current_session, "laps", None)

    if laps is None:
        return pd.DataFrame()

    try:
        df = laps.copy()
    except Exception:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    if "Driver" not in df.columns:
        return pd.DataFrame()

    if "Team" not in df.columns:
        df["Team"] = ""

    if "LapTimeSeconds" in df.columns:
        df["LapTimeSeconds"] = pd.to_numeric(
            df["LapTimeSeconds"],
            errors="coerce",
        )
    elif "LapTime" in df.columns:
        df["LapTimeSeconds"] = _timedelta_to_seconds(df["LapTime"])
    else:
        return pd.DataFrame()

    valid = df["LapTimeSeconds"].notna()

    if "PitOutTime" in df.columns:
        valid = valid & df["PitOutTime"].isna()

    if "PitInTime" in df.columns:
        valid = valid & df["PitInTime"].isna()

    if "IsAccurate" in df.columns:
        accurate = df["IsAccurate"]

        if str(accurate.dtype) == "bool":
            valid = valid & accurate.fillna(False)
        else:
            valid = valid & accurate.astype(str).str.lower().isin(
                ["true", "1", "yes", "y"]
            )

    if "Deleted" in df.columns:
        deleted = df["Deleted"]

        if str(deleted.dtype) == "bool":
            valid = valid & ~deleted.fillna(False)
        else:
            valid = valid & ~deleted.astype(str).str.lower().isin(
                ["true", "1", "yes", "y"]
            )

    df = df[valid].copy()

    if df.empty:
        return pd.DataFrame()

    best = (
        df.sort_values("LapTimeSeconds", ascending=True)
        .groupby("Driver", as_index=False)
        .first()
    )

    best["Driver"] = best["Driver"].map(_normalise_driver)
    best["actual_grid_team"] = best["Team"].astype(str)
    best["actual_grid_score"] = pd.to_numeric(
        best["LapTimeSeconds"],
        errors="coerce",
    )

    best = best.dropna(subset=["actual_grid_score"]).copy()

    if best.empty:
        return pd.DataFrame()

    best["actual_grid_position"] = (
        best["actual_grid_score"]
        .rank(method="first", ascending=True)
        .astype(int)
    )

    return best[
        [
            "Driver",
            "actual_grid_team",
            "actual_grid_position",
            "actual_grid_score",
        ]
    ].sort_values("actual_grid_position").reset_index(drop=True)


def _extract_actual_grid(
    current_session: Any | None,
    current_session_type: str,
) -> pd.DataFrame:
    session_type = str(current_session_type).upper()

    if session_type not in QUALI_SESSION_TYPES:
        return pd.DataFrame()

    actual = _extract_actual_quali_grid_from_results(current_session)

    if not actual.empty:
        return actual

    return _extract_actual_quali_grid_from_laps(current_session)


def _estimate_grid_from_features(
    model_features: pd.DataFrame,
    current_features: pd.DataFrame,
) -> pd.DataFrame:
    base = model_features.copy()

    if base.empty:
        return pd.DataFrame()

    base["Driver"] = base["Driver"].map(_normalise_driver)

    if "Team" not in base.columns:
        base["Team"] = "Unknown"

    estimate = base[["Driver", "Team"]].copy()

    current = current_features.copy()

    if not current.empty and "Driver" in current.columns:
        current["Driver"] = current["Driver"].map(_normalise_driver)

        current_score_col = _first_existing_column(
            current,
            [
                "true_pace",
                "relative_pace",
                "model_pace",
                "best_lap",
                "race_pace",
            ],
        )

        current_cols = ["Driver"]

        if current_score_col:
            current_cols.append(current_score_col)

        if "clean_laps" in current.columns:
            current_cols.append("clean_laps")

        current_small = current[current_cols].copy()

        rename_map = {}

        if current_score_col:
            rename_map[current_score_col] = "grid_current_pace"

        if "clean_laps" in current_small.columns:
            rename_map["clean_laps"] = "grid_current_laps"

        current_small = current_small.rename(columns=rename_map)

        estimate = estimate.merge(
            current_small,
            on="Driver",
            how="left",
        )
    else:
        estimate["grid_current_pace"] = np.nan
        estimate["grid_current_laps"] = np.nan

    if "grid_current_pace" not in estimate.columns:
        estimate["grid_current_pace"] = np.nan

    if "grid_current_laps" not in estimate.columns:
        estimate["grid_current_laps"] = np.nan

    model_score_col = _first_existing_column(
        base,
        [
            "quali_pace_score",
            "model_pace",
            "relative_pace",
            "race_pace_score",
        ],
    )

    if model_score_col:
        model_scores = base[["Driver", model_score_col]].copy()
        model_scores = model_scores.rename(
            columns={model_score_col: "grid_model_pace"}
        )

        estimate = estimate.merge(
            model_scores,
            on="Driver",
            how="left",
        )
    else:
        estimate["grid_model_pace"] = np.nan

    estimate["grid_current_pace"] = pd.to_numeric(
        estimate["grid_current_pace"],
        errors="coerce",
    )

    estimate["grid_model_pace"] = pd.to_numeric(
        estimate["grid_model_pace"],
        errors="coerce",
    )

    estimate["estimated_grid_score"] = estimate["grid_current_pace"].fillna(
        estimate["grid_model_pace"]
    )

    if estimate["estimated_grid_score"].isna().all():
        estimate["estimated_grid_score"] = np.arange(1, len(estimate) + 1)

    estimate["estimated_grid_score"] = estimate["estimated_grid_score"].fillna(
        estimate["estimated_grid_score"].median()
    )

    estimate["estimated_grid_position"] = (
        estimate["estimated_grid_score"]
        .rank(method="first", ascending=True)
        .astype(int)
    )

    return estimate[
        [
            "Driver",
            "grid_current_pace",
            "grid_current_laps",
            "grid_model_pace",
            "estimated_grid_score",
            "estimated_grid_position",
        ]
    ].sort_values("estimated_grid_position").reset_index(drop=True)


def build_grid_features(
    model_features: pd.DataFrame,
    current_features: pd.DataFrame,
    current_session_type: str,
    current_session: Any | None = None,
) -> pd.DataFrame:
    """
    Adds grid information to model features.

    Priority:
    1. Actual Q/SQ FastF1 session.results Position
    2. Actual Q/SQ fastest-lap fallback
    3. Estimated grid from current/model pace
    """

    if model_features.empty:
        return model_features.copy()

    output = model_features.copy()
    output["Driver"] = output["Driver"].map(_normalise_driver)

    grid_cols_to_remove = [
        "actual_grid_team",
        "actual_grid_position",
        "actual_grid_score",
        "grid_current_pace",
        "grid_current_laps",
        "grid_model_pace",
        "estimated_grid_score",
        "estimated_grid_position",
        "grid_position",
        "grid_source",
        "grid_score",
        "grid_confidence",
    ]

    output = output.drop(
        columns=[col for col in grid_cols_to_remove if col in output.columns],
        errors="ignore",
    )

    actual_grid = _extract_actual_grid(
        current_session=current_session,
        current_session_type=current_session_type,
    )

    estimated_grid = _estimate_grid_from_features(
        model_features=output,
        current_features=current_features,
    )

    if not estimated_grid.empty:
        output = output.merge(
            estimated_grid,
            on="Driver",
            how="left",
        )
    else:
        output["estimated_grid_position"] = np.nan
        output["estimated_grid_score"] = np.nan
        output["grid_current_pace"] = np.nan
        output["grid_current_laps"] = np.nan
        output["grid_model_pace"] = np.nan

    if not actual_grid.empty:
        output = output.merge(
            actual_grid,
            on="Driver",
            how="left",
        )
    else:
        output["actual_grid_team"] = ""
        output["actual_grid_position"] = np.nan
        output["actual_grid_score"] = np.nan

    output["grid_position"] = output["actual_grid_position"].fillna(
        output["estimated_grid_position"]
    )

    if output["grid_position"].isna().any():
        fallback_rank = (
            pd.to_numeric(output["estimated_grid_score"], errors="coerce")
            .fillna(pd.to_numeric(output.get("model_pace", 0), errors="coerce"))
            .rank(method="first", ascending=True)
            .astype(int)
        )

        output["grid_position"] = output["grid_position"].fillna(fallback_rank)

    output["grid_position"] = pd.to_numeric(
        output["grid_position"],
        errors="coerce",
    ).astype(int)

    output["grid_source"] = np.where(
        output["actual_grid_position"].notna(),
        "actual_session_results",
        "estimated_model_grid",
    )

    output["grid_score"] = np.where(
        output["actual_grid_position"].notna(),
        output["actual_grid_score"],
        output["estimated_grid_score"],
    )

    output["grid_confidence"] = np.where(
        output["actual_grid_position"].notna(),
        1.00,
        0.38,
    )

    output = output.sort_values(
        ["grid_position", "Driver"],
        ascending=[True, True],
    ).reset_index(drop=True)

    return output