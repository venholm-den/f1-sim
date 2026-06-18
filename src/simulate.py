from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.model_config import SIMULATION_PARAMETERS


F1_POINTS = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
}


def _sim_param(key: str, default: float) -> float:
    value = SIMULATION_PARAMETERS.get(key, default)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return number


def _to_float_or_default(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return float(number)


def _series(
    df: pd.DataFrame,
    column: str,
    default: float,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")

    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _weather_value(
    weather_modifiers: dict | None,
    key: str,
    default: float,
) -> float:
    if not weather_modifiers:
        return default

    return _to_float_or_default(weather_modifiers.get(key), default)


def _calculate_red_flag_probability(weather_modifiers: dict | None) -> float:
    chaos_factor = _weather_value(weather_modifiers, "chaos_factor", 1.0)
    rainfall = bool(weather_modifiers.get("rainfall_flag", False)) if weather_modifiers else False
    wind_speed = _weather_value(weather_modifiers, "wind_speed_avg", 0.0)

    probability = 0.035

    if rainfall:
        probability += 0.035

    if wind_speed >= 6:
        probability += 0.020
    elif wind_speed >= 4:
        probability += 0.010

    probability *= chaos_factor

    return float(np.clip(probability, 0.01, 0.18))


def _prepare_features(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        raise ValueError("No features supplied to simulation.")

    required = {"Driver", "Team"}
    missing = required - set(features.columns)

    if missing:
        raise ValueError(f"Simulation features missing columns: {sorted(missing)}")

    base = features.copy()
    base["Driver"] = base["Driver"].astype(str)
    base["Team"] = base["Team"].astype(str)

    base["grid_position"] = _series(base, "grid_position", np.nan)

    if base["grid_position"].isna().all():
        if "estimated_grid_position" in base.columns:
            base["grid_position"] = _series(base, "estimated_grid_position", np.nan)
        else:
            pace_for_grid = _series(base, "quali_pace_score", np.nan)

            if pace_for_grid.isna().all():
                pace_for_grid = _series(base, "model_pace", 0.0)

            base["grid_position"] = pace_for_grid.rank(method="first").astype(int)

    grid_median = base["grid_position"].median()

    if not np.isfinite(grid_median):
        grid_median = 10.5

    base["grid_position"] = (
        pd.to_numeric(base["grid_position"], errors="coerce")
        .fillna(grid_median)
        .rank(method="first")
        .astype(int)
    )

    if "grid_source" not in base.columns:
        base["grid_source"] = "estimated_model_grid"

    base["grid_source"] = base["grid_source"].astype(str)

    base["grid_confidence"] = _series(base, "grid_confidence", np.nan)

    default_grid_confidence = pd.Series(
        np.where(
            base["grid_source"].eq("actual_session_results"),
            1.00,
            0.38,
        ),
        index=base.index,
        dtype="float64",
    )

    base["grid_confidence"] = (
        base["grid_confidence"]
        .fillna(default_grid_confidence)
        .clip(0.10, 1.00)
    )

    model_pace_default = 0.0

    if "model_pace" in base.columns:
        model_pace_median = pd.to_numeric(base["model_pace"], errors="coerce").median()
        model_pace_default = _to_float_or_default(model_pace_median, 0.0)

    base["quali_pace_score"] = _series(
        base,
        "quali_pace_score",
        model_pace_default,
    )

    base["race_pace_score"] = _series(base, "race_pace_score", np.nan)

    if base["race_pace_score"].isna().all():
        base["race_pace_score"] = _series(base, "model_pace", 0.0)

    base["race_pace_score"] = base["race_pace_score"].fillna(
        _series(base, "model_pace", 0.0)
    )

    base["long_run_pace_score"] = _series(
        base,
        "long_run_pace_score",
        np.nan,
    ).fillna(base["race_pace_score"])

    base["tyre_deg_score"] = _series(base, "tyre_deg_score", 0.0).clip(-0.04, 0.18)
    base["strategy_score"] = _series(base, "strategy_score", 0.35).clip(0.0, 2.0)

    base["reliability_score"] = _series(base, "reliability_score", np.nan)

    if base["reliability_score"].isna().all():
        base["reliability_score"] = _series(base, "dnf_prob", 0.045)

    base["reliability_score"] = (
        base["reliability_score"]
        .fillna(_series(base, "dnf_prob", 0.045))
        .clip(0.005, 0.30)
    )

    base["performance_uncertainty"] = _series(
        base,
        "performance_uncertainty",
        np.nan,
    )

    if base["performance_uncertainty"].isna().all():
        base["performance_uncertainty"] = _series(base, "model_uncertainty", 1.2)

    base["performance_uncertainty"] = (
        base["performance_uncertainty"]
        .fillna(_series(base, "model_uncertainty", 1.2))
        .clip(0.60, 4.00)
    )

    base["estimated_race_laps"] = _series(base, "estimated_race_laps", 57).clip(40, 90)

    base["base_winner_race_time_seconds"] = _series(
        base,
        "base_winner_race_time_seconds",
        np.nan,
    )

    if base["base_winner_race_time_seconds"].isna().all():
        race_pace = _series(base, "race_pace", np.nan)
        race_pace = race_pace[(race_pace >= 45) & (race_pace <= 160)]

        if race_pace.notna().any():
            base_lap = float(race_pace.quantile(0.20))
        else:
            base_lap = 90.0

        laps = int(round(float(base["estimated_race_laps"].median())))
        base_time = base_lap * laps + 28.0
        base["base_winner_race_time_seconds"] = base_time

    base_time_median = base["base_winner_race_time_seconds"].median()

    if not np.isfinite(base_time_median):
        base_time_median = 90.0 * 57 + 28.0

    base["base_winner_race_time_seconds"] = (
        base["base_winner_race_time_seconds"]
        .fillna(base_time_median)
    )

    base = base.sort_values("grid_position").reset_index(drop=True)

    return base


def _points_for_positions(positions: np.ndarray) -> np.ndarray:
    points = np.zeros_like(positions, dtype=float)

    for pos, pts in F1_POINTS.items():
        points[positions == pos] = pts

    return points


def simulate_races(
    features: pd.DataFrame,
    n_sims: int = 50000,
    seed: int = 42,
    overtaking_difficulty: float = 0.55,
    weather_modifiers: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Simulates races by estimating total projected race time per driver.

    Lower projected time wins.

    Returns:
    - summary
    - position_matrix
    - raw results
    """

    base = _prepare_features(features)

    rng = np.random.default_rng(seed)

    n_drivers = len(base)

    if n_drivers == 0:
        raise ValueError("No drivers available to simulate.")

    driver_array = base["Driver"].to_numpy()
    team_array = base["Team"].to_numpy()

    race_laps = float(base["estimated_race_laps"].median())
    base_winner_time = float(base["base_winner_race_time_seconds"].median())

    chaos_factor = _weather_value(weather_modifiers, "chaos_factor", 1.0)
    strategy_factor = _weather_value(weather_modifiers, "strategy_factor", 1.0)
    dnf_factor = _weather_value(weather_modifiers, "dnf_factor", 1.0)
    degradation_factor = _weather_value(weather_modifiers, "degradation_factor", 1.0)
    uncertainty_factor = _weather_value(weather_modifiers, "uncertainty_factor", 1.0)

    race_control_red_flag_probability_hint = _weather_value(
        weather_modifiers,
        "race_control_red_flag_probability_hint",
        0.02,
    )

    race_pace_seconds_multiplier = _sim_param("race_pace_seconds_multiplier", 0.20)
    long_run_penalty_multiplier = _sim_param("long_run_penalty_multiplier", 0.25)
    tyre_deg_multiplier = _sim_param("tyre_deg_multiplier", 7.00)
    grid_loss_multiplier = _sim_param("grid_loss_multiplier", 1.65)
    strategy_loss_multiplier = _sim_param("strategy_loss_multiplier", 2.50)
    race_noise_multiplier = _sim_param("race_noise_multiplier", 3.80)
    start_noise_seconds = _sim_param("start_noise_seconds", 1.15)
    strategy_noise_seconds = _sim_param("strategy_noise_seconds", 1.50)
    chaos_noise_seconds = _sim_param("chaos_noise_seconds", 1.25)
    red_flag_field_compression = _sim_param("red_flag_field_compression", 0.72)
    red_flag_noise_seconds = _sim_param("red_flag_noise_seconds", 2.00)

    red_flag_probability = _calculate_red_flag_probability(weather_modifiers)
    red_flag_probability = max(
        red_flag_probability,
        race_control_red_flag_probability_hint,
    )
    red_flag_probability = min(red_flag_probability, 0.45)

    red_flags = rng.random(n_sims) < red_flag_probability

    race_pace = base["race_pace_score"].to_numpy(dtype=float)
    long_run_pace = base["long_run_pace_score"].to_numpy(dtype=float)
    tyre_deg = base["tyre_deg_score"].to_numpy(dtype=float)
    strategy_score = base["strategy_score"].to_numpy(dtype=float)
    uncertainty = base["performance_uncertainty"].to_numpy(dtype=float)
    dnf_prob = base["reliability_score"].to_numpy(dtype=float)
    grid = base["grid_position"].to_numpy(dtype=float)
    grid_confidence = base["grid_confidence"].to_numpy(dtype=float)

    race_pace_loss = race_pace * race_laps * race_pace_seconds_multiplier

    long_run_loss = (
        np.maximum(long_run_pace - race_pace, 0)
        * race_laps
        * long_run_penalty_multiplier
    )

    degradation_loss = (
        np.maximum(tyre_deg, 0)
        * race_laps
        * tyre_deg_multiplier
        * degradation_factor
    )

    grid_loss = (
        (grid - 1)
        * float(overtaking_difficulty)
        * grid_confidence
        * grid_loss_multiplier
    )

    strategy_baseline_loss = (
        strategy_score
        * strategy_loss_multiplier
        * strategy_factor
    )

    deterministic_time = (
        base_winner_time
        + race_pace_loss
        + long_run_loss
        + degradation_loss
        + grid_loss
        + strategy_baseline_loss
    )

    deterministic_time = deterministic_time - deterministic_time.min() + base_winner_time

    race_noise = rng.normal(
        loc=0.0,
        scale=(uncertainty * race_noise_multiplier * uncertainty_factor),
        size=(n_sims, n_drivers),
    )

    start_noise = rng.normal(
        loc=0.0,
        scale=start_noise_seconds,
        size=(n_sims, n_drivers),
    )

    strategy_noise = rng.normal(
        loc=0.0,
        scale=(strategy_noise_seconds * strategy_factor),
        size=(n_sims, n_drivers),
    )

    degradation_noise = rng.normal(
        loc=0.0,
        scale=(np.maximum(tyre_deg, 0.01) * race_laps * 1.4 * degradation_factor),
        size=(n_sims, n_drivers),
    )

    chaos_noise = rng.normal(
        loc=0.0,
        scale=chaos_noise_seconds * chaos_factor,
        size=(n_sims, n_drivers),
    )

    projected_times = (
        deterministic_time.reshape(1, n_drivers)
        + race_noise
        + start_noise
        + strategy_noise
        + degradation_noise
        + chaos_noise
    )

    if red_flags.any():
        red_flag_rows = red_flags.reshape(n_sims, 1)

        field_best = projected_times.min(axis=1).reshape(n_sims, 1)
        compressed = field_best + (
            projected_times - field_best
        ) * red_flag_field_compression

        red_flag_noise = rng.normal(
            loc=0.0,
            scale=red_flag_noise_seconds,
            size=(n_sims, n_drivers),
        )

        projected_times = np.where(
            red_flag_rows,
            compressed + red_flag_noise,
            projected_times,
        )

    dnf_random = rng.random((n_sims, n_drivers))
    effective_dnf_prob = np.clip(dnf_prob * dnf_factor, 0.002, 0.45)
    dnf_matrix = dnf_random < effective_dnf_prob.reshape(1, n_drivers)

    dnf_penalty = rng.uniform(600.0, 1600.0, size=(n_sims, n_drivers))

    classified_times = np.where(
        dnf_matrix,
        projected_times + dnf_penalty,
        projected_times,
    )

    order = np.argsort(classified_times, axis=1)
    positions = np.empty_like(order)

    row_index = np.arange(n_sims)[:, None]
    positions[row_index, order] = np.arange(1, n_drivers + 1)

    race_points = _points_for_positions(positions)
    race_points = np.where(dnf_matrix, 0.0, race_points)

    positions_gained = grid.reshape(1, n_drivers) - positions

    fastest_lap_matrix = np.zeros((n_sims, n_drivers), dtype=bool)

    fastest_lap_score = (
        projected_times
        - projected_times.min(axis=1).reshape(n_sims, 1)
        + rng.normal(0, 2.0, size=(n_sims, n_drivers))
    )

    eligible_fastest_lap = (~dnf_matrix) & (positions <= 10)

    fastest_lap_score = np.where(
        eligible_fastest_lap,
        fastest_lap_score,
        np.inf,
    )

    fastest_lap_winners = np.argmin(fastest_lap_score, axis=1)

    fastest_lap_matrix[np.arange(n_sims), fastest_lap_winners] = np.isfinite(
        fastest_lap_score[np.arange(n_sims), fastest_lap_winners]
    )

    dotd_matrix = np.zeros((n_sims, n_drivers), dtype=bool)

    dotd_eligible = (
        (~dnf_matrix)
        & (
            (positions <= 5)
            | ((positions <= 10) & (positions_gained >= 4))
            | (positions_gained >= 8)
        )
    )

    dotd_score = (
        positions_gained * 1.25
        + np.where(positions <= 3, 4.0, 0.0)
        + np.where(positions <= 5, 2.0, 0.0)
        + np.where((positions <= 10) & (positions_gained >= 4), 2.0, 0.0)
        + rng.normal(0, 2.75, size=(n_sims, n_drivers))
    )

    dotd_score = np.where(dotd_eligible, dotd_score, -np.inf)
    dotd_winners = np.argmax(dotd_score, axis=1)

    dotd_matrix[np.arange(n_sims), dotd_winners] = np.isfinite(
        dotd_score[np.arange(n_sims), dotd_winners]
    )

    records = []

    for driver_idx in range(n_drivers):
        driver_records = pd.DataFrame(
            {
                "sim_id": np.arange(n_sims),
                "Driver": driver_array[driver_idx],
                "Team": team_array[driver_idx],
                "grid_position": int(grid[driver_idx]),
                "finish_position": positions[:, driver_idx].astype(int),
                "position": positions[:, driver_idx].astype(int),
                "Position": positions[:, driver_idx].astype(int),
                "points": race_points[:, driver_idx],
                "race_points": race_points[:, driver_idx],
                "projected_race_time_seconds": projected_times[:, driver_idx],
                "classified_race_time_seconds": classified_times[:, driver_idx],
                "performance_score": projected_times[:, driver_idx],
                "dnf": dnf_matrix[:, driver_idx],
                "DNF": dnf_matrix[:, driver_idx],
                "red_flag": red_flags,
                "red_flag_probability": red_flag_probability,
                "positions_gained": positions_gained[:, driver_idx],
                "fastest_lap": fastest_lap_matrix[:, driver_idx],
                "dotd": dotd_matrix[:, driver_idx],
            }
        )

        records.append(driver_records)

    results = pd.concat(records, ignore_index=True)

    summary_rows = []

    for driver, group in results.groupby("Driver", sort=False):
        team = str(group["Team"].iloc[0])
        driver_feature = base[base["Driver"] == driver].iloc[0]

        finish = group["finish_position"]
        pts = group["points"]

        row = {
            "Driver": driver,
            "Team": team,
            "avg_grid": float(group["grid_position"].mean()),
            "avg_finish": float(finish.mean()),
            "finish_p25": float(finish.quantile(0.25)),
            "finish_p75": float(finish.quantile(0.75)),
            "avg_points": float(pts.mean()),
            "points_p25": float(pts.quantile(0.25)),
            "points_p75": float(pts.quantile(0.75)),
            "win_chance": float((finish == 1).mean()),
            "podium_chance": float((finish <= 3).mean()),
            "top5_chance": float((finish <= 5).mean()),
            "points_chance": float((finish <= 10).mean()),
            "dnf_chance": float(group["dnf"].mean()),
            "red_flag_chance": float(group["red_flag"].mean()),
            "avg_projected_race_time_seconds": float(
                group["projected_race_time_seconds"].mean()
            ),
            "race_time_p25": float(
                group["projected_race_time_seconds"].quantile(0.25)
            ),
            "race_time_p50": float(
                group["projected_race_time_seconds"].quantile(0.50)
            ),
            "race_time_p75": float(
                group["projected_race_time_seconds"].quantile(0.75)
            ),
        }

        for col in [
            "race_pace",
            "relative_pace",
            "model_pace",
            "model_uncertainty",
            "grid_position",
            "grid_score",
            "grid_source",
            "grid_confidence",
            "current_relative_pace",
            "current_relative_pace_capped",
            "baseline_relative_pace",
            "baseline_pace_std",
            "baseline_rounds",
            "current_weight",
            "best_lap",
            "lap_std",
            "deg_per_lap",
            "clean_laps",
            "raw_laps",
            "quali_pace_score",
            "race_pace_score",
            "long_run_pace_score",
            "tyre_deg_score",
            "reliability_score",
            "strategy_score",
            "performance_uncertainty",
            "projected_lap_time",
            "estimated_race_laps",
            "base_winner_race_time_seconds",
            "performance_model_version",
            "historical_model_available",
            "historical_predicted_finish",
            "historical_finish_score",
            "historical_dnf_probability",
            "historical_finish_weight",
            "historical_dnf_weight",
            "historical_calibration_note",
        ]:
            if col in base.columns:
                row[col] = driver_feature.get(col)

        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values("avg_finish", ascending=True).reset_index(drop=True)

    position_matrix = pd.crosstab(
        results["Driver"],
        results["finish_position"],
        normalize="index",
    )

    for position in range(1, n_drivers + 1):
        if position not in position_matrix.columns:
            position_matrix[position] = 0.0

    position_matrix = position_matrix[range(1, n_drivers + 1)]
    position_matrix.columns = [f"P{position}" for position in range(1, n_drivers + 1)]
    position_matrix = position_matrix.reset_index()

    return summary, position_matrix, results
