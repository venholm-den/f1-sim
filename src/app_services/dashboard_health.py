"""Saved-output context and diagnostics, without changing simulation inputs."""
from pathlib import Path
import json

import pandas as pd

from src.app_services.output_index import read_output_table


def output_context(output_dir, year, event, session):
    snapshot = read_output_table(output_dir, 'history/latest_prediction_snapshot.csv', max_rows=1)
    if not snapshot.empty and {'year', 'event', 'session'}.issubset(snapshot.columns):
        row = snapshot.iloc[0]
        return {'year': int(row.year), 'event': str(row.event), 'session': str(row.session),
                'source': 'saved_prediction_snapshot'}
    # Snapshot output is optional. New runs also persist resolved context with
    # their weather inputs, so a changed form cannot relabel a saved run.
    try:
        saved = json.loads((Path(output_dir)/'weather_context.json').read_text(encoding='utf-8'))
        if isinstance(saved, dict) and all(saved.get(key) is not None for key in ('year', 'event', 'session')):
            return {'year': int(saved['year']), 'event': str(saved['event']), 'session': str(saved['session']),
                    'source': 'saved_weather_context'}
    except (ValueError, TypeError, OSError):
        pass
    laps = read_output_table(output_dir, 'lap_details/weekend_lap_details.csv', max_rows=20000)
    selected = laps[laps.Session.eq(session)] if 'Session' in laps else laps
    if not selected.empty and {'Year', 'Event'}.issubset(selected.columns):
        contexts = selected[['Year', 'Event']].dropna().drop_duplicates()
        if len(contexts) == 1:
            row = contexts.iloc[0]
            return {'year': int(row.Year), 'event': str(row.Event), 'session': session,
                    'source': 'saved_lap_details'}
    return {'year': year, 'event': event, 'session': session, 'source': 'requested_setup'}


def saved_data_health(output_dir, context, requested, track):
    laps = read_output_table(output_dir, 'lap_details/weekend_lap_details.csv', max_rows=20000)
    laps = laps[laps.Session.eq(context['session'])] if 'Session' in laps else laps.iloc[:0]
    if {'Year', 'Event'}.issubset(laps.columns):
        laps = laps[pd.to_numeric(laps.Year, errors='coerce').eq(context['year']) & laps.Event.eq(context['event'])]
    summary = read_output_table(output_dir, 'simulation_summary.csv', max_rows=100)
    lap_drivers = set(laps.Driver.dropna().astype(str)) if 'Driver' in laps else set()
    model_drivers = set(summary.Driver.dropna().astype(str)) if 'Driver' in summary else set()
    duplicates = int(summary.Driver.duplicated().sum()) if 'Driver' in summary else 0
    missing = sorted(lap_drivers - model_drivers)
    clean = int(laps.CleanPushLap.astype(str).str.lower().isin(['true', '1']).sum()) if 'CleanPushLap' in laps else None
    path = Path(output_dir) / 'lap_details/weekend_lap_details.csv'
    modified = pd.Timestamp(path.stat().st_mtime, unit='s', tz='UTC') if path.exists() else None
    mismatch = (context['year'] != requested['year'] or context['session'] != requested['session']
                or requested['event'] not in ('latest', context['event']))
    selection = {}
    for candidate in (Path(output_dir) / 'forecast_context.json', Path(output_dir).parent / 'forecast_context.json'):
        if candidate.is_file():
            try:
                saved = json.loads(candidate.read_text(encoding='utf-8'))
                if saved.get('event') == context['event'] and saved.get('session') == context['session']:
                    selection = saved
                    break
            except (ValueError, OSError):
                pass
    grid_sources = sorted(summary.grid_source.dropna().astype(str).unique()) if 'grid_source' in summary else []
    return {
        'context': context, 'setup_mismatch': mismatch,
        'message': 'Setup differs from saved results. Run a simulation to apply it.' if mismatch
                   else 'Showing saved results; changing setup does not regenerate them.',
        'drivers_in_laps': len(lap_drivers), 'drivers_in_model': len(model_drivers),
        'matched_drivers': len(lap_drivers & model_drivers), 'missing_model_drivers': missing,
        'duplicate_model_drivers': duplicates, 'lap_rows': len(laps), 'clean_laps': clean,
        'telemetry_status': track['status'], 'telemetry_message': track['message'],
        'completion': track.get('completion', 'not_recorded'),
        'saved_at_utc': modified.isoformat() if modified is not None else None,
        'output_age_hours': round(max(0, (pd.Timestamp.now(tz='UTC') - modified).total_seconds() / 3600), 2)
                            if modified is not None else None,
        'context_source': context['source'],
        'selection_reason': selection.get('session_evidence', {}).get(context['session'], 'Not recorded; manually selected or older output'),
        'selection_policy': selection.get('session_policy', 'No saved automatic selection policy'),
        'grid_sources': grid_sources,
    }
