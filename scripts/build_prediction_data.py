"""Build new, versioned enrichment datasets from downloaded session archives."""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src.app_services import historical_library as library
from src.historical_model import build_historical_feature_table
from src.prediction_data import KEYS, practice_features, outcome_records, strategy_records, delay_records


def archived_origin(pointer, saved):
    """Recover UTC origin from archived raw car Date minus SessionTime.

    Time alone can be relative to a cropped telemetry segment and is not used.
    Only one already-downloaded driver trace is needed; no new telemetry request.
    """
    for file, info in library.partition_files(pointer.parent, saved):
        if not info['table'].startswith('car_'):
            continue
        if library.sha256(file) != info['sha256']:
            raise ValueError('Archived timing-origin telemetry checksum failed.')
        frame = pd.read_csv(file, nrows=100)
        if not {'Date', 'SessionTime'}.issubset(frame):
            continue
        origins = (pd.to_datetime(frame.Date, utc=True, errors='coerce') -
                   pd.to_timedelta(frame.SessionTime, errors='coerce')).dropna()
        if len(origins) >= 10 and (origins.max()-origins.min()).total_seconds() <= .002:
            return origins.median(), {'path': str(file), 'sha256': info['sha256'], 'table': 'utc_origin_trace'}
    return pd.NaT, None


def build(workspace, years, output, *, delay_labels=None, retirement_causes=None, refresh_race_timing=0, cached_practice=0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    tables, sources, sessions, venues = {}, [], [], []
    refresh, refresh_report = {}, []
    if refresh_race_timing:
        import fastf1
        candidates = []
        for year in years:
            for pointer in (library.library_root(workspace)/str(year)/'detailed').glob('*/session.json'):
                saved = library.read_json(pointer)
                if saved.get('session') == 'R' and saved.get('status') == 'complete':
                    candidates.append(saved)
        enable_cache(str(Path(workspace)/'data/cache'))
        fastf1.Cache.offline_mode(True)
        try:
            for saved in sorted(candidates, key=lambda s: (s['year'], s['round']), reverse=True)[:refresh_race_timing]:
                try:
                    fresh, _, _ = library.fetch(saved, 'detailed', False)
                    refresh[(saved['year'], saved['round'])] = {name: frame for name, frame in fresh.items() if name in {'laps', 'weather_samples', 'session_status'}}
                    refresh_report.append({'year': saved['year'], 'round': saved['round'], 'status': 'cached_timing_refreshed'})
                except Exception as exc:
                    refresh_report.append({'year': saved['year'], 'round': saved['round'], 'status': 'cache_unavailable', 'error': type(exc).__name__})
        finally:
            fastf1.Cache.offline_mode(False)
    for year in years:
        for pointer in sorted((library.library_root(workspace)/str(year)/'detailed').glob('*/session.json')):
            saved = library.read_json(pointer)
            if saved.get('status') != 'complete':
                continue
            sessions.append({key: saved[key] for key in ['year', 'round', 'event', 'session']})
            venues.append({**{key: saved[key] for key in ['year', 'round', 'event', 'session']}, **saved.get('venue', {})})
            origin, origin_source = archived_origin(pointer, saved)
            if origin_source:
                sources.append(origin_source)
            for file, info in library.partition_files(pointer.parent, saved):
                if info['table'] not in library.EXPORT_NAMES:
                    continue
                if library.sha256(file) != info['sha256']:
                    raise ValueError(f'Archive checksum failed: {file.name}')
                replacement = refresh.get((year, saved['round']), {}).get(info['table']) if saved['session'] == 'R' else None
                frame = replacement.copy() if replacement is not None else pd.read_csv(file)
                if info['table'] == 'weather_samples' and 'ObservedAtUtc' not in frame and pd.notna(origin) and 'Time' in frame:
                    frame['ObservedAtUtc'] = origin + pd.to_timedelta(frame.Time, errors='coerce')
                if info['table'] == 'laps' and 'LapStartUtc' not in frame and pd.notna(origin) and 'LapStartTimeSeconds' in frame:
                    frame['LapStartUtc'] = origin + pd.to_timedelta(frame.LapStartTimeSeconds, unit='s')
                for col, value in [('Year', year), ('Round', saved['round']), ('Event', saved['event']), ('Session', saved['session'])]:
                    # Legacy strategy tables omitted identity columns. The pinned
                    # session manifest is authoritative for those missing fields.
                    if col not in frame and info['table'] == 'strategy':
                        frame[col] = value
                    if col not in frame or not frame[col].astype(str).eq(str(value)).all():
                        raise ValueError(f'Archived {info["table"]} identity disagrees with manifest: {pointer.parent.name}, {col}.')
                tables.setdefault(info['table'], []).append(frame)
                sources.append({'path': str(file), 'sha256': info['sha256'], 'table': info['table'],
                                'source_type': 'cached_timing_refresh' if replacement is not None else 'pinned_archive'})
            for name, frame in refresh.get((year, saved['round']), {}).items() if saved['session'] == 'R' else []:
                if name not in {info['table'] for info in saved['files'].values()}:
                    tables.setdefault(name, []).append(frame)
                    sources.append({'table': name, 'year': year, 'round': saved['round'], 'source_type': 'cached_timing_refresh'})
    assembled = {}
    practice_backfill = []
    if cached_practice:
        import fastf1
        enable_cache(str(Path(workspace)/'data/cache'))
        fastf1.Cache.offline_mode(True)
        existing = {(s['year'], s['round'], s['session']) for s in sessions}
        candidates = sorted([s for s in sessions if s['session'] == 'Q'], key=lambda s: (s['year'], s['round']), reverse=True)
        attempted = 0
        try:
            for race in candidates:
                if attempted >= cached_practice:
                    break
                if (race['year'], race['round'], 'FP2') in existing:
                    continue
                task = {**race, 'session': 'FP2'}
                attempted += 1
                try:
                    fresh, venue, _ = library.fetch(task, 'detailed', False)
                    for name, frame in fresh.items():
                        if name in library.EXPORT_NAMES:
                            tables.setdefault(name, []).append(frame)
                    sessions.append(task)
                    venues.append({**task, **venue})
                    practice_backfill.append({**task, 'status': 'cached_practice_added'})
                    sources.append({**task, 'source_type': 'cached_practice_backfill'})
                except Exception as exc:
                    practice_backfill.append({**task, 'status': 'cache_unavailable_or_not_scheduled', 'error': type(exc).__name__})
        finally:
            fastf1.Cache.offline_mode(False)
    for table, frames in tables.items():
        assembled[table] = pd.concat(frames, ignore_index=True)
        assembled[table].to_csv(output/f'{library.EXPORT_NAMES[table]}.csv', index=False)
    empty = pd.DataFrame()
    laps, results = assembled.get('laps', empty), assembled.get('results', empty)
    practice = practice_features(laps, assembled.get('race_control_messages', empty), assembled.get('weather', empty))
    causes = pd.read_csv(retirement_causes) if retirement_causes else pd.DataFrame(columns=KEYS + ['DriverCode', 'OutcomeClass', 'SourceURL', 'PublishedAtUtc', 'Verified'])
    outcomes = outcome_records(results, causes)
    stints, pits = strategy_records(laps)
    labels = delay_records(pd.read_csv(delay_labels) if delay_labels else empty)
    for name, frame in [('practice_features', practice), ('retirement_records', outcomes),
                        ('race_stints', stints), ('pit_lane_traversals', pits), ('start_delay_labels', labels)]:
        frame.to_csv(output/f'{name}.csv', index=False)
    # A review queue is evidence, not a delay label; no keyword match never means no delay.
    messages = assembled.get('race_control_messages', empty)
    if not messages.empty and 'Message' in messages:
        queue = messages[messages.Session.eq('R') & messages.Message.astype(str).str.contains('DELAY|POSTPON|ABORT|START PROCEDURE', case=False, regex=True)].copy()
        queue['Verified'] = False
        queue.to_csv(output/'start_delay_review_queue.csv', index=False)
    pd.DataFrame(venues).to_csv(output/'session_venues.csv', index=False)
    # An empty schema for human-confirmed causes preserves unknowns until reviewed.
    causes.to_csv(output/'retirement_causes.csv', index=False)
    features = build_historical_feature_table(output, enriched=True)
    features.to_csv(output/'enriched_feature_table.csv', index=False)
    coverage = []
    for (year, number, event), group in pd.DataFrame(sessions).groupby(['year', 'round', 'event']) if sessions else []:
        codes = set(group.session)
        coverage.append({'Year': int(year), 'Round': int(number), 'Event': event,
                         'available_sessions': sorted(codes), 'missing_sessions': sorted(set(['FP1', 'FP2', 'FP3', 'Q', 'R'])-codes)})
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'workspace': str(Path(workspace).resolve()),
              'years': years, 'sessions': len(sessions), 'session_counts': dict(Counter(s['session'] for s in sessions)),
              'practice_driver_rows': len(practice), 'retirement_rows': len(outcomes), 'stints': len(stints),
              'measured_pit_traversals': len(pits), 'verified_start_delay_events': len(labels),
              'races': coverage, 'sources': sources, 'timing_refresh': refresh_report,
              'practice_backfill': practice_backfill, 'activated': False,
              'limitations': ['Retrospective provider revisions are possible.', 'Missing practice is unknown.',
                              'Stint trend includes fuel burn and track evolution.',
                              'Pit traversal is not total pit-stop time loss.', 'Provider retirement causes are not independently verified.'],
              'output_sha256': {p.name: library.sha256(p) for p in output.glob('*.csv')}}
    library.write_json(output/'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, default=Path('outputs/prediction_data')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    parser.add_argument('--delay-labels', type=Path)
    parser.add_argument('--retirement-causes', type=Path)
    parser.add_argument('--refresh-race-timing', type=int, default=0, help='Refresh the N latest races from local FastF1 cache only, into the new dataset.')
    parser.add_argument('--cached-practice', type=int, default=0, help='Try the N latest missing FP2 sessions from local cache only.')
    parser.add_argument('--collect-fia', action='store_true')
    parser.add_argument('--fia-index', type=Path, default=Path('data/fia_documents/fia_document_index.csv'))
    parser.add_argument('--pdf-python', type=Path)
    parser.add_argument('--max-documents', type=int, default=100)
    parser.add_argument('--weather-requests', type=Path, help='CSV of explicit original runs and race/circuit identities.')
    args = parser.parse_args()
    if args.collect_fia and (not args.pdf_python or not args.pdf_python.is_file()):
        parser.error('--collect-fia requires --pdf-python pointing to an existing PDF-capable Python.')
    if not 1 <= args.max_documents <= 1000:
        parser.error('--max-documents must be between 1 and 1000.')
    if not 0 <= args.refresh_race_timing <= 50:
        parser.error('--refresh-race-timing must be between 0 and 50.')
    if not 0 <= args.cached_practice <= 100:
        parser.error('--cached-practice must be between 0 and 100.')
    report = build(args.workspace, sorted(set(args.years)), args.output, delay_labels=args.delay_labels,
                   retirement_causes=args.retirement_causes, refresh_race_timing=args.refresh_race_timing, cached_practice=args.cached_practice)
    if args.collect_fia:
        from src.data_sources.fia_extraction import collect
        report['fia'] = collect(pd.read_csv(args.fia_index).fillna(''), pd.read_csv(args.output/'fastf1_race_results.csv'),
                                args.output/'fia', args.pdf_python, args.max_documents)
    if args.weather_requests:
        from src.data_sources.weather_archive import collect_run, pair_samples, validate_identity
        weather_report = []
        for number, row in enumerate(pd.read_csv(args.weather_requests).fillna('').to_dict('records')):
            try:
                validate_identity(row, pd.read_csv(args.output/'session_venues.csv'))
                folder = args.output/'weather'/str(number)
                run = collect_run(row, folder)
                samples = pd.read_csv(args.output/'fastf1_weather_samples.csv') if (args.output/'fastf1_weather_samples.csv').exists() else pd.DataFrame()
                if not samples.empty:
                    samples = samples[samples.Session.eq('R') & samples.Year.eq(row['Year']) & samples.Round.eq(row['Round']) & samples.Event.eq(row['Event'])]
                raw = json.loads((folder/'raw.json').read_text())
                pairs = pair_samples(raw, samples, row['ScheduledStartUtc'])
                pairs.to_csv(folder/'observation_pairs.csv', index=False)
                weather_report.append({'request': number, 'status': 'collected', 'availability_verified': run['availability_verified'], 'paired_observations': len(pairs)})
            except (ValueError, OSError, KeyError, requests.RequestException) as exc:
                weather_report.append({'request': number, 'status': 'unavailable', 'error': type(exc).__name__})
        report['weather'] = weather_report
    library.write_json(args.output/'report.json', report)
    print(json.dumps({key: value for key, value in report.items() if key not in ['sources', 'races', 'fia']}, indent=2))


if __name__ == '__main__':
    main()
