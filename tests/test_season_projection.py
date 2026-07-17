from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.season_projection import (
    build_season_projection_table,
    load_latest_snapshot_projection,
    make_season_projection_chart,
)


def test_build_season_projection_table_mixes_actuals_and_current_projection(tmp_path) -> None:
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2, 3],
            "EventName": ["Bahrain Grand Prix", "Saudi Arabian Grand Prix", "Australian Grand Prix"],
            "EventDateParsed": pd.to_datetime(["2026-03-08", "2026-03-15", "2026-03-22"]),
        }
    )
    current_projection = pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "avg_points": [18.0, 15.0],
        }
    )

    def actual_loader(year: int, round_number: int) -> pd.DataFrame:
        assert year == 2026
        assert round_number == 1
        return pd.DataFrame(
            {
                "Abbreviation": ["RUS", "HAM"],
                "TeamName": ["Mercedes", "Ferrari"],
                "Points": [25.0, 18.0],
            }
        )

    table = build_season_projection_table(
        schedule=schedule,
        current_projection=current_projection,
        year=2026,
        target_round=2,
        history_dir=tmp_path,
        now=datetime(2026, 3, 20),
        actual_results_loader=actual_loader,
        projection_loader=lambda round_number, history_dir: pd.DataFrame(),
    )

    rus = table[table["Driver"].eq("RUS")].sort_values("round")

    assert rus["status"].tolist() == ["actual", "projected", "projected"]
    assert rus["race_points"].tolist() == [25.0, 18.0, 18.0]
    assert rus["cumulative_points"].tolist() == [25.0, 43.0, 61.0]


def test_projection_table_uses_future_snapshot_when_available(tmp_path) -> None:
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2],
            "EventName": ["Bahrain Grand Prix", "Saudi Arabian Grand Prix"],
            "EventDateParsed": pd.to_datetime(["2026-03-08", "2026-03-15"]),
        }
    )
    current_projection = pd.DataFrame({"Driver": ["RUS"], "Team": ["Mercedes"], "avg_points": [18.0]})
    snapshot_projection = pd.DataFrame(
        {
            "Driver": ["RUS"],
            "Team": ["Mercedes"],
            "projected_points": [22.0],
            "projection_source": ["snapshot:round_2.csv"],
        }
    )

    table = build_season_projection_table(
        schedule=schedule,
        current_projection=current_projection,
        year=2026,
        target_round=1,
        history_dir=tmp_path,
        now=datetime(2026, 3, 7),
        actual_results_loader=lambda year, round_number: pd.DataFrame(),
        projection_loader=lambda round_number, history_dir: snapshot_projection if round_number == 2 else pd.DataFrame(),
    )

    round_two = table[table["round"].eq(2)].iloc[0]
    assert round_two["race_points"] == 22.0
    assert round_two["projection_source"] == "snapshot:round_2.csv"


def test_load_latest_snapshot_projection_reads_newest_matching_round(tmp_path) -> None:
    old_path = Path(tmp_path, "2026_R02_old_prediction_snapshot.csv")
    new_path = Path(tmp_path, "2026_R02_new_prediction_snapshot.csv")

    pd.DataFrame(
        {
            "round": [2],
            "Driver": ["RUS"],
            "Team": ["Mercedes"],
            "avg_points": [10.0],
        }
    ).to_csv(old_path, index=False)
    pd.DataFrame(
        {
            "round": [2],
            "Driver": ["RUS"],
            "Team": ["Mercedes"],
            "avg_points": [21.0],
        }
    ).to_csv(new_path, index=False)

    old_path.touch()
    new_path.touch()

    projection = load_latest_snapshot_projection(2, tmp_path)

    assert projection.iloc[0]["projected_points"] == 21.0
    assert str(projection.iloc[0]["projection_source"]).startswith("snapshot:2026_R02_new")


def test_make_season_projection_chart_creates_png(tmp_path) -> None:
    projection = pd.DataFrame(
        {
            "year": [2026, 2026, 2026, 2026],
            "round": [1, 2, 1, 2],
            "event": ["A", "B", "A", "B"],
            "status": ["actual", "projected", "actual", "projected"],
            "Driver": ["RUS", "RUS", "HAM", "HAM"],
            "Team": ["Mercedes", "Mercedes", "Ferrari", "Ferrari"],
            "race_points": [25.0, 18.0, 18.0, 15.0],
            "cumulative_points": [25.0, 43.0, 18.0, 33.0],
            "projection_source": ["fastf1", "current_run", "fastf1", "current_run"],
        }
    )

    path = make_season_projection_chart(projection, tmp_path / "season.png", "Season Test")

    assert path.endswith("season.png")
    assert (tmp_path / "season.png").exists()
