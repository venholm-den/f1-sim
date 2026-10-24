from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.model_config import FANTASY_SCORING


def _ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)


def _to_float_or_nan(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")

    if not np.isfinite(number):
        return float("nan")

    return float(number)


def _to_bool_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "bool":
        return series.fillna(False).astype(bool)

    text = series.astype(str).str.strip().str.lower()

    return text.isin({"true", "1", "yes", "y"})


def _series_or_default(
    df: pd.DataFrame,
    column: str,
    default: Any,
) -> pd.Series:
    if column in df.columns:
        return df[column]

    return pd.Series([default] * len(df), index=df.index)


def _scoring_value(key: str, default: float | None, scoring: dict | None = None) -> float | None:
    value = (FANTASY_SCORING if scoring is None else scoring).get(key, default)

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_points_mapping(mapping: dict[Any, Any]) -> dict[int, float]:
    output: dict[int, float] = {}

    for key, value in mapping.items():
        try:
            position = int(key)
            points = float(value)
        except (TypeError, ValueError):
            continue

        output[position] = points

    return output


def _finish_points_mapping(scoring: dict | None = None) -> dict[int, float]:
    return _normalise_points_mapping(
        (FANTASY_SCORING if scoring is None else scoring).get(
            "finish_points",
            {
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
            },
        )
    )


def _quali_points_mapping(scoring: dict | None = None) -> dict[int, float]:
    return _normalise_points_mapping(
        (FANTASY_SCORING if scoring is None else scoring).get(
            "quali_points",
            {
                1: 10,
                2: 9,
                3: 8,
                4: 7,
                5: 6,
                6: 5,
                7: 4,
                8: 3,
                9: 2,
                10: 1,
            },
        )
    )


def _sprint_points_mapping(scoring: dict | None = None) -> dict[int, float]:
    return _normalise_points_mapping(
        (FANTASY_SCORING if scoring is None else scoring).get(
            "sprint_finish_points",
            {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1},
        )
    )


def _points_from_position(
    position: Any,
    mapping: dict[int, float],
) -> float:
    number = _to_float_or_nan(position)

    if not np.isfinite(number):
        return 0.0

    return float(mapping.get(int(round(number)), 0.0))


def _position_change_points(gained: pd.Series, scoring: dict | None = None) -> pd.Series:
    gain = _scoring_value("position_gain_points_per_place", 1.0, scoring)
    loss = _scoring_value("position_loss_points_per_place", -1.0, scoring)
    points = pd.Series(
        np.where(gained >= 0, gained * gain, gained.abs() * loss),
        index=gained.index,
        dtype="float64",
    )
    return points.clip(
        _scoring_value("position_change_min", None, scoring),
        _scoring_value("position_change_max", None, scoring),
    )


def _overtakes(
    df: pd.DataFrame,
    column: str,
    gained: pd.Series,
    not_classified: pd.Series,
    session: str,
    scoring: dict | None = None,
) -> tuple[pd.Series, bool]:
    """Counted passes when the run has them, otherwise the archived-fit estimate."""
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce").fillna(0.0), False

    fit = ((FANTASY_SCORING if scoring is None else scoring)
           .get("estimated_overtakes", {}).get(session, {}))
    estimate = (
        float(fit.get("base", 0.0))
        + gained.clip(lower=0) * float(fit.get("per_place_gained", 0.0))
        + (-gained).clip(lower=0) * float(fit.get("per_place_lost", 0.0))
    )
    return estimate.where(~not_classified, float(fit.get("not_classified", 0.0))), True


def _load_prices(prices_path: str) -> pd.DataFrame:
    path = Path(prices_path)

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["Driver", "Team", "fantasy_price"])

    try:
        prices = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["Driver", "Team", "fantasy_price"])

    if "Driver" not in prices.columns:
        prices["Driver"] = ""

    if "Team" not in prices.columns:
        prices["Team"] = ""

    if "fantasy_price" not in prices.columns:
        prices["fantasy_price"] = np.nan

    prices["Driver"] = prices["Driver"].astype(str)
    prices["Team"] = prices["Team"].astype(str)
    prices["fantasy_price"] = pd.to_numeric(
        prices["fantasy_price"],
        errors="coerce",
    )

    return prices[["Driver", "Team", "fantasy_price"]].copy()


def ensure_price_template(
    model_features: pd.DataFrame,
    prices_path: str = "data/fantasy_prices.csv",
) -> str:
    """
    Ensures data/fantasy_prices.csv exists and contains every current driver.

    Fill in fantasy_price manually if you want xPPM/value calculations.
    """

    _ensure_data_dir()

    path = Path(prices_path)

    required_cols = ["Driver", "Team", "fantasy_price"]

    if model_features.empty:
        if not path.exists():
            pd.DataFrame(columns=required_cols).to_csv(path, index=False)

        return str(path)

    current = model_features[["Driver", "Team"]].copy()
    current["Driver"] = current["Driver"].astype(str)
    current["Team"] = current["Team"].astype(str)
    current["fantasy_price"] = np.nan

    if path.exists() and path.stat().st_size > 0:
        existing = _load_prices(prices_path)
    else:
        existing = pd.DataFrame(columns=required_cols)

    combined = current.merge(
        existing[["Driver", "fantasy_price"]],
        on="Driver",
        how="left",
        suffixes=("", "_existing"),
    )

    combined["fantasy_price"] = combined["fantasy_price_existing"]
    combined = combined.drop(columns=["fantasy_price_existing"])

    combined = combined[required_cols].drop_duplicates(subset=["Driver"])

    combined.to_csv(path, index=False)

    return str(path)


def add_simulated_fantasy_points(
    results: pd.DataFrame,
    scoring: dict | None = None,
) -> pd.DataFrame:
    """
    Adds fantasy-point columns to every simulated driver result.

    Fantasy is scored per simulation, then averaged later. Optional columns
    (classified, overtakes, disqualified, qualifying_not_classified and the
    sprint_* equivalents) let archived results be scored by the same rules.
    """

    if results.empty:
        return results.copy()

    df = results.copy()

    if "Driver" not in df.columns:
        raise ValueError("results must contain Driver")

    if "Team" not in df.columns:
        df["Team"] = "Unknown"

    df["Driver"] = df["Driver"].astype(str)
    df["Team"] = df["Team"].astype(str)

    finish_points_map = _finish_points_mapping(scoring)
    quali_points_map = _quali_points_mapping(scoring)

    def value(key: str, default: float) -> float:
        return float(_scoring_value(key, default, scoring))

    finish_position = pd.to_numeric(
        _series_or_default(df, "finish_position", np.nan),
        errors="coerce",
    )

    grid_position = pd.to_numeric(
        _series_or_default(df, "grid_position", np.nan),
        errors="coerce",
    )

    if "positions_gained" in df.columns:
        positions_gained = pd.to_numeric(
            df["positions_gained"],
            errors="coerce",
        ).fillna(0.0)
    else:
        positions_gained = (grid_position - finish_position).fillna(0.0)

    fastest_lap = _to_bool_series(
        _series_or_default(df, "fastest_lap", False)
    )

    dotd = _to_bool_series(
        _series_or_default(df, "dotd", False)
    )

    dnf = _to_bool_series(
        _series_or_default(df, "dnf", False)
    )

    disqualified = _to_bool_series(_series_or_default(df, "disqualified", False))

    # A late retirement can still be classified, and then scores its place.
    if "classified" in df.columns:
        not_classified = ~_to_bool_series(df["classified"])
    else:
        not_classified = dnf
    not_classified = not_classified & ~disqualified
    unscored = not_classified | disqualified

    race_points = finish_position.map(
        lambda position: _points_from_position(position, finish_points_map)
    ).fillna(0.0).where(~unscored, 0.0)

    # Qualifying points follow the qualifying order; a grid penalty moves the
    # start position only. Older results have grid_position alone.
    qualifying_position = pd.to_numeric(
        _series_or_default(df, "qualifying_position", np.nan),
        errors="coerce",
    ).fillna(grid_position)

    quali_not_classified = _to_bool_series(
        _series_or_default(df, "qualifying_not_classified", False))
    quali_disqualified = _to_bool_series(
        _series_or_default(df, "qualifying_disqualified", False))

    quali_points = qualifying_position.map(
        lambda position: _points_from_position(position, quali_points_map)
    ).fillna(0.0).where(~(quali_not_classified | quali_disqualified), 0.0)
    quali_points = (
        quali_points
        + quali_not_classified.astype(float) * value("quali_not_classified_penalty", -5.0)
        + quali_disqualified.astype(float) * value("quali_disqualified_penalty", -5.0)
    )

    # Not classified or disqualified: the penalty replaces any position change.
    position_change_points = _position_change_points(positions_gained, scoring).where(~unscored, 0.0)

    overtakes, overtakes_estimated = _overtakes(
        df, "overtakes", positions_gained, unscored, "race", scoring)
    overtake_points = overtakes * value("overtake_points", 1.0)

    fastest_lap_points = fastest_lap.astype(float) * value("fastest_lap_bonus", 10.0)
    dotd_points = dotd.astype(float) * value("dotd_bonus", 10.0)
    dnf_points = (
        not_classified.astype(float) * value("dnf_penalty", -20.0)
        + disqualified.astype(float) * value("race_disqualified_penalty", -20.0)
    )

    df["finish_fantasy_points"] = race_points
    df["quali_fantasy_points"] = quali_points
    df["position_change_points"] = position_change_points
    df["overtake_points"] = overtake_points
    df["overtakes_estimated"] = overtakes_estimated
    df["fastest_lap_points"] = fastest_lap_points
    df["dotd_points"] = dotd_points
    df["dnf_penalty_points"] = dnf_points

    # Sprint weekends: sprint place points, position change, overtakes, the
    # sprint fastest lap and the sprint penalties. Absent columns score nothing.
    sprint_fantasy_points = 0.0
    if "sprint_position" in df.columns:
        sprint_position = pd.to_numeric(df["sprint_position"], errors="coerce")
        # Rows from a weekend without a sprint carry blanks and score nothing.
        held = sprint_position.notna()
        sprint_dnf = _to_bool_series(_series_or_default(df, "sprint_dnf", False))
        sprint_dsq = _to_bool_series(_series_or_default(df, "sprint_disqualified", False))
        if "sprint_classified" in df.columns:
            held = held | df["sprint_classified"].notna()
            sprint_dnf = ~_to_bool_series(df["sprint_classified"])
        held = held | sprint_dnf | sprint_dsq
        if "sprint_classified" in df.columns:
            sprint_dnf = sprint_dnf & df["sprint_classified"].notna()
        sprint_dnf = sprint_dnf & ~sprint_dsq
        sprint_unscored = sprint_dnf | sprint_dsq
        sprint_gained = pd.to_numeric(
            _series_or_default(df, "sprint_positions_gained", 0.0), errors="coerce").fillna(0.0)
        sprint_map = _sprint_points_mapping(scoring)
        sprint_place = sprint_position.map(
            lambda position: _points_from_position(position, sprint_map)
        ).fillna(0.0).where(~sprint_unscored, 0.0)
        sprint_change = _position_change_points(sprint_gained, scoring).where(~sprint_unscored, 0.0)
        sprint_overtakes, _ = _overtakes(
            df, "sprint_overtakes", sprint_gained, sprint_unscored, "sprint", scoring)
        sprint_fastest = _to_bool_series(_series_or_default(df, "sprint_fastest_lap", False))
        sprint_fantasy_points = (
            sprint_place
            + sprint_change
            + sprint_overtakes * value("overtake_points", 1.0)
            + sprint_fastest.astype(float) * value("sprint_fastest_lap_bonus", 5.0)
            + sprint_dnf.astype(float) * value("sprint_dnf_penalty", -10.0)
            + sprint_dsq.astype(float) * value("sprint_disqualified_penalty", -10.0)
        ).where(held, 0.0)
        df["sprint_fantasy_points"] = sprint_fantasy_points

    df["fantasy_points"] = (
        df["finish_fantasy_points"]
        + df["quali_fantasy_points"]
        + df["position_change_points"]
        + df["overtake_points"]
        + df["fastest_lap_points"]
        + df["dotd_points"]
        + df["dnf_penalty_points"]
        + sprint_fantasy_points
    )

    df["avg_positions_gained_input"] = positions_gained

    return df


def _pit_stop_points(seconds: float | None, scoring: dict | None = None) -> float:
    if seconds is None or not np.isfinite(seconds):
        return 0.0
    bands = (FANTASY_SCORING if scoring is None else scoring)["constructor"]["pit_stop_bands"]
    for limit, points in bands:
        if round(float(seconds), 2) <= float(limit):
            return float(points)
    return 0.0


def add_constructor_fantasy_points(
    fantasy_results: pd.DataFrame,
    scoring: dict | None = None,
    pit_stop_points: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    One row per sim and team from scored driver rows.

    A constructor scores both drivers' points except Driver of the Day, plus a
    qualifying teamwork bonus. Pit stops are not simulated, so pit_stop_points
    adds each team's expected pit-stop points (from the archive) when given.
    """
    rules = (FANTASY_SCORING if scoring is None else scoring)["constructor"]
    teamwork = rules["qualifying_teamwork"]
    if fantasy_results.empty or "fantasy_points" not in fantasy_results.columns:
        return pd.DataFrame(columns=["sim_id", "Team", "constructor_fantasy_points"])

    df = fantasy_results.copy()
    if "sim_id" not in df.columns:
        df["sim_id"] = 0
    if "Team" not in df.columns:
        df["Team"] = "Unknown"
    df["_driver_points"] = df["fantasy_points"] - pd.to_numeric(
        _series_or_default(df, "dotd_points", 0.0), errors="coerce").fillna(0.0)
    qualifying = pd.to_numeric(
        _series_or_default(df, "qualifying_position", np.nan), errors="coerce"
    ).fillna(pd.to_numeric(_series_or_default(df, "grid_position", np.nan), errors="coerce"))
    quali_out = (_to_bool_series(_series_or_default(df, "qualifying_not_classified", False))
                 | _to_bool_series(_series_or_default(df, "qualifying_disqualified", False)))
    df["_q3"] = ((qualifying <= rules["q3_cutoff"]) & ~quali_out).astype(int)
    df["_q2"] = ((qualifying <= rules["q2_cutoff"]) & ~quali_out).astype(int)

    grouped = df.groupby(["sim_id", "Team"], sort=False).agg(
        driver_points=("_driver_points", "sum"),
        q2=("_q2", "sum"),
        q3=("_q3", "sum"),
    ).reset_index()

    def bonus(row: pd.Series) -> float:
        if row["q3"] >= 2:
            return float(teamwork["both_q3"])
        if row["q3"] == 1:
            return float(teamwork["one_q3"])
        if row["q2"] >= 2:
            return float(teamwork["both_q2"])
        if row["q2"] == 1:
            return float(teamwork["one_q2"])
        return float(teamwork["neither_q2"])

    grouped["teamwork_points"] = grouped.apply(bonus, axis=1) if len(grouped) else []
    pit = pit_stop_points or {}
    grouped["pit_stop_points"] = grouped["Team"].map(lambda team: float(pit.get(team, 0.0)))
    grouped["constructor_fantasy_points"] = (
        grouped["driver_points"] + grouped["teamwork_points"] + grouped["pit_stop_points"]
    )
    return grouped.drop(columns=["q2", "q3"])


def constructor_fantasy_summary(
    fantasy_results: pd.DataFrame,
    scoring: dict | None = None,
    pit_stop_points: dict[str, float] | None = None,
) -> pd.DataFrame:
    teams = add_constructor_fantasy_points(fantasy_results, scoring, pit_stop_points)
    if teams.empty:
        return pd.DataFrame(columns=["Team", "avg_constructor_points"])
    points = "constructor_fantasy_points"
    return teams.groupby("Team", as_index=False).agg(
        avg_constructor_points=(points, "mean"),
        constructor_floor_p10=(points, lambda s: float(s.quantile(0.10))),
        constructor_ceiling_p90=(points, lambda s: float(s.quantile(0.90))),
        avg_teamwork_points=("teamwork_points", "mean"),
        pit_stop_points=("pit_stop_points", "mean"),
    ).sort_values("avg_constructor_points", ascending=False).reset_index(drop=True)


def calculate_fantasy_summary(
    results: pd.DataFrame,
    race_summary: pd.DataFrame,
    prices_path: str = "data/fantasy_prices.csv",
    scoring: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
    - race summary merged with fantasy metrics
    - raw per-simulation fantasy results
    """

    if results.empty:
        summary = race_summary.copy()

        for col in [
            "avg_fantasy_points",
            "fantasy_p25",
            "fantasy_p75",
            "fantasy_std",
            "fantasy_floor_p10",
            "fantasy_ceiling_p90",
            "avg_positions_gained",
            "fastest_lap_chance",
            "dotd_chance",
            "avg_quali_points",
            "avg_finish_fantasy_points",
            "avg_position_change_points",
            "avg_overtake_points",
            "avg_fastest_lap_points",
            "avg_dotd_points",
            "avg_dnf_penalty",
            "fantasy_price",
            "fantasy_xppm",
        ]:
            summary[col] = np.nan

        return summary, results.copy()

    fantasy_results = add_simulated_fantasy_points(results, scoring)

    grouped = fantasy_results.groupby(["Driver", "Team"], dropna=False)
    has_sprint = "sprint_fantasy_points" in fantasy_results.columns

    fantasy_summary = grouped.agg(
        avg_fantasy_points=("fantasy_points", "mean"),
        fantasy_p25=("fantasy_points", lambda s: float(s.quantile(0.25))),
        fantasy_p75=("fantasy_points", lambda s: float(s.quantile(0.75))),
        fantasy_std=("fantasy_points", "std"),
        fantasy_floor_p10=("fantasy_points", lambda s: float(s.quantile(0.10))),
        fantasy_ceiling_p90=("fantasy_points", lambda s: float(s.quantile(0.90))),
        avg_positions_gained=("avg_positions_gained_input", "mean"),
        fastest_lap_chance=("fastest_lap", lambda s: float(_to_bool_series(s).mean())),
        dotd_chance=("dotd", lambda s: float(_to_bool_series(s).mean())),
        avg_quali_points=("quali_fantasy_points", "mean"),
        avg_finish_fantasy_points=("finish_fantasy_points", "mean"),
        avg_position_change_points=("position_change_points", "mean"),
        avg_overtake_points=("overtake_points", "mean"),
        avg_fastest_lap_points=("fastest_lap_points", "mean"),
        avg_dotd_points=("dotd_points", "mean"),
        avg_dnf_penalty=("dnf_penalty_points", "mean"),
        **({"avg_sprint_fantasy_points": ("sprint_fantasy_points", "mean")}
           if has_sprint else {}),
    ).reset_index()

    fantasy_summary["fantasy_std"] = fantasy_summary["fantasy_std"].fillna(0.0)

    prices = _load_prices(prices_path)

    if not prices.empty:
        fantasy_summary = fantasy_summary.merge(
            prices[["Driver", "fantasy_price"]],
            on="Driver",
            how="left",
        )
    else:
        fantasy_summary["fantasy_price"] = np.nan

    fantasy_summary["fantasy_xppm"] = np.where(
        pd.to_numeric(fantasy_summary["fantasy_price"], errors="coerce") > 0,
        fantasy_summary["avg_fantasy_points"]
        / pd.to_numeric(fantasy_summary["fantasy_price"], errors="coerce"),
        np.nan,
    )

    summary = race_summary.copy()

    if "Driver" not in summary.columns:
        raise ValueError("race_summary must contain Driver")

    if "Team" not in summary.columns:
        summary["Team"] = ""

    summary["Driver"] = summary["Driver"].astype(str)
    summary["Team"] = summary["Team"].astype(str)

    fantasy_merge_cols = [
        "Driver",
        "avg_fantasy_points",
        "fantasy_p25",
        "fantasy_p75",
        "fantasy_std",
        "fantasy_floor_p10",
        "fantasy_ceiling_p90",
        "avg_positions_gained",
        "fastest_lap_chance",
        "dotd_chance",
        "avg_quali_points",
        "avg_finish_fantasy_points",
        "avg_position_change_points",
        "avg_overtake_points",
        "avg_fastest_lap_points",
        "avg_dotd_points",
        "avg_dnf_penalty",
        "fantasy_price",
        "fantasy_xppm",
    ]
    if has_sprint:
        fantasy_merge_cols.append("avg_sprint_fantasy_points")

    summary = summary.merge(
        fantasy_summary[fantasy_merge_cols],
        on="Driver",
        how="left",
    )

    summary = summary.sort_values(
        ["avg_fantasy_points", "avg_points"],
        ascending=[False, False],
    ).reset_index(drop=True)

    return summary, fantasy_results

def check_scoring_against_archive(payload: dict, season: int) -> dict[str, Any]:
    """
    Re-scores an archived tools capture with this module and compares each
    session total with the points the game awarded. Returns counts and every
    mismatch, so a rules change shows up as a list of rows rather than a guess.
    """
    from src.fantasy_market import scored_archive_records
    from src.model_config import fantasy_scoring_for_season

    scoring = fantasy_scoring_for_season(season)
    drivers, constructors = scored_archive_records(payload, season)
    frame = pd.DataFrame(drivers)
    if frame.empty:
        return {"season": int(season), "drivers": 0, "constructors": 0, "mismatches": []}
    scored = add_simulated_fantasy_points(frame, scoring)
    race = (scored["finish_fantasy_points"] + scored["position_change_points"]
            + scored["overtake_points"] + scored["fastest_lap_points"]
            + scored["dotd_points"] + scored["dnf_penalty_points"])
    sprint = _series_or_default(scored, "sprint_fantasy_points", 0.0)
    checks = {"qualifying": (scored["quali_fantasy_points"], scored["actual_qualifying"]),
              "race": (race, scored["actual_race"]),
              "sprint": (sprint, scored["actual_sprint"]),
              "total": (scored["fantasy_points"], scored["actual_total"])}
    mismatches = []
    matched = {}
    for name, (ours, actual) in checks.items():
        actual = pd.to_numeric(actual, errors="coerce")
        known = actual.notna()
        wrong = known & ((ours - actual).abs() > 1e-9)
        matched[name] = int((known & ~wrong).sum())
        for index in scored.index[wrong]:
            mismatches.append({"asset": "driver", "session": name,
                               "round": int(scored.at[index, "round"]),
                               "code": scored.at[index, "Driver"],
                               "ours": float(ours[index]), "actual": float(actual[index])})

    teams = pd.DataFrame(constructors)
    team_matched = 0
    pit_unchecked = 0
    for round_number, group in scored.groupby("round"):
        pit = {}
        rows = teams[teams["round"] == round_number]
        for row in rows.itertuples():
            rules = scoring["constructor"]
            seconds = row.fastest_pit_stop_seconds
            if seconds is None or not np.isfinite(seconds):
                # Older captures omit the stop time; take the awarded pit points
                # as given so the rest of the constructor score is still checked.
                pit[row.Team] = float(row.actual_pit_stop)
                pit_unchecked += bool(row.actual_pit_stop)
                continue
            pit[row.Team] = (_pit_stop_points(seconds, scoring)
                             + rules["fastest_pit_stop_bonus"] * row.overall_fastest_pit_stop
                             + rules["world_record_pit_stop_bonus"] * row.world_record_pit_stop)
        ours = add_constructor_fantasy_points(group, scoring, pit).set_index("Team")
        for row in rows.itertuples():
            # Constructor disqualifications score by their own rule; not modelled.
            if row.disqualified or row.Team not in ours.index or row.actual_total is None:
                continue
            value = float(ours.at[row.Team, "constructor_fantasy_points"])
            if abs(value - float(row.actual_total)) > 1e-9:
                mismatches.append({"asset": "constructor", "session": "total",
                                   "round": int(round_number), "code": row.Team,
                                   "ours": value, "actual": float(row.actual_total)})
            else:
                team_matched += 1
    return {"season": int(season), "drivers": len(scored), "constructors": len(teams),
            "matched": {**matched, "constructor_total": team_matched},
            "pit_stops_without_time": pit_unchecked,
            "mismatches": mismatches}
