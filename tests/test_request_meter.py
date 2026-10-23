from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from requests_cache import CachedSession, CacheMixin

from src.app_services import request_meter as usage


@pytest.fixture
def job(tmp_path):
    folder = tmp_path/'outputs/app_runs/20261011T000000Z_aabbccdd'
    folder.mkdir(parents=True)
    return tmp_path, folder


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path.startswith('/redirect'):
                self.send_response(302); self.send_header('Location', '/cached')
            else:
                self.send_response(429 if self.path.startswith('/limited') else 200)
                self.send_header('Cache-Control', 'max-age=3600')
                self.send_header('Content-Type', 'application/json')
                if self.path.startswith('/limited'):
                    self.send_header('Retry-After', '120')
            self.end_headers()
            self.wfile.write(b'{}')
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}'
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=3)


def test_actual_transport_vs_http_and_processed_cache_hits_restore_hooks(job, server):
    from fastf1.req import _logger
    root, folder = job
    original_transport = requests.adapters.HTTPAdapter.send
    original_cache = CacheMixin.send
    with usage.monitor_requests(folder):
        with CachedSession(backend='memory') as session:
            assert not session.get(server+'/cached?token=do-not-log').from_cache
            assert session.get(server+'/cached?token=do-not-log').from_cache
        _logger.info('Using cached data for session_info')
        meter = usage.request_usage(root, folder)
        assert meter['requests_last_hour'] == meter['requests_job'] == 1
        assert meter['http_cache_hits_job'] == 1 and meter['data_cache_hits_job'] == 1
    assert requests.adapters.HTTPAdapter.send is original_transport
    assert CacheMixin.send is original_cache
    saved = (folder/'api_requests.jsonl').read_text()
    assert 'token' not in saved and 'do-not-log' not in saved and server not in saved


def test_redirects_count_transport_calls_and_retry_after_countdown(job, server):
    root, folder = job
    with usage.monitor_requests(folder):
        assert requests.get(server+'/redirect').status_code == 200
        assert requests.get(server+'/limited').status_code == 429
    result = usage.request_usage(root, folder)
    assert result['requests_job'] == 3
    row = result['providers'][0]
    assert row['rate_limit_seen'] and 115 < row['retry_at']-result['as_of'] <= 120


def test_transport_failure_is_counted_and_exception_still_propagates(job, monkeypatch):
    root, folder = job
    def failing(*a, **kw):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', failing)
    with pytest.raises(requests.ConnectionError):
        with usage.monitor_requests(folder):
            requests.get('https://api.openf1.org/v1/sessions')
    assert requests.adapters.HTTPAdapter.send is failing
    result = usage.request_usage(root, folder)
    assert result['requests_job'] == 1 and result['providers'][0]['network_errors_last_hour'] == 1


def test_guard_block_is_not_a_network_request_and_reset_decays_on_ui_poll(job, monkeypatch):
    from fastf1.req import _SessionWithRateLimiting
    from fastf1.exceptions import RateLimitExceededError
    root, folder = job
    monkeypatch.setattr(usage, '_guards', lambda now: [{'name': 'any API: 500 calls/h', 'limit': 3,
        'window_seconds': 3600, 'timestamps': [900., 901., 902.]}])
    def blocked(*a, **kw):
        raise RateLimitExceededError('any API: 500 calls/h')
    monkeypatch.setattr(_SessionWithRateLimiting, 'send', blocked)
    with usage.monitor_requests(folder, clock=lambda: 1000.):
        with pytest.raises(RateLimitExceededError):
            _SessionWithRateLimiting().get('https://api.jolpi.ca/ergast/f1/2025.json')
    result = usage.request_usage(root, folder, now=1000.)
    assert result['requests_job'] == 0
    assert result['providers'][0]['rate_limit_seen']
    assert result['guards'][0]['remaining'] == 0
    assert result['guards'][0]['next_slot_at'] == 4500.
    expired = usage.request_usage(root, folder, now=4501.)
    assert expired['guards'][0]['remaining'] == 2
    assert expired['guards'][0]['next_slot_at'] is None


def test_rolling_hour_spans_download_jobs_and_retains_separate_job_totals(job):
    root, folder = job
    old = folder.with_name('earlier'); old.mkdir()
    before = usage.RequestMeter(old, clock=lambda: 1000.)
    before.record('network', 'jolpica')
    before.record('http_cache', 'jolpica')
    current = usage.RequestMeter(folder, clock=lambda: 4000.)
    current.record('network', 'timing')
    current.record('http_cache', 'timing')
    result = usage.request_usage(root, folder, now=4001.)
    assert result['requests_last_hour'] == 2 and result['requests_job'] == 1
    assert result['http_cache_hits_job'] == 1
    assert {p['provider'] for p in result['providers']} == {'jolpica', 'timing'}
    assert usage.request_usage(root, folder, now=4600.)['requests_last_hour'] == 1
    assert usage.request_usage(root, folder, now=7601.)['requests_last_hour'] == 0


def test_old_jobs_are_unknown_and_interrupted_event_lines_do_not_zero_counts(job):
    root, folder = job
    assert usage.request_usage(root, folder)['status'] == 'unavailable'
    meter = usage.RequestMeter(folder, clock=lambda: 1000.)
    meter.record('network', 'openf1')
    with (folder/'api_requests.jsonl').open('a') as handle:
        handle.write('{"time":')
    assert usage.request_usage(root, folder, now=1001.)['requests_job'] == 1


@pytest.mark.parametrize('url,expected', [('https://api.openf1.org/v1/session_result?key=x', 'openf1'),
    ('https://api.jolpi.ca/ergast/f1', 'jolpica'), ('https://livetiming.formula1.com/static', 'timing'),
    ('https://raw.githubusercontent.com/theOehrly/f1schedule/master', 'github'),
    ('https://api.openf1.org.evil.example/', 'other')])
def test_provider_matching_does_not_record_urls(url, expected):
    assert usage.provider(url) == expected


def test_retry_after_accepts_seconds_and_http_date_but_not_unknown_values():
    assert usage.retry_time('120', 1000.) == 1120.
    stamp = datetime.fromtimestamp(1120., timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    assert usage.retry_time(stamp, 1000.) == 1120.
    for invalid in (None, '-1', 'nan', 'not-a-date'):
        assert usage.retry_time(invalid, 1000.) is None


def test_download_status_exposes_meter_without_changing_completed_data(job):
    from src.app_services.simulation_jobs import SimulationJobs, write_json
    root, folder = job
    write_json(folder/'job.json', {'id': folder.name, 'kind': 'historical_download', 'status': 'completed',
                                  'created_at': '2026-10-11T00:00:00Z'})
    usage.RequestMeter(folder).record('network', 'timing')
    service = SimulationJobs(root)
    result = service.status(folder.name)
    assert result['request_usage']['requests_job'] == 1
    assert result['status'] == 'completed'


def test_access_errors_pair_fallback_and_reset_between_sessions(job, monkeypatch):
    root, folder = job
    def response(adapter, request, **kwargs):
        result = requests.Response()
        result.status_code = 404 if 'mirror' in request.url else 401
        result._content = b''
        result.request = request
        result.url = request.url
        return result
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', response)
    with usage.monitor_requests(folder) as meter:
        requests.get('https://livetiming.formula1.com/static/session?secret=private')
        assert meter.provider_issue() is None  # Give the fallback a chance.
        requests.get('https://livetiming-mirror.fastf1.dev/static/session')
        assert 'HTTP 401' in meter.provider_issue() and 'HTTP 404' in meter.provider_issue()
        assert usage.request_usage(root, folder)['providers'][0]['http_errors_job'] == 2
        meter.begin_session()
        assert meter.provider_issue() is None
        meter.observe_response('https://livetiming.formula1.com/static/session', 403)
        meter.observe_response('https://livetiming-mirror.fastf1.dev/static/session', 200)
        assert meter.provider_issue() is None
    journal = (folder/'api_requests.jsonl').read_text()
    assert 'private' not in journal and '/static/' not in journal
    assert requests.adapters.HTTPAdapter.send is response
