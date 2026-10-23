import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from src import race_weather as weather
from src.race_weather_shadow import simulate_weather_windows
from src.app_services import beta, discord_reports

START = '2026-10-11T12:00:00Z'
NOW = '2026-10-05T10:00:00Z'


def payload(*, ensemble=False):
    times = pd.date_range('2026-10-11T10:00:00Z', '2026-10-11T16:00:00Z', freq='h')
    hourly = {'time': [t.strftime('%Y-%m-%dT%H:%M') for t in times]}
    for suffix in ('', '_member01') if ensemble else ('',):
        hourly.update({'precipitation' + suffix: [0, 0, 4, 0, 0, 0, 0] if not suffix else [0] * 7,
                       'temperature_2m' + suffix: [28] * 7,
                       'relative_humidity_2m' + suffix: [75] * 7,
                       'wind_speed_10m' + suffix: [2] * 7})
    if not ensemble:
        hourly.update(precipitation_probability=[50] * 7, wind_gusts_10m=[3] * 7, visibility=[10000] * 7)
    return {'hourly': hourly, 'utc_offset_seconds': 0,
            'hourly_units': {'precipitation': 'mm', 'wind_speed_10m': 'm/s'}}


def responses():
    calls = []

    def get(url, params, timeout):
        calls.append((url, params, timeout))
        class Response:
            def raise_for_status(self):
                pass
            def json(self):
                return payload(ensemble=url == weather.ENSEMBLE_URL)
        return Response()
    return get, calls


def test_race_target_utc_and_previous_hour_rain_not_qualifying_weather():
    get, calls = responses()
    report, raw = weather.collect_race_weather('2026-10-11T20:00:00+08:00', 1.29, 103.86, now=NOW, get=get)
    assert report['race_start_utc'] == '2026-10-11T12:00:00+00:00'
    assert all(c[1]['timezone'] == 'GMT' and c[1]['start_hour'] == '2026-10-11T10:00' for c in calls)
    assert calls[1][1]['models'] == 'ecmwf_ifs025'
    scheduled = report['scenarios'][0]
    # The 4 mm labelled 12:00 fell in 11:00-12:00, before the race.
    assert scheduled['wet_hour_frequency'] == 0
    assert scheduled['members'][0]['pre_start_rain_mm'] == 4
    assert scheduled['members'][0]['rain_mm'] == 0
    assert report['delay_probability'] is None
    assert all(s['delay_probability'] is None for s in report['scenarios'])
    assert report['raw_sha256'] == weather.payload_hash(raw)
    assert report['applied_to_live_predictions'] is False


def test_delayed_window_changes_weather_and_preserves_member_dependence():
    rain = payload(ensemble=True)
    # One member stays wet for the two-hour scheduled window, one stays dry.
    rain['hourly']['precipitation'] = [0, 0, 0, 2, 2, 0, 0]
    scenarios = weather.analyse_windows({'ensemble': {'payload': rain}}, START)
    assert scenarios[0]['wet_hour_frequency'] == .5  # Not 1-(1-.5)^2 = .75.
    assert scenarios[0]['rain_mm_p50'] == 2
    assert scenarios[1]['members'][0]['rain_mm'] == 3  # Half-hour prorating.
    assert scenarios[3]['wet_hour_frequency'] == 0
    assert scenarios[3]['start_utc'] == '2026-10-11T14:00:00+00:00'


def test_incomplete_member_withholds_probability_rather_than_biasing_to_dry():
    rain = payload(ensemble=True)
    rain['hourly']['precipitation_member01'][3] = None
    result = weather.analyse_windows({'ensemble': {'payload': rain}}, START)[0]
    assert result['complete_member_count'] == 1 and result['member_count'] == 2
    assert result['wet_hour_frequency'] is None
    assert result['rain_mm_p50'] is None


def test_short_forecast_horizon_does_not_select_nearest_unrelated_day():
    rain = payload(ensemble=True)
    rain['hourly']['time'] = [t.replace('2026-10-11', '2026-10-06') for t in rain['hourly']['time']]
    result = weather.analyse_windows({'ensemble': {'payload': rain}}, START)
    assert all(s['wet_hour_frequency'] is None for s in result)


@pytest.mark.parametrize('date,lat,lon,status', [
    ('2026-11-01T12:00:00Z', 1., 100., 'outside_forecast_horizon'),
    ('2026-10-04T12:00:00Z', 1., 100., 'past_or_incomplete_future_window'),
    (START, None, None, 'coordinates_unavailable'),
    (START, 100, 100., 'coordinates_unavailable'),
])
def test_unavailable_is_explicit_without_network(date, lat, lon, status):
    report, raw = weather.collect_race_weather(date, lat, lon, now=NOW, get=lambda *a, **k: pytest.fail('Network'))
    assert report['status'] == status and raw == {}
    assert report['delay_probability'] is None


def test_http_failure_leaves_unknown_weather_and_no_dry_assumption():
    def fail(*args, **kwargs):
        raise requests.Timeout('remote detail')
    report, _ = weather.collect_race_weather(START, 1., 100., now=NOW, get=fail)
    assert report['status'] == 'unavailable'
    assert all(s['wet_hour_frequency'] is None for s in report['scenarios'])
    assert 'remote detail' not in json.dumps(report)


def test_non_utc_response_and_wrong_units_are_rejected():
    get, _ = responses()
    def wrong(url, params, timeout):
        response = get(url, params, timeout)
        original = response.json()
        original['utc_offset_seconds'] = 28800
        response.json = lambda: original
        return response
    result, _ = weather.collect_race_weather(START, 1., 100., now=NOW, get=wrong)
    assert result['status'] == 'unavailable'


def test_naive_race_start_rejected_instead_of_guessing_timezone():
    with pytest.raises(ValueError, match='timezone-aware'):
        weather.collect_race_weather('2026-10-11T12:00', 1., 100., now=NOW)


def test_shadow_delays_change_modifiers_without_assuming_probability(monkeypatch):
    rain = payload(ensemble=True)
    rain['hourly']['precipitation'] = [0, 0, 0, 2, 2, 0, 0]
    scenarios = weather.analyse_windows({'ensemble': {'payload': rain}}, START)
    calls = []
    def simulate(features, **kwargs):
        calls.append(kwargs)
        wet = kwargs['weather_modifiers']['chaos_factor'] > 1
        frame = pd.DataFrame({'Driver': ['A', 'B'], 'avg_finish': [1.5, 1.5],
                              'win_chance': [.6 if wet else .8, .4 if wet else .2],
                              'podium_chance': [1., 1.], 'points_chance': [1., 1.], 'dnf_chance': [.1, .1]})
        return frame, None, None
    monkeypatch.setattr('src.race_weather_shadow.simulate_races', simulate)
    features = pd.DataFrame({'Driver': ['A', 'B']})
    original = features.copy(deep=True)
    frame, metadata = simulate_weather_windows(features, {'scenarios': scenarios}, sims_per_member=10)
    assert frame.query('Driver == "A" and delay_minutes == 0').win_chance.iloc[0] == pytest.approx(.7)
    assert frame.query('Driver == "A" and delay_minutes == 120').win_chance.iloc[0] == pytest.approx(.8)
    assert metadata['delay_weights'] is None and 'no_blended' in metadata['delay_weight_source']
    assert len(calls) == 8
    assert [c['seed'] for c in calls[:2]] == [c['seed'] for c in calls[-2:]]
    pd.testing.assert_frame_equal(features, original)


@pytest.mark.parametrize('weights', [[1, 1, 0, 0], [-1, 1, 1, 0], [float('nan'), 0, 0, 1], [1, 0]])
def test_invalid_delay_weights_rejected(weights):
    with pytest.raises(ValueError, match='Delay weights'):
        simulate_weather_windows(pd.DataFrame(), {'scenarios': [{}] * 4}, delay_weights=weights)


def test_new_weather_files_are_frozen_verified_and_used_by_discord(tmp_path):
    get, _ = responses()
    report, raw = weather.collect_race_weather(START, 1.29, 103.86, now=NOW, get=get)
    beta.dump_new(tmp_path / 'race_weather.json', report)
    beta.dump_new(tmp_path / 'race_weather_raw.json', raw)
    pd.DataFrame({'Driver': ['A'], 'avg_finish': [1.]}).to_csv(tmp_path / 'simulation_summary.csv', index=False)
    context = {'year': 2026, 'event': 'Singapore Grand Prix', 'session': 'Q', 'race_start_utc': START}
    beta.freeze_snapshot(tmp_path, context, now=NOW)
    manifest = beta.verified_snapshot(tmp_path)
    assert {'race_weather.json', 'race_weather_raw.json'}.issubset(manifest['files'])
    message = discord_reports.forecast_message(tmp_path)
    values = {f['name']: f['value'] for f in message['embeds'][0]['fields']}
    assert 'Start +120 min' in values['Race weather and delayed starts']
    assert 'Start-delay probability unavailable' in values['Race weather and delayed starts']
    assert 'informational' in values['Data and assumptions']
    (tmp_path / 'frozen/race_weather_raw.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        beta.verified_snapshot(tmp_path)


def test_periodic_updates_refresh_hourly_near_race_and_preserve_archive(tmp_path, monkeypatch):
    from src.app_services import race_weather_updates as updates
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/track_profiles.csv').write_text('existing reference')
    monkeypatch.setattr(updates, 'load_track_profile', lambda *a, **k: {'latitude': 1., 'longitude': 100.})
    get, calls = responses()
    monkeypatch.setattr(updates, 'collect_race_weather', lambda *a, **kw: weather.collect_race_weather(*a, **kw, get=get))
    context = {'year': 2026, 'round': 17, 'event': 'Singapore Grand Prix', 'race_start_utc': START}
    first = updates.capture_weather_update(tmp_path, context, now='2026-10-10T12:00:00Z')
    original = {path: path.read_bytes() for path in Path(first['folder']).iterdir()}
    cached = updates.capture_weather_update(tmp_path, context, now='2026-10-10T12:30:00Z')
    second = updates.capture_weather_update(tmp_path, context, now='2026-10-10T13:00:00Z')
    assert cached['status'] == 'cached' and cached['folder'] == first['folder']
    assert second['folder'] != first['folder'] and len(calls) == 4
    assert all(path.read_bytes() == content for path, content in original.items())


def test_periodic_updates_use_six_hour_interval_further_out_and_recapture_corruption(tmp_path, monkeypatch):
    from src.app_services import race_weather_updates as updates
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/track_profiles.csv').write_text('existing reference')
    monkeypatch.setattr(updates, 'load_track_profile', lambda *a, **k: {'latitude': 1., 'longitude': 100.})
    get, calls = responses()
    monkeypatch.setattr(updates, 'collect_race_weather', lambda *a, **kw: weather.collect_race_weather(*a, **kw, get=get))
    context = {'year': 2026, 'round': 17, 'event': 'Singapore Grand Prix', 'race_start_utc': START}
    first = updates.capture_weather_update(tmp_path, context, now='2026-10-05T10:00:00Z')
    assert updates.capture_weather_update(tmp_path, context, now='2026-10-05T11:00:00Z')['status'] == 'cached'
    (Path(first['folder']) / 'race_weather_raw.json').write_text('corrupted')
    second = updates.capture_weather_update(tmp_path, context, now='2026-10-05T12:00:00Z')
    assert second['folder'] != first['folder'] and len(calls) == 4
