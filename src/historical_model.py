from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.base import BaseEstimator, RegressorMixin

from src.result_status import STATUS_POLICY_VERSION, classify_result_status, retirement_label
from src.qualifying_features import build_qualifying_features, QUALIFYING_CONTRACT


class GridResidualRegressor(RegressorMixin, BaseEstimator):
    """Learn a change from qualifying order; retain the anchor at inference."""

    def __init__(self, estimator):
        self.estimator = estimator

    def fit(self, frame, target):
        self.estimator_ = clone(self.estimator)
        self.estimator_.fit(frame, np.asarray(target) - np.asarray(frame['q_rank']))
        return self

    def predict(self, frame):
        return np.asarray(frame['q_rank']) + self.estimator_.predict(frame)


def coherent_finish_order(scores, drivers):
    """Produce unique ranks, breaking tied scores by stable driver identifier."""
    scores = np.asarray(scores, dtype=float)
    drivers = np.asarray(drivers, dtype=str)
    if not np.isfinite(scores).all() or len(set(drivers)) != len(scores):
        raise ValueError('Finish scores must be finite with unique driver identifiers.')
    order = np.lexsort((drivers, scores))
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


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
    return classify_result_status(status) == 'finished'


def _build_weather_features(weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty:
        return pd.DataFrame()

    weather = _normalise_event_keys(weather)
    if 'Session' not in weather:
        return pd.DataFrame()
    weather = weather[weather['Session'].astype(str).eq('Q')].copy()

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
    if 'Session' not in race_control:
        return pd.DataFrame()
    race_control = race_control[race_control['Session'].astype(str).eq('Q')].copy()
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


def build_historical_feature_table(historical_dir: str | Path = "data/historical_model", *, enriched: bool = False) -> pd.DataFrame:
    root = Path(historical_dir)
    results = _normalise_event_keys(_read_csv(root / "fastf1_race_results.csv"))
    laps = _read_csv(root / "fastf1_laps.csv")
    weather = _read_csv(root / "fastf1_weather_summary.csv")
    race_control = _read_csv(root / "fastf1_race_control_summary.csv")

    if results.empty:
        return pd.DataFrame()
    if 'Session' not in results or not {'Year', 'Event', 'Round', 'Abbreviation', 'TeamName', 'Position', 'Status'}.issubset(results):
        raise ValueError('Historical race classifications are missing required columns.')
    qualifying_results = results.copy()
    results = results[results.Session.astype(str).eq('R')].copy()

    result = results.copy()
    result["DriverCode"] = _safe_series(result, "Abbreviation", "").astype(str)
    result["Team"] = _safe_series(result, "TeamName", "").astype(str)
    result["actual_finish_position"] = _to_numeric(_safe_series(result, "Position"))
    # Race-day GridPosition can include penalties decided after qualifying.
    # This training table represents a post-Q forecast, not the final grid.
    result['grid_position'] = np.nan
    result["actual_points"] = _to_numeric(_safe_series(result, "Points"))
    result['outcome_class'] = _safe_series(result, 'Status', '').map(classify_result_status)
    result["actual_dnf"] = _safe_series(result, "Status", "").map(retirement_label)

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
            "outcome_class",
        ]
    ].copy()

    quali = build_qualifying_features(_normalise_event_keys(laps), qualifying_results)
    if not quali.empty:
        features = features.merge(
            quali,
            on=["Year", "Event", "Round", "DriverCode"],
            how="left",
            validate='one_to_one',
        )

    weather_features = _build_weather_features(weather)
    if not weather_features.empty:
        features = features.merge(weather_features, on=["Year", "Event", "Round"], how="left")

    race_control_features = _build_race_control_features(race_control)
    if not race_control_features.empty:
        features = features.merge(race_control_features, on=["Year", "Event", "Round"], how="left")

    features['grid_position'] = features.get('q_rank', np.nan)
    features['grid_vs_quali_delta'] = 0.0
    if enriched:
        from src.prediction_data import practice_features, prior_reliability, KEYS
        messages = _read_csv(root/'fastf1_race_control_messages.csv')
        practice = practice_features(laps, messages, weather)
        if not practice.empty:
            features = features.merge(practice, on=KEYS + ['DriverCode'], how='left', validate='one_to_one')
        cutoffs = None
        if not messages.empty and {'Session', 'Time', 'Year', 'Round'}.issubset(messages):
            q = messages[messages.Session.eq('Q')].copy()
            q['_utc'] = pd.to_datetime(q.Time, utc=True, errors='coerce')
            cutoffs = q.groupby(['Year', 'Round'])._utc.max().to_dict()
        features = prior_reliability(features, results, _read_csv(root/'retirement_causes.csv'), cutoffs)
    return features


def _preprocessor(feature_table: pd.DataFrame) -> tuple[ColumnTransformer, list[str], list[str]]:
    from src.prediction_data import PRACTICE_FEATURES, RELIABILITY_FEATURES
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
            *PRACTICE_FEATURES,
            *RELIABILITY_FEATURES,
        ]
        if column in feature_table.columns and feature_table[column].notna().any()
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
    events = feature_table[['Year', 'Round']].drop_duplicates().sort_values(['Year', 'Round'])
    if len(events) < 3:
        raise ValueError('At least three distinct races are required for chronological validation.')
    years = sorted(events['Year'].unique())
    if len(years) >= 2:
        validation_keys = events[events.Year.eq(years[-1])]
    else:
        validation_keys = events.iloc[max(1, int(len(events) * 0.75)):]
    validation_index = pd.MultiIndex.from_frame(validation_keys)
    is_validation = pd.MultiIndex.from_frame(feature_table[['Year', 'Round']]).isin(validation_index)
    train = feature_table.loc[~is_validation].copy()
    validation = feature_table.loc[is_validation].copy()
    if train.empty or validation.empty:
        raise ValueError('Chronological training and validation sets must both be nonempty.')
    return train, validation


def train_historical_models(
    historical_dir: str | Path = "data/historical_model",
    model_dir: str | Path = "data/models",
    *, finish_target: str = 'grid_residual', enriched: bool = False,
) -> HistoricalModelArtifacts:
    if finish_target not in {'absolute', 'grid_residual'}:
        raise ValueError('Choose absolute or grid_residual finish target.')
    output_dir = Path(model_dir)
    if any((output_dir / name).exists() for name in ['historical_feature_table.csv',
            'historical_finish_model.joblib', 'historical_dnf_model.joblib',
            'historical_model_metrics.json', 'validation_predictions.csv']):
        raise FileExistsError('Preserve existing model artifacts; choose a new candidate directory.')
    output_dir.mkdir(parents=True, exist_ok=True)

    feature_table = build_historical_feature_table(historical_dir, enriched=enriched)
    if feature_table.empty:
        raise ValueError("No historical feature rows found.")

    original_rows = len(feature_table)
    excluded_outcomes = feature_table.outcome_class.isin(['did_not_start', 'disqualified'])
    excluded_outcome_count = int(excluded_outcomes.sum())
    feature_table = feature_table.loc[~excluded_outcomes].copy()
    if 'q_rank' not in feature_table or feature_table.q_rank.isna().all():
        raise ValueError('Download official qualifying classifications alongside race classifications before training.')
    # Do not train a smaller, selected field when an archive lacks Q entrants.
    complete_q = feature_table.groupby(['Year', 'Round']).q_rank.transform(lambda ranks: ranks.notna().all())
    feature_table = feature_table.loc[complete_q].copy()
    feature_table = feature_table.replace([np.inf, -np.inf], np.nan).dropna(
        subset=['actual_finish_position', 'q_rank']).copy()
    if feature_table.duplicated(['Year', 'Round', 'DriverCode']).any():
        raise ValueError('Duplicate driver/race outcomes found in historical data.')
    train, validation = _split_train_validation(feature_table)
    # Validation availability must not decide which predictors are selected.
    preprocessor, numeric_columns, categorical_columns = _preprocessor(train)
    feature_columns = numeric_columns + categorical_columns

    finish_model = Pipeline(
        steps=[
            ("preprocess", clone(preprocessor)),
            ("model", Ridge(alpha=2.0)),
        ]
    )
    if finish_target == 'grid_residual':
        finish_model = GridResidualRegressor(finish_model)
    finish_model.fit(train[feature_columns], train["actual_finish_position"])

    dnf_train = train.loc[train.actual_dnf.notna()]
    if dnf_train.empty:
        raise ValueError('No known retirement labels in the training partition.')
    if dnf_train["actual_dnf"].nunique() >= 2:
        dnf_estimator: Any = LogisticRegression(max_iter=1000)
    else:
        dnf_estimator = DummyClassifier(strategy="prior")

    dnf_model = Pipeline(
        steps=[
            ("preprocess", clone(preprocessor)),
            ("model", dnf_estimator),
        ]
    )
    dnf_model.fit(dnf_train[feature_columns], dnf_train["actual_dnf"].astype(int))

    finish_prediction = finish_model.predict(validation[feature_columns])
    classes = list(dnf_model.classes_)
    probabilities = dnf_model.predict_proba(validation[feature_columns])
    dnf_probability = probabilities[:, classes.index(1)] if 1 in classes else np.zeros(len(validation))
    known_dnf = validation.actual_dnf.notna()
    actual_dnf = validation.loc[known_dnf, 'actual_dnf'].astype(int)
    prior_dnf = float(dnf_train.actual_dnf.mean())
    validation_ranks = validation[['Year', 'Round', 'DriverCode']].copy()
    validation_ranks['score'] = finish_prediction
    validation_ranks['rank'] = 0
    for _, part in validation_ranks.groupby(['Year', 'Round']):
        validation_ranks.loc[part.index, 'rank'] = coherent_finish_order(part.score, part.DriverCode)

    metrics = {
        'training_source_sha256': {name: hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest()
                                  for name in ['historical_model.py', 'qualifying_features.py', 'result_status.py']
                                  + (['prediction_data.py'] if enriched else [])},
        'excluded_rows_without_qualifying_or_finish': original_rows - excluded_outcome_count - len(feature_table),
        'excluded_dns_or_disqualified_rows': excluded_outcome_count,
        'dnf_train_known_rows': len(dnf_train),
        'dnf_train_unknown_rows': int(train.actual_dnf.isna().sum()),
        'dnf_validation_known_rows': int(known_dnf.sum()),
        'dnf_validation_unknown_rows': int((~known_dnf).sum()),
        'status_policy_version': STATUS_POLICY_VERSION,
        'qualifying_feature_contract': QUALIFYING_CONTRACT,
        'finish_target': finish_target,
        'feature_set': 'practice_reliability_v1' if enriched else 'qualifying_v1',
        'feature_coverage': {column: {'train': int(train[column].notna().sum()),
                                    'validation': int(validation[column].notna().sum())}
                             for column in feature_columns},
        'activated': False,
        'promotion_eligible': False,
        'promotion_note': 'Candidate only; requires independent simulation validation before activation.',
        "rows": int(len(feature_table)),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "validation_years": sorted(_to_numeric(validation["Year"]).dropna().astype(int).unique().tolist()),
        "feature_columns": feature_columns,
        'feature_cutoff': 'post_qualifying; race weather/control and final race grid excluded',
        'validation_policy': 'whole races, chronological, disjoint',
        "finish_mae": float(mean_absolute_error(validation["actual_finish_position"], finish_prediction)),
        "finish_rmse": float(mean_squared_error(validation["actual_finish_position"], finish_prediction) ** 0.5),
        "dnf_brier": float(brier_score_loss(actual_dnf, dnf_probability[known_dnf])) if known_dnf.any() else None,
        'finish_order_mae': float(mean_absolute_error(validation.actual_finish_position, validation_ranks['rank'])),
        'qualifying_baseline_mae': float(mean_absolute_error(validation.actual_finish_position, validation.q_rank)),
        'dnf_prior_baseline_brier': float(brier_score_loss(actual_dnf, np.full(len(actual_dnf), prior_dnf))) if known_dnf.any() else None,
        'dnf_training_rate': prior_dnf,
        'train_races': train[['Year', 'Round', 'Event']].drop_duplicates().to_dict('records'),
        'validation_races': validation[['Year', 'Round', 'Event']].drop_duplicates().to_dict('records'),
        'model_fit_policy': 'Models fitted on training races only; validation outcomes are never fitted.',
    }

    if actual_dnf.nunique() >= 2:
        metrics["dnf_log_loss"] = float(log_loss(actual_dnf, dnf_probability[known_dnf]))

    feature_path = output_dir / "historical_feature_table.csv"
    finish_model_path = output_dir / "historical_finish_model.joblib"
    dnf_model_path = output_dir / "historical_dnf_model.joblib"
    metrics_path = output_dir / "historical_model_metrics.json"

    feature_table.to_csv(feature_path, index=False)
    joblib.dump(finish_model, finish_model_path)
    joblib.dump(dnf_model, dnf_model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    predictions = validation[['Year', 'Round', 'Event', 'DriverCode', 'actual_finish_position', 'actual_dnf', 'q_rank']].copy()
    predictions['predicted_finish'] = finish_prediction
    predictions['predicted_finish_order'] = validation_ranks['rank']
    predictions['predicted_dnf_probability'] = dnf_probability
    predictions.to_csv(output_dir/'validation_predictions.csv', index=False)

    return HistoricalModelArtifacts(
        feature_table=str(feature_path),
        finish_model=str(finish_model_path),
        dnf_model=str(dnf_model_path),
        metrics=str(metrics_path),
    )
