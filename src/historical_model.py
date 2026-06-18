from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


CLASSIFIED_STATUS_PREFIXES = ("+",)
CLASSIFIED_STATUSES = {"finished"}


@dataclass(frozen=True)
class HistoricalModelArtifacts:
    feature_table: str
    finish_model: str
    dnf_model: str
    metrics: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)

    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame()

    return pd.read_csv(file_path)


def _to_numeric(series: pd.Series | Any) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_series(frame: pd.DataFrame, column: str, default: Any = None) -> pd.Series:
    if column in frame.columns:
        return frame[column]

    return pd.Series([default] * len(frame), index=frame.index)


def _normalise_event_keys(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    rename = {}

    for source, target in [
        ("year", "Year"),
        ("event", "Event"),
        ("round", "Round"),
        ("session", "Session"),
    ]:
        if source in output.columns and target not in output.columns:
            rename[source] = target

    output = output.rename(columns=rename)

    if "Year" in output.columns:
        output["Year"] = _to_numeric(output["Year"]).astype("Int64")
    if "Round" in output.columns:
        output["Round"] = _to_numeric(output["Round"]).astype("Int64")
    if "Event" in output.columns:
        output["Event"] = output["Event"].astype(str)

    return output


def _classified(status: Any) -> bool:
    text = str(status or "").strip().lower()

    if text in CLASSIFIED_STATUSES:
        return True

    return any(text.startswith(prefix.lower()) for prefix in CLASSIFIED_STATUS_PREFIXES)


def _build_quali_features(laps: pd.DataFrame) -> pd.DataFrame:
    if laps.empty:
        return pd.DataFrame()

    laps = _normalise_event_keys(laps)

    required = {"Year", "Event", "Round", "Session", "Driver", "LapTimeSeconds"}
    if not required.issubset(laps.columns):
        return pd.DataFrame()

    quali = laps[laps["Session"].astype(str).eq("Q")].copy()

    if "CleanPushLap" in quali.columns:
        quali = quali[quali["CleanPushLap"].astype(str).str.lower().isin(["true", "1"])]

    if quali.empty:
        return pd.DataFrame()

    numeric_cols = [
        "LapTimeSeconds",
        "Sector1Seconds",
        "Sector2Seconds",
        "Sector3Seconds",
        "SpeedI1",
        "SpeedI2",
        "SpeedFL",
        "SpeedST",
    ]

    for column in numeric_cols:
        if column in quali.columns:
            quali[column] = _to_numeric(quali[column])

    agg_map: dict[str, tuple[str, str]] = {
        "q_best_lap": ("LapTimeSeconds", "min"),
    }

    for source, output in [
        ("Sector1Seconds", "q_best_s1"),
        ("Sector2Seconds", "q_best_s2"),
        ("Sector3Seconds", "q_best_s3"),
        ("SpeedST", "q_best_speed_trap"),
    ]:
        if source in quali.columns:
            agg_map[output] = (source, "min" if "Sector" in source else "max")

    grouped = (
        quali.groupby(["Year", "Event", "Round", "Driver", "Team"], dropna=False)
        .agg(**agg_map)
        .reset_index()
    )

    grouped["q_rank"] = grouped.groupby(["Year", "Event"])["q_best_lap"].rank(method="min")
    grouped["q_gap_to_best"] = grouped["q_best_lap"] - grouped.groupby(["Year", "Event"])["q_best_lap"].transform("min")
    grouped = grouped.rename(columns={"Driver": "DriverCode", "Team": "Team"})
    return grouped


def _build_weather_features(weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty:
        return pd.DataFrame()

    weather = _normalise_event_keys(weather)
    if "Session" in weather.columns:
        weather = weather[weather["Session"].astype(str).eq("R")].copy()

    keep = [
        "Year",
        "Event",
        "Round",
        "air_temp_avg",
        "track_temp_avg",
        "humidity_avg",
        "pressure_avg",
        "wind_speed_avg",
        "rainfall_flag",
        "chaos_factor",
        "strategy_factor",
        "dnf_factor",
        "degradation_factor",
        "uncertainty_factor",
    ]
    selected = [column for column in keep if column in weather.columns]
    return weather[selected].drop_duplicates(subset=["Year", "Event", "Round"], keep="last")


def _build_race_control_features(race_control: pd.DataFrame) -> pd.DataFrame:
    if race_control.empty:
        return pd.DataFrame()

    race_control = _normalise_event_keys(race_control)
    keep = [
        "Year",
        "Event",
        "Round",
        "safety_car_count",
        "virtual_safety_car_count",
        "red_flag_count",
        "yellow_flag_count",
        "track_status_disruption_score",
        "race_control_disruption_score",
    ]
    selected = [column for column in keep if column in race_control.columns]
    return race_control[selected].drop_duplicates(subset=["Year", "Event", "Round"], keep="last")


def build_historical_feature_table(historical_dir: str | Path = "data/historical_model") -> pd.DataFrame:
    root = Path(historical_dir)
    results = _normalise_event_keys(_read_csv(root / "fastf1_race_results.csv"))
    laps = _read_csv(root / "fastf1_laps.csv")
    weather = _read_csv(root / "fastf1_weather_summary.csv")
    race_control = _read_csv(root / "fastf1_race_control_summary.csv")

    if results.empty:
        return pd.DataFrame()

    result = results.copy()
    result["DriverCode"] = _safe_series(result, "Abbreviation", "").astype(str)
    result["Team"] = _safe_series(result, "TeamName", "").astype(str)
    result["actual_finish_position"] = _to_numeric(_safe_series(result, "Position"))
    result["grid_position"] = _to_numeric(_safe_series(result, "GridPosition"))
    result["actual_points"] = _to_numeric(_safe_series(result, "Points"))
    result["actual_dnf"] = ~_safe_series(result, "Status", "").map(_classified)

    features = result[
        [
            "Year",
            "Event",
            "Round",
            "DriverCode",
            "Team",
            "grid_position",
            "actual_finish_position",
            "actual_points",
            "actual_dnf",
        ]
    ].copy()

    quali = _build_quali_features(laps)
    if not quali.empty:
        features = features.merge(
            quali,
            on=["Year", "Event", "Round", "DriverCode", "Team"],
            how="left",
        )

    weather_features = _build_weather_features(weather)
    if not weather_features.empty:
        features = features.merge(weather_features, on=["Year", "Event", "Round"], how="left")

    race_control_features = _build_race_control_features(race_control)
    if not race_control_features.empty:
        features = features.merge(race_control_features, on=["Year", "Event", "Round"], how="left")

    features["grid_vs_quali_delta"] = features["grid_position"] - features.get("q_rank", np.nan)
    return features


def _preprocessor(feature_table: pd.DataFrame) -> tuple[ColumnTransformer, list[str], list[str]]:
    numeric_columns = [
        column
        for column in [
            "Year",
            "Round",
            "grid_position",
            "q_rank",
            "q_gap_to_best",
            "q_best_lap",
            "q_best_s1",
            "q_best_s2",
            "q_best_s3",
            "q_best_speed_trap",
            "grid_vs_quali_delta",
            "air_temp_avg",
            "track_temp_avg",
            "humidity_avg",
            "pressure_avg",
            "wind_speed_avg",
            "chaos_factor",
            "strategy_factor",
            "dnf_factor",
            "degradation_factor",
            "uncertainty_factor",
            "safety_car_count",
            "virtual_safety_car_count",
            "red_flag_count",
            "yellow_flag_count",
            "track_status_disruption_score",
            "race_control_disruption_score",
        ]
        if column in feature_table.columns
    ]
    categorical_columns = [column for column in ["Event", "DriverCode", "Team", "rainfall_flag"] if column in feature_table.columns]

    transformer = ColumnTransformer(
        transformers=[
            (
                "numeric",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_columns,
            ),
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_columns,
            ),
        ],
        remainder="drop",
    )
    return transformer, numeric_columns, categorical_columns


def _split_train_validation(feature_table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = sorted(_to_numeric(feature_table["Year"]).dropna().astype(int).unique().tolist())

    if len(years) < 2:
        return feature_table.copy(), feature_table.copy()

    validation_year = years[-1]
    train = feature_table[feature_table["Year"].astype(int).lt(validation_year)].copy()
    validation = feature_table[feature_table["Year"].astype(int).eq(validation_year)].copy()

    if len(train) < 30 or len(validation) < 10:
        return feature_table.copy(), feature_table.copy()

    return train, validation


def train_historical_models(
    historical_dir: str | Path = "data/historical_model",
    model_dir: str | Path = "data/models",
) -> HistoricalModelArtifacts:
    output_dir = Path(model_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    feature_table = build_historical_feature_table(historical_dir)
    if feature_table.empty:
        raise ValueError("No historical feature rows found.")

    feature_table = feature_table.dropna(subset=["actual_finish_position"]).copy()
    train, validation = _split_train_validation(feature_table)
    preprocessor, numeric_columns, categorical_columns = _preprocessor(feature_table)
    feature_columns = numeric_columns + categorical_columns

    finish_model = Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("model", Ridge(alpha=2.0)),
        ]
    )
    finish_model.fit(train[feature_columns], train["actual_finish_position"])

    if train["actual_dnf"].nunique() >= 2:
        dnf_estimator: Any = LogisticRegression(max_iter=1000, class_weight="balanced")
    else:
        dnf_estimator = DummyClassifier(strategy="prior")

    dnf_model = Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("model", dnf_estimator),
        ]
    )
    dnf_model.fit(train[feature_columns], train["actual_dnf"].astype(int))

    finish_prediction = finish_model.predict(validation[feature_columns])
    dnf_probability = dnf_model.predict_proba(validation[feature_columns])[:, 1]
    actual_dnf = validation["actual_dnf"].astype(int)

    metrics = {
        "rows": int(len(feature_table)),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "validation_years": sorted(_to_numeric(validation["Year"]).dropna().astype(int).unique().tolist()),
        "feature_columns": feature_columns,
        "finish_mae": float(mean_absolute_error(validation["actual_finish_position"], finish_prediction)),
        "finish_rmse": float(mean_squared_error(validation["actual_finish_position"], finish_prediction) ** 0.5),
        "dnf_brier": float(brier_score_loss(actual_dnf, dnf_probability)),
    }

    if actual_dnf.nunique() >= 2:
        metrics["dnf_log_loss"] = float(log_loss(actual_dnf, dnf_probability))

    feature_path = output_dir / "historical_feature_table.csv"
    finish_model_path = output_dir / "historical_finish_model.joblib"
    dnf_model_path = output_dir / "historical_dnf_model.joblib"
    metrics_path = output_dir / "historical_model_metrics.json"

    feature_table.to_csv(feature_path, index=False)
    joblib.dump(finish_model, finish_model_path)
    joblib.dump(dnf_model, dnf_model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    return HistoricalModelArtifacts(
        feature_table=str(feature_path),
        finish_model=str(finish_model_path),
        dnf_model=str(dnf_model_path),
        metrics=str(metrics_path),
    )
