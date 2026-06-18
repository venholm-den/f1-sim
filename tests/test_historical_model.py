from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.historical_model import build_historical_feature_table, train_historical_models


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
