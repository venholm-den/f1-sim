from __future__ import annotations

import pandas as pd
import pytest

from src.simulate import simulate_races
from src.model_config import SIMULATION_PARAMETERS


def _minimal_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Driver": ["RUS", "HAM", "ANT", "LEC"],
            "Team": ["Mercedes", "Ferrari", "Mercedes", "Ferrari"],
            "grid_position": [1, 2, 3, 10],
            "grid_source": ["actual_session_results"] * 4,
            "grid_confidence": [1.0, 1.0, 1.0, 1.0],
            "quali_pace_score": [0.25, 0.33, 0.00, 0.45],
            "race_pace_score": [0.64, 0.54, 0.00, 0.59],
            "long_run_pace_score": [0.64, 0.54, 0.00, 0.59],
            "tyre_deg_score": [-0.02, -0.01, -0.03, -0.02],
            "strategy_score": [0.15, 0.15, 0.15, 0.15],
            "reliability_score": [0.04, 0.04, 0.04, 0.04],
            "performance_uncertainty": [1.8, 1.6, 1.4, 1.7],
            "estimated_race_laps": [66, 66, 66, 66],
            "base_winner_race_time_seconds": [5400.0, 5400.0, 5400.0, 5400.0],
        }
    )


def test_simulate_races_returns_expected_outputs() -> None:
    summary, position_matrix, results = simulate_races(
        features=_minimal_features(),
        n_sims=100,
        seed=123,
        overtaking_difficulty=0.72,
        weather_modifiers={
            "chaos_factor": 1.0,
            "strategy_factor": 1.0,
            "dnf_factor": 1.0,
            "degradation_factor": 1.0,
            "uncertainty_factor": 1.0,
            "rainfall_flag": False,
            "wind_speed_avg": 2.0,
        },
    )

    assert len(summary) == 4
    assert len(position_matrix) == 4
    assert len(results) == 400

    required_result_cols = {
        "sim_id",
        "Driver",
        "Team",
        "grid_position",
        "finish_position",
        "points",
        "projected_race_time_seconds",
        "classified_race_time_seconds",
        "dnf",
        "positions_gained",
        "fastest_lap",
        "dotd",
    }

    assert required_result_cols.issubset(results.columns)

    for _, group in results.groupby("sim_id"):
        assert sorted(group["finish_position"].tolist()) == [1, 2, 3, 4]


def test_simulation_summary_contains_probability_columns() -> None:
    summary, _, _ = simulate_races(
        features=_minimal_features(),
        n_sims=50,
        seed=456,
        overtaking_difficulty=0.72,
        weather_modifiers=None,
    )

    required_summary_cols = {
        "Driver",
        "Team",
        "avg_finish",
        "win_chance",
        "podium_chance",
        "points_chance",
        "avg_points",
        "race_pace_score",
        "performance_uncertainty",
    }

    assert required_summary_cols.issubset(summary.columns)
    assert summary["win_chance"].between(0, 1).all()
    assert summary["podium_chance"].between(0, 1).all()
    assert summary["points_chance"].between(0, 1).all()


def test_grid_override_is_scoped_and_default_output_is_unchanged():
    before = dict(SIMULATION_PARAMETERS)
    implicit = simulate_races(_minimal_features(), n_sims=100, seed=42)
    explicit = simulate_races(_minimal_features(), n_sims=100, seed=42,
                              grid_loss_multiplier=before['grid_loss_multiplier'])
    for first, second in zip(implicit, explicit):
        pd.testing.assert_frame_equal(first, second)
    stronger = simulate_races(_minimal_features(), n_sims=100, seed=42,
                              grid_loss_multiplier=13.2)
    assert not implicit[0]['avg_finish'].equals(stronger[0]['avg_finish'])
    assert stronger[0]['grid_loss_multiplier'].eq(13.2).all()
    assert SIMULATION_PARAMETERS == before
    after = simulate_races(_minimal_features(), n_sims=100, seed=42)
    for first, second in zip(implicit, after):
        pd.testing.assert_frame_equal(first, second)


@pytest.mark.parametrize('weight', [-1, 51, float('nan'), float('inf')])
def test_invalid_grid_override_is_rejected(weight):
    with pytest.raises(ValueError, match='grid_loss_multiplier'):
        simulate_races(_minimal_features(), n_sims=10, grid_loss_multiplier=weight)


def test_top10_and_scoring_probabilities_have_distinct_targets():
    features = pd.DataFrame({'Driver':['A','B'], 'Team':['T','U'],
        'grid_position':[1,2], 'reliability_score':[.3,.3]})
    summary, _, results = simulate_races(features, n_sims=1000,
        weather_modifiers={'dnf_factor':1.5})
    for row in summary.itertuples():
        actual = results[results.Driver.eq(row.Driver)]
        assert row.top10_chance == row.points_chance == 1.0
        assert row.points_scoring_chance == actual.points.gt(0).mean()
        assert row.points_scoring_chance < row.top10_chance


def test_safety_car_candidate_is_off_by_default_and_reproducible() -> None:
    default = simulate_races(_minimal_features(), n_sims=300, seed=42)
    disabled = simulate_races(_minimal_features(), n_sims=300, seed=42,
                              safety_car_probability=None)
    pd.testing.assert_frame_equal(default[0], disabled[0])
    assert "safety_car" not in default[2]

    first = simulate_races(_minimal_features(), n_sims=300, seed=42,
                           safety_car_probability=0.5)
    second = simulate_races(_minimal_features(), n_sims=300, seed=42,
                            safety_car_probability=0.5)
    pd.testing.assert_frame_equal(first[0], second[0])
    assert 0.4 < first[0]["safety_car_chance"].iloc[0] < 0.6


def test_safety_car_never_deployed_leaves_engine_unchanged() -> None:
    default = simulate_races(_minimal_features(), n_sims=300, seed=7)
    never = simulate_races(_minimal_features(), n_sims=300, seed=7,
                           safety_car_probability=0.0)
    for column in ("finish_position", "projected_race_time_seconds", "dnf", "fastest_lap"):
        assert (default[2][column].to_numpy() == never[2][column].to_numpy()).all()


def test_safety_car_compresses_gaps_and_mixes_order() -> None:
    features = _minimal_features()
    no_sc = simulate_races(features, n_sims=3000, seed=11, safety_car_probability=0.0)
    always = simulate_races(features, n_sims=3000, seed=11, safety_car_probability=1.0)

    def spread(results):
        times = results.pivot(index="sim_id", columns="Driver",
                              values="projected_race_time_seconds")
        return (times.max(axis=1) - times.min(axis=1)).mean()

    assert spread(always[2]) < spread(no_sc[2])
    favourite_win = lambda summary: summary.set_index("Driver").loc["ANT", "win_chance"]
    assert favourite_win(always[0]) < favourite_win(no_sc[0])


def test_safety_car_rejects_invalid_probability_and_agent_engine() -> None:
    for probability in (-0.1, 1.5, float("nan")):
        with pytest.raises(ValueError):
            simulate_races(_minimal_features(), n_sims=10,
                           safety_car_probability=probability)
    with pytest.raises(ValueError, match="neutralisation"):
        simulate_races(_minimal_features(), n_sims=10, safety_car_probability=0.4,
                       agent_settings={})


def test_multi_safety_car_candidate_keeps_default_draws_and_reports_counts() -> None:
    default = simulate_races(_minimal_features(), n_sims=2000, seed=42)
    multi = simulate_races(_minimal_features(), n_sims=2000, seed=42,
                           multi_safety_car_probability=0.5)
    again = simulate_races(_minimal_features(), n_sims=2000, seed=42,
                           multi_safety_car_probability=0.5)
    pd.testing.assert_frame_equal(multi[0], again[0])
    assert (default[2]["dnf"].to_numpy() == multi[2]["dnf"].to_numpy()).all()
    assert 0.45 < multi[0]["safety_car_chance"].iloc[0] < 0.55
    assert 0.35 < multi[0]["vsc_chance"].iloc[0] < 0.45
    assert multi[2]["safety_car_model"].eq("multi_sc_v1").all()
    assert multi[2]["safety_car_count"].max() <= 3
    with pytest.raises(ValueError, match="one safety-car"):
        simulate_races(_minimal_features(), n_sims=10, safety_car_probability=0.4,
                       multi_safety_car_probability=0.4)
    with pytest.raises(ValueError, match="neutralisation"):
        simulate_races(_minimal_features(), n_sims=10, multi_safety_car_probability=0.4,
                       agent_settings={})


def test_driver_of_the_day_mostly_goes_to_the_winner_and_never_to_a_retiree() -> None:
    _, _, results = simulate_races(features=_minimal_features(), n_sims=2000, seed=7,
                                   overtaking_difficulty=0.72, weather_modifiers=None)
    assert results.groupby("sim_id").dotd.sum().eq(1).mean() > 0.99
    assert not (results.dotd & results.dnf).any()
    votes = results[results.dotd]
    # With four cars everyone is in the top five, so the winner's share sits
    # well above a quarter but below certainty.
    assert 0.45 < votes.finish_position.eq(1).mean() < 0.85
