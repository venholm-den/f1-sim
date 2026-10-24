from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.fantasy import (
    add_constructor_fantasy_points,
    add_simulated_fantasy_points,
    check_scoring_against_archive,
)


def test_fantasy_points_include_finish_quali_position_and_bonuses() -> None:
    results = pd.DataFrame(
        {
            "sim_id": [0],
            "Driver": ["ANT"],
            "Team": ["Mercedes"],
            "grid_position": [3],
            "finish_position": [1],
            "points": [25.0],
            "positions_gained": [2.0],
            "fastest_lap": [True],
            "dotd": [True],
            "dnf": [False],
        }
    )

    scored = add_simulated_fantasy_points(results)

    row = scored.iloc[0]

    assert row["finish_fantasy_points"] == 25.0
    assert row["quali_fantasy_points"] == 8.0
    assert row["position_change_points"] == 2.0
    # No pass count in the run: base 3.44 + 0.36 per place gained.
    assert row["overtake_points"] == pytest.approx(4.16)
    assert row["fastest_lap_points"] == 10.0
    assert row["dotd_points"] == 10.0
    assert row["dnf_penalty_points"] == 0.0
    assert row["fantasy_points"] == pytest.approx(59.16)


def test_dnf_does_not_double_punish_position_loss() -> None:
    results = pd.DataFrame(
        {
            "sim_id": [0],
            "Driver": ["LIN"],
            "Team": ["Racing Bulls"],
            "grid_position": [11],
            "finish_position": [22],
            "points": [0.0],
            "positions_gained": [-11.0],
            "fastest_lap": [False],
            "dotd": [False],
            "dnf": [True],
        }
    )

    scored = add_simulated_fantasy_points(results)

    row = scored.iloc[0]

    assert row["position_change_points"] == 0.0
    assert row["dnf_penalty_points"] == -20.0
    assert row["overtake_points"] == 1.5
    assert row["fantasy_points"] == -18.5

def test_position_change_is_uncapped_and_losses_cost_a_point_each() -> None:
    results = pd.DataFrame({
        "Driver": ["A", "B"], "Team": ["T", "T"],
        "grid_position": [20, 2], "finish_position": [4, 18],
        "overtakes": [16, 0], "dnf": [False, False],
    })

    scored = add_simulated_fantasy_points(results).set_index("Driver")

    assert scored.at["A", "position_change_points"] == 16.0
    assert scored.at["B", "position_change_points"] == -16.0
    assert scored.at["A", "overtake_points"] == 16.0
    assert not scored.at["A", "overtakes_estimated"]


def test_classified_late_retirement_scores_its_place() -> None:
    results = pd.DataFrame({
        "Driver": ["A"], "Team": ["T"], "grid_position": [5], "finish_position": [9],
        "overtakes": [0], "dnf": [True], "classified": [True],
    })

    row = add_simulated_fantasy_points(results).iloc[0]

    assert row["finish_fantasy_points"] == 2.0
    assert row["position_change_points"] == -4.0
    assert row["dnf_penalty_points"] == 0.0


def test_constructor_scores_drivers_without_dotd_plus_teamwork_and_pit_stop() -> None:
    results = pd.DataFrame({
        "sim_id": [0, 0], "Driver": ["A", "B"], "Team": ["T", "T"],
        "qualifying_position": [3, 14], "grid_position": [3, 14],
        "finish_position": [1, 12], "overtakes": [0, 2], "dotd": [True, False],
        "dnf": [False, False],
    })

    scored = add_simulated_fantasy_points(results)
    team = add_constructor_fantasy_points(scored, pit_stop_points={"T": 5.0}).iloc[0]

    drivers = scored["fantasy_points"].sum() - 10.0
    assert team["teamwork_points"] == 5.0  # one car in Q3
    assert team["constructor_fantasy_points"] == pytest.approx(drivers + 5.0 + 5.0)


def test_scoring_matches_archived_2026_points_exactly() -> None:
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "fantasy_tools_2026_sample.json").read_text())

    report = check_scoring_against_archive(payload, 2026)

    assert report["mismatches"] == []
    assert report["matched"]["total"] == report["drivers"] == 44
    assert report["matched"]["sprint"] == 22
    assert report["matched"]["constructor_total"] == 22
