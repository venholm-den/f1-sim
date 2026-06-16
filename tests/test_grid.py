from __future__ import annotations

import pandas as pd

from src.grid import build_grid_features


class FakeQualifyingSession:
    def __init__(self) -> None:
        self.results = pd.DataFrame(
            {
                "Abbreviation": ["RUS", "HAM", "ANT", "LEC"],
                "TeamName": ["Mercedes", "Ferrari", "Mercedes", "Ferrari"],
                "Position": [1, 2, 3, 10],
            }
        )


def test_grid_uses_actual_qualifying_results_when_available() -> None:
    model_features = pd.DataFrame(
        {
            "Driver": ["ANT", "HAM", "RUS", "LEC"],
            "Team": ["Mercedes", "Ferrari", "Mercedes", "Ferrari"],
            "quali_pace_score": [0.0, 0.3, 0.2, 0.5],
            "model_pace": [0.0, 0.3, 0.2, 0.5],
        }
    )

    current_features = pd.DataFrame(
        {
            "Driver": ["ANT", "HAM", "RUS", "LEC"],
            "true_pace": [80.0, 80.3, 80.2, 80.5],
            "clean_laps": [5, 5, 5, 5],
        }
    )

    output = build_grid_features(
        model_features=model_features,
        current_features=current_features,
        current_session_type="Q",
        current_session=FakeQualifyingSession(),
    )

    grid = output.set_index("Driver")["grid_position"].to_dict()
    source = output.set_index("Driver")["grid_source"].to_dict()

    assert grid["RUS"] == 1
    assert grid["HAM"] == 2
    assert grid["ANT"] == 3
    assert grid["LEC"] == 10
    assert set(source.values()) == {"actual_session_results"}


def test_fia_official_grid_overrides_qualifying_results() -> None:
    model_features = pd.DataFrame(
        {
            "Driver": ["ANT", "HAM", "RUS", "LEC"],
            "Team": ["Mercedes", "Ferrari", "Mercedes", "Ferrari"],
            "quali_pace_score": [0.0, 0.3, 0.2, 0.5],
            "model_pace": [0.0, 0.3, 0.2, 0.5],
        }
    )

    current_features = pd.DataFrame(
        {
            "Driver": ["ANT", "HAM", "RUS", "LEC"],
            "true_pace": [80.0, 80.3, 80.2, 80.5],
            "clean_laps": [5, 5, 5, 5],
        }
    )

    fia_context = {
        "official_grid": pd.DataFrame(
            {
                "Driver": ["LEC", "HAM", "ANT", "RUS"],
                "team": ["Ferrari", "Ferrari", "Mercedes", "Mercedes"],
                "fia_grid_position": [1, 2, 3, 4],
                "fia_grid_source": ["Official Starting Grid"] * 4,
                "document_url": ["https://example.test/grid.pdf"] * 4,
                "published_at": ["2026-01-01T12:00:00"] * 4,
            }
        ),
        "penalties": pd.DataFrame(
            {
                "driver": ["RUS"],
                "penalty_type": ["grid penalty"],
                "penalty_value": ["3 places"],
                "document_title": ["Stewards Decision"],
                "notes": ["Impeding"],
            }
        ),
    }

    output = build_grid_features(
        model_features=model_features,
        current_features=current_features,
        current_session_type="Q",
        current_session=FakeQualifyingSession(),
        fia_context=fia_context,
    )

    rows = output.set_index("Driver")

    assert rows.loc["LEC", "grid_position"] == 1
    assert rows.loc["RUS", "grid_position"] == 4
    assert rows.loc["RUS", "grid_source"] == "fia_official_grid"
    assert rows.loc["RUS", "fia_penalty_count"] == 1
    assert "3 places" in rows.loc["RUS", "fia_penalty_notes"]
