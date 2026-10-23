import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.accuracy_benchmark import ReplayRace
from src.model_config import SIMULATION_PARAMETERS
from src.multi_score_tuning import (TUNABLE_BOUNDS, brier_decomposition, expected_calibration_error,
    live_parameters, promotion_decision, score_predictions, season_blocks, tune_multi_score)
from src.simulate import simulate_races
from tests.test_long_run_pace import practice_laps
from tests.test_simulate import _minimal_features as _features


def seasons(years=(2022, 2023, 2024), rounds=4):
    output = []
    for year in years:
        for round_number in range(1, rounds + 1):
            sessions = {}
            for code in ['FP2', 'Q', 'R']:
                results = pd.DataFrame({'Abbreviation': ['A', 'B'], 'TeamName': ['A', 'B'],
                    'Position': [1, 2] if round_number % 2 else [2, 1],
                    'Status': ['Finished', 'Finished']})
                sessions[code] = SimpleNamespace(laps=practice_laps(), results=results,
                    weather_data=pd.DataFrame(), track_status=pd.DataFrame())
            output.append(ReplayRace(year, round_number, 'Example GP', sessions))
    return output


def test_calibration_error_and_decomposition():
    assert expected_calibration_error([0.25, 0.25, 0.25, 0.25], [1, 0, 0, 0]) == 0
    assert expected_calibration_error([0.95, 0.95], [0, 0]) == pytest.approx(0.95)
    parts = brier_decomposition(np.array([0.1, 0.1, 0.9, 0.9]), np.array([0, 0, 1, 1]))
    assert parts['brier'] == pytest.approx(0.01)
    assert parts['brier'] == pytest.approx(parts['reliability'] - parts['resolution'] + parts['uncertainty'])


def test_objective_rewards_rank_and_penalises_overconfidence():
    actual = pd.DataFrame({'year': 2024, 'round': 1, 'session': 'Q', 'actual_position': [1, 2, 3, 4]})
    good = actual.assign(avg_finish=[1, 2, 3, 4], win_chance=[.7, .2, .1, 0],
                         podium_chance=[1, .9, .8, .3], points_chance=1.0)
    reversed_order = good.assign(avg_finish=[4, 3, 2, 1], win_chance=[0, .1, .2, .7])
    assert score_predictions(good)['spearman'] == pytest.approx(1)
    assert score_predictions(good)['objective'] > score_predictions(reversed_order)['objective']


def test_overrides_default_to_live_engine_and_change_only_this_call():
    before = dict(SIMULATION_PARAMETERS)
    plain, _, _ = simulate_races(_features(), n_sims=300, seed=5)
    same, _, _ = simulate_races(_features(), n_sims=300, seed=5, parameter_overrides=live_parameters())
    pd.testing.assert_frame_equal(plain, same)
    noisy, _, _ = simulate_races(_features(), n_sims=300, seed=5,
                                 parameter_overrides={'race_noise_multiplier': 20.0})
    assert not noisy.avg_finish.equals(plain.avg_finish)
    assert SIMULATION_PARAMETERS == before
    with pytest.raises(ValueError, match='Unknown'):
        simulate_races(_features(), n_sims=100, parameter_overrides={'not_a_setting': 1})
    with pytest.raises(ValueError, match='once'):
        simulate_races(_features(), n_sims=100, grid_loss_multiplier=2,
                       parameter_overrides={'grid_loss_multiplier': 3})


def test_bounds_contain_live_defaults():
    for name, (low, high) in TUNABLE_BOUNDS.items():
        assert low <= SIMULATION_PARAMETERS[name] <= high


def test_season_blocks_are_chronological_and_protect_2026():
    races = seasons()
    splits = season_blocks(races, [2022, 2023], [2024])
    assert {split for key, split in splits.items() if key[0] == 2024} == {'holdout'}
    with pytest.raises(ValueError, match='precede'):
        season_blocks(races, [2024], [2023])
    with pytest.raises(ValueError, match='reserved'):
        season_blocks(races, [2024], [2026])


def test_promotion_requires_gain_and_no_regression():
    live = dict(objective=.5, brier=.1, ece=.05, spearman=.6)
    better = dict(objective=.56, brier=.09, ece=.04, spearman=.62)
    assert promotion_decision(live, better, 8) == (True, [])
    passed, reasons = promotion_decision(live, dict(better, ece=.06), 8)
    assert not passed and 'held-out ece regressed' in reasons
    assert not promotion_decision(live, better, 3)[0]


def test_tuning_selects_on_fit_seasons_and_never_changes_defaults(tmp_path):
    before = dict(SIMULATION_PARAMETERS)
    bounds = {'grid_loss_multiplier': (0.0, 15.0), 'race_noise_multiplier': (1.0, 8.0)}
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'holdout_races': [[2024, 1]]}))
    report = tune_multi_score(seasons(), tmp_path / 'out', fit_years=[2022, 2023], holdout_years=[2024],
                              bounds=bounds, tune_sims=100, eval_sims=100, seeds=[1, 2], maxiter=1,
                              popsize=3, inspected_reports=[prior])
    assert SIMULATION_PARAMETERS == before and not report['live_defaults_changed']
    assert set(report['tuned_parameters']) == set(bounds)
    assert all(key[0] < 2024 for key in report['fit_races'])
    assert report['previously_inspected_holdout_races'] == [[2024, 1]]
    assert report['unseen_holdout_race_count'] == 3
    assert not report['promotion_gate_passed']
    assert set(report['identifiability']) == set(bounds)
    history = pd.read_csv(tmp_path / 'out/optimizer_history.csv')
    assert history.iloc[0][list(bounds)].to_dict() == pytest.approx(live_parameters(bounds))
    predictions = pd.read_csv(tmp_path / 'out/predictions.csv')
    assert set(predictions.variant) == {'live', 'tuned'}
    # Seeds are averaged per driver, so each driver appears once per variant.
    assert not predictions.duplicated(['variant', 'year', 'round', 'session', 'Driver']).any()
    with pytest.raises(FileExistsError):
        tune_multi_score(seasons(), tmp_path / 'out', fit_years=[2022], holdout_years=[2024], bounds=bounds)
