import json
from types import SimpleNamespace

import pandas as pd
import pytest

from portable_app import web_backend as api
from src.app_services.dashboard_health import output_context, saved_data_health


@pytest.fixture
def outputs(tmp_path):
    laps = tmp_path / 'lap_details'
    laps.mkdir()
    pd.DataFrame({'Year': [2026, 2026], 'Event': ['Example GP'] * 2,
                  'Session': ['FP3'] * 2, 'Driver': ['AAA', 'BBB'],
                  'CleanPushLap': [True, False]}).to_csv(laps / 'weekend_lap_details.csv', index=False)
    pd.DataFrame({'Driver': ['AAA', 'AAA'], 'red_flag_chance': [.35, .35],
                  'dnf_chance': [.05, .05], 'performance_uncertainty': [1.9, 1.9]}).to_csv(tmp_path / 'simulation_summary.csv', index=False)
    api.TRACK_LAYOUT_CACHE.clear()
    return tmp_path


def test_latest_resolves_from_saved_outputs(outputs):
    context = output_context(outputs, 2026, 'latest', 'FP3')
    assert context['event'] == 'Example GP'
    assert context['source'] == 'saved_lap_details'


def test_snapshot_context_is_authoritative_when_setup_changes(outputs):
    history = outputs / 'history'
    history.mkdir()
    pd.DataFrame({'year': [2026], 'event': ['Example GP'], 'session': ['FP3']}).to_csv(history / 'latest_prediction_snapshot.csv', index=False)
    context = output_context(outputs, 2026, 'Other GP', 'Q')
    health = saved_data_health(outputs, context, {'year': 2026, 'event': 'Other GP', 'session': 'Q'},
                              {'status': 'not_checked', 'message': 'not checked'})
    assert context['session'] == 'FP3'
    assert health['setup_mismatch']
    assert health['missing_model_drivers'] == ['BBB']
    assert health['duplicate_model_drivers'] == 1
    assert health['clean_laps'] == 1
    assert health['completion'] == 'not_recorded'


def test_telemetry_lookup_resolves_latest_and_failed_load_can_retry(outputs, monkeypatch):
    import fastf1
    from unittest.mock import Mock
    monkeypatch.setattr(fastf1.Cache, 'enable_cache', lambda _: None)
    telemetry = pd.DataFrame({'X': [0, 1, 2], 'Y': [0, 1, 0], 'Distance': [0, 10, 20]})
    session = SimpleNamespace(load=lambda **kwargs: None,
        laps=SimpleNamespace(pick_fastest=lambda: SimpleNamespace(
            get_telemetry=lambda: SimpleNamespace(add_distance=lambda: telemetry))),
        session_status=pd.DataFrame({'Status': ['Finished', 'Ends']}))
    get_session = Mock(side_effect=[RuntimeError('offline'), session])
    monkeypatch.setattr(fastf1, 'get_session', get_session)
    failed = api.track_layout_payload(outputs, 2026, 'latest', 'FP3')
    assert failed['status'] == 'load_failed'
    assert not api.TRACK_LAYOUT_CACHE
    loaded = api.track_layout_payload(outputs, 2026, 'latest', 'FP3')
    assert loaded['status'] == 'available' and len(loaded['points']) == 3
    assert loaded['completion'] == 'Ends'
    assert get_session.call_args.args == (2026, 'Example GP', 'FP3')


def test_missing_context_is_not_reported_as_unpublished_telemetry(tmp_path):
    result = api.track_layout_payload(tmp_path, 2026, 'latest', 'FP3')
    assert result['status'] == 'context_missing'


def test_weather_does_not_invent_rain_from_commentary(outputs):
    report = outputs / 'report'
    report.mkdir()
    (report / 'model_commentary.txt').write_text('No rain detected; wet conditions not expected.')
    weather = api.weather_summary(outputs)
    assert weather['rain'] is None
    assert weather['chaos'] == pytest.approx(35)
    assert weather['uncertainty'] == pytest.approx(1.9)
    assert weather['observed'] == {}


def test_saved_rain_forecast_uses_percentage_units_without_observation_claim(outputs):
    (outputs / 'weather_context.json').write_text(json.dumps({
        'weather_source': 'open_meteo_forecast', 'rain_probability': 60,
        'rainfall_flag': True, 'chaos_factor': 1.2}))
    weather = api.weather_summary(outputs)
    assert weather['rain'] == 60
    assert weather['observed'] == {}
    assert weather['modifiers']['chaos_factor'] == 1.2


def test_observed_weather_is_separate_from_simulated_red_flag(outputs):
    (outputs / 'weather_context.json').write_text(json.dumps({
        'weather_source': 'fastf1_session_weather', 'rain_probability': None,
        'rainfall_flag': False, 'air_temp_avg': 25, 'chaos_factor': 1.0}))
    weather = api.weather_summary(outputs)
    assert weather['rain'] is None and weather['chaos'] == pytest.approx(35)
    assert weather['observed']['air_temp_avg'] == 25


def test_empty_results_are_unknown_not_zero(tmp_path):
    weather = api.weather_summary(tmp_path)
    assert weather['rain'] is None and weather['chaos'] is None
