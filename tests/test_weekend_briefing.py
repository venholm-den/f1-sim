import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from PIL import Image

from src.app_services import weekend_briefing as weekend


def clock(value):
    return datetime.fromisoformat(value)


def calendar(first='2026-06-05T11:30:00Z', sprint=False):
    starts = [first, '2026-06-05T15:00:00Z', '2026-06-06T10:30:00Z',
              '2026-06-06T14:00:00Z', '2026-06-07T13:00:00Z']
    names = ['Practice 1', 'Sprint Qualifying', 'Sprint', 'Qualifying', 'Race'] if sprint else [
        'Practice 1', 'Practice 2', 'Practice 3', 'Qualifying', 'Race']
    row = {'RoundNumber': 8, 'EventName': 'Monaco Grand Prix', 'Location': 'Monte Carlo'}
    for i, (name, start) in enumerate(zip(names, starts), 1):
        row[f'Session{i}'] = name
        row[f'Session{i}DateUtc'] = start
    return pd.DataFrame([row])


def selected(now='2026-06-04T08:00:00+00:00', **kwargs):
    return weekend.select_weekend(calendar(**kwargs), 2026, clock(now))


@pytest.mark.parametrize('now, status', [
    ('2026-06-03T12:00:00+00:00', 'not_due'),
    ('2026-06-04T07:59:00+00:00', 'not_due'),
    ('2026-06-04T08:00:00+00:00', 'ready'),
    ('2026-06-04T22:59:59+00:00', 'ready'),
    ('2026-06-04T23:00:00+00:00', 'not_due'),
    ('2026-06-05T08:00:00+00:00', 'not_due'),
])
def test_only_uk_day_before_first_session_after_nine(now, status):
    briefing = selected(now)
    assert briefing['due_date'] == '2026-06-04'
    assert weekend.briefing_status(briefing, clock(now))['status'] == status


def test_sprint_schedule_is_preserved_in_uk_time():
    briefing = selected(sprint=True)
    assert briefing['format'] == 'Sprint'
    assert [s['code'] for s in briefing['sessions']] == ['FP1', 'SQ', 'S', 'Q', 'R']
    assert briefing['sessions'][0]['uk_time'] == '12:30 BST'
    assert briefing['track']['circuit_id'] == 'monaco'


def test_first_session_near_midnight_uses_uk_calendar_date():
    briefing = selected(first='2026-06-04T23:30:00Z')
    assert briefing['due_date'] == '2026-06-04'  # FP1 is Friday in the UK.


def test_dst_changes_are_converted_per_session():
    data = calendar()
    starts = ['2026-10-23T09:00Z', '2026-10-23T13:00Z', '2026-10-24T09:00Z',
              '2026-10-24T13:00Z', '2026-10-25T13:00Z']
    for i, value in enumerate(starts, 1):
        data.loc[0, f'Session{i}DateUtc'] = value
    briefing = weekend.select_weekend(data, 2026, clock('2026-10-22T09:00:00+00:00'))
    assert briefing['sessions'][0]['uk_time'] == '10:00 BST'
    assert briefing['sessions'][-1]['uk_time'] == '13:00 GMT'


@pytest.mark.parametrize('change', ['missing_fp1', 'missing_race', 'testing', 'out_of_order'])
def test_incomplete_calendar_or_testing_never_creates_briefing(change):
    data = calendar()
    if change == 'missing_fp1':
        data.loc[0, 'Session1DateUtc'] = None
    elif change == 'missing_race':
        data.loc[0, 'Session5DateUtc'] = None
    elif change == 'testing':
        data.loc[0, 'RoundNumber'] = 0
    else:
        data.loc[0, 'Session2DateUtc'] = '2026-06-04T09:00Z'
    assert weekend.select_weekend(data, 2026, clock('2026-06-04T08:00:00+00:00')) is None


@pytest.fixture
def ready(monkeypatch):
    briefing = selected()
    monkeypatch.setattr(weekend, 'upcoming_weekend', lambda *a: briefing)
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.invalid/secret')
    return briefing


def test_check_only_and_disabled_discord_never_write_or_send(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(weekend, 'post_files_to_discord', lambda **k: pytest.fail('Unexpected upload'))
    now = clock('2026-06-04T08:00:00+00:00')
    assert weekend.run_weekend_briefing(tmp_path, now=now, check_only=True)['status'] == 'ready'
    assert weekend.run_weekend_briefing(tmp_path, now=now)['status'] == 'ready'
    assert not (tmp_path / 'outputs').exists()


def test_success_is_once_per_weekend_and_receipts_are_scrubbed(tmp_path, monkeypatch, ready):
    calls = []
    monkeypatch.setattr(weekend, 'post_files_to_discord', lambda **k: calls.append(k) or {
        'ok': True, 'status': 200, 'response': 'private URL'})
    now = clock('2026-06-04T08:00:00+00:00')
    first = weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    second = weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    assert first['discord']['ok'] and second['discord']['skipped'] and len(calls) == 1
    folder = tmp_path / 'outputs/weekend_briefings/2026_round_08'
    receipt = (folder / 'discord_post_result.json').read_text()
    assert 'response' not in receipt and 'secret' not in receipt
    with Image.open(folder / 'weekend_briefing.png') as image:
        assert image.size == (1600, 1280)
    assert len(calls[0]['file_paths']) == 1
    assert 'your device timezone' in calls[0]['embeds'][0]['description']


def test_http_retry_pins_payload_and_never_posts_on_following_day(tmp_path, monkeypatch, ready):
    calls = []
    monkeypatch.setattr(weekend, 'post_files_to_discord', lambda **k: calls.append(k) or {'ok': False, 'status': 503})
    now = clock('2026-06-04T08:00:00+00:00')
    first = weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    folder = tmp_path / 'outputs/weekend_briefings/2026_round_08'
    plan = (folder / 'delivery_plan.json').read_bytes()
    assert first['discord']['delivery_state'] == 'pending'
    assert weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)['discord']['skipped']
    assert len(calls) == 1
    weekend.run_weekend_briefing(tmp_path, now=clock('2026-06-04T09:00:00+00:00'), discord_enabled=True)
    assert len(calls) == 2 and calls[0]['embeds'] == calls[1]['embeds']
    assert (folder / 'delivery_plan.json').read_bytes() == plan
    result = weekend.post_briefing(folder, now=clock('2026-06-04T23:00:00+00:00'))
    assert result['reason'] == 'outside_announcement_window' and len(calls) == 2


@pytest.mark.parametrize('outcome', ['url_error', 'crash'])
def test_uncertain_upload_is_never_repeated(tmp_path, monkeypatch, ready, outcome):
    calls = []
    def post(**kwargs):
        calls.append(kwargs)
        if outcome == 'crash':
            raise RuntimeError('Transport ended after request')
        return {'ok': False, 'status': outcome}
    monkeypatch.setattr(weekend, 'post_files_to_discord', post)
    now = clock('2026-06-04T08:00:00+00:00')
    first = weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    second = weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    assert first['discord']['delivery_state'] == 'uncertain'
    assert second['discord']['requires_review'] and len(calls) == 1


def test_modified_card_and_corrupt_receipt_fail_closed(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(weekend, 'post_files_to_discord', lambda **k: {'ok': False, 'status': 503})
    now = clock('2026-06-04T08:00:00+00:00')
    weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)
    folder = tmp_path / 'outputs/weekend_briefings/2026_round_08'
    (folder / 'weekend_briefing.png').write_bytes(b'changed')
    monkeypatch.setattr(weekend, 'post_files_to_discord', lambda **k: pytest.fail('Unexpected upload'))
    with pytest.raises(ValueError, match='changed'):
        weekend.post_briefing(folder, now=clock('2026-06-04T09:00:00+00:00'))
    (folder / 'discord_post_result.json').write_text('damaged')
    with pytest.raises(json.JSONDecodeError):
        weekend.run_weekend_briefing(tmp_path, now=now, discord_enabled=True)


def test_conflicting_venue_withholds_track_geometry(tmp_path):
    data = calendar()
    data.loc[0, 'Location'] = 'Silverstone'
    briefing = weekend.select_weekend(data, 2026, clock('2026-06-04T08:00:00+00:00'))
    weekend._track_reference(tmp_path, briefing)
    assert briefing['track']['venue_status'] == 'conflict'
    assert not briefing['track'].get('length_km')
