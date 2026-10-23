"""Append-only OpenF1 checks. Never overrides FIA/FastF1 inputs or score labels."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from src.app_services.beta import verified_snapshot
from src.app_services.practice_collection import utc
from src.data_sources.openf1 import OpenF1Client
from src.result_status import classify_result_status, retirement_label
from src.stage_ensemble_benchmark import digest, dump_new
from src.venues import resolve_venue

CONFIG = 'config/classification_checks.json'
ROOT = 'outputs/classification_checks'


def resolve_race_session(rows, context):
    """No 'latest', country-only match, or event-name-only circuit fallback."""
    expected = (context.get('venue') or {}).get('circuit_id')
    if not expected:
        raise ValueError('An explicit resolved target circuit is required.')
    matches = []
    for row in rows:
        if row.get('session_name') != 'Race' or row.get('year') != int(context['year']):
            continue
        stamp = utc(row['date_start'])
        if abs((stamp-utc(context['race_start_utc'])).total_seconds()) > 60:
            continue
        # Resolve the feed hint alone: a known event name cannot mask missing hints.
        hint = row.get('circuit_short_name')
        venue = resolve_venue(int(context['year']), '', circuit_hint=hint)
        if hint and venue['venue_status'] == 'resolved' and venue['circuit_id'] == expected:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('No unique OpenF1 race with matching year, start time and circuit.')
    return matches[0]


def compare_classification(primary, rows, drivers, session_key, *, position_column, source):
    """Require a complete exact roster before reporting rank disagreements."""
    if not rows:
        return {'status': 'unavailable', 'reason': 'OpenF1 endpoint has no published rows', 'changes': []}
    if (not {'Driver', position_column}.issubset(primary) or primary.Driver.duplicated().any()
            or primary.empty):
        raise ValueError('Incomplete primary classification.')
    mapping = pd.DataFrame(drivers)
    remote = pd.DataFrame(rows)
    for table in (mapping, remote):
        if (not {'driver_number', 'session_key'}.issubset(table)
                or not table.session_key.eq(session_key).all()
                or table.driver_number.duplicated().any()):
            raise ValueError('Ambiguous driver mapping or incorrect OpenF1 session.')
    if 'name_acronym' not in mapping or mapping.name_acronym.duplicated().any():
        raise ValueError('Missing or duplicate driver acronyms.')
    remote = remote.merge(mapping[['driver_number', 'name_acronym']], on='driver_number',
                          how='left', validate='one_to_one').rename(columns={'name_acronym': 'Driver'})
    if remote.Driver.isna().any() or set(remote.Driver) != set(primary.Driver):
        raise ValueError('OpenF1 and primary classifications have different driver coverage.')
    if 'position' not in remote:
        raise ValueError('Missing OpenF1 positions.')
    expected = sorted(range(1, len(primary)+1))
    for values in (primary[position_column], remote.position):
        numeric = pd.to_numeric(values, errors='coerce')
        if numeric.isna().any() or sorted(numeric) != expected:
            raise ValueError('Partial or invalid classification positions.')
    changes = []; unknown_status = []
    merged = primary.merge(remote, on='Driver', validate='one_to_one', suffixes=('', '_openf1'))
    remote_position = 'position_openf1' if position_column == 'position' else 'position'
    for _, row in merged.iterrows():
        if row[position_column] != row[remote_position]:
            changes.append({'Driver': row.Driver, 'field': 'position',
                            'primary': int(row[position_column]), 'openf1': int(row[remote_position])})
        if 'actual_status' not in primary:
            continue
        outcome = classify_result_status(row.actual_status)
        flags = {'dns': outcome == 'did_not_start', 'dsq': outcome == 'disqualified'}
        dnf = retirement_label(row.actual_status)
        if pd.notna(dnf):
            flags['dnf'] = bool(dnf)
        if outcome == 'unknown':
            unknown_status.append(row.Driver)
            continue
        for field, value in flags.items():
            observed = row.get(field)
            if not isinstance(observed, (bool, np.bool_)):
                unknown_status.append(row.Driver)
            elif bool(observed) != value:
                changes.append({'Driver': row.Driver, 'field': field, 'primary': value, 'openf1': bool(observed)})
    return {'status': 'disagreement' if changes else 'match', 'primary_source': source,
            'changes': changes, 'unknown_status_drivers': sorted(set(unknown_status)),
            'drivers': len(primary), 'automatic_override': False}


def compare_stint_ages(ledger, rows, drivers, session_key, session_code):
    """Cross-check the first observed lap, without treating stints as set IDs."""
    required = {'Driver', 'Session', 'Stint', 'Compound', 'first_lap_number', 'start_tyre_life'}
    if not required.issubset(ledger) or not rows:
        return {'status': 'unavailable', 'reason': 'No comparable frozen/OpenF1 stint observations', 'changes': []}
    primary = ledger.loc[ledger.Session.eq(session_code)].copy()
    remote = pd.DataFrame(rows); mapping = pd.DataFrame(drivers)
    if (primary.empty or not {'driver_number', 'session_key', 'stint_number', 'lap_start', 'compound', 'tyre_age_at_start'}.issubset(remote)
            or not {'driver_number', 'session_key', 'name_acronym'}.issubset(mapping)
            or not remote.session_key.eq(session_key).all() or not mapping.session_key.eq(session_key).all()
            or mapping.driver_number.duplicated().any() or mapping.name_acronym.duplicated().any()
            or remote.duplicated(['driver_number', 'stint_number']).any()
            or primary.duplicated(['Driver', 'Stint']).any()):
        raise ValueError('Missing or ambiguous stint/session identities.')
    remote = remote.merge(mapping[['driver_number', 'name_acronym']], on='driver_number', how='left', validate='many_to_one')
    remote = remote.rename(columns={'name_acronym': 'Driver', 'stint_number': 'Stint'})
    merged = primary.merge(remote, on=['Driver', 'Stint'], how='left', validate='one_to_one')
    changes = []; unavailable = []; compared = 0
    for _, row in merged.iterrows():
        values = pd.to_numeric(pd.Series([row.first_lap_number, row.start_tyre_life,
                                         row.lap_start, row.tyre_age_at_start]), errors='coerce')
        if (values.isna().any() or not np.isfinite(values).all() or (values < 0).any()
                or not values.eq(values.round()).all() or row.first_lap_number < row.lap_start
                or row.Compound != row.compound):
            unavailable.append({'Driver': row.Driver, 'stint': int(row.Stint)})
            continue
        expected = int(row.tyre_age_at_start + row.first_lap_number - row.lap_start + 1)
        compared += 1
        if int(row.start_tyre_life) != expected:
            changes.append({'Driver': row.Driver, 'stint': int(row.Stint), 'field': 'first_observed_tyre_life',
                            'primary': int(row.start_tyre_life), 'openf1': expected})
    return {'status': 'disagreement' if changes else 'match' if compared and not unavailable else 'partial',
            'changes': changes, 'compared_stints': compared, 'unavailable_stints': unavailable,
            'automatic_override': False, 'official_inventory': False,
            'age_convention': 'FastF1 first observed TyreLife = OpenF1 starting age + observed lap offset + 1'}


def capture_checks(root, forecast, *, client=None, now=None, official_folder=None):
    root, forecast = Path(root), Path(forecast)
    manifest = verified_snapshot(forecast)
    context = manifest['context']; stamp = utc(now or datetime.now(timezone.utc))
    if stamp < utc(manifest['created_at_utc']):
        raise ValueError('Cannot backdate an independent classification check.')
    primary_path = forecast/'frozen/features.csv'
    official_sha = None
    if official_folder is not None:
        official_folder = Path(official_folder)
        score = json.loads((official_folder/'score.json').read_text(encoding='utf-8'))
        if (score.get('snapshot_sha256') != digest(forecast/'frozen/manifest.json')
                or stamp < utc(score['evaluated_at_utc']) or stamp < utc(context['race_start_utc']) + pd.Timedelta(hours=8)):
            raise ValueError('Post-race comparison requires a completed matching official score.')
        primary_path = official_folder/'actual_results.csv'
        official_sha = digest(primary_path)
    elif stamp >= utc(context['race_start_utc']):
        return {'status': 'ineligible', 'reason': 'Use a completed official score for post-race checks.'}
    if not (context.get('venue') or {}).get('circuit_id'):
        return {'status': 'not_applicable', 'reason':
                'Legacy frozen forecast has no explicit circuit identity. Independent check withheld; frozen provenance is unchanged.'}
    primary = pd.read_csv(primary_path)
    if official_sha is None:
        verified_grid = 'grid_source' in primary and primary.grid_source.eq('fia_official_grid').all()
        qualifying = context['session'] == 'Q' and 'q_rank' in primary and primary.q_rank.notna().all()
        tyres = context['session'] == 'Q' and 'tyre_set_ledger_estimated.csv' in manifest['files']
        if not (verified_grid or qualifying or tyres):
            return {'status': 'not_applicable', 'reason':
                    'No verified FIA grid or complete qualifying classification to cross-check. No OpenF1 request needed.'}
    identity = digest(forecast/'frozen/manifest.json')[:16] + ('_race_'+official_sha[:12] if official_sha else '_pre')
    base = root/ROOT/identity
    # Cache successful and unavailable observations; later observations remain separate.
    for path in sorted(base.glob('*/report.json'), reverse=True):
        old = json.loads(path.read_text(encoding='utf-8'))
        if old['status'] in {'capture_failed', 'access_unavailable'} and old.get('request_policy') != 'bounded_session_window_v1':
            # A failure from the former whole-season query must not suppress
            # the corrected, bounded request for another hour.
            continue
        for response in old['requests']:
            if 'file' in response and digest(path.parent/response['file']) != response['sha256']:
                raise ValueError('Saved OpenF1 response checksum differs.')
        elapsed = (stamp-utc(old['checked_at_utc'])).total_seconds()
        ttl = 6*3600 if old['status'] == 'access_unavailable' or (old['status'] == 'completed' and all(c['status'] in ('match', 'disagreement') for c in old['checks'].values())) else 3600
        if 0 <= elapsed < ttl:
            return {'status': 'cached' if old['status'] == 'completed' else old['status'],
                    'folder': str(path.parent), 'checks': old['checks'], 'errors': old.get('errors', [])}
        break
    folder = base/(stamp.strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    client = client or OpenF1Client(timeout_seconds=10)
    requests = []; checks = {}; errors = []

    def fetch(endpoint, params):
        began = utc(now or datetime.now(timezone.utc)).isoformat()
        try:
            rows = client.get_json(endpoint, params)
        except Exception as exc:
            requests.append({'endpoint': endpoint, 'params': params, 'request_started_at_utc': began,
                'response_received_at_utc': utc(now or datetime.now(timezone.utc)).isoformat(),
                'error_type': type(exc).__name__, 'http_status': getattr(getattr(exc, 'response', None), 'status_code', None),
                'publication_time_utc': None})
            raise
        received = utc(now or datetime.now(timezone.utc)).isoformat()
        name = f'{len(requests):02}_{endpoint}.json'
        dump_new(folder/name, rows)
        requests.append({'endpoint': endpoint, 'params': params, 'request_started_at_utc': began,
            'response_received_at_utc': received, 'file': name, 'sha256': digest(folder/name),
            'publication_time_utc': None})
        return rows

    try:
        start = utc(context['race_start_utc'])
        race = resolve_race_session(fetch('sessions', {'year': int(context['year']), 'session_name': 'Race',
            'date_start>': (start-pd.Timedelta(minutes=1)).isoformat(),
            'date_start<': (start+pd.Timedelta(minutes=1)).isoformat()}), context)
        if official_sha:
            if 'actual_result_source' not in primary or not primary.actual_result_source.eq('fastf1_results').all():
                raise ValueError('Post-race primary must be official FastF1 results.')
            targets = [('race_result', 'session_result', race, 'actual_position', 'fastf1_results')]
        else:
            targets = []
            if 'grid_source' in primary and primary.grid_source.eq('fia_official_grid').all():
                targets.append(('starting_grid', 'starting_grid', race, 'grid_position', 'fia_official_grid'))
            else:
                checks['starting_grid'] = {'status': 'unavailable', 'reason': 'Saved grid is not a verified FIA grid', 'changes': []}
            has_q = context['session'] == 'Q' and 'q_rank' in primary and primary.q_rank.notna().all()
            has_tyres = context['session'] == 'Q' and 'tyre_set_ledger_estimated.csv' in manifest['files']
            q_session = None
            if has_q or has_tyres:
                sessions = fetch('sessions', {'meeting_key': race['meeting_key'], 'session_name': 'Qualifying'})
                sessions = [s for s in sessions if s.get('meeting_key') == race['meeting_key']
                            and s.get('session_name') == 'Qualifying' and s.get('year') == int(context['year'])
                            and utc(s['date_start']) < min(stamp, utc(context['race_start_utc']))]
                if len(sessions) != 1:
                    raise ValueError('No unique qualifying session in the matched race meeting.')
                q_session = sessions[0]
                if has_q:
                    targets.append(('qualifying_result', 'session_result', q_session, 'q_rank', 'frozen_fastf1_q_rank'))
            if not has_q:
                checks['qualifying_result'] = {'status': 'unavailable', 'reason': 'No complete frozen Q classification', 'changes': []}
        for label, endpoint, session, column, source in targets:
            try:
                rows = fetch(endpoint, {'session_key': session['session_key']})
                drivers = fetch('drivers', {'session_key': session['session_key']}) if rows else []
                checks[label] = compare_classification(primary, rows, drivers, session['session_key'],
                                                       position_column=column, source=source)
            except Exception as exc:
                checks[label] = {'status': 'unavailable', 'reason': str(exc)[:300], 'changes': []}
        if not official_sha and has_tyres and q_session:
            try:
                key = q_session['session_key']
                stint_rows = fetch('stints', {'session_key': key})
                drivers = fetch('drivers', {'session_key': key}) if stint_rows else []
                ledger = pd.read_csv(forecast/'frozen/tyre_set_ledger_estimated.csv')
                checks['starting_tyre_age'] = compare_stint_ages(ledger, stint_rows, drivers, key, 'Q')
            except Exception as exc:
                checks['starting_tyre_age'] = {'status': 'unavailable', 'reason': str(exc)[:300], 'changes': []}
    except Exception as exc:
        errors.append({'error_type': type(exc).__name__, 'reason': str(exc)[:300]})
    access_unavailable = any(request.get('http_status') in (401, 403) for request in requests)
    report = {'schema_version': 1, 'status': 'access_unavailable' if access_unavailable else 'capture_failed' if errors else 'completed',
        'request_policy': 'bounded_session_window_v1',
        'checked_at_utc': stamp.isoformat(), 'forecast_manifest_sha256': digest(forecast/'frozen/manifest.json'),
        'source_feature_cutoff_utc': context['data_cutoff_utc'], 'context': context,
        'primary_sha256': digest(primary_path) if primary_path.is_file() else None,
        'official_results_sha256': official_sha, 'checks': checks, 'requests': requests, 'errors': errors,
        'automatic_override': False,
        'policy': 'FIA/FastF1 priority retained. Retrieval time is not publication time; disagreements require review.'}
    dump_new(folder/'report.json', report)
    return {'status': report['status'], 'folder': str(folder), 'checks': checks, 'errors': errors}


def try_capture_checks(root, forecast, *, official_folder=None):
    try:
        config = Path(root)/CONFIG
        if not config.is_file() or json.loads(config.read_text(encoding='utf-8')).get('enabled') is not True:
            return {'status': 'disabled'}
        return capture_checks(root, forecast, official_folder=official_folder)
    except Exception as exc:
        return {'status': 'capture_failed', 'error_type': type(exc).__name__, 'reason': str(exc)[:300]}
