"""Versioned forecast publication contract and a local fixture store.

The producer PC builds an immutable payload from a verified frozen snapshot and
pushes it outbound. Nothing here opens a network connection: the local store
stands in for hosted storage so atomic publication, retries, failed validation
and producer outages can be rehearsed with fixtures before any service exists.
See docs/forecast-publication.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pandas as pd

CONTRACT = 'f1-sim.forecast-publication'
SCHEMA_VERSION = 1
STAGES = ('PRE', 'FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q')
VISIBILITIES = ('subscribers', 'preview')
PROBABILITY_FIELDS = ('win_chance', 'podium_chance', 'points_chance', 'dnf_chance')
PREDICTION_FIELDS = ('Driver', 'avg_finish') + PROBABILITY_FIELDS
MIN_DRIVERS = 15
# Someone always wins, so win chances sum to one apart from rounding.
WIN_SUM_TOLERANCE = 0.02
REQUIRED = ('contract', 'schema_version', 'publication_id', 'kind', 'visibility', 'event', 'stage',
            'available_sessions', 'input_cutoff_utc', 'generated_at_utc', 'model', 'provenance',
            'limitations', 'predictions', 'checksum')
# Keys that must never leave the producer PC, at any depth.
FORBIDDEN_KEYS = {'source_dir', 'credentials', 'password', 'token', 'webhook', 'webhook_url',
                  'api_key', 'secret', 'cookie', 'path', 'output_dir'}
LOCAL_PATH = re.compile(r'(?i)\b[a-z]:[\\/]|(?:^|\s)(?:/home/|/Users/|\\\\)')


class PublicationRejected(ValueError):
    def __init__(self, errors):
        super().__init__('; '.join(errors))
        self.errors = list(errors)


def canonical_bytes(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def payload_checksum(payload):
    """sha256 over the canonical payload without its checksum block."""
    body = {key: value for key, value in payload.items() if key != 'checksum'}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def event_key(event):
    return f"{int(event['year'])}-r{int(event['round']):02d}"


def publication_id(event, stage, snapshot_sha256):
    # The frozen manifest hash makes retries of one snapshot share one id.
    return f"{event_key(event)}-{stage.lower()}-{snapshot_sha256[:12]}"


def model_fingerprint(source_hashes):
    return hashlib.sha256(canonical_bytes(source_hashes)).hexdigest()


def build_publication(folder, model_id, visibility='subscribers'):
    """Payload for one verified frozen forecast; adds nothing from local config."""
    from src.app_services.beta import digest, verified_snapshot
    folder = Path(folder)
    manifest = verified_snapshot(folder)
    if manifest['category'] != 'prospective':
        raise ValueError('Only prospective pre-race snapshots can be published as official forecasts.')
    context = manifest['context']
    snapshot_sha = digest(folder/'frozen/manifest.json')
    frame = pd.read_csv(folder/'frozen/simulation_summary.csv')
    predictions = json.loads(frame[[c for c in PREDICTION_FIELDS if c in frame]].to_json(orient='records'))
    job = json.loads((folder/'job.json').read_text(encoding='utf-8')) if (folder/'job.json').is_file() else {}
    event = {'year': int(context['year']), 'round': int(context['round']), 'name': str(context['event']),
             'race_start_utc': context['race_start_utc']}
    payload = {
        'contract': CONTRACT, 'schema_version': SCHEMA_VERSION,
        'publication_id': publication_id(event, context['session'], snapshot_sha),
        'kind': 'official', 'visibility': visibility, 'event': event,
        'stage': context['session'], 'available_sessions': list(context['available_sessions']),
        'input_cutoff_utc': context['data_cutoff_utc'], 'generated_at_utc': manifest['created_at_utc'],
        'model': {'model_id': str(model_id), 'app_version': manifest['app_version'],
                  'source_fingerprint': model_fingerprint(manifest['model_source_hashes']),
                  'settings': {k: job[k] for k in ('n_sims', 'seed', 'overtaking_difficulty') if k in job}},
        'provenance': {'snapshot_manifest_sha256': snapshot_sha, 'snapshot_schema_version': manifest['schema_version'],
                       'category': manifest['category'], 'input_sha256': dict(manifest['files']),
                       'timestamp_authority': manifest['timestamp_authority'],
                       'session_evidence': dict(context.get('session_evidence', {}))},
        'limitations': list(manifest['limitations']),
        'predictions': predictions,
    }
    payload['checksum'] = {'algorithm': 'sha256', 'value': payload_checksum(payload)}
    return payload


def _utc(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError('timestamp has no timezone')
    return stamp.tz_convert('UTC')


def _forbidden(data, where='payload'):
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(f'{where}.{key}')
            found += _forbidden(value, f'{where}.{key}')
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found += _forbidden(value, f'{where}[{index}]')
    elif isinstance(data, str) and LOCAL_PATH.search(data):
        found.append(f'{where} (local path)')
    return found


def validate_publication(payload):
    """Every reason a payload must not be published; empty means accepted."""
    if not isinstance(payload, dict):
        return ['payload is not an object']
    errors = [f'missing {key}' for key in REQUIRED if key not in payload]
    if errors:
        return errors
    if payload['contract'] != CONTRACT or payload['schema_version'] != SCHEMA_VERSION:
        errors.append(f"unsupported contract {payload['contract']!r} v{payload['schema_version']!r}")
    if payload['kind'] != 'official':
        errors.append('personal scenarios cannot be published as official forecasts')
    if payload['visibility'] not in VISIBILITIES:
        errors.append(f"unknown visibility {payload['visibility']!r}")
    if payload['provenance'].get('category') != 'prospective':
        errors.append('only prospective snapshots are publishable')
    for leak in _forbidden(payload):
        errors.append(f'producer-only data in {leak}')

    event, stage, sessions = payload['event'], payload['stage'], payload['available_sessions']
    try:
        expected_id = publication_id(event, stage, payload['provenance']['snapshot_manifest_sha256'])
        if payload['publication_id'] != expected_id:
            errors.append('publication_id does not match event, stage and snapshot')
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append('event or provenance identity is incomplete')
    if stage not in STAGES:
        errors.append(f'unknown stage {stage!r}')
    elif (stage == 'PRE') != (not sessions) or (stage != 'PRE' and stage not in sessions):
        # Mirrors next-race selection: PRE only with no completed session, and a
        # stage is never claimed unless its session data was available.
        errors.append('stage is not consistent with the available sessions')
    if any(code not in STAGES or code == 'PRE' for code in sessions):
        errors.append('available_sessions contains an unknown session')

    try:
        cutoff, generated = _utc(payload['input_cutoff_utc']), _utc(payload['generated_at_utc'])
        race_start = _utc(event['race_start_utc'])
        if generated < cutoff:
            errors.append('generated before its input cutoff')
        if generated >= race_start:
            errors.append('generated after the race started; not a pre-race forecast')
    except (KeyError, TypeError, ValueError):
        errors.append('timestamps must be ISO 8601 with a timezone')

    rows = payload['predictions']
    if not isinstance(rows, list) or len(rows) < MIN_DRIVERS:
        errors.append(f'predictions must cover at least {MIN_DRIVERS} drivers')
    else:
        drivers = [row.get('Driver') for row in rows]
        if len(set(drivers)) != len(drivers) or not all(isinstance(d, str) and d for d in drivers):
            errors.append('predictions need one row per named driver')
        for field in PROBABILITY_FIELDS:
            values = [row.get(field) for row in rows if field in row]
            if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in values):
                errors.append(f'{field} outside 0-1')
        finishes = [row.get('avg_finish') for row in rows]
        if any(not isinstance(v, (int, float)) or not 1 <= v <= len(rows) for v in finishes):
            errors.append('avg_finish outside the field')
        wins = [row.get('win_chance') for row in rows]
        if all(isinstance(v, (int, float)) for v in wins) and abs(sum(wins) - 1) > WIN_SUM_TOLERANCE:
            errors.append('win chances do not sum to one')

    checksum = payload['checksum']
    if not isinstance(checksum, dict) or checksum.get('algorithm') != 'sha256' \
            or checksum.get('value') != payload_checksum(payload):
        errors.append('checksum does not match payload')
    return errors


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('wb') as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True, allow_nan=False).encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class LocalPublicationStore:
    """File-backed stand-in for hosted storage with one producer.

    Snapshots are write-once; the per-event latest pointer is replaced
    atomically and only moves forward, so a failed run or a late retry of an
    older forecast never replaces a healthy newer publication.
    """

    def __init__(self, root, stale_after=timedelta(hours=30), producer_timeout=timedelta(hours=2)):
        self.root = Path(root)
        self.stale_after, self.producer_timeout = stale_after, producer_timeout

    def _snapshot(self, key, pid):
        return self.root/'snapshots'/key/f'{pid}.json'

    def _latest(self, key):
        return self.root/'latest'/f'{key}.json'

    def _now(self, now):
        return pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz='UTC')

    def publish(self, payload, now=None):
        now = self._now(now)
        errors = validate_publication(payload)
        if errors:
            self._reject(payload, errors, now)
            if isinstance(payload, dict) and isinstance(payload.get('event'), dict):
                try:
                    self.record_failure(payload['event'], payload.get('stage'), 'validation_failed', now)
                except (KeyError, TypeError, ValueError):
                    pass
            return {'status': 'rejected', 'errors': errors}
        key, pid = event_key(payload['event']), payload['publication_id']
        target = self._snapshot(key, pid)
        if target.is_file():
            stored = _read(target)
            if stored['publication']['checksum']['value'] != payload['checksum']['value']:
                errors = ['publication_id already published with different content']
                self._reject(payload, errors, now)
                return {'status': 'rejected', 'errors': errors}
            status = 'duplicate'
        else:
            # Single producer: the existence check above is the reservation.
            _write_atomic(target, {'published_at_utc': now.isoformat(), 'publication': payload})
            status = 'published'
        # Repeated even for a duplicate so a retry repairs a pointer update
        # that was interrupted after the snapshot write.
        moved = self._advance_latest(key, payload, now)
        self._update_status(key, {'last_success_utc': now.isoformat(), 'last_publication_id': pid})
        self.heartbeat(now)
        return {'status': status, 'publication_id': pid, 'latest': moved or self._is_latest(key, pid)}

    def _is_latest(self, key, pid):
        path = self._latest(key)
        return path.is_file() and _read(path)['publication_id'] == pid

    def _advance_latest(self, key, payload, now):
        path = self._latest(key)
        if path.is_file():
            current = _read(path)
            # More completed sessions wins, then the newer run, so neither a
            # late retry nor a fresh run on fewer inputs can roll latest back.
            ahead = (len(payload['available_sessions']), _utc(payload['generated_at_utc'])) \
                > (current['session_count'], _utc(current['generated_at_utc']))
            if current['publication_id'] == payload['publication_id'] or not ahead:
                return False
        _write_atomic(path, {'publication_id': payload['publication_id'], 'stage': payload['stage'],
                             'session_count': len(payload['available_sessions']),
                             'generated_at_utc': payload['generated_at_utc'],
                             'checksum': payload['checksum']['value'], 'pointer_updated_at_utc': now.isoformat()})
        return True

    def _reject(self, payload, errors, now):
        self.root.mkdir(parents=True, exist_ok=True)
        pid = payload.get('publication_id') if isinstance(payload, dict) else None
        with (self.root/'rejections.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at_utc': now.isoformat(), 'publication_id': pid, 'errors': errors}) + '\n')

    def _status_path(self, key):
        return self.root/'status'/f'{key}.json'

    def _update_status(self, key, changes):
        path = self._status_path(key)
        status = _read(path) if path.is_file() else {}
        status.update(changes)
        _write_atomic(path, status)

    def record_failure(self, event, stage, reason, now=None):
        """A producer run that produced nothing publishable; latest is untouched."""
        now = self._now(now)
        self._update_status(event_key(event), {'last_failure_utc': now.isoformat(),
                                               'last_failure_stage': stage, 'last_failure_reason': reason})

    def heartbeat(self, now=None):
        _write_atomic(self.root/'producer.json', {'last_seen_utc': self._now(now).isoformat()})

    def read_latest(self, event, now=None):
        """What a client shows: the last valid forecast plus explicit freshness."""
        now, key = self._now(now), event_key(event)
        pointer = self._latest(key)
        if not pointer.is_file():
            return {'state': 'unavailable', 'reasons': ['no forecast published yet'], 'publication': None}
        latest = _read(pointer)
        record = _read(self._snapshot(key, latest['publication_id']))
        payload = record['publication']
        if payload_checksum(payload) != latest['checksum'] or validate_publication(payload):
            return {'state': 'unavailable', 'reasons': ['stored forecast failed its integrity check'],
                    'publication': None}
        common = {'published_at_utc': record['published_at_utc'], 'publication': payload}
        if now >= _utc(payload['event']['race_start_utc']):
            return {'state': 'closed', 'reasons': ['race has started; this is the final pre-race forecast'], **common}
        reasons = []
        generated = _utc(payload['generated_at_utc'])
        if now - generated > self.stale_after:
            reasons.append(f'forecast is {int((now - generated) / pd.Timedelta(hours=1))}h old')
        heartbeat = self.root/'producer.json'
        if not heartbeat.is_file() or now - _utc(_read(heartbeat)['last_seen_utc']) > self.producer_timeout:
            reasons.append('forecast producer is offline; updates are paused')
        status = _read(self._status_path(key)) if self._status_path(key).is_file() else {}
        failed, succeeded = status.get('last_failure_utc'), status.get('last_success_utc')
        if failed and (not succeeded or _utc(failed) > _utc(succeeded)):
            stage = status.get('last_failure_stage')
            reasons.append(f"the latest {stage + ' ' if stage else ''}update failed; showing the previous forecast")
        return {'state': 'stale' if reasons else 'current', 'reasons': reasons, **common}
