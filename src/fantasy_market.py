"""Public Fantasy feeds: immutable captures and a separate, source-labelled archive.

No account, private export API, or scoring-rule inference is used. Historical
round prices retain the source's meaning; they are never treated as an observed
pre-race quote. Official live prices can be snapshotted for future races only.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

import requests

OFFICIAL = 'https://fantasy.formula1.com'
TOOLS = 'https://f1fantasytools.com'
FIRST_SEASON = 2023
FIELDS = ['source', 'season', 'round', 'event', 'country', 'race_start',
          'asset_type', 'asset_id', 'code', 'name', 'team', 'is_active',
          'price', 'price_change', 'price_basis', 'actual_points', 'points_status',
          'qualifying_points', 'sprint_points', 'race_points', 'season_points',
          'captured_at', 'source_url']


def utc_now():
    return datetime.now(timezone.utc)


def number(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def archive_root(workspace):
    return Path(workspace) / 'data' / 'fantasy_market'


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def _atomic_json(path, value):
    temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


@contextmanager
def _collection_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.collector.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Fantasy collection is already running.') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def parse_tools(payload, year, captured_at, url):
    season = payload['seasonResult']
    if int(season['season']) != year or not isinstance(season['raceResults'], dict):
        raise ValueError('Historical Fantasy feed season/schema mismatch.')
    races = {int(r['roundNumber']): r for r in payload['races']}
    rows = []
    for raw_round, result in season['raceResults'].items():
        round_number = int(raw_round)
        race = races.get(round_number)
        if race is None:
            raise ValueError('Fantasy round is missing its source event metadata.')
        for kind, key in [('driver', 'drivers'), ('constructor', 'constructors')]:
            assets = result[key]
            constructors = {x['id']: x['abbreviation'] for x in result['constructors']}
            for asset in assets:
                sessions = asset.get('raceResult') or {}
                def points(code):
                    return number(sessions.get(code, {}).get('totalPoints', {}).get('points'))
                actual = number(asset.get('totalPoints'))
                start = instant(race.get('start_times', {}).get('race'))
                captured = instant(captured_at)
                completed = (points('R') is not None and start is not None
                             and captured is not None and start <= captured)
                active = asset.get('isActive')
                rows.append(dict(zip(FIELDS, [
                    'f1fantasytools', year, round_number, race['name'], race.get('countryName', ''),
                    race.get('start_times', {}).get('race', ''), kind, str(asset['id']),
                    asset['abbreviation'], asset.get('name', asset['abbreviation']),
                    constructors.get(asset.get('constructorId'), ''),
                    '' if active is None else str(active).lower(), number(asset.get('price')),
                    number(asset.get('priceChange')), 'source_reported_round',
                    actual if completed else None, 'completed' if completed else 'unavailable',
                    points('Q'), points('S'), points('R'), None, captured_at, url,
                ])))
    if not rows:
        raise ValueError('Historical Fantasy feed contained no assets.')
    identities = {(r['round'], r['asset_type'], r['asset_id']) for r in rows}
    if len(identities) != len(rows):
        raise ValueError('Historical Fantasy feed contains duplicate assets.')
    return rows


def official_weekends(payload):
    groups = {}
    for item in payload['Data']['Value']:
        key = (int(item['Season']), int(item['GamedayId']))
        groups.setdefault(key, []).append(item)
    return groups


def parse_official(payload, weekend, captured_at, url):
    race = next((r for r in weekend if r['SessionType'] == 'Race'), None)
    if race is None:
        raise ValueError('Official Fantasy weekend has no race metadata.')
    completed = int(race['GDStatus']) == 4
    started = any(int(r.get('GDStatus', 0)) >= 3 for r in weekend)
    status = 'completed' if completed else 'provisional' if started else 'unavailable'
    rows = []
    for asset in payload['Data']['Value']:
        kind = str(asset['PositionName']).lower()
        if kind not in {'driver', 'constructor'}:
            continue
        rows.append(dict(zip(FIELDS, [
            'official', int(race['Season']), int(race['GamedayId']), race['MeetingName'],
            race.get('CountryName', ''), race['SessionStartDateISO8601'], kind,
            str(asset['PlayerId']), asset['DriverTLA'], asset.get('FUllName', ''),
            asset.get('TeamName', ''), str(asset.get('IsActive', '')) == '1',
            number(asset.get('Value')), None, 'official_feed_quote',
            number(asset.get('GamedayPoints')) if started else None, status,
            number(asset.get('QualifyingPoints')) if started else None,
            number(asset.get('SprintPoints')) if started else None,
            number(asset.get('RacePoints')) if completed else None,
            number(asset.get('OverallPpints')), captured_at, url,
        ])))
    if not rows or not any(r['asset_type'] == 'constructor' for r in rows):
        raise ValueError('Official Fantasy feed contained no driver/constructor market.')
    if len({r['asset_id'] for r in rows}) != len(rows):
        raise ValueError('Official Fantasy feed contains duplicate asset identifiers.')
    return rows


def collect(workspace, years=None, *, force=False, now=None, fetch=None):
    """Fetch current feeds every six hours; completed older seasons only once.

    A capture is published atomically after parsing succeeds. Failed sources keep
    their last successful capture and retry after one hour. Other sources continue.
    """
    now = now or utc_now()
    requested = sorted(set(int(y) for y in (years or [now.year])))
    if any(y < FIRST_SEASON or y > now.year for y in requested):
        raise ValueError(f'Fantasy history is available from {FIRST_SEASON} through {now.year}.')
    root = archive_root(workspace)
    session = requests.Session()
    session.headers['User-Agent'] = 'F1Sim-FantasyArchive/1.0 (personal local statistics archive)'
    def request(url):
        response = session.get(url, timeout=(10, 35))
        response.raise_for_status()
        return response.json()
    fetch = fetch or request
    with _collection_lock(root):
        index = _read_json(root / 'index.json', {'captures': {}, 'attempts': {}})
        captures = index.setdefault('captures', {})
        attempts = index.setdefault('attempts', {})
        results = []
        stamp = now.isoformat()
        def due(key, historical=False):
            previous = captures.get(key)
            attempted = instant(attempts.get(key, {}).get('at'))
            retry_hours = 6 if attempts.get(key, {}).get('status') == 'ok' else 1
            if not force and attempted and now - attempted < timedelta(hours=retry_hours):
                return False
            captured = instant((previous or {}).get('captured_at'))
            return force or not captured or (not historical and now - captured >= timedelta(hours=6))
        def capture(key, url, parser):
            try:
                payload = fetch(url)
                rows = parser(payload, stamp, url)
                folder = root / 'captures' / (now.strftime('%Y%m%dT%H%M%S%fZ') + '_' + key + '_' + uuid.uuid4().hex[:6])
                folder.mkdir(parents=True)
                raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                (folder / 'raw.json').write_bytes(raw)
                with (folder / 'rows.csv').open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                manifest = {'key': key, 'source_url': url, 'captured_at': stamp,
                            'row_count': len(rows), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                            'rows_sha256': hashlib.sha256((folder / 'rows.csv').read_bytes()).hexdigest(),
                            'folder': str(folder.relative_to(root))}
                (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                captures[key] = manifest
                attempts[key] = {'at': stamp, 'status': 'ok'}
                results.append({'key': key, 'status': 'updated', 'rows': len(rows)})
            except Exception as exc:
                # URLs and credentials from exception text are never copied to the UI/log.
                attempts[key] = {'at': stamp, 'status': 'error', 'error': type(exc).__name__}
                results.append({'key': key, 'status': 'error', 'error': type(exc).__name__})
        for year in requested:
            key = f'tools_{year}'
            if due(key, historical=year < now.year):
                capture(key, f'{TOOLS}/api/statistics/{year}',
                        lambda p, at, url, y=year: parse_tools(p, y, at, url))
        if now.year in requested and due(f'official_{now.year}'):
            try:
                url = f'{OFFICIAL}/feeds/schedule/raceday_en.json'
                schedule = fetch(url)
                groups = official_weekends(schedule)
                # The current gameweek contains current purchasable quotes. Also
                # collect the last completed week, even if the next has opened.
                current = [k for k, w in groups.items() if k[0] == now.year
                           and any(int(r.get('GDIsCurrent', 0)) == 1 for r in w)]
                completed = [k for k, w in groups.items() if k[0] == now.year
                             and any(r['SessionType'] == 'Race' and int(r['GDStatus']) == 4 for r in w)]
                targets = set(current + (sorted(completed)[-1:]))
                if not targets:
                    raise ValueError('Official feed has no current or completed weekend.')
                for year, round_number in sorted(targets):
                    key = f'official_{year}_{round_number}'
                    if due(key):
                        capture(key, f'{OFFICIAL}/feeds/drivers/{round_number}_en.json',
                                lambda p, at, u, w=groups[(year, round_number)]: parse_official(p, w, at, u))
                folder = root / 'schedules'
                folder.mkdir(exist_ok=True)
                _atomic_json(folder / f'{now.year}.json', schedule)
                failed = any(r['key'].startswith('official_') and r['status'] == 'error' for r in results)
                attempts[f'official_{now.year}'] = {'at': stamp, 'status': 'error' if failed else 'ok'}
            except Exception as exc:
                attempts[f'official_{now.year}'] = {'at': stamp, 'status': 'error', 'error': type(exc).__name__}
                results.append({'key': f'official_{now.year}', 'status': 'error', 'error': type(exc).__name__})
        _atomic_json(root / 'index.json', index)
        rebuild_csv(root, index)
    return {'status': 'updated' if results else 'not_due', 'results': results,
            'archive': str(root)}


def _capture_rows(root, manifest):
    folder = (root / manifest['folder']).resolve()
    if not folder.is_relative_to(root.resolve()):
        raise ValueError('Fantasy capture path is outside its archive.')
    path = folder / 'rows.csv'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['rows_sha256']:
        raise ValueError('Fantasy capture checksum failed.')
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def rebuild_csv(root, index):
    """Latest version of each source/week; older immutable versions remain saved."""
    temporary = root / ('weekly_history.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for key, capture in sorted(index['captures'].items()):
            writer.writerows(_capture_rows(root, capture))
    os.replace(temporary, root / 'weekly_history.csv')


def history(workspace):
    root = archive_root(workspace)
    index = _read_json(root / 'index.json', {'captures': {}, 'attempts': {}})
    rows, errors = [], []
    for key, capture in index.get('captures', {}).items():
        try:
            rows.extend(_capture_rows(root, capture))
        except (OSError, ValueError, KeyError):
            errors.append(f'{key}: capture unavailable or checksum failed')
    return rows, index, errors


def snapshot_prices(workspace, metadata, output_dir, *, now=None):
    """Use observed official prices only for the exact upcoming source event.

    Historical source prices are deliberately excluded. The quote must have been
    captured this week, before race start, and before this simulation began.
    """
    now = now or utc_now()
    rows, _, _ = history(workspace)
    eligible = []
    for row in rows:
        captured, race = instant(row['captured_at']), instant(row['race_start'])
        if (row['source'] == 'official' and row['asset_type'] == 'driver'
                and row['is_active'].lower() in {'true', '1'}
                and int(row['season']) == int(metadata['year'])
                and row['event'].casefold() == str(metadata['event']).casefold()
                and captured and race and race > now >= captured
                and now - captured < timedelta(days=7) and number(row['price']) is not None):
            eligible.append(row)
    if not eligible:
        return None
    latest = max(row['captured_at'] for row in eligible)
    eligible = [r for r in eligible if r['captured_at'] == latest]
    if len({r['code'] for r in eligible}) != len(eligible):
        return None
    path = Path(output_dir) / 'fantasy_market_prices.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['Driver', 'Team', 'fantasy_price', 'captured_at', 'source_url'])
        writer.writeheader()
        writer.writerows({'Driver': r['code'], 'Team': r['team'], 'fantasy_price': r['price'],
                          'captured_at': r['captured_at'], 'source_url': r['source_url']} for r in eligible)
    return str(path)
