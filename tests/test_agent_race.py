from dataclasses import asdict, replace

import numpy as np
import pandas as pd
import pytest

from src.agent_race import AgentSettings, physical_ahead, run_agents
from src.simulate import simulate_races
from src.run_config import load_app_config, config_to_dict
from src.accuracy_candidates import candidate_simulation_options
from tests.test_simulate import _minimal_features


def run(paces=(90., 87.), laps=12, *, settings=None, limits=None, trace=True, n=1, seed=42):
    plans = [{'Driver': str(i), 'name': 'test', 'weight': 1., 'pit_laps': [laps - 1],
              'compounds': ['MEDIUM', 'HARD'], 'pit_loss_seconds': .001} for i in range(len(paces))]
    cfg = AgentSettings(lap_noise_seconds=0., initial_fuel_kg=0., thermal_penalty_seconds=0.,
                        thermal_wear_seconds_per_lap=0., dirty_air_slope=0.)
    if settings:
        cfg = replace(cfg, **settings)
    return run_agents(np.tile(paces, (n, 1)), np.arange(1, len(paces) + 1), laps, plans,
        np.tile(np.arange(len(paces)), (n, 1)), np.tile(limits or [laps] * len(paces), (n, 1)),
        settings=cfg, seed=seed, record_trace=trace)


def test_physical_neighbour_handles_lapped_cars_and_pit_exclusion():
    progress = np.array([[2.97, 1.98, 3.4]])
    ahead, gap = physical_ahead(progress, np.ones_like(progress, dtype=bool))
    assert ahead.tolist() == [[1, 2, 0]]
    assert gap[0, 0] == pytest.approx(.01)
    ahead, gap = physical_ahead(progress, np.array([[True, False, True]]))
    assert ahead[0, 0] == 2
    _, gap = physical_ahead(progress, np.array([[True, False, False]]))
    assert np.isinf(gap).all()


def test_faster_car_is_blocked_until_an_actual_pass_with_coherent_crossings():
    blocked = run(laps=20, settings={'passability': 0.})
    permitted = run(laps=20, settings={'passability': 1., 'pass_intercept': 50., 'following_laps': 0.})
    before_pits = blocked['trace'].query('completed_laps < 19').pivot(index='clock_seconds', columns='car', values='progress_laps').dropna()
    assert (before_pits[0] >= before_pits[1]).all()
    assert blocked['overtakes'].sum() == 0
    assert permitted['overtakes'][0, 1] >= 1
    assert permitted['elapsed_seconds'][0, 1] < permitted['elapsed_seconds'][0, 0]
    # An approved move never simply swaps labels: the passer covers the distance.
    trace = permitted['trace'].pivot(index='clock_seconds', columns='car', values='progress_laps')
    assert (trace.diff().dropna() >= 0).all().all()


def test_blue_flags_allow_lapping_with_no_racing_passes_and_finish_at_chequered():
    state = run((70., 120.), laps=12, settings={'passability': 0.})
    assert state['blue_flag_passes'][0, 0] > 0
    assert state['overtakes'].sum() == 0
    assert state['completed_laps'][0, 0] == 12
    assert 6 <= state['completed_laps'][0, 1] < 12
    assert not state['dnf'].any()
    assert state['elapsed_seconds'][0, 1] >= state['elapsed_seconds'][0, 0]
    # One yield per encounter; proximity does not charge a repeated lap penalty.
    assert state['blue_flag_passes'].sum() < 12


def test_retirement_is_independent_distance_and_stops_state_updates():
    state = run((90., 90.), limits=[3, 12], settings={'initial_fuel_kg': 70.})
    assert state['completed_laps'][0, 0] == 3 and state['dnf'][0, 0]
    assert state['completed_pit_stops'][0, 0] == 0
    assert state['fuel_kg'][0, 0] == pytest.approx(52.5)
    after = state['trace'].query('car == 0 and terminal')
    assert after.progress_laps.nunique() == 1
    assert after.fuel_kg.nunique() == 1
    zero = run(limits=[0, 12], trace=False)
    assert zero['elapsed_seconds'][0, 0] == 0


def test_neutralisation_disables_passes_and_aid_and_fuel_thermal_states_stay_bounded():
    state = run((90., 87.), settings={'neutralised_windows': [[0., 10000.]],
        'passability': 1., 'pass_intercept': 50., 'following_laps': 0.,
        'initial_fuel_kg': 70., 'overtaking_aid': 'electrical_proxy', 'season_year': 2026,
        'aid_lap_gain_seconds': 1.})
    assert state['overtakes'].sum() == state['blue_flag_passes'].sum() == 0
    assert (state['fuel_kg'] >= 0).all()
    trace = run(laps=30, settings={'initial_fuel_kg': 70., 'passability': 0.,
        'thermal_penalty_seconds': .2, 'thermal_wear_seconds_per_lap': .02})['trace']
    assert trace.thermal_heat.between(0, 1).all()
    assert trace.thermal_wear_seconds.between(0, 2).all()
    assert trace.fuel_kg.between(0, 70).all()
    assert trace.query('car == 1').thermal_heat.max() > .1


def test_shared_clock_step_convergence_and_seed_repeatability():
    coarse = run(trace=False, n=300, settings={'step_seconds': 2.})
    fine = run(trace=False, n=300, settings={'step_seconds': 1.})
    assert abs(coarse['elapsed_seconds'].mean() - fine['elapsed_seconds'].mean()) < .5
    repeat = run(trace=False, n=300, settings={'step_seconds': 2.})
    for key in ('elapsed_seconds', 'overtakes', 'blue_flag_passes', 'completed_laps'):
        np.testing.assert_array_equal(coarse[key], repeat[key])


def test_net_pit_delay_is_charged_once_and_used_tyres_reset_to_recorded_age():
    def scenario(loss):
        plan = {'Driver': 'A', 'name': 'used', 'weight': 1., 'pit_laps': [6],
            'compounds': ['MEDIUM', 'HARD'], 'pit_loss_seconds': loss, 'tyre_ages': [4, 2]}
        return run_agents(np.array([[90.]]), np.array([1]), 12, [plan], np.array([[0]]),
            np.array([[12]]), settings=AgentSettings(lap_noise_seconds=0., initial_fuel_kg=0.),
            record_trace=True)
    quick = scenario(.001)
    slow = scenario(22.)
    assert slow['completed_pit_stops'][0, 0] == 1
    assert slow['pit_loss_seconds'][0, 0] == 22.
    assert slow['elapsed_seconds'][0, 0] - quick['elapsed_seconds'][0, 0] == pytest.approx(21.999, abs=.03)
    trace = slow['trace']
    assert trace.tyre_age.iloc[0] == 4
    assert trace.query('completed_laps == 6').tyre_age.eq(2).all()
    assert trace.tyre_age.iloc[-1] == 8


def test_fuel_reference_can_represent_zero_fuel_or_mean_fuel_without_negative_mass():
    common = dict(trace=False, paces=(90.,), laps=12)
    mean_reference = run(**common, settings={'initial_fuel_kg': 70., 'fuel_reference_fraction': .5})
    zero_reference = run(**common, settings={'initial_fuel_kg': 70., 'fuel_reference_fraction': 0.})
    # Changing only the pace reference adds the half-load penalty on every lap.
    assert (zero_reference['elapsed_seconds'] - mean_reference['elapsed_seconds'])[0, 0] == pytest.approx(.035 * 35 * 12, abs=.1)
    assert zero_reference['fuel_kg'][0, 0] == mean_reference['fuel_kg'][0, 0] == 0.


@pytest.mark.parametrize('settings', [
    {'overtaking_aid': 'legacy_drs_proxy', 'season_year': 2026},
    {'overtaking_aid': 'electrical_proxy', 'season_year': 2025},
    {'overtaking_aid': 'electrical_proxy'}, {'passability': 1.5},
    {'step_seconds': 0}, {'initial_fuel_kg': float('nan')},
    {'aid_lap_gain_seconds': 1}, {'neutralised_windows': [[10, 5]]},
])
def test_invalid_or_wrong_era_assumptions_fail_closed(settings):
    with pytest.raises(ValueError):
        AgentSettings(**settings)


def test_candidate_integration_output_contract_roster_order_and_wet_rejection():
    features = _minimal_features()
    options = candidate_simulation_options('agent_laps_v1', features)
    outputs = simulate_races(features, n_sims=100, seed=7, **options)
    reordered = simulate_races(features.iloc[::-1], n_sims=100, seed=7, **options)
    for actual, repeated in zip(outputs, reordered):
        pd.testing.assert_frame_equal(actual, repeated)
    summary, matrix, raw = outputs
    assert matrix.filter(regex='^P').sum(axis=1).eq(1).all()
    assert summary.win_chance.sum() == pytest.approx(1)
    assert raw.groupby('sim_id').finish_position.nunique().eq(4).all()
    assert raw.loc[~raw.classified, 'points'].eq(0).all()
    assert raw.race_engine.eq('agent_laps_v1').all()
    assert raw.completed_pit_stops.le(raw.planned_pit_stops).all()
    with pytest.raises(ValueError, match='dry'):
        simulate_races(features, n_sims=1, **options, weather_modifiers={'rainfall_flag': True})
    with pytest.raises(ValueError, match='grid loss'):
        simulate_races(features, n_sims=1, **options, grid_loss_multiplier=3.3)


def test_agent_configuration_is_roundtrippable_and_local_only(tmp_path, monkeypatch):
    import json
    monkeypatch.delenv('POST_TO_DISCORD', raising=False)
    config = config_to_dict(load_app_config())
    config['ignore_environment_overrides'] = True
    config['outputs']['post_to_discord'] = False
    config['model'].update(race_engine='agent_laps_v1', agent_settings=asdict(AgentSettings()))
    path = tmp_path/'agent.json'
    path.write_text(json.dumps(config))
    loaded = load_app_config(str(path))
    assert loaded.model.race_engine == 'agent_laps_v1'
    assert loaded.model.agent_settings['initial_fuel_kg'] == 70.
    config['outputs']['post_to_discord'] = True
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='local output'):
        load_app_config(str(path))
