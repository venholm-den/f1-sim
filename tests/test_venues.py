import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.venues import event_display, resolve_venue, venue_for_context
from src.track import load_track_profile
from src.performance import _estimate_race_laps
from src import strategy_history as history
from src.app_services import beta, discord_reports


@pytest.mark.parametrize('year,event,location,circuit,laps', [
    (2026, 'Bahrain Grand Prix', 'Kuala Lumpur', 'sepang', 56),
    (2025, 'Bahrain Grand Prix', 'Sakhir', 'bahrain', 57),
    (2026, 'Spanish Grand Prix', 'Madrid', 'madring', 57),
    (2025, 'Spanish Grand Prix', 'Barcelona', 'catalunya', 66),
    (2026, 'Barcelona Grand Prix', 'Barcelona', 'catalunya', 66),
    (2026, 'Miami Grand Prix', 'Miami Gardens', 'miami', 57),
])
def test_season_identity_distance_and_physical_weather_location(year, event, location, circuit, laps):
    venue = resolve_venue(year, event, location=location)
    assert venue['venue_status'] == 'resolved' and venue['circuit_id'] == circuit
    assert venue['race_laps'] == laps
    assert _estimate_race_laps({'year': year, 'event': event, 'venue': venue}) == laps
    if circuit == 'sepang':
        assert venue['latitude'] == pytest.approx(2.76083)
        assert venue['venue_country'] == 'Malaysia'


def test_feed_conflict_withholds_weather_and_circuit_priors(tmp_path):
    venue = resolve_venue(2026, 'Bahrain Grand Prix', location='Sakhir')
    profile = load_track_profile('Bahrain Grand Prix', str(tmp_path/'unused.csv'),
                                 metadata={'venue': venue})
    assert venue['venue_status'] == 'conflict'
    assert profile['latitude'] is None and profile['longitude'] is None
    assert profile['profile_status'] == 'withheld_unresolved_venue'
    assert not (tmp_path/'unused.csv').exists()


def test_pre_fp1_keeps_calendar_location_for_conflict_detection(monkeypatch):
    from src import collect
    monkeypatch.setattr(collect, 'enable_fastf1_cache', lambda: None)
    monkeypatch.setattr(collect, '_normalise_schedule', lambda year: pd.DataFrame([
        {'EventName': 'Bahrain Grand Prix', 'RoundNumber': 16, 'Location': 'Sakhir'}]))
    session, metadata = collect.load_pre_fp1_session(2026, 'Bahrain Grand Prix')
    assert venue_for_context(metadata, session=session)['venue_status'] == 'conflict'


def test_weather_request_uses_resolved_venue_and_old_cache_cannot_hide_relocation(tmp_path, monkeypatch):
    from src.app_services import race_weather_updates as updates
    (tmp_path/'data').mkdir()
    (tmp_path/'data/track_profiles.csv').write_text('Event,OvertakingDifficulty\nBahrain Grand Prix,0.45\n')
    calls = []
    def collect(start, latitude, longitude, **kwargs):
        calls.append((latitude, longitude))
        return {'status': 'available'}, {}
    monkeypatch.setattr(updates, 'collect_race_weather', collect)
    context = {'year': 2026, 'round': 16, 'event': 'Bahrain Grand Prix', 'race_start_utc': '2026-10-04T07:00Z'}
    first = updates.capture_weather_update(tmp_path, context, now='2026-10-03T12:00Z')
    assert calls == [(2.76083, 101.738)]
    # Simulate a legacy cache without circuit provenance.
    path = __import__('pathlib').Path(first['folder'])/'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['context'].pop('venue')
    path.write_text(json.dumps(manifest))
    second = updates.capture_weather_update(tmp_path, context, now='2026-10-03T12:30Z')
    assert second['folder'] != first['folder'] and len(calls) == 2


def test_session_circuit_hint_is_checked_even_if_event_country_is_wrong():
    session = SimpleNamespace(event={'Country': 'Bahrain', 'Location': 'Kuala Lumpur'},
        session_info={'Meeting': {'Country': {'Code': 'BRN'}, 'Location': 'Kuala Lumpur',
                                 'Circuit': {'ShortName': 'Kuala Lumpur'}}})
    context = {'year': 2026, 'event': 'Bahrain Grand Prix'}
    assert venue_for_context(context, session=session)['circuit_id'] == 'sepang'
    session.session_info['Meeting']['Circuit']['ShortName'] = 'Sakhir'
    assert venue_for_context(context, session=session)['venue_status'] == 'conflict'


def test_old_event_rows_cannot_supply_relocated_track_factors(tmp_path):
    path = tmp_path/'profiles.csv'
    pd.DataFrame([{'Event': 'Bahrain Grand Prix', 'OvertakingDifficulty': .1,
                   'Latitude': 26, 'Longitude': 50}]).to_csv(path, index=False)
    new = load_track_profile('Bahrain Grand Prix', str(path), metadata={'year': 2026, 'event': 'Bahrain Grand Prix'})
    old = load_track_profile('Bahrain Grand Prix', str(path), metadata={'year': 2025, 'event': 'Bahrain Grand Prix'})
    assert new['overtaking_difficulty'] == .55 and new['profile_status'] == 'generic_uncalibrated'
    assert new['latitude'] == pytest.approx(2.76083)
    assert old['overtaking_difficulty'] == .1 and old['circuit_id'] == 'bahrain'


@pytest.mark.parametrize('target_event', ['Bahrain Grand Prix', 'Spanish Grand Prix'])
def test_history_does_not_load_wrong_circuit_even_if_grand_prix_name_matches(monkeypatch, target_event):
    monkeypatch.setattr('fastf1.get_event_schedule', lambda year: pd.DataFrame([
        {'EventName': 'Bahrain Grand Prix', 'Location': 'Sakhir', 'RoundNumber': 1},
        {'EventName': 'Spanish Grand Prix', 'Location': 'Barcelona', 'RoundNumber': 9}]))
    monkeypatch.setattr(history, 'load_session', lambda *a: pytest.fail('Wrong physical circuit loaded'))
    assert history._load_historical_race(2025, target_event, venue=resolve_venue(2026, target_event)) is None


def test_history_follows_same_layout_through_event_rename(monkeypatch):
    monkeypatch.setattr('fastf1.get_event_schedule', lambda year: pd.DataFrame([
        {'EventName': 'Spanish Grand Prix', 'Location': 'Barcelona', 'RoundNumber': 9}]))
    calls = []
    def load(year, round_number, code):
        calls.append((year, round_number, code))
        return SimpleNamespace(event={'Location': 'Barcelona'}), {'year': year, 'event': 'Spanish Grand Prix'}
    monkeypatch.setattr(history, 'load_session', load)
    result = history._load_historical_race(2025, 'Barcelona Grand Prix', venue=resolve_venue(2026, 'Barcelona Grand Prix'))
    assert result[1]['venue']['circuit_id'] == 'catalunya' and calls == [(2025, 9, 'R')]
    # Same physical circuit, incompatible old layout: no strategy import.
    calls.clear()
    assert history._load_historical_race(2022, 'Barcelona Grand Prix', venue=resolve_venue(2026, 'Barcelona Grand Prix')) is None
    assert not calls


def test_new_discord_report_archives_venue_but_legacy_identity_stays_original(tmp_path):
    context = {'year': 2026, 'event': 'Bahrain Grand Prix', 'session': 'Q', 'race_start_utc': '2026-10-04T07:00Z',
        'venue': {**resolve_venue(2026, 'Bahrain Grand Prix'), 'profile_status': 'generic_uncalibrated'}}
    pd.DataFrame({'Driver': ['A'], 'avg_finish': [1.], 'win_chance': [1.]}).to_csv(tmp_path/'simulation_summary.csv', index=False)
    beta.dump_new(tmp_path/'venue_context.json', context['venue'])
    beta.freeze_snapshot(tmp_path, context, now='2026-10-03T12:00Z')
    manifest = beta.verified_snapshot(tmp_path)
    assert 'venue_context.json' in manifest['files'] and 'venues.py' in manifest['model_source_hashes']
    message = discord_reports.forecast_message(tmp_path)
    assert 'Sepang International Circuit' in message['embeds'][0]['title']
    assert 'generic track factors' in json.dumps(message)
    assert event_display({'event': 'Bahrain Grand Prix'}) == 'Bahrain Grand Prix'
    (tmp_path/'frozen/venue_context.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        beta.verified_snapshot(tmp_path)
