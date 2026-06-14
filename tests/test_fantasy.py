from __future__ import annotations

import pandas as pd

from src.fantasy import add_simulated_fantasy_points


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
    assert row["fastest_lap_points"] == 5.0
    assert row["dotd_points"] == 10.0
    assert row["dnf_penalty_points"] == 0.0
    assert row["fantasy_points"] == 50.0


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
    assert row["dnf_penalty_points"] == -10.0
    assert row["fantasy_points"] == -10.0