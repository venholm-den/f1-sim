"""Explicit, checksum-verified archived Q classifications for offline replay.

Saved feeds can contain later corrections. This adapter does not prove original
publication times, fetch remote data, or change the FastF1 cache.
"""
from __future__ import annotations

from copy import copy
from pathlib import Path
import hashlib
import json

import pandas as pd


def read_qualifying_archive(path):
    path = Path(path)
    if path.is_file():
        frame = pd.read_csv(path)
        frame['ClassificationArchiveSHA256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        from src.app_services.historical_library import partition_files, sha256
        frames = []
        for pointer in sorted(path.glob('*/detailed/*/session.json')):
            saved = json.loads(pointer.read_text(encoding='utf-8'))
            if saved.get('session') != 'Q' or saved.get('status') != 'complete':
                continue
            for file, info in partition_files(pointer.parent, saved):
                if info.get('table') != 'results':
                    continue
                if sha256(file) != info['sha256']:
                    raise ValueError('Qualifying archive checksum mismatch.')
                row = pd.read_csv(file).assign(Year=saved['year'], Round=saved['round'],
                    Event=saved['event'], Session='Q', ClassificationArchiveSHA256=info['sha256'])
                frames.append(row)
        if not frames:
            raise ValueError('No saved qualifying classifications in the selected archive.')
        frame = pd.concat(frames, ignore_index=True)
    required = {'Year', 'Round', 'Event', 'Session', 'Abbreviation', 'Position'}
    if not required.issubset(frame):
        raise ValueError('Qualifying archive is missing classification keys.')
    frame = frame.loc[frame.Session.eq('Q')].copy()
    if frame.duplicated(['Year', 'Round', 'Event', 'Abbreviation']).any():
        raise ValueError('Ambiguous duplicate qualifying archive classifications.')
    return frame


def with_qualifying_classification(session, metadata, archive):
    if metadata.get('session') != 'Q' or session is None:
        return session
    selected = archive.loc[archive.Year.eq(metadata['year']) & archive.Round.eq(metadata['round'])
                           & archive.Event.eq(metadata['event'])].copy()
    if selected.empty:
        return session
    current = session.results.copy()
    ranks = pd.to_numeric(selected.Position, errors='coerce')
    if (set(selected.Abbreviation) != set(current.Abbreviation) or ranks.isna().any()
            or sorted(ranks) != list(range(1, len(selected) + 1))):
        return session  # No partial fill, fabricated order or mixed versions.
    old = pd.to_numeric(current.Position, errors='coerce')
    positions = selected.set_index('Abbreviation').Position
    mapped = current.Abbreviation.map(positions)
    if old.notna().any() and not old[old.notna()].eq(mapped[old.notna()]).all():
        raise ValueError('Cached and archived qualifying classifications conflict.')
    current['Position'] = mapped.to_numpy()
    current['ClassificationArchiveSHA256'] = current.Abbreviation.map(
        selected.set_index('Abbreviation').ClassificationArchiveSHA256).to_numpy()
    current['ClassificationSource'] = 'explicit_saved_Q_archive_retrospective'
    cloned = copy(session)
    if hasattr(cloned, '_results'):
        cloned._results = current
    else:
        cloned.results = current
    return cloned


def attach_archive(races, path):
    from src.accuracy_benchmark import ReplayRace
    archive = read_qualifying_archive(path)
    output = []
    for race in races:
        sessions = dict(race.sessions)
        if 'Q' in sessions:
            sessions['Q'] = with_qualifying_classification(sessions['Q'],
                dict(year=race.year, round=race.round, event=race.event, session='Q'), archive)
        output.append(ReplayRace(race.year, race.round, race.event, sessions))
    return output
