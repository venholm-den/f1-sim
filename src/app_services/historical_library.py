"""Resumable historical downloads with a durable checkpoint per session."""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.app_services.historical_runs import SESSION_CODES
from src.app_services.simulation_jobs import write_json
from src.historical_data import _extract_results, _extract_weather, _extract_race_control, _safe_slug

SESSIONS = ('FP1', 'FP2', 'FP3', 'Q', 'SQ', 'S', 'R')
TABLES = ('laps', 'results', 'strategy', 'weather', 'race_control', 'weather_samples', 'race_control_messages', 'track_status', 'session_status')
EXPORT_NAMES = {'laps': 'fastf1_laps', 'results': 'fastf1_race_results', 'strategy': 'fastf1_actual_strategy',
                'weather': 'fastf1_weather_summary', 'race_control': 'fastf1_race_control_summary',
                'weather_samples': 'fastf1_weather_samples', 'race_control_messages': 'fastf1_race_control_messages',
                'track_status': 'fastf1_track_status', 'session_status': 'fastf1_session_status'}


def library_root(root):
    return Path(root)/'data/historical_library'


def options(payload):
    if not isinstance(payload, dict):
        raise ValueError('Choose seasons and a download type.')
    mode = str(payload.get('mode', 'detailed'))
    if mode not in {'detailed', 'results'}:
        raise ValueError('Choose detailed sessions or race classifications.')
    minimum = 2018 if mode == 'detailed' else 1950
    years = sorted({int(year) for year in payload.get('years', [])})
    if not years or any(not minimum <= year <= datetime.now(timezone.utc).year for year in years):
        raise ValueError(f'Choose at least one season from {minimum} to the current year.')
    sessions = [code for code in SESSIONS if code in payload.get('sessions', ['R'])]
    if mode == 'detailed' and (not sessions or set(payload.get('sessions', ['R'])) - set(SESSIONS)):
        raise ValueError('Choose at least one supported session type.')
    return {'years': years, 'mode': mode, 'sessions': sessions if mode == 'detailed' else ['R'],
            'telemetry': bool(payload.get('telemetry', False)) if mode == 'detailed' else False}


def read_json(path):
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def partition_files(path, manifest):
    for name, info in manifest.get('files', {}).items():
        file = (path/name).resolve()
        if not file.is_relative_to(path.resolve()) or not file.is_file() or file.stat().st_size != info['bytes']:
            raise ValueError('Saved session has missing or changed files; download again to repair it.')
        yield file, info


def complete(path, telemetry=False, verify=False):
    saved = read_json(path/'session.json')
    if saved.get('status') != 'complete' or not saved.get('files') or (telemetry and not saved.get('telemetry_available', saved.get('telemetry_requested'))):
        return False
    try:
        return all(not verify or sha256(file) == info['sha256'] for file, info in partition_files(path, saved))
    except (ValueError, KeyError, TypeError, OSError):
        return False


def discover(root, year, mode, sessions, now=None):
    import fastf1
    from fastf1.ergast import Ergast
    cache = Path(root)/'data/cache'
    cache.mkdir(parents=True, exist_ok=True)
    enable_cache(str(cache))
    cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True).normalize()
    tasks = []
    if mode == 'results':
        schedule = Ergast().get_race_schedule(season=year, limit=1000)
        for _, row in schedule.iterrows():
            date = pd.to_datetime(row.get('raceDate'), utc=True, errors='coerce')
            if pd.notna(date) and date < cutoff:
                tasks.append({'year': year, 'round': int(row['round']), 'event': str(row.raceName), 'session': 'R',
                              'circuit_id': row.get('circuitId'), 'circuit_name': row.get('circuitName')})
    else:
        schedule = fastf1.get_event_schedule(year)
        for _, row in schedule.iterrows():
            if int(row.get('RoundNumber', 0)) <= 0:
                continue
            for index in range(1, 6):
                code = SESSION_CODES.get(row.get(f'Session{index}'))
                date = pd.to_datetime(row.get(f'Session{index}DateUtc', row.get(f'Session{index}Date')), utc=True, errors='coerce')
                if code in sessions and pd.notna(date) and date < cutoff:
                    tasks.append({'year': year, 'round': int(row.RoundNumber), 'event': str(row.EventName), 'session': code})
    return tasks


def fetch(task, mode, telemetry):
    if mode == 'results':
        from fastf1.ergast import Ergast
        response = Ergast().get_race_results(season=task['year'], round=task['round'], limit=1000)
        if not response.is_complete:
            raise ValueError('Provider returned a partial classification; not marked complete.')
        frames = response.content
        if not frames or frames[0].empty:
            raise ValueError('No published race classification is available.')
        results = frames[0].copy()
        for name, value in [('Year', task['year']), ('Event', task['event']), ('Round', task['round']), ('Session', 'R')]:
            results.insert(0, name, value)
        return {'results': results}, {'circuit_id': task.get('circuit_id'), 'circuit_name': task.get('circuit_name'),
                                     'venue_source': 'jolpica_classification_schedule'}, []
    import fastf1
    from fastf1.exceptions import DataNotLoadedError
    from src.actual_strategy import extract_actual_strategy_from_session
    from src.collect import completed_race_quality
    from src.historical_data import _with_metadata
    from src.lap_details import extract_lap_details
    from src.race_control import _get_session_dataframe
    from src.venues import venue_for_context
    session = fastf1.get_session(task['year'], task['round'], task['session'])
    session.load(laps=True, telemetry=telemetry, weather=True, messages=True)
    states = _get_session_dataframe(session, 'session_status').get('Status', pd.Series(dtype=str)).dropna().astype(str)
    if states.empty or states.iloc[-1] not in {'Finished', 'Finalised', 'Ends'}:
        raise ValueError('Session is not confirmed finished; retry when finalised.')
    race_quality = completed_race_quality(session, archive=True) if task['session'] == 'R' else None
    metadata = {key: task[key] for key in ('year', 'round', 'event', 'session')}
    laps = extract_lap_details(session, metadata)
    if laps.empty or 'Driver' not in laps or not laps.Driver.notna().any():
        raise ValueError('Usable lap/driver data is unavailable.')
    tables = {'laps': laps}
    if not _get_session_dataframe(session, 'results').empty:
        tables['results'] = _extract_results(session, metadata)
    weather = _get_session_dataframe(session, 'weather_data')
    if not weather.empty:
        try:
            origin = pd.to_datetime(getattr(session, 't0_date', None), utc=True, errors='coerce')
        except Exception:
            # FastF1 only calculates t0_date when telemetry was loaded.
            origin = pd.NaT
        if pd.notna(origin) and 'Time' in weather:
            weather = weather.copy()
            weather['ObservedAtUtc'] = origin + pd.to_timedelta(weather.Time, errors='coerce')
        tables.update(weather=_extract_weather(session, metadata), weather_samples=_with_metadata(weather, metadata))
    session_status = _get_session_dataframe(session, 'session_status')
    if not session_status.empty:
        tables['session_status'] = _with_metadata(session_status, metadata)
    messages = _get_session_dataframe(session, 'race_control_messages')
    track_status = _get_session_dataframe(session, 'track_status')
    if not messages.empty or not track_status.empty:
        tables['race_control'] = _extract_race_control(session, metadata)
    if not messages.empty:
        tables['race_control_messages'] = _with_metadata(messages, metadata)
    if not track_status.empty:
        tables['track_status'] = _with_metadata(track_status, metadata)
    if task['session'] in {'R', 'S'}:
        tables['strategy'] = _with_metadata(extract_actual_strategy_from_session(session, metadata), metadata)
    missing = [key for key in ('results', 'weather', 'race_control') if key not in tables or tables[key].empty]
    if telemetry:
        for prefix, attribute in [('car', 'car_data'), ('position', 'pos_data')]:
            try:
                frames = getattr(session, attribute)
            except DataNotLoadedError:
                frames = {}
            for driver, frame in frames.items():
                if not frame.empty:
                    tables[f'{prefix}_{_safe_slug(driver)}'] = frame.copy()
        if not any(key.startswith('car_') for key in tables) or not any(key.startswith('position_') for key in tables):
            missing.append('telemetry')
    venue = venue_for_context(metadata, event_data=session.event)
    if race_quality:
        venue['race_quality'] = race_quality
    return tables, venue, missing


def save_partition(path, task, config, tables, venue, missing):
    if not any(not frame.empty for frame in tables.values()):
        raise ValueError('No usable data was returned; the session was not saved.')
    version = path/'versions'/uuid4().hex[:12]
    version.mkdir(parents=True, exist_ok=False)
    files = {}
    for key, frame in tables.items():
        if frame.empty:
            continue
        file = version/f'{key}.csv.gz'
        frame.to_csv(file, index=False, compression='gzip')
        files[str(file.relative_to(path))] = {'table': key, 'rows': len(frame), 'bytes': file.stat().st_size, 'sha256': sha256(file)}
    saved = {**task, 'schema_version': 1, 'status': 'complete', 'mode': config['mode'], 'files': files,
             'provider': 'FastF1' if config['mode'] == 'detailed' else 'Jolpica', 'venue': venue,
             'telemetry_requested': config['telemetry'], 'unavailable_optional_tables': missing,
             'telemetry_available': config['telemetry'] and 'telemetry' not in missing,
             'downloaded_at_utc': datetime.now(timezone.utc).isoformat()}
    write_json(version/'provenance.json', saved)
    # Commit the pointer only when every file is durable. Previous versions stay intact.
    write_json(path/'session.json', saved)


def download(root, job_folder, payload, *, discover_fn=None, fetch_fn=None, pause_seconds=1):
    from src.app_services.request_meter import monitor_requests
    with monitor_requests(job_folder) as meter:
        return _download(root, job_folder, payload, discover_fn=discover_fn,
                         fetch_fn=fetch_fn, pause_seconds=pause_seconds, meter=meter)


def _download(root, job_folder, payload, *, discover_fn=None, fetch_fn=None, pause_seconds=1, meter):
    config = options(payload)
    discover_fn, fetch_fn = discover_fn or discover, fetch_fn or fetch
    root, job_folder = Path(root), Path(job_folder)
    progress = {'status': 'discovering', 'total': 0, 'processed': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0,
                'years': config['years'], 'current': 'Loading calendars', 'errors': [], 'incomplete_telemetry': 0}
    access_failures = 0
    def publish():
        meter.publish()
        write_json(job_folder/'download_progress.json', progress)
    def stopped():
        return (job_folder/'stop_requested').exists()
    publish()
    tasks = []
    for year in config['years']:
        if stopped():
            break
        progress['current'] = f'Loading {year} calendar'
        publish()
        try:
            tasks.extend(discover_fn(root, year, config['mode'], config['sessions']))
        except Exception as exc:
            progress['failed'] += 1
            progress['errors'].append({'year': year, 'message': str(exc)})
            if rate_limited(exc):
                progress['status'] = 'paused'
                break
    progress['total'] = len(tasks)
    if progress['status'] == 'paused':
        publish()
        write_json(job_folder/'download_result.json', progress)
        return progress
    progress['status'] = 'downloading'
    if not tasks and not progress['failed'] and not stopped():
        progress['status'] = 'no_data'
        progress['current'] = 'No eligible prior-day sessions found for the selected seasons.'
        publish()
        write_json(job_folder/'download_result.json', progress)
        return progress
    publish()
    for task in tasks:
        if stopped():
            progress['status'] = 'cancelled'
            break
        path = library_root(root)/str(task['year'])/config['mode']/f"{task['round']:02d}_{_safe_slug(task['event'])}_{task['session']}"
        progress['current'] = f"{task['year']} · {task['event']} · {task['session']}"
        publish()
        if complete(path, config['telemetry'], verify=True):
            progress['skipped'] += 1
            print(f"Already saved: {progress['current']}", flush=True)
        else:
            meter.begin_session()
            missing = []
            try:
                print(f"Downloading {progress['current']}", flush=True)
                tables, venue, missing = fetch_fn(task, config['mode'], config['telemetry'])
                save_partition(path, task, config, tables, venue, missing)
                progress['downloaded'] += 1
                if 'telemetry' in missing:
                    progress['incomplete_telemetry'] += 1
                    progress['errors'].append({**task, 'message': 'Session saved, but requested telemetry is incomplete. Retry to add telemetry.'})
            except Exception as exc:
                error = {**task, 'message': meter.provider_issue() or str(exc)}
                path.mkdir(parents=True, exist_ok=True)
                write_json(path/'last_error.json', error)
                progress['failed'] += 1
                progress['errors'].append(error)
                print(f"Unavailable: {progress['current']} · {exc}", flush=True)
                if rate_limited(exc):
                    progress['status'] = 'paused'
                    progress['pause_reason'] = 'Provider request limit reached. Wait before resuming; saved sessions will be skipped.'
            issue = meter.provider_issue()
            access_failures = access_failures + 1 if issue else 0
            if issue and 'telemetry' in missing:
                progress['errors'][-1]['message'] += ' ' + issue
            if access_failures >= 2:
                progress['status'] = 'paused'
                progress['pause_reason'] = issue
            if pause_seconds:
                time.sleep(pause_seconds)
        progress['processed'] += 1
        publish()
        if progress['status'] == 'paused':
            break
    if stopped():
        progress['status'] = 'cancelled'
    elif progress['status'] != 'paused':
        progress['status'] = 'partial' if progress['failed'] or progress['incomplete_telemetry'] else 'completed'
    publish()
    write_json(job_folder/'download_result.json', progress)
    return progress


def rate_limited(exc):
    text = str(exc).lower()
    return any(word in text for word in ('rate limit', 'rate-limit', 'ratelimit', '429', '500 calls/h', 'too many requests'))


def inventory(root):
    library = library_root(root)
    rows, totals = [], {'sessions': 0, 'rows': 0, 'bytes': 0}
    for year in sorted(library.glob('[0-9][0-9][0-9][0-9]'), reverse=True):
        for mode in ('detailed', 'results'):
            complete_count, failures, table_rows, bytes_used, last = 0, 0, {}, 0, ''
            for folder in (year/mode).glob('*'):
                saved = read_json(folder/'session.json')
                if complete(folder):
                    complete_count += 1
                    if saved.get('telemetry_requested') and not saved.get('telemetry_available', True):
                        failures += 1
                    last = max(last, saved['downloaded_at_utc'])
                    for info in saved['files'].values():
                        table_rows[info['table']] = table_rows.get(info['table'], 0) + info['rows']
                        bytes_used += info['bytes']
                elif (folder/'last_error.json').exists() or saved:
                    failures += 1
            if complete_count or failures:
                rows.append({'year': int(year.name), 'mode': mode, 'sessions': complete_count, 'needs_retry': failures,
                             'lap_rows': table_rows.get('laps', 0), 'result_rows': table_rows.get('results', 0),
                             'bytes': bytes_used, 'last_download_utc': last})
                totals['sessions'] += complete_count
                totals['rows'] += sum(table_rows.values())
                totals['bytes'] += bytes_used
    return {'root': str(library), 'seasons': rows, 'totals': totals, 'free_bytes': shutil.disk_usage(root).free,
            'current_year': datetime.now(timezone.utc).year}


def preview(root, year, mode, table, page=1):
    config = options({'years': [year], 'mode': mode})
    if table not in TABLES:
        raise ValueError('Choose an available archive table.')
    frames, total = [], 0
    page = max(1, int(page))
    for pointer in sorted((library_root(root)/str(config['years'][0])/mode).glob('*/session.json')):
        saved = read_json(pointer)
        for file, info in partition_files(pointer.parent, saved):
            if info['table'] == table:
                start, end = total, total + info['rows']
                if end > (page-1)*20 and start < page*20:
                    frame = pd.read_csv(file, nrows=min(info['rows'], page*20-start))
                    frames.append(frame.iloc[max(0, (page-1)*20-start):])
                total = end
    frame = pd.concat(frames, ignore_index=True).head(20) if frames else pd.DataFrame()
    return {'columns': frame.columns.tolist(), 'rows': json.loads(frame.to_json(orient='records')),
            'page': page, 'pages': max(1, (total+19)//20), 'total_rows': total}


def export(root, payload):
    config = options({'years': payload.get('years', []), 'mode': payload.get('mode', 'detailed')})
    destination = library_root(root)/'exports'/f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}"
    inputs = []
    schemas = {}
    for year in config['years']:
        for pointer in sorted((library_root(root)/str(year)/config['mode']).glob('*/session.json')):
            if not complete(pointer.parent, verify=True):
                raise ValueError('Archive files changed or are missing. Resume the download to repair them before export.')
            for file, info in partition_files(pointer.parent, read_json(pointer)):
                if info['table'] in TABLES:
                    inputs.append((file, info['table']))
                    schemas.setdefault(info['table'], {})
                    schemas[info['table']].update(dict.fromkeys(pd.read_csv(file, nrows=0).columns))
    if not inputs:
        raise ValueError('Download at least one selected season before exporting.')
    destination.mkdir(parents=True, exist_ok=False)
    written = set()
    for file, table in inputs:
        for chunk in pd.read_csv(file, chunksize=10000):
            name = EXPORT_NAMES[table] if config['mode'] == 'detailed' else 'race_classifications'
            chunk.reindex(columns=list(schemas[table])).to_csv(destination/f'{name}.csv', index=False,
                mode='a' if table in written else 'w', header=table not in written)
            written.add(table)
    write_json(destination/'export.json', {'years': config['years'], 'mode': config['mode'],
               'created_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'complete', 'source_files': len(inputs),
               'model_training_performed': False, 'uploaded': False})
    return {'folder': str(destination), 'files': sorted(f'{EXPORT_NAMES[table]}.csv' if config['mode'] == 'detailed' else 'race_classifications.csv' for table in written), 'uploaded': False}
