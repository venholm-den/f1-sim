"""Original-run weather archive, with separate availability and observation gates."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.race_weather import CORE_VARIABLES, analyse_windows, utc, _hourly

ENDPOINT = 'https://single-runs-api.open-meteo.com/v1/forecast'


def collect_run(request, output, get=None):
    """Initialisation before cutoff alone does not prove public availability."""
    run, cutoff, start = (utc(request[key]) for key in ('RunUtc', 'CutoffUtc', 'ScheduledStartUtc'))
    if not run < cutoff < start:
        raise ValueError('Require model initialisation < forecast cutoff < scheduled race start.')
    if start + pd.Timedelta(hours=4) > run + pd.Timedelta(days=10):
        raise ValueError('Race window exceeds the requested original-run horizon.')
    lat, lon = float(request['Latitude']), float(request['Longitude'])
    if not np.isfinite([lat, lon]).all() or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid circuit coordinates.')
    if not request.get('CircuitId') or not request.get('LayoutId'):
        raise ValueError('Physical circuit and layout identity are required.')
    available = request.get('RunAvailableAtUtc')
    evidence = request.get('AvailabilitySourceURL')
    known_available = bool(available and evidence and utc(available) >= run and utc(available) <= cutoff)
    params = {'latitude': lat, 'longitude': lon, 'models': request.get('Model') or 'ecmwf_ifs025',
              'timezone': 'GMT', 'wind_speed_unit': 'ms', 'hourly': ','.join(CORE_VARIABLES),
              'run': run.strftime('%Y-%m-%dT%H:%M'), 'forecast_days': 10}
    response = (get or requests.get)(ENDPOINT, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    _hourly(payload)
    units = payload.get('hourly_units', {})
    if units.get('precipitation') != 'mm' or units.get('wind_speed_10m') != 'm/s':
        raise ValueError('Unexpected weather units.')
    raw = {'forecast': {'endpoint': ENDPOINT, 'parameters': params, 'payload': payload,
                        'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}}
    scenarios = analyse_windows(raw, start)
    complete = all(s.get('best_match', {}).get('simulation_usable', False) for s in scenarios)
    report = {'request': request, 'scenarios': scenarios,
              'availability_verified': known_available,
              'eligible_for_training': known_available and complete and request.get('ArchiveKind') == 'original_operational',
              'validation_type': 'archived_run_replay; availability unverified' if not known_available else 'archived_run_replay',
              'delay_probability': None, 'activated': False}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw_path = output/'raw.json'
    raw_path.write_text(json.dumps(raw, indent=2), encoding='utf-8')
    report['raw_sha256'] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def validate_identity(request, venues):
    required = {'year', 'round', 'event', 'circuit_id', 'layout_id', 'latitude', 'longitude'}
    if not required.issubset(venues):
        raise ValueError('Saved physical venue evidence is unavailable.')
    selected = venues[venues.year.eq(request['Year']) & venues['round'].eq(request['Round']) & venues.event.eq(request['Event'])]
    identities = selected[['circuit_id', 'layout_id', 'latitude', 'longitude']].drop_duplicates()
    if len(identities) != 1:
        raise ValueError('Weather request has missing or ambiguous saved venue identity.')
    saved = identities.iloc[0]
    if saved.circuit_id != request['CircuitId'] or saved.layout_id != request['LayoutId'] or not np.allclose(
            [float(saved.latitude), float(saved.longitude)], [float(request['Latitude']), float(request['Longitude'])], atol=1e-6, rtol=0):
        raise ValueError('Weather coordinates must match the saved physical circuit/layout.')


def pair_samples(raw, samples, start):
    """Pair temperature/wind at actual UTC sample times, never relative times.

    Binary FastF1 Rainfall observations cannot verify precipitation amounts.
    """
    columns = ['ObservedAtUtc', 'variable', 'forecast', 'observed', 'error']
    if samples.empty or 'ObservedAtUtc' not in samples:
        return pd.DataFrame(columns=columns)
    frame = _hourly(raw['forecast']['payload'])
    start = utc(start)
    times = pd.to_datetime(samples.ObservedAtUtc, utc=True, errors='coerce')
    selected = samples[times.ge(start) & times.le(start+pd.Timedelta(hours=2))].copy()
    selected['_utc'] = times.loc[selected.index]
    rows = []
    for variable, observed in [('temperature_2m', 'AirTemp'), ('wind_speed_10m', 'WindSpeed')]:
        if variable not in frame or observed not in selected:
            continue
        for _, row in selected.iterrows():
            stamp = row['_utc']
            lower, upper = stamp.floor('h'), stamp.ceil('h')
            if lower not in frame.index or upper not in frame.index:
                continue
            lo, hi, actual = frame.loc[lower, variable], frame.loc[upper, variable], pd.to_numeric(row[observed], errors='coerce')
            if not np.isfinite([lo, hi, actual]).all():
                continue
            fraction = (stamp-lower).total_seconds()/3600
            forecast = float(lo + fraction*(hi-lo))
            rows.append({'ObservedAtUtc': stamp.isoformat(), 'variable': variable,
                         'forecast': forecast, 'observed': float(actual), 'error': forecast-float(actual)})
    return pd.DataFrame(rows, columns=columns)
