"""Replay a downloaded session and review lap telemetry from the local archive.

Everything here reads the historical library only. Car and position telemetry
are optional downloads, so every payload says what it could and could not use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.app_services import archive_telemetry, historical_library as library

SESSION_ORDER = {code: index for index, code in enumerate(library.SESSIONS)}
RACE_SESSIONS = {'R', 'S'}
# Position samples further apart than this are a gap (garage, pit box or lost signal).
MAX_GAP_SECONDS = 5.0
MAX_TRACE_POINTS = 1500


def _tables(saved):
    return {info.get('table') for info in saved.get('files', {}).values()}


def _has_telemetry(tables):
    return any(name.startswith('position_') for name in tables) and any(name.startswith('car_') for name in tables)


def sessions(root):
    """Saved detailed sessions, newest first."""
    found = []
    archive = library.library_root(root)
    for pointer in archive.glob('[0-9][0-9][0-9][0-9]/detailed/*/session.json'):
        saved = library.read_json(pointer)
        if saved.get('status') != 'complete' or not isinstance(saved.get('year'), int):
            continue
        tables = _tables(saved)
        if 'laps' not in tables:
            continue
        found.append({'id': pointer.parent.relative_to(archive).as_posix(), 'year': saved['year'],
                      'round': int(saved.get('round', 0)), 'event': str(saved.get('event', '')),
                      'session': str(saved.get('session', '')), 'telemetry': _has_telemetry(tables)})
    found.sort(key=lambda row: (-row['year'], -row['round'], SESSION_ORDER.get(row['session'], 99)))
    return {'sessions': found}


def _open(root, session_id):
    archive = library.library_root(root).resolve()
    folder = (archive/str(session_id)).resolve()
    parts = folder.relative_to(archive).parts if folder.is_relative_to(archive) else ()
    if len(parts) != 3 or parts[1] != 'detailed':
        raise ValueError('Choose a saved detailed session.')
    saved = library.read_json(folder/'session.json')
    if saved.get('status') != 'complete':
        raise ValueError('This session is not fully downloaded. Resume its download in Historical Data.')
    files = {info['table']: (file, info) for file, info in library.partition_files(folder, saved)}
    return saved, files


def _read(files, table):
    file, info = files[table]
    if library.sha256(file) != info['sha256']:
        raise ValueError('Archived data failed its checksum; resume the download to repair it.')
    return pd.read_csv(file)


def _number(value):
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return ''


def _finite(value):
    value = pd.to_numeric(value, errors='coerce')
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def _flag(value):
    return str(value).strip().lower() in {'true', '1'}


def _drivers_and_laps(laps):
    laps = laps.copy()
    laps['number'] = laps.get('DriverNumber', pd.Series(dtype=object)).map(_number)
    laps = laps[laps.number.ne('')]
    for column in ('LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds', 'TyreLife'):
        laps[column] = pd.to_numeric(laps[column], errors='coerce') if column in laps else np.nan
    laps = laps.dropna(subset=['LapNumber']).sort_values(['number', 'LapNumber'])
    drivers, lap_rows = [], {}
    for number, group in laps.groupby('number', sort=False):
        first = group.iloc[0]
        drivers.append({'number': number, 'code': str(first.get('Driver', number)),
                        'team': str(first.get('Team', '')) if pd.notna(first.get('Team')) else ''})
        starts = group.LapStartTimeSeconds.to_numpy(dtype=float)
        rows = []
        for index, (_, lap) in enumerate(group.iterrows()):
            start, duration = _finite(lap.LapStartTimeSeconds), _finite(lap.LapTimeSeconds)
            # A lap without a recorded time still ends when the next one starts.
            following = starts[index+1] if index+1 < len(starts) and np.isfinite(starts[index+1]) else None
            end = start+duration if start is not None and duration is not None else following
            compound = str(lap.get('Compound', ''))
            rows.append({'lap': int(lap.LapNumber), 'start': start, 'end': end, 'time': duration,
                         's1': _finite(lap.get('Sector1Seconds')), 's2': _finite(lap.get('Sector2Seconds')),
                         's3': _finite(lap.get('Sector3Seconds')),
                         'compound': '' if compound.lower() in {'nan', 'none', ''} else compound,
                         'tyreLife': _finite(lap.TyreLife), 'pitIn': _flag(lap.get('PitIn')),
                         'pitOut': _flag(lap.get('PitOut')), 'deleted': _flag(lap.get('Deleted')),
                         'accurate': _flag(lap.get('IsAccurate', True))})
        lap_rows[number] = rows
    return drivers, lap_rows


def _apply_results(drivers, results):
    """Prefer the classification's names and order the drivers by it."""
    if results is None or results.empty or 'DriverNumber' not in results:
        return drivers
    rows = {_number(row.DriverNumber): row for _, row in results.iterrows()}
    for driver in drivers:
        row = rows.get(driver['number'])
        if row is None:
            continue
        if pd.notna(row.get('TeamName')):
            driver['team'] = str(row.TeamName)
        if pd.notna(row.get('Abbreviation')):
            driver['code'] = str(row.Abbreviation)
        driver['position'] = _finite(row.get('Position'))
    return sorted(drivers, key=lambda driver: (driver.get('position') is None, driver.get('position') or 0))


def _resample(samples, grid):
    """Positions on a fixed time grid; None where the car was not on track."""
    if samples.empty:
        return None
    if 'Status' in samples:
        samples = samples[samples.Status.astype(str).str.lower().eq('ontrack')]
    samples = samples[~(samples.X.eq(0) & samples.Y.eq(0))]
    if len(samples) < 2:
        return None
    seconds = samples.seconds.to_numpy(dtype=float)
    x = np.interp(grid, seconds, samples.X.to_numpy(dtype=float))
    y = np.interp(grid, seconds, samples.Y.to_numpy(dtype=float))
    index = np.clip(np.searchsorted(seconds, grid), 1, len(seconds)-1)
    gap = seconds[index]-seconds[index-1]
    hidden = (grid < seconds[0]) | (grid > seconds[-1]) | (gap > MAX_GAP_SECONDS)
    return [None if off else [int(round(a)), int(round(b))] for a, b, off in zip(x, y, hidden)]


def _track_status(files):
    if 'track_status' not in files:
        return []
    frame = _read(files, 'track_status')
    if 'Time' not in frame:
        return []
    frame = frame.assign(t=archive_telemetry._seconds(frame.Time)).dropna(subset=['t']).sort_values('t')
    return [{'t': float(row.t), 'status': _number(row.get('Status')), 'message': str(row.get('Message', ''))}
            for _, row in frame.iterrows()]


def replay(root, session_id, step=1.0):
    saved, files = _open(root, session_id)
    if 'laps' not in files:
        raise ValueError('This session has no lap data to replay.')
    drivers, laps = _drivers_and_laps(_read(files, 'laps'))
    if not drivers:
        raise ValueError('This session has no usable driver laps.')
    drivers = _apply_results(drivers, _read(files, 'results') if 'results' in files else None)
    starts = [lap['start'] for rows in laps.values() for lap in rows if lap['start'] is not None]
    ends = [lap['end'] for rows in laps.values() for lap in rows if lap['end'] is not None]
    if not starts or not ends:
        raise ValueError('Lap start times are missing, so this session cannot be replayed.')
    begin, finish = float(min(starts)), float(max(ends))
    track = archive_telemetry.layout(root, saved['year'], saved['event'], saved['session'])
    payload = {'id': session_id, 'year': saved['year'], 'round': saved.get('round'), 'event': saved['event'],
               'session': saved['session'], 'race': saved['session'] in RACE_SESSIONS,
               'start': begin, 'end': finish, 'step': step, 'drivers': drivers, 'laps': laps,
               'trackStatus': _track_status(files),
               'outline': [{'x': point['x'], 'y': point['y']} for point in track.get('points', [])],
               'outlineSource': track.get('message', ''), 'positions': {}, 'telemetry': _has_telemetry(set(files))}
    if not any(table.startswith('position_') for table in files):
        payload['positionsMessage'] = ('Car positions were not downloaded for this session. The running order and lap chart '
                                       'use timing data. Download it again in Historical Data with telemetry to see cars on track.')
        return _clean(payload)
    grid = np.arange(begin, finish+step, step)
    for driver in drivers:
        table = 'position_'+driver['number']
        if table in files:
            payload['positions'][driver['number']] = _resample(archive_telemetry._position_samples(_read(files, table)), grid)
    missing = [driver['code'] for driver in drivers if not payload['positions'].get(driver['number'])]
    if missing:
        payload['positionsMessage'] = f"No position data for {', '.join(missing)}."
    return _clean(payload)


def _lap(laps, driver, lap_number):
    rows = laps.get(_number(driver), [])
    lap = next((row for row in rows if row['lap'] == int(lap_number)), None)
    if lap is None or lap['start'] is None or lap['end'] is None:
        raise ValueError('That lap has no recorded start and end time.')
    return lap


def lap_telemetry(root, session_id, driver, lap_number):
    """Speed, throttle, brake, gear, RPM and DRS against distance for one lap."""
    saved, files = _open(root, session_id)
    _, laps = _drivers_and_laps(_read(files, 'laps'))
    lap = _lap(laps, driver, lap_number)
    number = _number(driver)
    if 'car_'+number not in files:
        raise ValueError('Car telemetry was not downloaded for this driver. Download the session again with telemetry.')
    car = _read(files, 'car_'+number)
    time_column = next((name for name in ('SessionTime', 'Time') if name in car), None)
    if not time_column or 'Speed' not in car:
        raise ValueError('Archived car telemetry has no speed or time channel.')
    car = car.assign(seconds=archive_telemetry._seconds(car[time_column]))
    car = car[car.seconds.between(lap['start']-1e-3, lap['end'])].dropna(subset=['seconds']).sort_values('seconds')
    if len(car) < 10:
        raise ValueError('Too few telemetry samples were recorded on this lap.')
    if len(car) > MAX_TRACE_POINTS:
        car = car.iloc[np.unique(np.linspace(0, len(car)-1, MAX_TRACE_POINTS, dtype=int))]
    seconds = car.seconds.to_numpy(dtype=float)
    speed = pd.to_numeric(car.Speed, errors='coerce').ffill().fillna(0).to_numpy(dtype=float)
    # Distance from speed (km/h) integrated over time, as FastF1's add_distance does,
    # measured from the lap's start rather than its first sample.
    distance = np.cumsum(speed/3.6*np.diff(np.r_[lap['start'], seconds]))
    channel = lambda name: pd.to_numeric(car[name], errors='coerce').round(1).tolist() if name in car else None
    brake = [100 if _flag(value) else 0 for value in car.Brake] if 'Brake' in car else None
    lap_distance = distance[-1]+speed[-1]/3.6*max(0.0, lap['end']-seconds[-1])
    trace = {'lapDistance': round(float(lap_distance), 1), 'distance': np.round(distance, 1).tolist(), 'time': np.round(seconds-lap['start'], 3).tolist(),
             'speed': np.round(speed, 1).tolist(), 'throttle': channel('Throttle'), 'brake': brake,
             'gear': channel('nGear'), 'rpm': channel('RPM'), 'drs': channel('DRS'), 'xy': None}
    if 'position_'+number in files:
        position = archive_telemetry._position_samples(_read(files, 'position_'+number))
        position = position[position.seconds.between(lap['start']-1, lap['end']+1)]
        if len(position) >= 2:
            x = np.interp(seconds, position.seconds, position.X)
            y = np.interp(seconds, position.seconds, position.Y)
            trace['xy'] = np.round(np.c_[x, y]).astype(int).tolist()
    payload = {'driver': number, 'lap': lap, 'trace': trace, 'session': saved['session'], 'event': saved['event']}
    return _clean(payload)


def _clean(value):
    """JSON-safe copy: NaN and infinity become None."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
