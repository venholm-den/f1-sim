from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.historical_model import (build_historical_feature_table, train_historical_models,
    _split_train_validation, GridResidualRegressor, coherent_finish_order)


def _write_fixture(root: Path) -> None:
    rows = []
    lap_rows = []
    weather_rows = []
    race_control_rows = []

    for year in [2024, 2025, 2026]:
        for round_number in [1, 2]:
            event = f"Event {round_number}"

            for index, driver in enumerate(["AAA", "BBB", "CCC", "DDD"], start=1):
                finish = index if year < 2026 else 5 - index
                rows.append(
                    {
                        "Year": year,
                        "Event": event,
                        "Round": round_number,
                        "Session": "R",
                        "Abbreviation": driver,
                        "TeamName": f"Team {driver}",
                        "Position": finish,
                        "GridPosition": index,
                        "Status": "Finished" if driver != "DDD" else "Gearbox",
                        "Points": max(0, 26 - finish),
                    }
                )
                rows.append({**rows[-1], 'Session': 'Q', 'Position': index, 'Status': '', 'Points': 0})
                lap_rows.append(
                    {
                        "Year": year,
                        "Event": event,
                        "Round": round_number,
                        "Session": "Q",
                        "Driver": driver,
                        "Team": f"Team {driver}",
                        "LapTimeSeconds": 80 + index,
                        "Sector1Seconds": 25 + index,
                        "Sector2Seconds": 30 + index,
                        "Sector3Seconds": 25 + index,
                        "SpeedST": 300 - index,
                        "CleanPushLap": True,
                    }
                )

            weather_rows.append(
                {
                    "Year": year,
                    "Event": event,
                    "Round": round_number,
                    "Session": "R",
                    "air_temp_avg": 20 + round_number,
                    "track_temp_avg": 35 + round_number,
                    "humidity_avg": 50,
                    "wind_speed_avg": 3,
                    "rainfall_flag": False,
                    "chaos_factor": 1.0,
                    "strategy_factor": 1.0,
                    "dnf_factor": 1.0,
                    "degradation_factor": 1.0,
                    "uncertainty_factor": 1.0,
                }
            )
            race_control_rows.append(
                {
                    "Year": year,
                    "Event": event,
                    "Round": round_number,
                    "Session": "R",
                    "safety_car_count": 0,
                    "virtual_safety_car_count": 0,
                    "red_flag_count": 0,
                    "yellow_flag_count": 1,
                    "track_status_disruption_score": 0.1,
                    "race_control_disruption_score": 0.1,
                }
            )

    pd.DataFrame(rows).to_csv(root / "fastf1_race_results.csv", index=False)
    pd.DataFrame(lap_rows).to_csv(root / "fastf1_laps.csv", index=False)
    pd.DataFrame(weather_rows).to_csv(root / "fastf1_weather_summary.csv", index=False)
    pd.DataFrame(race_control_rows).to_csv(root / "fastf1_race_control_summary.csv", index=False)


def test_build_historical_feature_table(tmp_path) -> None:
    _write_fixture(tmp_path)

    table = build_historical_feature_table(tmp_path)

    assert not table.empty
    assert {"q_rank", "q_gap_to_best", "actual_finish_position", "actual_dnf"}.issubset(table.columns)
    assert table["actual_dnf"].sum() > 0
    assert 'air_temp_avg' not in table
    assert 'safety_car_count' not in table
    assert table.grid_position.equals(table.q_rank)


def test_single_season_split_has_no_overlap_and_small_data_fails():
    frame = pd.DataFrame({'Year': [2024] * 8, 'Round': [1, 1, 2, 2, 3, 3, 4, 4]})
    train, validation = _split_train_validation(frame)
    assert train.Round.max() < validation.Round.min()
    assert not set(train.index) & set(validation.index)
    with pytest.raises(ValueError, match='three distinct'):
        _split_train_validation(frame[frame.Round.eq(1)])


def test_train_historical_models_writes_artifacts(tmp_path) -> None:
    historical_dir = tmp_path / "historical"
    model_dir = tmp_path / "models"
    historical_dir.mkdir()
    _write_fixture(historical_dir)

    artifacts = train_historical_models(historical_dir, model_dir)

    assert Path(artifacts.feature_table).exists()
    assert Path(artifacts.finish_model).exists()
    assert Path(artifacts.dnf_model).exists()
    metrics = json.loads(Path(artifacts.metrics).read_text(encoding="utf-8"))
    assert metrics["rows"] > 0
    assert "finish_mae" in metrics
    assert "dnf_brier" in metrics


def test_single_class_dnf_and_later_unknown_drivers_are_supported(tmp_path):
    import joblib
    _write_fixture(tmp_path)
    results = pd.read_csv(tmp_path/'fastf1_race_results.csv')
    results.loc[results.Year.lt(2026), 'Status'] = 'Finished'
    results.loc[results.Year.eq(2026), 'TeamName'] += ' New'
    results.to_csv(tmp_path/'fastf1_race_results.csv', index=False)
    laps = pd.read_csv(tmp_path/'fastf1_laps.csv')
    laps.loc[laps.Year.eq(2026), 'Team'] += ' New'
    laps.to_csv(tmp_path/'fastf1_laps.csv', index=False)
    artifacts = train_historical_models(tmp_path, tmp_path/'candidate')
    predictions = pd.read_csv(tmp_path/'candidate/validation_predictions.csv')
    assert predictions.predicted_dnf_probability.eq(0).all()
    assert set(joblib.load(artifacts.dnf_model).classes_) == {0}
    assert json.loads(Path(artifacts.metrics).read_text())['dnf_brier'] == .25


def test_lapped_dns_and_unknown_training_labels_are_handled_separately(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path/'fastf1_race_results.csv'
    results = pd.read_csv(path)
    results.loc[results.Abbreviation.eq('AAA'), 'Status'] = 'Lapped'
    results.loc[results.Abbreviation.eq('BBB'), 'Status'] = 'Did not start'
    results.loc[results.Abbreviation.eq('CCC'), 'Status'] = 'Mystery'
    results.to_csv(path, index=False)
    table = build_historical_feature_table(tmp_path)
    assert table.loc[table.DriverCode.eq('AAA'), 'actual_dnf'].eq(0).all()
    assert table.loc[table.DriverCode.isin(['BBB', 'CCC']), 'actual_dnf'].isna().all()
    artifacts = train_historical_models(tmp_path, tmp_path/'candidate')
    metrics = json.loads(Path(artifacts.metrics).read_text())
    assert metrics['excluded_dns_or_disqualified_rows'] == 6
    assert metrics['dnf_train_unknown_rows'] == 4
    assert metrics['dnf_validation_known_rows'] == 4
    assert metrics['dnf_validation_unknown_rows'] == 2
    predictions = pd.read_csv(tmp_path/'candidate/validation_predictions.csv')
    assert not predictions.DriverCode.eq('BBB').any()
    assert predictions.loc[predictions.DriverCode.eq('CCC'), 'actual_dnf'].isna().all()
    with pytest.raises(FileExistsError, match='Preserve'):
        train_historical_models(tmp_path, tmp_path/'candidate')


def test_residual_model_retains_grid_anchor_and_joint_order_is_unique():
    from sklearn.dummy import DummyRegressor
    x = pd.DataFrame({'q_rank': [1., 2., 3.]})
    model = GridResidualRegressor(DummyRegressor(strategy='mean')).fit(x, [1., 2., 3.])
    assert model.predict(x).tolist() == [1., 2., 3.]
    assert coherent_finish_order([2, 2, 1], ['B', 'A', 'C']).tolist() == [3, 2, 1]


def test_validation_unknown_labels_report_unavailable_dnf_score(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path/'fastf1_race_results.csv'
    results = pd.read_csv(path)
    results.loc[results.Year.eq(2026), 'Status'] = 'Mystery'
    results.to_csv(path, index=False)
    artifacts = train_historical_models(tmp_path, tmp_path/'candidate')
    metrics = json.loads(Path(artifacts.metrics).read_text())
    assert metrics['dnf_brier'] is None and metrics['dnf_prior_baseline_brier'] is None
