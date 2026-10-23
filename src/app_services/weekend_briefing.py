"""One schedule/track briefing, only on the UK day before the first F1 session."""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.app_services.beta import digest
from src.app_services.discord_cards import number, render_weekend_card
from src.app_services.historical_runs import SESSION_CODES
from src.app_services.simulation_jobs import write_json
from src.discord_post import post_files_to_discord, validate_message
from src.venues import resolve_venue

UK = ZoneInfo('Europe/London')
POST_HOUR = 9


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError('Weekend briefing requires a timezone-aware time.')
    return value.astimezone(timezone.utc)


def _read(path):
    # A damaged receipt must fail closed instead of being treated as unsent.
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def select_weekend(schedule, year, now=None):
    """Use all five published UTC session starts, never infer a missing FP1."""
    now = _now(now)
    candidates = []
    for _, row in schedule.iterrows():
        if number(row.get('RoundNumber')) is None or row['RoundNumber'] <= 0:
            continue
        sessions = []
        for i in range(1, 6):
            name = row.get(f'Session{i}')
            start = pd.to_datetime(row.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
            code = SESSION_CODES.get(name)
            if not code or pd.isna(start):
                break
            local = start.tz_convert(UK)
            sessions.append({'name': str(name), 'code': code, 'start_utc': start.isoformat(),
                             'uk_date': local.strftime('%a %d %b'),
                             'uk_time': local.strftime('%H:%M %Z')})
        if (len(sessions) != 5 or len({s['code'] for s in sessions}) != 5
                or sessions[0]['code'] != 'FP1' or sessions[-1]['code'] != 'R'):
            continue
        starts = [pd.Timestamp(s['start_utc']) for s in sessions]
        if starts != sorted(starts) or starts[0] <= now:
            continue
        due = starts[0].tz_convert(UK).date() - timedelta(days=1)
        event = str(row['EventName'])
        candidates.append({'year': int(year), 'round': int(row['RoundNumber']), 'event': event,
            'first_session_utc': starts[0].isoformat(), 'due_date': due.isoformat(),
            'sessions': sessions, 'format': 'Sprint' if any(s['code'] == 'S' for s in sessions) else 'Standard',
            'track': resolve_venue(year, event, location=row.get('Location')),
            'captured_at_utc': now.isoformat(), 'schedule_source': 'FastF1 event schedule (UTC)',
            'timezone': 'Europe/London', 'post_hour': POST_HOUR})
    return min(candidates, key=lambda c: c['first_session_utc']) if candidates else None


def upcoming_weekend(root, now=None):
    import fastf1
    now = _now(now)
    cache = Path(root) / 'data/cache'
    if cache.is_dir():
        enable_cache(str(cache))
    for year in (now.year, now.year + 1):
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        result = select_weekend(schedule, year, now)
        if result:
            return result
    return None


def _track_reference(root, briefing):
    track = briefing['track']
    path = Path(root) / 'data/track_profiles.csv'
    if track.get('venue_status') != 'resolved' or not path.is_file():
        track['reference_label'] = 'Track reference unavailable'
        return
    data = pd.read_csv(path)
    if 'CircuitId' not in data:
        return
    rows = data.loc[data.CircuitId.eq(track['circuit_id'])]
    if rows.empty:
        return
    row = rows.iloc[0]
    season = number(row.get('GeometrySeason'))
    # A later layout is not reference evidence for an earlier weekend.
    if season is not None and season <= briefing['year']:
        length = number(row.get('CircuitLengthKm'))
        track['length_km'] = length if length is not None and length > 0 else None
        track['reference_label'] = f'{int(season)} circuit reference; race laps may vary'
        source = row.get('GeometrySourceURL')
        track['reference_url'] = source if isinstance(source, str) and source.startswith('https://') else None
    else:
        track['reference_label'] = 'Lap count is a circuit assumption'


def briefing_message(briefing):
    from src.app_services.discord_reports import _text
    sessions = '\n'.join(f"**{_text(s['name'])}** — <t:{int(pd.Timestamp(s['start_utc']).timestamp())}:F>"
                         for s in briefing['sessions'])
    t = briefing['track']
    track = f"{_text(t.get('circuit_name') or 'Circuit identity unresolved')} • {_text(t.get('venue_country') or 'Unknown country')}"
    if t.get('venue_status') == 'resolved':
        track += f"\nReference race laps: {t.get('race_laps') or 'unavailable'} (race-specific changes may apply)."
        if t.get('length_km'):
            track += f"\nReference lap length: {t['length_km']:.3f} km."
        if t.get('reference_url'):
            track += f"\n[Circuit reference]({t['reference_url']})"
    payload = {'content': '', 'embeds': [{
        'title': f"{briefing['year']} {_text(briefing['event'])} | Weekend briefing",
        'description': f"Round {briefing['round']} • {_text(briefing['format'])} weekend. Graphic times are UK (GMT/BST); Discord timestamps use your device timezone.",
        'color': 0x67DCE5,
        'fields': [{'name': 'Weekend schedule', 'value': sessions},
                   {'name': 'The track', 'value': track}],
        'footer': {'text': 'FastF1 published calendar • session starts may change • track figures are reference data'},
        'timestamp': briefing['captured_at_utc'],
    }]}
    validate_message(**payload)
    return payload


def briefing_status(briefing, now=None):
    if not briefing:
        return {'status': 'not_due', 'reason': 'no_complete_upcoming_weekend'}
    local = _now(now).astimezone(UK)
    ready = local.date().isoformat() == briefing['due_date'] and local.hour >= POST_HOUR
    return {'status': 'ready' if ready else 'not_due', 'event': briefing['event'],
            'year': briefing['year'], 'round': briefing['round'],
            'due_date': briefing['due_date'], 'post_hour': POST_HOUR, 'timezone': 'Europe/London'}


def post_briefing(folder, *, now=None, webhook_url=None):
    """Caller holds workspace lock. Retries never cross the announcement day."""
    now = _now(now)
    receipt_path = folder / 'discord_post_result.json'
    receipt = _read(receipt_path)
    if receipt.get('ok') or receipt.get('delivery_state') in {'sending', 'uncertain'}:
        return {**receipt, 'skipped': True, 'requires_review': not bool(receipt.get('ok'))}
    plan = _read(folder / 'delivery_plan.json')
    if now.astimezone(UK).date().isoformat() != plan['due_date'] or now.astimezone(UK).hour < POST_HOUR:
        return {'status': 'not_due', 'skipped': True, 'reason': 'outside_announcement_window'}
    if receipt.get('next_attempt_at') and now < datetime.fromisoformat(receipt['next_attempt_at']):
        return {**receipt, 'skipped': True}
    files = [folder / name for name in plan['files']]
    for name, checksum in plan['sha256'].items():
        if Path(name).name != name or digest(folder / name) != checksum:
            raise ValueError('Weekend briefing changed; nothing was posted.')
    validate_message(**plan['payload'])
    webhook_url = webhook_url or os.getenv('DISCORD_WEBHOOK_URL', '')
    if not webhook_url:
        raise ValueError('Discord webhook missing; weekend briefing remains local.')
    attempts = int(receipt.get('attempts', 0)) + 1
    reservation = {'ok': False, 'delivery_state': 'sending', 'attempts': attempts,
                   'attempted_at': now.isoformat()}
    write_json(receipt_path, reservation)
    try:
        response = post_files_to_discord(webhook_url=webhook_url, **plan['payload'],
                                         file_paths=files, username='F1 Sim')
    except Exception:
        response = {'ok': False, 'status': 'network_exception'}
    uncertain = response.get('status') in {'url_error', 'network_exception'}
    result = {**reservation, 'ok': bool(response.get('ok')), 'status': response.get('status'),
              'delivery_state': 'sent' if response.get('ok') else 'uncertain' if uncertain else 'pending',
              'posted_files': [str(p) for p in files]}
    if not result['ok'] and not uncertain:
        delay = min(360, 15 * 2 ** min(attempts - 1, 5))
        result['next_attempt_at'] = (now + timedelta(minutes=delay)).isoformat()
    write_json(receipt_path, result)
    return result


def run_weekend_briefing(root, *, discord_enabled=False, now=None, check_only=False):
    """Independent of forecast eligibility; a calendar error does not stop forecasts."""
    now = _now(now)
    briefing = upcoming_weekend(root, now)
    status = briefing_status(briefing, now)
    if status['status'] != 'ready' or check_only or not discord_enabled:
        return status
    folder = Path(root) / 'outputs/weekend_briefings' / f"{briefing['year']}_round_{briefing['round']:02d}"
    if not (folder / 'delivery_plan.json').exists():
        folder.mkdir(parents=True, exist_ok=True)
        _track_reference(root, briefing)
        payload = briefing_message(briefing)
        write_json(folder / 'briefing.json', briefing)
        card = render_weekend_card(briefing, folder)
        plan = {'format_version': 1, 'due_date': briefing['due_date'], 'payload': payload,
                'files': [card.name], 'sha256': {p.name: digest(p) for p in [card, folder / 'briefing.json']}}
        write_json(folder / 'delivery_plan.json', plan)
    return {**status, 'folder': str(folder), 'discord': post_briefing(folder, now=now)}
