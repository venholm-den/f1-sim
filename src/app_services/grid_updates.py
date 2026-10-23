"""Compare a saved forecast with publication-aware FIA starting-grid evidence.

This reports freshness; it never overlays new positions onto old probabilities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.data_sources.fia_documents import build_fia_context
from src.grid import _extract_fia_official_grid


def forecast_grid_status(root, output_dir, context, *, index_path=None, cutoff=None):
    root, folder = Path(root), Path(output_dir)
    stamp = pd.Timestamp(cutoff or pd.Timestamp.now(tz='UTC'))
    result = {'status': 'unavailable', 'checked_at_utc': stamp.isoformat(), 'changes': []}
    try:
        if stamp.tzinfo is None:
            raise ValueError('Grid update cutoff must be timezone aware.')
        race_start = pd.to_datetime(context.get('race_start_utc'), utc=True, errors='coerce')
        result['refresh_allowed'] = bool(pd.notna(race_start) and stamp < race_start)
        # A desktop review after the race must not acquire hindsight evidence.
        asof = min(stamp, race_start - pd.Timedelta(nanoseconds=1)) if pd.notna(race_start) else stamp
        if folder.name == 'source' and (folder.parent/'frozen/features.csv').is_file():
            folder = folder.parent
        candidates = [folder/'frozen/features.csv', folder/'driver_model_features.csv', folder/'features.csv']
        feature_path = next((path for path in candidates if path.is_file()), None)
        if feature_path is None:
            return {**result, 'status': 'no_saved_grid'}
        features = pd.read_csv(feature_path)
        if not {'Driver','grid_position'}.issubset(features) or features.Driver.duplicated().any():
            return {**result, 'status': 'no_saved_grid'}
        positions = pd.to_numeric(features.grid_position, errors='coerce')
        if positions.isna().any() or not positions.eq(positions.round()).all():
            return {**result, 'status': 'no_saved_grid'}
        saved = dict(zip(features.Driver.astype(str), positions.astype(int)))
        result['saved_grid_source'] = 'fia_official_grid' if ('grid_source' in features and features.grid_source.eq('fia_official_grid').all()) else 'saved_model_grid'
        path = Path(index_path) if index_path else root/'data/fia_documents/fia_document_index.csv'
        if not path.is_file():
            return {**result, 'status': 'no_verified_grid'}
        evidence = build_fia_context(year=int(context['year']), event=context['event'],
                                    path=str(path), cutoff=asof.isoformat(), safe_asof=True)
        grid = _extract_fia_official_grid(evidence)
        if grid.empty or set(grid.Driver) != set(saved):
            return {**result, 'status': 'no_verified_grid'}
        latest = dict(zip(grid.Driver, grid.fia_grid_position.astype(int)))
        pit_lane = dict(zip(grid.Driver, grid.fia_pit_lane_start))
        saved_pit = dict(zip(features.Driver, features.get('fia_pit_lane_start', pd.Series(False, index=features.index)).astype(str).str.lower().eq('true')))
        canonical = sorted((driver, position, bool(pit_lane[driver])) for driver, position in latest.items())
        changes = [{'Driver':driver, 'saved_position':saved[driver], 'latest_position':position,
                    'pit_lane_start':bool(pit_lane[driver])}
                   for driver, position in latest.items()
                   if position != saved[driver] or bool(pit_lane[driver]) != bool(saved_pit[driver])]
        row = grid.iloc[0]
        return {**result, 'status':'grid_update_available' if changes else 'current_grid',
                'fingerprint':hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
                'document_title':str(row.fia_grid_source),
                'document_url':str(row.fia_grid_document_url),
                'published_at':str(row.fia_grid_published_at),
                'positions':latest, 'changes':changes}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {**result, 'error_type':type(exc).__name__}


def validate_grid_revision(folder, revision):
    """Fail before completing a revision that did not apply its promised grid."""
    features = pd.read_csv(Path(folder)/'frozen/features.csv')
    actual = dict(zip(features.Driver, pd.to_numeric(features.grid_position, errors='raise').astype(int)))
    if actual != revision['positions'] or not features.grid_source.eq('fia_official_grid').all():
        raise ValueError('FIA grid revision was not applied to the complete forecast roster.')
