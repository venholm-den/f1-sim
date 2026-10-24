import numpy as np
import pandas as pd
import pytest

from src.pace_uncertainty import (PaceUncertaintySettings, estimate_pace_error, sample_pace_offsets,
                                  simulate_uncertain_agent_races)
from src.shadow_settings import SHADOW_SETTINGS, shadow_overrides
from src.simulate import simulate_races
from tests.test_simulate import _minimal_features

OFF = {'team_pace_sd': 0., 'driver_pace_sd': 0., 'incident_probability': 0.}


def test_zero_spreads_reproduce_the_agent_engine_draw_for_draw():
    features = _minimal_features()
    expected, _, _ = simulate_races(features, n_sims=40, seed=9, agent_settings={})
    actual, _, raw = simulate_uncertain_agent_races(features, 40, 9, uncertainty=OFF)
    columns = ['avg_finish', 'win_chance', 'podium_chance', 'points_chance', 'dnf_chance']
    pd.testing.assert_frame_equal(expected[['Driver', *columns]].reset_index(drop=True),
                                  actual[['Driver', *columns]].reset_index(drop=True))
    assert (raw.pace_uncertainty_model == 'pace_uncertainty_v1').all()
    assert (raw.incident_seconds == 0).all()


def test_team_offsets_are_shared_and_driver_offsets_scale_with_uncertainty():
    features = _minimal_features()
    team_only, _ = sample_pace_offsets(features, 4000, 1, PaceUncertaintySettings(
        team_pace_sd=.5, driver_pace_sd=0., incident_probability=0.))
    assert np.allclose(team_only[:, 0], team_only[:, 2])  # RUS and ANT share Mercedes
    assert np.allclose(team_only[:, 1], team_only[:, 3])
    assert team_only[:, 0].std() == pytest.approx(.5, rel=.05)
    driver_only, _ = sample_pace_offsets(features, 20000, 1, PaceUncertaintySettings(
        team_pace_sd=0., driver_pace_sd=.3, incident_probability=0.))
    relative = features.performance_uncertainty / features.performance_uncertainty.median()
    assert driver_only.std(axis=0) == pytest.approx(.3 * relative.to_numpy(), rel=.05)
    assert abs(np.corrcoef(driver_only[:, 0], driver_only[:, 2])[0, 1]) < .03


def test_incidents_are_rare_heavy_tailed_capped_and_skip_retirements():
    _, losses = sample_pace_offsets(_minimal_features(), 50000, 3, PaceUncertaintySettings(
        team_pace_sd=0., driver_pace_sd=0., incident_probability=.15, incident_median_seconds=6.,
        incident_cap_seconds=60.))
    hit = losses[losses > 0]
    assert (losses > 0).mean() == pytest.approx(.15, abs=.01)
    assert np.median(hit) == pytest.approx(6., rel=.08)
    assert hit.max() == 60.
    assert np.quantile(hit, .99) > 5 * np.median(hit)
    features = _minimal_features().assign(reliability_score=.4)
    _, _, raw = simulate_uncertain_agent_races(features, 200, 4, uncertainty={'incident_probability': .5})
    assert (raw.loc[raw.dnf, 'incident_seconds'] == 0).all()
    assert (raw.loc[~raw.dnf, 'incident_seconds'] > 0).any()


def test_pace_uncertainty_widens_outcomes_and_repeats_by_seed():
    features = _minimal_features()
    tight, matrix_a, _ = simulate_uncertain_agent_races(features, 300, 5, uncertainty=OFF)
    wide, matrix_b, _ = simulate_uncertain_agent_races(features, 300, 5, uncertainty={'team_pace_sd': .8})
    again, _, _ = simulate_uncertain_agent_races(features, 300, 5, uncertainty={'team_pace_sd': .8})
    pd.testing.assert_frame_equal(wide, again)
    favourite = tight.sort_values('win_chance').Driver.iloc[-1]
    assert wide.set_index('Driver').win_chance[favourite] < tight.set_index('Driver').win_chance[favourite]


def test_settings_reject_invalid_values():
    for bad in ({'team_pace_sd': -1}, {'incident_probability': .7}, {'driver_pace_sd': float('nan')},
                {'incident_median_seconds': 0.}):
        with pytest.raises(ValueError):
            PaceUncertaintySettings(**bad)


def _history(team_miss, driver_miss, rounds=8):
    rng = np.random.default_rng(0)
    teams = [f'T{i}' for i in range(10)]
    true = {team: rng.normal(0, 1) for team in teams}
    rows = []
    for round_ in range(1, rounds + 1):
        shift = {team: rng.normal(0, team_miss) for team in teams}
        for team in teams:
            for car in range(2):
                rows.append({'Driver': f'{team}{car}', 'Team': team, 'source_round': round_,
                             'relative_pace': 3 + true[team] + shift[team] + rng.normal(0, driver_miss)})
    return pd.DataFrame(rows)


def test_error_estimate_uses_earlier_races_only_and_leans_on_the_prior_early():
    history = _history(.6, .2, rounds=30)
    early = estimate_pace_error(history, before_round=4)
    assert early == {'team_pace_sd': .5, 'driver_pace_sd': .3, 'races_used': 0}
    late = estimate_pace_error(history, before_round=31, prior_races=0.)
    # Forecast misses on a 3-race mean carry the target's shift plus a third of the history's.
    expected_team = np.sqrt(.6 ** 2 * (1 + 1 / 3))
    expected_driver = np.sqrt(.2 ** 2 * (1 + 1 / 3))
    assert late['races_used'] == 27
    assert late['team_pace_sd'] == pytest.approx(expected_team, rel=.15)
    assert late['driver_pace_sd'] == pytest.approx(expected_driver, rel=.15)
    changed = history.copy()
    changed.loc[changed.source_round.eq(30), 'relative_pace'] += np.arange(20.) / 10
    assert estimate_pace_error(changed, before_round=30) == estimate_pace_error(history, before_round=30)


def test_tuned_shadow_settings_are_known_simulation_parameters_and_reach_the_engine():
    assert SHADOW_SETTINGS['multi_score_tuned_v1']['lane'] == 'accuracy'
    overrides = shadow_overrides('multi_score_tuned_v1')
    assert overrides == {'race_pace_seconds_multiplier': .52, 'grid_loss_multiplier': 11.}
    features = _minimal_features()
    live, _, _ = simulate_races(features, n_sims=200, seed=1)
    tuned, _, _ = simulate_races(features, n_sims=200, seed=1, parameter_overrides=overrides)
    assert not np.allclose(live.avg_finish, tuned.avg_finish)
    with pytest.raises(ValueError):
        shadow_overrides('missing')
