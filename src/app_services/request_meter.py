"""Local download HTTP observations; no provider/account-wide quota claims.

Transport attempts include failures/redirects. HTTP cache hits and FastF1's
processed-data cache hits are separate units. Hooks live only inside a download
worker and restore on exit; installed libraries and their limits are unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

PROVIDERS = {'timing': 'Formula 1 timing', 'jolpica': 'Jolpica / Ergast',
             'openf1': 'OpenF1', 'github': 'GitHub calendars', 'other': 'Other HTTP'}
_hook_lock = threading.Lock()


def provider(url):
    host = (urlsplit(url).hostname or '').lower()
    if host == 'api.openf1.org':
        return 'openf1'
    if host == 'api.jolpi.ca' or host == 'ergast.com' or host.endswith('.ergast.com'):
        return 'jolpica'
    if host == 'livetiming-mirror.fastf1.dev' or host == 'formula1.com' or host.endswith('.formula1.com'):
        return 'timing'
    if host in ('raw.githubusercontent.com', 'api.github.com', 'github.com'):
        return 'github'
    return 'other'


def retry_time(value, now):
    if value is None:
        return None
    try:
        seconds = float(value)
        result = now + seconds
    except (TypeError, ValueError):
        try:
            result = parsedate_to_datetime(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None
    return result if math.isfinite(result) and now <= result <= now + 7*86400 else None


def _guards(now):
    """Read the installed FastF1 guards; do not guess from a request counter."""
    from fastf1.req import _SessionWithRateLimiting
    result = []
    for limiters in _SessionWithRateLimiting._RATE_LIMITS.values():
        for limiter in limiters:
            queue = getattr(limiter, '_timestamps', None)
            if queue is None:
                continue
            interval = float(limiter._interval)
            result.append({'name': str(limiter._info), 'limit': queue.maxlen,
                'window_seconds': interval,
                'timestamps': [float(t) for t in list(queue) if now-interval < t <= now]})
    return result


class RequestMeter:
    def __init__(self, folder, *, clock=time.time):
        self.folder = Path(folder)
        self.clock = clock
        self.started = clock()
        self.lock = threading.RLock()
        self.errors = 0
        self.session_responses = {}

    def begin_session(self):
        self.session_responses.clear()

    def observe_response(self, url, status):
        host = (urlsplit(url).hostname or '').lower()
        endpoint = ('primary' if host == 'livetiming.formula1.com' else
                    'mirror' if host == 'livetiming-mirror.fastf1.dev' else None)
        if endpoint:
            # Paths are used only in memory to pair primary/fallback responses.
            self.session_responses.setdefault(urlsplit(url).path, {})[endpoint] = status
        if status >= 400:
            self.record('http_error', provider(url), status=status, endpoint=endpoint)

    def provider_issue(self):
        pairs = list(self.session_responses.values())
        blocked = [p for p in pairs if p.get('primary') in (401, 403)
                   and p.get('mirror', 0) >= 400]
        if blocked:
            statuses = ', '.join(str(s) for s in sorted({p['primary'] for p in blocked}))
            mirror = ', '.join(str(s) for s in sorted({p['mirror'] for p in blocked}))
            return (f'Formula 1 timing access refused (HTTP {statuses}); fallback mirror failed '
                    f'(HTTP {mirror}). Cached data may still work. Sign in to F1 from Historical Data '
                    'with an active F1 TV Access subscription or higher before retrying; '
                    'waiting for the request limit alone will not fix this.')
        return None

    def publish(self):
        # Observability must not turn a successful download into a failed one.
        try:
            with self.lock:
                now = self.clock()
                try:
                    guards = _guards(now)
                except (AttributeError, ImportError, TypeError, RuntimeError):
                    guards = []  # Unsupported library versions expose unknown allowance.
                data = {'schema_version': 1, 'monitored_since': self.started, 'updated_at': now,
                        'guards': guards, 'recording_errors': self.errors}
                temporary = self.folder/'request_usage.tmp'
                temporary.write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
                temporary.replace(self.folder/'request_usage.json')
        except (OSError, ValueError):
            self.errors += 1

    def record(self, kind, source='other', **extra):
        try:
            with self.lock:
                event = {'time': self.clock(), 'kind': kind, 'provider': source, **extra}
                with (self.folder/'api_requests.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, allow_nan=False)+'\n')
                self.publish()
        except (OSError, ValueError):
            self.errors += 1


class _DataCacheHandler(logging.Handler):
    def __init__(self, meter):
        super().__init__()
        self.meter = meter

    def emit(self, record):
        if record.getMessage().startswith('Using cached data for '):
            self.meter.record('data_cache', 'timing')


@contextmanager
def monitor_requests(folder, *, clock=time.time):
    import requests.adapters
    from requests_cache import CacheMixin
    from fastf1.exceptions import RateLimitExceededError
    from fastf1.req import _SessionWithRateLimiting, _logger

    if not _hook_lock.acquire(blocking=False):
        raise RuntimeError('A request meter is already active in this worker.')
    meter = RequestMeter(folder, clock=clock)
    adapter_send = requests.adapters.HTTPAdapter.send
    cached_send = CacheMixin.send
    fastf1_send = _SessionWithRateLimiting.send
    logger = _logger
    handler = _DataCacheHandler(meter)

    def transport(adapter, request, **kwargs):
        source = provider(request.url)
        meter.record('network', source)
        try:
            response = adapter_send(adapter, request, **kwargs)
        except Exception:
            meter.record('network_error', source)
            raise
        if response.status_code == 429:
            meter.record('http_429', source, retry_at=retry_time(response.headers.get('Retry-After'), clock()))
        meter.observe_response(request.url, response.status_code)
        return response

    def cache(session, request, **kwargs):
        response = cached_send(session, request, **kwargs)
        if getattr(response, 'from_cache', False):
            meter.record('http_cache', provider(request.url))
            meter.observe_response(request.url, response.status_code)
        return response

    def guarded(session, request, **kwargs):
        try:
            return fastf1_send(session, request, **kwargs)
        except RateLimitExceededError:
            meter.record('guard_block', provider(request.url))
            raise

    try:
        requests.adapters.HTTPAdapter.send = transport
        CacheMixin.send = cache
        _SessionWithRateLimiting.send = guarded
        logger.addHandler(handler)
        meter.publish()
        yield meter
    finally:
        requests.adapters.HTTPAdapter.send = adapter_send
        CacheMixin.send = cached_send
        _SessionWithRateLimiting.send = fastf1_send
        logger.removeHandler(handler)
        meter.publish()
        _hook_lock.release()


def _events(path):
    try:
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if (row.get('kind') in {'network', 'network_error', 'http_error', 'http_429', 'guard_block', 'http_cache', 'data_cache'}
                            and row.get('provider') in PROVIDERS and math.isfinite(row['time'])):
                        yield row
                except (ValueError, KeyError, TypeError):
                    continue  # An interrupted last line cannot erase earlier observations.
    except OSError:
        return


def request_usage(root, folder, *, now=None):
    """Refresh rolling windows at UI polling time, even after a worker pauses."""
    now = time.time() if now is None else float(now)
    root, folder = Path(root).resolve(), Path(folder).resolve()
    try:
        state = json.loads((folder/'request_usage.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'status': 'unavailable', 'reason': 'This download started before request monitoring was available.',
                'providers': [], 'guards': []}
    selected = [e for e in _events(folder/'api_requests.jsonl') if e['time'] <= now]
    recent = []
    paths = set((root/'outputs/app_runs').glob('*/api_requests.jsonl')) | {folder/'api_requests.jsonl'}
    for path in paths:
        try:
            if path.stat().st_mtime < now-3600:
                continue
        except OSError:
            continue
        recent.extend(e for e in _events(path) if now-3600 < e['time'] <= now)
    rows = []
    for identifier, label in PROVIDERS.items():
        events = [e for e in recent if e['provider'] == identifier]
        job = [e for e in selected if e['provider'] == identifier]
        network = [e for e in events if e['kind'] == 'network']
        limits = [e for e in events if e['kind'] in ('http_429', 'guard_block')]
        retries = [e['retry_at'] for e in limits if e.get('retry_at') is not None and e['retry_at'] > now]
        if events or job:
            rows.append({'provider': identifier, 'label': label, 'requests_last_hour': len(network),
                'http_cache_hits_job': sum(e['kind'] == 'http_cache' for e in job),
                'requests_job': sum(e['kind'] == 'network' for e in job),
                'network_errors_last_hour': sum(e['kind'] == 'network_error' for e in events),
                'http_errors_job': sum(e['kind'] == 'http_error' for e in job),
                'rate_limit_seen': bool(limits), 'retry_at': max(retries, default=None)})
    guards = []
    for guard in state.get('guards', []):
        timestamps = [t for t in guard['timestamps'] if now-guard['window_seconds'] < t <= now]
        guards.append({'name': guard['name'], 'limit': guard['limit'], 'used': len(timestamps),
            'window_seconds': guard['window_seconds'], 'remaining': max(0, guard['limit']-len(timestamps)),
            'next_expiry_at': min(timestamps)+guard['window_seconds'] if timestamps else None,
            'next_slot_at': min(timestamps)+guard['window_seconds'] if len(timestamps) >= guard['limit'] else None})
    return {'status': 'recording_degraded' if state.get('recording_errors') else 'available',
        'monitored_since': state['monitored_since'], 'as_of': now,
        'requests_last_hour': sum(r['requests_last_hour'] for r in rows),
        'requests_job': sum(e['kind'] == 'network' for e in selected),
        'http_cache_hits_job': sum(e['kind'] == 'http_cache' for e in selected),
        'data_cache_hits_job': sum(e['kind'] == 'data_cache' for e in selected),
        'providers': rows, 'guards': guards,
        'scope': 'Observed historical download jobs in this workspace; excludes other apps and uninstrumented jobs.'}
