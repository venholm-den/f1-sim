"""Read a single complete lap's track geometry from the downloaded session archive."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.app_services import historical_library as library


def _seconds(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='coerce')
    return pd.to_timedelta(series, errors='coerce').dt.total_seconds()


def _usable_laps(frame):
    required = {'DriverNumber', 'LapTimeSeconds', 'LapStartTimeSeconds'}
    if not required.issubset(frame):
        return pd.DataFrame()
    frame = frame.copy()
    for column in ('LapTimeSeconds', 'LapStartTimeSeconds'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=list(required))
    frame = frame[frame.LapTimeSeconds.gt(0) & frame.LapStartTimeSeconds.ge(0)]
    for column in ('Deleted', 'PitIn', 'PitOut'):
        if column in frame:
            frame = frame[~frame[column].astype(str).str.lower().isin(['true', '1'])]
    return frame.sort_values('LapTimeSeconds')


def _position_samples(position):
    time_column = next((name for name in ('SessionTime', 'Time') if name in position), None)
    if not time_column or not {'X', 'Y'}.issubset(position):
        return pd.DataFrame()
    position = position.copy()
    position['seconds'] = _seconds(position[time_column])
    for column in ('X', 'Y'):
        position[column] = pd.to_numeric(position[column], errors='coerce')
    position = position.replace([np.inf, -np.inf], np.nan).dropna(subset=['seconds', 'X', 'Y'])
    return position.sort_values('seconds').drop_duplicates('seconds')


def _lap_points(position, lap):
    if position.empty:
        return []
    start, duration = float(lap.LapStartTimeSeconds), float(lap.LapTimeSeconds)
    position = position[position.seconds.between(start, start+duration)]
    position = position[~(position.X.eq(0) & position.Y.eq(0))]
    if 'Status' in position:
        position = position[position.Status.astype(str).str.lower().eq('ontrack')]
    # A short arc or a garage coordinate is not a circuit outline.
    if len(position) < 20 or position.seconds.iloc[0] > start+duration*.03 or position.seconds.iloc[-1] < start+duration*.97:
        return []
    xy = position[['X', 'Y']].to_numpy()
    if np.ptp(xy[:, 0]) < 10 or np.ptp(xy[:, 1]) < 10:
        return []
    distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    if not math.isfinite(distance[-1]) or distance[-1] <= 0:
        return []
    samples = np.unique(np.linspace(0, len(position)-1, min(450, len(position)), dtype=int))
    s1 = pd.to_numeric(lap.get('Sector1Seconds'), errors='coerce')
    s2 = pd.to_numeric(lap.get('Sector2Seconds'), errors='coerce')
    points = []
    for index in samples:
        row = position.iloc[index]
        point = {'x': float(row.X), 'y': float(row.Y), 'progress': float(distance[index]/distance[-1])}
        if pd.notna(s1) and pd.notna(s2) and s1 > 0 and s2 > 0:
            elapsed = row.seconds-start
            point['sector'] = 'S1' if elapsed < s1 else 'S2' if elapsed < s1+s2 else 'S3'
        points.append(point)
    return points


def layout(root, year, event, session='Q', venue=None, *, allow_reference=False):
    year, event, session = int(year), str(event), str(session).upper()
    base = {'year': year, 'event': event, 'requested_session': session, 'session': session,
            'points': [], 'sectors': {}, 'fastestLap': {}, 'source': 'historical_library', 'status': 'data_missing',
            'message': 'No complete archived lap with position telemetry for this race. Download detailed sessions with telemetry.',
            'completion': 'not_recorded'}
    candidates = []
    archive = library.library_root(root)
    pointers = (archive/str(year)/'detailed').glob('*/session.json')
    if allow_reference:
        pointers = archive.glob('[0-9][0-9][0-9][0-9]/detailed/*/session.json')
    for pointer in pointers:
        saved = library.read_json(pointer)
        source_year = saved.get('year')
        if not isinstance(source_year, int) or source_year > year or saved.get('status') != 'complete':
            continue
        saved_venue = saved.get('venue', {})
        reference = source_year != year or saved.get('event') != event
        if reference:
            # Historical geometry is a display reference only. Both identities
            # must be explicit; a missing ID is not evidence of an unchanged layout.
            if (not allow_reference or not venue or venue.get('venue_status') != 'resolved'
                    or saved_venue.get('venue_status') != 'resolved'
                    or any(not venue.get(key) or venue[key] != saved_venue.get(key)
                           for key in ('circuit_id', 'layout_id'))):
                continue
        if venue and any(venue.get(key) and saved_venue.get(key) and venue[key] != saved_venue[key]
                         for key in ('circuit_id', 'layout_id')):
            continue
        if saved_venue.get('venue_status') == 'conflict':
            continue
        priority = [session, 'Q', 'R', 'FP3', 'FP2', 'FP1', 'SQ', 'S']
        rank = (int(reference), -source_year,
                priority.index(saved['session']) if saved['session'] in priority else 99, str(pointer))
        candidates.append((rank, pointer, saved))
    errors = []
    for _, pointer, saved in sorted(candidates, key=lambda item: (item[0], str(item[1]))):
        try:
            files = {info['table']: (file, info) for file, info in library.partition_files(pointer.parent, saved)}
            if 'laps' not in files or not any(table.startswith('position_') for table in files):
                continue
            file, info = files['laps']
            if library.sha256(file) != info['sha256']:
                raise ValueError('Archived lap checksum failed; resume the download to repair it.')
            laps = _usable_laps(pd.read_csv(file))
            loaded = {}
            for _, lap in laps.iterrows():
                number = str(int(float(lap.DriverNumber)))
                table = 'position_'+number
                if table not in files:
                    continue
                if number not in loaded:
                    file, info = files[table]
                    if library.sha256(file) != info['sha256']:
                        raise ValueError('Archived position checksum failed; resume the download to repair it.')
                    loaded[number] = _position_samples(pd.read_csv(file))
                points = _lap_points(loaded[number], lap)
                if not points:
                    continue
                reference = saved['year'] != year or saved['event'] != event
                if reference:
                    return {**base, 'points': [{k: v for k, v in point.items() if k != 'sector'} for point in points],
                            'status': 'available', 'completion': 'reference_geometry',
                            'geometry_year': saved['year'], 'geometry_event': saved['event'],
                            'geometry_session': saved['session'], 'reference_geometry': True,
                            'message': f"Circuit outline reference: {saved['year']} {saved['event']} · {saved['session']}. "
                                       'Matching circuit and layout. Reference outline only; no current-weekend lap or sector times supplied. Forecast inputs are unchanged.'}
                sectors = {}
                for label, column in [('S1', 'Sector1Seconds'), ('S2', 'Sector2Seconds'), ('S3', 'Sector3Seconds')]:
                    if column in laps and 'Driver' in laps:
                        values = pd.to_numeric(laps[column], errors='coerce').dropna()
                        if not values.empty:
                            best = laps.loc[values.idxmin()]
                            sectors[label] = {'driver': str(best.Driver), 'seconds': float(values.min())}
                return {**base, 'points': points, 'status': 'available', 'completion': 'archived_complete',
                        'session': saved['session'], 'geometry_driver': str(lap.get('Driver', number)),
                        'message': f"Downloaded {year} {event} · {saved['session']} · {lap.get('Driver', number)} lap {int(lap.get('LapNumber', 0))}. Geometry only; forecast inputs are unchanged.",
                        'sectors': sectors, 'fastestLap': {'driver': str(laps.iloc[0].get('Driver', '')),
                        'seconds': float(laps.iloc[0].LapTimeSeconds), 'lap': str(laps.iloc[0].get('LapNumber', ''))}}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append(str(exc))
    if errors:
        base.update(status='archive_error', message=errors[0])
    return base
