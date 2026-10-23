"""Opt-in candidates: shared team noise, grid sampling, grid penalties, sprints."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.fantasy import add_simulated_fantasy_points, calculate_fantasy_summary
from src.grid_penalties import (apply_announced_penalties, penalised_grid,
                                penalty_columns, sample_grids)
from src.run_config import config_to_dict, load_app_config
from src.shared_noise import apply_team_noise
from src.simulate import simulate_races
from src.sprint import add_sprints, simulate_sprints, sprint_laps


def _features(grid_source='actual_session_results') -> pd.DataFrame:
    drivers = ['RUS', 'HAM', 'ANT', 'LEC', 'NOR', 'PIA']
    return pd.DataFrame({
        'Driver': drivers,
        'Team': ['Mercedes', 'Ferrari', 'Mercedes', 'Ferrari', 'McLaren', 'McLaren'],
        'grid_position': [1, 2, 3, 4, 5, 6],
        'grid_source': [grid_source] * 6,
        'grid_confidence': [1.0 if grid_source != 'estimated_model_grid' else 0.38] * 6,
        'race_pace_score': [0.0, 0.2, 0.1, 0.3, 0.25, 0.35],
        'long_run_pace_score': [0.0, 0.2, 0.1, 0.3, 0.25, 0.35],
        'tyre_deg_score': [0.01] * 6,
        'strategy_score': [0.15] * 6,
        'reliability_score': [0.04] * 6,
        'performance_uncertainty': [1.5] * 6,
        'estimated_race_laps': [56] * 6,
        'base_winner_race_time_seconds': [5400.0] * 6,
    })


def _teammate_correlation(results, a='LEC', b='HAM'):
    times = results.pivot(index='sim_id', columns='Driver', values='projected_race_time_seconds')
    return np.corrcoef(times[a], times[b])[0, 1]


def test_team_noise_is_shared_within_a_team_only() -> None:
    times = np.zeros((4000, 4))
    adjusted, offsets = apply_team_noise(times, ['A', 'B', 'A', 'C'], seed=1)
    assert (offsets[:, 0] == offsets[:, 2]).all()
    assert abs(np.corrcoef(offsets[:, 0], offsets[:, 1])[0, 1]) < 0.05
    assert offsets[:, 0].std() == pytest.approx(3.0, rel=0.05)
    assert (adjusted == offsets).all()
    with pytest.raises(ValueError):
        apply_team_noise(times, ['A', 'B'], seed=1)


def test_team_noise_candidate_correlates_teammates_and_leaves_default_alone() -> None:
    default = simulate_races(_features(), n_sims=3000, seed=4)
    shared = simulate_races(_features(), n_sims=3000, seed=4, team_noise_seconds=3.0)
    assert 'shared_noise_model' not in default[2]
    assert abs(_teammate_correlation(default[2])) < 0.06
    assert _teammate_correlation(shared[2]) > 0.12
    # Default output is independent of the new stream.
    again = simulate_races(_features(), n_sims=3000, seed=4)
    pd.testing.assert_frame_equal(default[0], again[0])


def test_penalised_grid_drops_and_back_of_grid() -> None:
    ranks = penalised_grid([1, 2, 3, 4, 5], places=[3, 0, 0, 0, 0], back=[False, True, False, False, False])
    # P1 drops three places behind P4; P2 goes to the back.
    assert list(ranks) == [3, 5, 1, 2, 4]
    matrix = penalised_grid(np.array([[1, 2, 3], [3, 2, 1]]), np.zeros((2, 3)), np.array([[True, False, False]] * 2))
    assert matrix.tolist() == [[3, 1, 2], [3, 2, 1]]


def test_announced_penalties_skip_official_grid_and_keep_qualifying_order() -> None:
    penalties = pd.DataFrame({'driver': ['RUS', 'LEC', 'NOR'], 'penalty_type': ['grid_drop', 'back_of_grid', 'grid_drop'],
                              'penalty_value': ['5', '', '3'], 'target_session': ['R', 'R', 'S'],
                              'status': ['verified_decision'] * 3})
    columns = penalty_columns(penalties, ['RUS', 'LEC', 'NOR']).set_index('Driver')
    assert columns.loc['RUS', 'grid_penalty_places'] == 5 and columns.loc['LEC', 'grid_penalty_back']
    assert columns.loc['NOR', 'grid_penalty_places'] == 0  # Sprint penalty does not move the race grid.

    applied = apply_announced_penalties(_features(), penalties).set_index('Driver')
    assert applied.loc['RUS', 'grid_position'] == 5 and applied.loc['RUS', 'qualifying_position'] == 1
    assert applied.loc['LEC', 'grid_position'] == 6 and applied.loc['HAM', 'grid_position'] == 1
    official = apply_announced_penalties(_features('fia_official_grid'), penalties).set_index('Driver')
    assert official.loc['RUS', 'grid_position'] == 1
    assert (official.grid_penalty_model == 'not_applied_official_grid').all()


def test_penalised_pole_sitter_keeps_qualifying_fantasy_points() -> None:
    penalties = pd.DataFrame({'driver': ['RUS'], 'penalty_type': ['back_of_grid'], 'penalty_value': ['']})
    features = apply_announced_penalties(_features(), penalties)
    summary, _, results = simulate_races(features, n_sims=200, seed=3)
    rus = add_simulated_fantasy_points(results).query("Driver == 'RUS'")
    assert (rus.grid_position == 6).all() and (rus.quali_fantasy_points == 10).all()


def test_grid_sampling_only_for_estimated_grids() -> None:
    qualifying, grid = sample_grids(np.arange(1, 7), np.zeros(6), np.zeros(6, dtype=bool), 2000, seed=8)
    assert (np.sort(grid, axis=1) == np.arange(1, 7)).all() and (grid == qualifying).all()
    assert (qualifying[:, 0] == 1).mean() < 0.9

    actual = simulate_races(_features(), n_sims=500, seed=2, sample_estimated_grid=True)
    assert actual[2].groupby('Driver').grid_position.nunique().max() == 1
    assert 'grid_sampling_model' not in actual[2]

    estimated = simulate_races(_features('estimated_model_grid'), n_sims=2000, seed=2, sample_estimated_grid=True)
    raw = estimated[2]
    assert raw.groupby('Driver').grid_position.nunique().min() > 1
    fantasy = add_simulated_fantasy_points(raw).query("Driver == 'RUS'")
    assert fantasy.quali_fantasy_points.nunique() > 1
    default = simulate_races(_features('estimated_model_grid'), n_sims=2000, seed=2)
    assert add_simulated_fantasy_points(default[2]).query("Driver == 'RUS'").quali_fantasy_points.nunique() == 1


def test_sprint_simulation_and_fantasy_points() -> None:
    assert sprint_laps(56) == 19 and sprint_laps(71) == 24
    sprints = simulate_sprints(_features(), n_sims=1500, seed=5)
    assert len(sprints) == 1500 * 6 and sprints.sprint_points.max() == 8
    assert (sprints.groupby('sim_id').sprint_position.apply(sorted).map(tuple) == tuple(range(1, 7))).all()
    assert (sprints.loc[sprints.sprint_dnf, 'sprint_points'] == 0).all()
    assert sprints.query("Driver == 'RUS'").sprint_points.mean() > sprints.query("Driver == 'PIA'").sprint_points.mean()

    race = simulate_races(_features(), n_sims=1500, seed=5)
    without, _ = calculate_fantasy_summary(race[2], race[0], prices_path='missing.csv')
    combined = add_sprints(race[2], sprints)
    with_sprint, raw = calculate_fantasy_summary(combined, race[0], prices_path='missing.csv')
    assert 'avg_sprint_fantasy_points' not in without
    merged = with_sprint.set_index('Driver')
    gap = merged.avg_fantasy_points - without.set_index('Driver').avg_fantasy_points
    assert gap.round(6).equals(merged.avg_sprint_fantasy_points.round(6))
    assert merged.loc['RUS', 'avg_sprint_fantasy_points'] > 0
    assert 'sprint_fantasy_points' in raw


def test_candidate_config_roundtrip_and_validation(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv('POST_TO_DISCORD', raising=False)
    config = config_to_dict(load_app_config())
    keys = {'shared_noise_model': 'team_noise_v1', 'grid_sampling_model': 'estimated_grid_v1',
            'grid_penalty_model': 'announced_v1', 'sprint_model': 'sprint_v1'}
    assert all(config['model'][key] == 'off' for key in keys)
    config['ignore_environment_overrides'] = True
    config['outputs']['post_to_discord'] = False
    config['model'].update(keys)
    path = tmp_path / 'candidates.json'
    path.write_text(json.dumps(config))
    loaded = load_app_config(str(path)).model
    assert all(getattr(loaded, key) == value for key, value in keys.items())

    for update, message in [({'outputs': {'post_to_discord': True}}, 'local output'),
                            ({'model': {'sprint_model': 'always'}}, 'sprint_model'),
                            ({'model': {'race_engine': 'agent_laps_v1'}}, 'aggregate engine')]:
        changed = json.loads(json.dumps(config))
        for section, values in update.items():
            changed[section].update(values)
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match=message):
            load_app_config(str(path))
