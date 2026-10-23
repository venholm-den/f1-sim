from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.agent_race import AgentSettings, run_agents
from src.neutralisation import fit_neutralisation, race_schedule, sample_schedules
from tests.test_agent_race import run


def labelled_session(labels=('1', '4', '1', '6', '7', '1')):
    return SimpleNamespace(weather_data=pd.DataFrame({'Rainfall': [False]}), laps=pd.DataFrame({'LapNumber': [1, 2],
        'LapStartTime': pd.to_timedelta([10, 510], unit='s'),
        'Time': pd.to_timedelta([510, 1010], unit='s')}),
        track_status=pd.DataFrame({'Time': pd.to_timedelta([0, 100, 200, 400, 450, 500][:len(labels)], unit='s'),
                                   'Status': list(labels)}))


def test_labels_collapse_vsc_ending_and_keep_known_green_races():
    events = race_schedule(labelled_session())
    assert [e['kind'] for e in events] == ['SC', 'VSC']
    assert events[1]['start_fraction'] == pytest.approx(.39)
    assert events[1]['end_fraction'] == pytest.approx(.49)
    assert race_schedule(labelled_session(('1',))) == []


def test_missing_coverage_and_red_flags_are_excluded_not_zero_event_races():
    missing = SimpleNamespace(laps=pd.DataFrame())
    history = [(dict(year=2025, round=r), {'R': s}) for r, s in enumerate(
        [labelled_session(), missing, labelled_session(('1', '5'))], 1)]
    model = fit_neutralisation(history, dict(year=2026, round=1))
    assert len(model['schedules']) == 1 and len(model['excluded']) == 2
    with pytest.raises(ValueError, match='No covered'):
        fit_neutralisation(history[1:], dict(year=2026, round=1))
    with pytest.raises(ValueError, match='strictly earlier'):
        fit_neutralisation(history, dict(year=2025, round=2))


def test_whole_schedule_sampling_reproducible_independent_per_race():
    history = [(dict(year=2025, round=r), {'R': labelled_session(labels)})
               for r, labels in [(1, ('1',)), (2, ('1', '4', '1'))]]
    model = fit_neutralisation(history, dict(year=2026, round=1))
    a = sample_schedules(model, (), np.full(100, 1000.), 42)
    b = sample_schedules(model, (), np.full(100, 1000.), 42)
    c = sample_schedules(model, (), np.full(100, 1000.), 43)
    for first, second in zip(a, b):
        np.testing.assert_array_equal(first, second)
    assert 0 < (a[2] > 0).sum() < 100
    assert not np.array_equal(a[2], c[2])


def test_sc_compresses_field_vsc_preserves_gap_and_only_sc_has_restart():
    states = {}
    for kind in ('SC', 'VSC'):
        states[kind] = run((90., 90.), laps=8, settings={'grid_spacing_seconds': 30., 'step_seconds': 1.,
            'passability': 0., 'neutralisation_events': ({'kind': kind, 'start_seconds': 30., 'end_seconds': 210.},)})
        state = states[kind]
        progress = state['trace'].query('clock_seconds <= 210').pivot(index='clock_seconds', columns='car', values='progress_laps')
        assert (progress.diff().dropna() >= 0).all().all()
        assert (progress[0] >= progress[1]).all()
        assert state['overtakes'].sum() == 0
        assert state['neutralised_seconds'][0] == 180.
    sc = states['SC']['trace'].query('clock_seconds == 210').progress_laps.to_numpy()
    vsc = states['VSC']['trace'].query('clock_seconds == 210').progress_laps.to_numpy()
    assert sc[0]-sc[1] < 5./90
    assert vsc[0]-vsc[1] == pytest.approx(30./90)
    assert states['SC']['sc_restarts'][0] == 1
    assert states['VSC']['sc_restarts'][0] == 0
    assert states['SC']['trace'].restart_active.any()
    assert not states['VSC']['trace'].restart_active.any()


@pytest.mark.parametrize('kind,fraction', [('SC', .6), ('VSC', .8)])
def test_neutralised_pit_discount_applied_once_preserves_stationary_time(kind, fraction):
    plan = dict(Driver='A', name='p', weight=1., pit_laps=[1], compounds=['MEDIUM', 'HARD'], pit_loss_seconds=22.)
    settings = AgentSettings(step_seconds=1., initial_fuel_kg=0., lap_noise_seconds=0.,
        neutralisation_events=({'kind': kind, 'start_seconds': 40., 'end_seconds': 250.},))
    state = run_agents([[90.]], [1], 6, [plan], np.array([[0]]), [[6]], settings=settings)
    assert state['pit_loss_seconds'][0, 0] == pytest.approx(2.5+(22.-2.5)*fraction)
    assert state['completed_pit_stops'][0, 0] == 1
    assert state['completed_laps'][0, 0] == 6 and not state['dnf'][0, 0]


def test_invalid_or_conflicting_neutralisation_settings_fail_closed():
    with pytest.raises(ValueError, match='ordered'):
        AgentSettings(neutralisation_events=({'kind': 'SC', 'start_seconds': 10., 'end_seconds': 5.},))
    with pytest.raises(ValueError, match='combined'):
        AgentSettings(neutralised_windows=((1., 3.),), neutralisation_events=({'kind': 'SC', 'start_seconds': 5., 'end_seconds': 8.},))
