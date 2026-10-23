"""Pinned empirical SC/VSC schedules for the shadow agent model.

Whole race schedules preserve event clustering and known zero-event races.
TrackStatus is the timing feed label; missing coverage and red-flag races are
excluded, never treated as green. Pace/compression/restart parameters are still
assumptions. No incident or retirement coupling is inferred from these labels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VERSION = 'neutralisation_empirical_v1'


def race_schedule(session):
    laps = pd.DataFrame(session.laps)
    status = pd.DataFrame(getattr(session, 'track_status', None))
    weather = pd.DataFrame(getattr(session, 'weather_data', None))
    if ('Rainfall' not in weather or not weather.Rainfall.notna().any()
            or weather.Rainfall.dropna().astype(bool).any()):
        raise ValueError('Dry candidate requires known dry historical race weather.')
    if not {'LapNumber', 'LapStartTime', 'Time'}.issubset(laps) or not {'Time', 'Status'}.issubset(status):
        raise ValueError('Missing race/track-status coverage.')
    start = pd.to_timedelta(laps.loc[laps.LapNumber.eq(1), 'LapStartTime']).min().total_seconds()
    end = pd.to_timedelta(laps.Time).max().total_seconds()
    times = pd.to_timedelta(status.Time).dt.total_seconds()
    labels = status.Status.astype(str)
    if (not np.isfinite([start, end]).all() or end <= start or times.isna().any()
            or times.duplicated().any() or not times.is_monotonic_increasing
            or times.min() > start or not labels.isin(['1', '2', '4', '6', '7']).all()):
        raise ValueError('Incomplete, ambiguous or unsupported (including red flag) status history.')
    events = []
    for index, (time, label) in enumerate(zip(times, labels)):
        stop = float(times.iloc[index + 1]) if index + 1 < len(times) else end
        left, right = max(start, time), min(end, stop)
        kind = 'SC' if label == '4' else 'VSC' if label in ('6', '7') else None
        if kind is None or right <= left:
            continue
        if events and events[-1]['kind'] == kind and np.isclose(events[-1]['end_fraction'], (left-start)/(end-start)):
            events[-1]['end_fraction'] = (right-start)/(end-start)
        else:
            events.append({'kind': kind, 'start_fraction': (left-start)/(end-start),
                           'end_fraction': (right-start)/(end-start)})
    return events


def fit_neutralisation(history, context):
    target = int(context['year']), int(context['round'])
    circuit = (context.get('venue') or {}).get('circuit_id')
    schedules = []; excluded = []; seen = set()
    for metadata, sessions in history:
        key = int(metadata['year']), int(metadata['round'])
        if key >= target or key in seen:
            raise ValueError('Neutralisation training requires unique, strictly earlier races.')
        seen.add(key)
        try:
            events = race_schedule(sessions['R'])
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            excluded.append({'race': list(key), 'reason': str(exc)})
            continue
        schedules.append({'race': list(key), 'circuit_id': (metadata.get('venue') or {}).get('circuit_id'),
                          'events': events})
    if not schedules:
        raise ValueError('No covered SC/VSC timing labels in pinned history; arm skipped.')
    local = np.array([bool(circuit) and s['circuit_id'] == circuit for s in schedules])
    # Fixed shrinkage prior: five pooled race equivalents, not a tuned parameter.
    mix = float(local.sum() / (local.sum() + 5.))
    weights = np.full(len(schedules), (1-mix)/len(schedules))
    if local.any():
        weights += local * mix/local.sum()
    return {'version': VERSION, 'target': list(target), 'schedules': schedules,
            'weights': weights.tolist(), 'excluded': excluded, 'circuit_weight': mix,
            'label_source': 'FastF1 track_status; missing/red-flag races excluded',
            'limitations': ['Resampled elapsed-race fractions; no incident/DNF coupling',
                           'SC speed, queue gap, pit discount and restart response are assumptions']}


def validate_events(events):
    previous = -1.
    for event in events:
        start, end = event['start_seconds'], event['end_seconds']
        if (event['kind'] not in ('SC', 'VSC') or not np.isfinite([start, end]).all()
                or start < previous or not 0 <= start < end):
            raise ValueError('SC/VSC events must be finite, ordered and disjoint.')
        previous = end


def sample_schedules(model, explicit_events, reference_seconds, seed):
    """Return per-race event arrays; empty history is never fabricated as green."""
    references = np.asarray(reference_seconds, dtype=float)
    if not np.isfinite(references).all() or (references <= 0).any():
        raise ValueError('Invalid reference race durations.')
    if model is not None and explicit_events:
        raise ValueError('Choose empirical or explicit events, not both.')
    if model is None:
        validate_events(explicit_events)
        schedules = [list(explicit_events) for _ in references]
    else:
        rows = model['schedules']; weights = np.asarray(model['weights'], dtype=float)
        if (model.get('version') != VERSION or not rows or weights.shape != (len(rows),)
                or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1)):
            raise ValueError('Invalid empirical neutralisation model.')
        for row in rows:
            validate_events([{'kind': e['kind'], 'start_seconds': e['start_fraction'],
                              'end_seconds': e['end_fraction']} for e in row['events']])
            if any(e['end_fraction'] > 1 for e in row['events']):
                raise ValueError('Event fractions exceed the race window.')
        rng = np.random.default_rng(np.random.SeedSequence([seed, 6185]))
        selected = rng.choice(len(rows), len(references), p=weights)
        schedules = [[{'kind': e['kind'], 'start_seconds': e['start_fraction']*duration,
                       'end_seconds': e['end_fraction']*duration} for e in rows[index]['events']]
                     for index, duration in zip(selected, references)]
    count = max((len(s) for s in schedules), default=0)
    starts = np.full((len(references), count), np.inf); ends = starts.copy()
    kinds = np.zeros(starts.shape, dtype=int)
    for sim, events in enumerate(schedules):
        for index, event in enumerate(events):
            starts[sim, index], ends[sim, index] = event['start_seconds'], event['end_seconds']
            kinds[sim, index] = 1 if event['kind'] == 'SC' else 2
    return starts, ends, kinds
