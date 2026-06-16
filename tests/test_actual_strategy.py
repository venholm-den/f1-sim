from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.actual_strategy import (
    compare_predicted_to_actual_strategy,
    extract_actual_tyre_strategy_from_session,
    parse_strategy_sequence,
)


def test_parse_strategy_sequence_handles_model_labels() -> None:
    assert parse_strategy_sequence("Medium(new) → Hard(new) → Medium(new)") == [
        "MEDIUM",
        "HARD",
        "MEDIUM",
    ]
    assert parse_strategy_sequence("Sn Mn Hn") == ["SOFT", "MEDIUM", "HARD"]


def test_extract_actual_tyre_strategy_from_session_groups_stints() -> None:
    laps = pd.DataFrame(
        [
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 1, "Stint": 1, "Compound": "MEDIUM"},
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 2, "Stint": 1, "Compound": "MEDIUM"},
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 3, "Stint": 2, "Compound": "HARD"},
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 4, "Stint": 2, "Compound": "HARD"},
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 5, "Stint": 3, "Compound": "SOFT"},
            {"Driver": "AAA", "Team": "Team A", "LapNumber": 6, "Stint": 3, "Compound": "SOFT"},
        ]
    )

    session = SimpleNamespace(laps=laps)
    actual = extract_actual_tyre_strategy_from_session(session, metadata={"year": 2026, "event": "Test GP"})

    assert len(actual) == 1
    row = actual.iloc[0]
    assert row["Driver"] == "AAA"
    assert row["actual_strategy_sequence"] == "MEDIUM-HARD-SOFT"
    assert row["actual_stops"] == 2
    assert row["actual_strategy_source"] == "fastf1_race_lap_stint_data"


def test_compare_predicted_to_actual_strategy_scores_matches() -> None:
    predicted = pd.DataFrame(
        [
            {"Driver": "AAA", "PredictedStrategy": "Medium(new) → Hard(new) → Soft(new)"},
            {"Driver": "BBB", "PredictedStrategy": "Medium(new) → Hard(new)"},
        ]
    )
    actual = pd.DataFrame(
        [
            {
                "Driver": "AAA",
                "actual_strategy": "Medium → Hard → Soft",
                "actual_stops": 2,
                "actual_first_compound": "MEDIUM",
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            },
            {
                "Driver": "BBB",
                "actual_strategy": "Hard → Medium → Soft",
                "actual_stops": 2,
                "actual_first_compound": "HARD",
                "actual_strategy_source": "fastf1_race_lap_stint_data",
            },
        ]
    )

    comparison = compare_predicted_to_actual_strategy(predicted, actual)

    assert comparison.loc[comparison["Driver"] == "AAA", "exact_strategy_match"].iloc[0]
    assert not bool(comparison.loc[comparison["Driver"] == "BBB", "stop_count_match"].iloc[0])
