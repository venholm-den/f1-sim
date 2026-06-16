from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.actual_strategy import (
    build_strategy_comparison,
    build_strategy_metrics,
    extract_actual_strategy_from_session,
    parse_strategy_sequence,
    strategy_overlap_score,
)


def test_parse_strategy_sequence_handles_project_formats() -> None:
    assert parse_strategy_sequence("Medium(new) → Hard(new) → Soft(used/unknown)") == [
        "MEDIUM",
        "HARD",
        "SOFT",
    ]
    assert parse_strategy_sequence("Mn Hn Sn") == ["MEDIUM", "HARD", "SOFT"]
    assert parse_strategy_sequence("SOFT-HARD-MEDIUM-HARD") == ["SOFT", "HARD", "MEDIUM", "HARD"]


def test_extract_actual_strategy_from_session_groups_by_stint() -> None:
    laps = pd.DataFrame(
        [
            {"Driver": "RUS", "Team": "Mercedes", "LapNumber": 1, "Stint": 1, "Compound": "MEDIUM"},
            {"Driver": "RUS", "Team": "Mercedes", "LapNumber": 2, "Stint": 1, "Compound": "MEDIUM"},
            {"Driver": "RUS", "Team": "Mercedes", "LapNumber": 3, "Stint": 2, "Compound": "HARD"},
            {"Driver": "RUS", "Team": "Mercedes", "LapNumber": 4, "Stint": 2, "Compound": "HARD"},
            {"Driver": "HAM", "Team": "Ferrari", "LapNumber": 1, "Stint": 1, "Compound": "SOFT"},
            {"Driver": "HAM", "Team": "Ferrari", "LapNumber": 2, "Stint": 2, "Compound": "HARD"},
            {"Driver": "HAM", "Team": "Ferrari", "LapNumber": 3, "Stint": 3, "Compound": "MEDIUM"},
            {"Driver": "HAM", "Team": "Ferrari", "LapNumber": 4, "Stint": 4, "Compound": "HARD"},
        ]
    )
    session = SimpleNamespace(laps=laps)

    actual = extract_actual_strategy_from_session(session, metadata={"year": 2026, "event": "Barcelona Grand Prix"})

    rus = actual.loc[actual["Driver"] == "RUS"].iloc[0]
    ham = actual.loc[actual["Driver"] == "HAM"].iloc[0]

    assert rus["actual_strategy"] == "MEDIUM-HARD"
    assert rus["actual_stops"] == 1
    assert ham["actual_strategy"] == "SOFT-HARD-MEDIUM-HARD"
    assert ham["actual_stops"] == 3
    assert rus["actual_strategy_source"] == "fastf1_race_lap_stint_data"


def test_build_strategy_comparison_and_metrics() -> None:
    predictions = pd.DataFrame(
        [
            {"Driver": "RUS", "Team": "Mercedes", "PredictedStrategy": "Medium(new) → Hard(new)"},
            {"Driver": "HAM", "Team": "Ferrari", "PredictedStrategy": "Medium(new) → Hard(new)"},
        ]
    )
    actual = pd.DataFrame(
        [
            {
                "Driver": "RUS",
                "Team": "Mercedes",
                "actual_strategy": "MEDIUM-HARD",
                "actual_stops": 1,
                "actual_stint_count": 2,
                "actual_first_compound": "MEDIUM",
                "actual_completed_likely": True,
                "actual_had_wet_compound": False,
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            },
            {
                "Driver": "HAM",
                "Team": "Ferrari",
                "actual_strategy": "SOFT-HARD-MEDIUM",
                "actual_stops": 2,
                "actual_stint_count": 3,
                "actual_first_compound": "SOFT",
                "actual_completed_likely": True,
                "actual_had_wet_compound": False,
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            },
        ]
    )

    comparison = build_strategy_comparison(predictions, actual)
    metrics = build_strategy_metrics(comparison, year=2026, event="Barcelona Grand Prix")

    assert comparison.loc[comparison["Driver"] == "RUS", "exact_strategy_match"].iloc[0]
    assert comparison.loc[comparison["Driver"] == "RUS", "stops_match"].iloc[0]
    assert strategy_overlap_score("MEDIUM-HARD", "MEDIUM-HARD") == 1.0
    assert metrics.iloc[0]["drivers_compared"] == 2
    assert metrics.iloc[0]["stop_count_accuracy"] == 0.5
