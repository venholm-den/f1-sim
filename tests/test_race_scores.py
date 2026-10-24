import numpy as np
import pandas as pd
import pytest

from src.race_scores import (head_to_head, head_to_head_brier, position_log_score, race_scores,
                             ranked_probability_score, threshold_rps)
from src.simulate import simulate_races


def test_certain_correct_forecast_scores_zero():
    probabilities = np.eye(3)
    assert ranked_probability_score(probabilities, [1, 2, 3]) == 0
    assert position_log_score(probabilities, [1, 2, 3]) == pytest.approx(0)


def test_rps_prefers_near_misses_to_far_misses():
    near = np.array([[0, 1, 0], [1, 0, 0], [0, 0, 1]], float)
    far = np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0]], float)
    actual = [1, 2, 3]
    assert ranked_probability_score(near, actual) < ranked_probability_score(far, actual)


def test_log_score_floor_caps_an_impossible_outcome():
    assert position_log_score(np.eye(2), [2, 1], floor=1e-3) == pytest.approx(-np.log(1e-3))


def test_head_to_head_counts_each_pair_once_and_teammates_separately():
    results = pd.DataFrame({'sim_id': [0, 0, 0, 1, 1, 1], 'Driver': list('ABCABC'),
                            'finish_position': [1, 2, 3, 2, 1, 3]})
    drivers, ahead = head_to_head(results, ['A', 'B', 'C'])
    assert ahead[0, 1] == 0.5 and ahead[0, 2] == 1.0 and ahead[2, 0] == 0.0
    scores = head_to_head_brier(ahead, [1, 2, 3], teams=['X', 'X', 'Y'])
    assert scores['pairs'] == 3 and scores['teammate_pairs'] == 1
    assert scores['teammate_brier'] == pytest.approx(0.25)
    assert scores['pair_brier'] == pytest.approx(0.25 / 3)


def test_threshold_rps_needs_a_complete_order():
    forecast = pd.DataFrame({'Driver': ['A', 'B'], 'win_chance': [1, 0], 'podium_chance': [1, 1],
                             'points_chance': [1, 1]})
    assert threshold_rps(forecast, pd.DataFrame({'Driver': ['A', 'B'], 'Position': [1, 2]})) == 0
    with pytest.raises(ValueError):
        threshold_rps(forecast, pd.DataFrame({'Driver': ['A', 'B'], 'Position': [1, 1]}))


def test_race_scores_from_a_simulation():
    features = pd.DataFrame({'Driver': [f'D{i}' for i in range(6)], 'Team': ['T0', 'T0', 'T1', 'T1', 'T2', 'T2'],
                             'grid_position': range(1, 7), 'race_pace_score': np.linspace(0, 1, 6),
                             'grid_source': 'actual_session_results'})
    summary, matrix, results = simulate_races(features, n_sims=400, seed=1)
    actual = pd.DataFrame({'Driver': features.Driver, 'Position': range(1, 7)})
    scores = race_scores(summary, matrix, results, actual)
    assert scores['pairs'] == 15 and scores['teammate_pairs'] == 3
    assert 0 <= scores['rps'] <= 1 and scores['log_score'] > 0
    assert 0 <= scores['pair_brier'] <= 1
