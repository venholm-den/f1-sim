"""Whole-season replay packets built from the saved historical library.

A packet holds the three tables the offline candidate benchmarks read
(scripts.benchmark_safety_car and scripts.promotion_check): per-race pace
features, race classifications and a race-control summary. It is built only
from race sessions already in <workspace>/data/historical_library, with each
consumed table hash-checked against its session manifest, so earlier seasons
can be scored without network access. Drivers who did not start (no
classified position) are left out of the classification. Pace features come
from build_driver_features on the saved laps, as in the recent-baseline
packets.

SC and VSC counts are read from the track-status feed between the first lap
start and the leader's finish. One neutralised run of codes 4/6/7 is one
phase; a run that includes code 4 counts as an SC, so a VSC upgraded to an SC
counts once, as an SC.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.features import build_driver_features

TABLES = ('laps', 'results', 'track_status')
NEUTRAL = {'4', '6', '7'}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(manifest_path: Path, manifest: dict) -> dict:
    folder = manifest_path.parent.resolve()
    frames = {}
    for name, info in manifest.get('files', {}).items():
        table = info.get('table')
        if table not in TABLES:
            continue
        file = (folder / name.replace('\\', '/')).resolve()
        if not file.is_relative_to(folder) or not file.is_file():
            raise ValueError(f'Invalid {table} path.')
        if file.stat().st_size != info['bytes'] or _sha256(file) != info['sha256']:
            raise ValueError(f'Changed {table} file.')
        frames[table] = pd.read_csv(file)
    missing = set(TABLES) - set(frames)
    if missing:
        raise ValueError(f"Missing {', '.join(sorted(missing))}.")
    return frames


def neutralisation_counts(laps: pd.DataFrame, track_status: pd.DataFrame) -> dict:
    """SC and VSC phases from the track-status feed during the race."""
    timing = laps[['LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds']].apply(pd.to_numeric, errors='coerce').dropna()
    timing = timing[(timing.LapTimeSeconds > 0) & (timing.LapNumber >= 1)]
    if timing.empty:
        raise ValueError('No lap timing.')
    start = float(timing.LapStartTimeSeconds.min())
    last = timing[timing.LapNumber.eq(timing.LapNumber.max())]
    end = float((last.LapStartTimeSeconds + last.LapTimeSeconds).min())
    feed = pd.DataFrame({'time': pd.to_timedelta(track_status.Time, errors='coerce').dt.total_seconds(),
                         'code': track_status.Status.astype(str).str.strip().str.removesuffix('.0')})
    feed = feed.dropna(subset=['time']).sort_values('time', kind='stable')
    initial = feed[feed.time <= start].tail(1)
    if initial.empty:
        raise ValueError('Track-status initial state unavailable.')
    codes = pd.concat([initial, feed[(feed.time > start) & (feed.time <= end)]]).code.tolist()
    sc = vsc = 0
    phase = None
    for code in codes + ['1']:
        if code in NEUTRAL:
            phase = (phase or set()) | {code}
        elif phase is not None:
            sc, vsc = (sc + 1, vsc) if '4' in phase else (sc, vsc + 1)
            phase = None
    return {'safety_car_flag': sc > 0, 'vsc_flag': vsc > 0, 'sc_count': sc, 'vsc_count': vsc}


def build_season_packet(workspace, year: int, destination) -> dict:
    """Write one season's packet; returns a small report with skipped races."""
    destination = Path(destination)
    library = Path(workspace) / 'data' / 'historical_library' / str(year) / 'detailed'
    paths = sorted(library.glob('*_R/session.json'))
    if not paths:
        raise ValueError(f'No saved {year} race sessions under {library}.')
    features, results, control, skipped = [], [], [], []
    for path in paths:
        manifest = json.loads(path.read_text(encoding='utf-8'))
        identity = {'Year': manifest.get('year'), 'Round': manifest.get('round'), 'Event': manifest.get('event')}
        try:
            if manifest.get('session') != 'R' or manifest.get('status') != 'complete' or manifest.get('year') != year:
                raise ValueError('Not a complete race session for this season.')
            frames = _read(path, manifest)
            classified = frames['results'][pd.to_numeric(frames['results'].Position, errors='coerce').notna()].copy()
            positions = sorted(classified.Position.astype(int))
            if positions != list(range(1, len(positions) + 1)):
                raise ValueError('Incomplete classification.')
            pace = build_driver_features(frames['laps'])
            if pace.empty:
                raise ValueError('No usable race pace features.')
            counts = neutralisation_counts(frames['laps'], frames['track_status'])
        except (ValueError, KeyError, OSError, pd.errors.ParserError) as exc:
            skipped.append({**identity, 'reason': str(exc)})
            continue
        features.append(pace.assign(source_year=year, source_round=identity['Round'], source_event=identity['Event']))
        results.append(classified.assign(Year=year, Round=identity['Round'], Event=identity['Event'])[
            ['Year', 'Round', 'Event', 'Abbreviation', 'TeamName', 'Position', 'GridPosition']])
        control.append({**identity, **counts})
    if not control:
        raise ValueError(f'No usable {year} races.')
    destination.mkdir(parents=True, exist_ok=False)
    pd.concat(features, ignore_index=True).to_csv(destination / 'baseline_race_features.csv', index=False)
    pd.concat(results, ignore_index=True).to_csv(destination / 'fastf1_race_results.csv', index=False)
    pd.DataFrame(control).to_csv(destination / 'fastf1_race_control_summary.csv', index=False)
    report = {'year': year, 'races': len(control), 'skipped': skipped,
              'safety_car_races': int(sum(row['safety_car_flag'] for row in control)),
              'vsc_races': int(sum(row['vsc_flag'] for row in control))}
    (destination / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
