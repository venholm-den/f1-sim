from datetime import datetime, timezone, timedelta
import copy
import csv
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from src import fantasy_market as market

NOW = datetime(2026, 10, 10, 18, tzinfo=timezone.utc)


def tools_payload(year=2026):
    def asset(kind, code, price, points):
        return {'id': code, 'abbreviation': code, 'type': kind,
                'constructorId': 'MER', 'isActive': True, 'price': price,
                'priceChange': 0.2, 'totalPoints': points,
                'raceResult': {'Q': {'totalPoints': {'points': 2}},
                               'R': {'totalPoints': {'points': points - 2}}}}
    return {'seasonResult': {'season': year, 'raceResults': {
        '1': {'drivers': [asset('driver', 'RUS', 20, -3)],
              'constructors': [asset('constructor', 'MER', 25, 14)]},
        '2': {'drivers': [], 'constructors': []}}},
        'races': [{'roundNumber': 1, 'name': 'Example Grand Prix',
                   'countryName': 'UK', 'start_times': {'race': f'{year}-05-01T12:00:00Z'}},
                  {'roundNumber': 2, 'name': 'Future Grand Prix',
                   'start_times': {'race': '2026-12-01T12:00:00Z'}}]}


def schedule_payload(status=3):
    race = {'Season': '2026', 'GamedayId': 17, 'SessionType': 'Race', 'GDStatus': status,
            'GDIsCurrent': 1, 'MeetingName': 'Singapore Grand Prix',
            'CountryName': 'Singapore', 'SessionStartDateISO8601': '2026-10-11T12:00:00Z'}
    return {'Data': {'Value': [race]}}


def official_payload():
    return {'Data': {'Value': [
        {'PlayerId': '1', 'PositionName': 'DRIVER', 'DriverTLA': 'RUS',
         'FUllName': 'George Russell', 'TeamName': 'Mercedes', 'IsActive': '1',
         'Value': 28, 'GamedayPoints': '-5', 'OverallPpints': '404',
         'QualifyingPoints': '-5', 'RacePoints': '0', 'SprintPoints': ''},
        {'PlayerId': '2', 'PositionName': 'CONSTRUCTOR', 'DriverTLA': 'MER',
         'FUllName': 'Mercedes', 'IsActive': '1', 'Value': 30,
         'GamedayPoints': '0', 'OverallPpints': '450', 'RacePoints': '0'}]}}


def fetcher(calls, *, fail_tools=False):
    def fetch(url):
        calls.append(url)
        if '/api/statistics/' in url:
            if fail_tools:
                raise ValueError('Changed schema')
            return tools_payload(int(url.rsplit('/', 1)[-1]))
        if '/schedule/' in url:
            return schedule_payload()
        return official_payload()
    return fetch


def test_historical_negative_scores_constructor_points_and_future_missing():
    payload = tools_payload()
    rows = market.parse_tools(payload, 2026, NOW.isoformat(), 'https://source')
    assert len(rows) == 2  # Empty future rounds are not zero-point results.
    driver, team = rows
    assert driver['actual_points'] == -3 and driver['race_points'] == -5
    assert driver['team'] == 'MER' and driver['price'] == 20
    assert driver['price_basis'] == 'source_reported_round'
    assert team['asset_type'] == 'constructor' and team['actual_points'] == 14
    future = copy.deepcopy(payload)
    future['races'][0]['start_times']['race'] = '2026-12-01T12:00:00Z'
    future_rows = market.parse_tools(future, 2026, NOW.isoformat(), 'source')
    assert all(r['actual_points'] is None and r['points_status'] == 'unavailable' for r in future_rows)
    with pytest.raises(ValueError, match='season'):
        market.parse_tools(payload, 2025, NOW.isoformat(), 'source')


def test_official_partial_weekend_is_provisional_and_unplayed_points_blank():
    weekend = schedule_payload()['Data']['Value']
    rows = market.parse_official(official_payload(), weekend, NOW.isoformat(), 'source')
    assert rows[0]['points_status'] == 'provisional'
    assert rows[0]['actual_points'] == -5
    assert rows[0]['race_points'] is None  # Placeholder zero is not a race result.
    assert rows[0]['season_points'] == 404
    assert rows[1]['actual_points'] == 0  # A genuine reported zero remains zero.
    weekend[0]['GDStatus'] = 0
    rows = market.parse_official(official_payload(), weekend, NOW.isoformat(), 'source')
    assert all(r['actual_points'] is None for r in rows)


def test_refresh_is_throttled_historical_once_and_captures_immutable(tmp_path):
    calls = []
    market.collect(tmp_path, [2025, 2026], now=NOW, fetch=fetcher(calls))
    assert len(calls) == 4
    root = market.archive_root(tmp_path)
    original = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / 'captures').rglob('*') if p.is_file()}
    calls.clear()
    result = market.collect(tmp_path, [2025, 2026], now=NOW + timedelta(hours=2), fetch=fetcher(calls))
    assert result['status'] == 'not_due' and not calls
    market.collect(tmp_path, [2025, 2026], now=NOW + timedelta(hours=7), fetch=fetcher(calls))
    assert len(calls) == 3 and not any('/2025' in u for u in calls)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in original.items())
    with (root / 'weekly_history.csv').open(newline='', encoding='utf8') as stream:
        assert len(list(csv.DictReader(stream))) == 6  # Latest per source, no duplicates on refresh.


def test_failed_source_keeps_last_good_capture_and_other_source_continues(tmp_path):
    market.collect(tmp_path, now=NOW, fetch=fetcher([]))
    root = market.archive_root(tmp_path)
    before = json.loads((root / 'index.json').read_text())['captures']['tools_2026']
    result = market.collect(tmp_path, now=NOW + timedelta(hours=7), fetch=fetcher([], fail_tools=True))
    assert any(r['status'] == 'error' for r in result['results'])
    after = json.loads((root / 'index.json').read_text())
    assert after['captures']['tools_2026'] == before
    assert after['captures']['official_2026_17']['captured_at'] != before['captured_at']
    assert len(market.history(tmp_path)[0]) == 4


def test_only_matching_future_event_official_quotes_can_enter_new_prediction(tmp_path):
    market.collect(tmp_path, now=NOW, fetch=fetcher([]))
    output = tmp_path / 'new_run'
    output.mkdir()
    context = {'year': 2026, 'event': 'Singapore Grand Prix'}
    path = market.snapshot_prices(tmp_path, context, output, now=NOW + timedelta(minutes=5))
    with open(path, newline='', encoding='utf8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and rows[0]['fantasy_price'] == '28.0'
    assert rows[0]['source_url'].startswith(market.OFFICIAL)
    for mismatched in [{'year': 2025, 'event': context['event']}, {'year': 2026, 'event': 'Example Grand Prix'}]:
        assert market.snapshot_prices(tmp_path, mismatched, output, now=NOW) is None
    assert market.snapshot_prices(tmp_path, context, output, now=NOW - timedelta(minutes=1)) is None
    assert market.snapshot_prices(tmp_path, context, output, now=NOW + timedelta(days=2)) is None


def test_changed_capture_is_rejected(tmp_path):
    market.collect(tmp_path, [2025], now=NOW, fetch=fetcher([]))
    csv_path = next(market.archive_root(tmp_path).glob('captures/*/rows.csv'))
    csv_path.write_text('tampered')
    rows, _, errors = market.history(tmp_path)
    assert not rows and errors


def test_official_feed_failure_retries_after_one_hour_without_refetching_good_history(tmp_path):
    calls = []
    normal = fetcher(calls)
    def fail_feed(url):
        if '/drivers/' in url:
            calls.append(url)
            raise ValueError('Feed unavailable')
        return normal(url)
    market.collect(tmp_path, now=NOW, fetch=fail_feed)
    calls.clear()
    market.collect(tmp_path, now=NOW + timedelta(minutes=30), fetch=normal)
    assert calls == []
    market.collect(tmp_path, now=NOW + timedelta(hours=1, minutes=5), fetch=normal)
    assert len(calls) == 2 and not any('/statistics/' in u for u in calls)


def test_desktop_reads_pc_archive_and_filters_history_without_changing_saved_results(tmp_path):
    from portable_app.web_backend import PortableWebApi
    pc = tmp_path / 'pc'
    pc.mkdir()
    market.collect(pc, [2025, 2026], now=NOW, fetch=fetcher([]))
    api = PortableWebApi.__new__(PortableWebApi)
    api.ui_preferences = {'pc_workspace': str(pc)}
    api._jobs = SimpleNamespace(root=tmp_path / 'desktop')
    api._fantasy_lock = threading.Lock()
    api._fantasy_progress = {'running': False, 'result': None}
    api.last_output = 'preserved-result'
    result = api.fantasy_state(2025)
    assert result['year'] == 2025 and all(r['season'] == '2025' for r in result['rows'])
    assert result['market'][0]['season'] == '2026'
    assert result['archive'] == str(market.archive_root(pc))
    assert api.last_output == 'preserved-result'


def test_used_market_quote_is_frozen_and_verified_with_the_forecast(tmp_path):
    from src.app_services.beta import freeze_snapshot, verified_snapshot
    (tmp_path / 'simulation_summary.csv').write_text('Driver,win_chance\nRUS,0.5\n')
    quote = tmp_path / 'fantasy_market_prices.csv'
    quote.write_text('Driver,fantasy_price,captured_at\nRUS,28,2026-10-10T18:00:00Z\n')
    freeze_snapshot(tmp_path, {'race_start_utc': '2026-10-11T12:00:00Z'}, now=NOW)
    manifest = verified_snapshot(tmp_path)
    assert 'fantasy_market_prices.csv' in manifest['files']
    (tmp_path / 'frozen' / quote.name).write_text('changed price')
    with pytest.raises(ValueError, match='changed'):
        verified_snapshot(tmp_path)
