import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from portable_app.web_backend import PortableWebApi
from src.app_services import automation_feed


def forecast(root, identifier, stamp, session='Q', status='completed', kind='forecast'):
    folder = root / 'outputs/app_runs' / identifier
    (folder/'frozen').mkdir(parents=True)
    (folder/'source').mkdir()
    summary = b'Driver,Team,avg_finish,win_chance,podium_chance,dnf_chance\nAAA,Team,1,0.8,0.9,0.02\n'
    (folder/'frozen/simulation_summary.csv').write_bytes(summary)
    # A mutable support export must never replace the frozen probabilities.
    (folder/'source/simulation_summary.csv').write_bytes(summary.replace(b'0.8', b'0.1'))
    context = {'year': 2026, 'event': 'Example GP', 'session': session}
    (folder/'frozen/manifest.json').write_text(json.dumps({
        'context': context, 'created_at_utc': stamp, 'category': 'prospective',
        'files': {'simulation_summary.csv': hashlib.sha256(summary).hexdigest()}}))
    (folder/'job.json').write_text(json.dumps({'id': identifier, 'kind': kind, 'status': status}))
    return folder


@pytest.fixture
def roots(tmp_path, monkeypatch):
    local, pc = tmp_path/'desktop', tmp_path/'pc'
    local.mkdir(); pc.mkdir()
    monkeypatch.setattr(automation_feed, 'DEFAULT_PC_WORKSPACE', pc)
    monkeypatch.chdir(local)
    return local, pc


def test_feed_orders_by_forecast_timestamp_across_workspaces_and_skips_other_jobs(roots):
    local, pc = roots
    forecast(pc, 'z-old', '2026-10-01T14:00:00Z', 'FP1')
    latest = forecast(local, 'a-new', '2026-10-02T15:00:00+01:00', 'Q')
    forecast(pc, 'new-running', '2026-10-03T15:00:00Z', status='running')
    forecast(pc, 'new-training', '2026-10-03T15:00:00Z', kind='historical_training')
    result = automation_feed.forecast_feed(local)
    assert result['latest']['id'] == str(latest)
    assert result['latest']['context']['session'] == 'Q'
    assert len(result['runs']) == 2


def test_changed_frozen_file_is_rejected_and_never_repaired(roots):
    local, pc = roots
    older = forecast(pc, 'old', '2026-10-01T14:00:00Z')
    bad = forecast(pc, 'bad', '2026-10-02T14:00:00Z')
    path = bad/'frozen/simulation_summary.csv'
    path.write_text('tampered')
    result = automation_feed.forecast_feed(local)
    assert result['latest']['id'] == str(older)
    assert result['rejected'] == 1
    assert path.read_text() == 'tampered'
    with pytest.raises(ValueError, match='unavailable'):
        automation_feed.selected_forecast(local, '', str(bad))


def test_repeat_polls_reuse_verification_until_a_frozen_file_changes(roots, monkeypatch):
    local, pc = roots
    run = forecast(pc, 'cached', '2026-10-01T14:00:00Z')
    calls = []
    original = automation_feed.verified_snapshot
    monkeypatch.setattr(automation_feed, 'verified_snapshot', lambda folder: calls.append(folder) or original(folder))
    for _ in range(3):
        assert automation_feed.forecast_feed(local)['latest']['id'] == str(run)
    assert len(calls) == 1
    (run/'frozen/simulation_summary.csv').write_text('tampered after the first poll')
    result = automation_feed.forecast_feed(local)
    assert result['latest'] is None and result['rejected'] == 1


def test_missing_pc_workspace_and_duplicate_roots(roots):
    local, pc = roots
    forecast(local, 'one', '2026-10-01T14:00:00Z')
    assert len(automation_feed.forecast_feed(local, str(local))['runs']) == 1
    result = automation_feed.forecast_feed(local, str(pc/'missing'))
    assert not result['pc_available']
    assert result['latest']['job_id'] == 'one'


def test_delivery_status_exposes_receipts_separately_from_health_without_secrets(roots):
    local, pc = roots
    run = forecast(pc, 'one', '2026-10-01T14:00:00Z')
    (run/'discord_post_result.json').write_text(json.dumps({'ok':True,'status':200,
        'delivery_state':'sent','attempted_at':'2026-10-01T14:02:00Z','response':'PRIVATE SECRET'}))
    weekend = pc/'outputs/weekend_briefings/2026_round_18'; weekend.mkdir(parents=True)
    (weekend/'briefing.json').write_text(json.dumps({'year':2026,'event':'US GP'}))
    (weekend/'discord_post_result.json').write_text(json.dumps({'ok':False,'delivery_state':'uncertain',
        'attempted_at':'2026-10-22T08:02:00Z','error':'PRIVATE SECRET'}))
    health = pc/'outputs/automation'; health.mkdir()
    (health/'last_health.json').write_text(json.dumps({'status':'warning','warnings':['classification_checks'],
        'checked_at_utc':'2026-10-23T18:00:00Z','secret':'PRIVATE SECRET'}))
    result = automation_feed.forecast_feed(local)
    assert result['deliveries'][0]['status'] == 'uncertain'
    assert result['deliveries'][1]['status'] == 'sent'
    assert result['health']['status'] == 'warning'
    assert 'PRIVATE' not in json.dumps(result)
    (run/'discord_post_result.json').write_text('{bad')
    assert automation_feed.delivery_status(run, label='Forecast', kind='forecast')['status'] == 'unreadable'


def test_initial_defaults_follow_frozen_context_even_when_calendar_has_no_session(roots, monkeypatch):
    local, pc = roots
    folder = forecast(pc, 'forecast', '2026-10-01T14:00:00Z', 'PRE')
    api = PortableWebApi()
    monkeypatch.setattr(api, 'setup_options', lambda *_: {'sessions':['Q']})
    monkeypatch.setattr(api, 'events_for_year', lambda *_: ['latest'])
    monkeypatch.setattr(api, 'outputs', lambda payload: {'outputDir': payload['output_dir']})
    initial = api.initial_state()
    assert initial['settings']['year'] == 2026
    assert initial['settings']['event'] == 'Example GP'
    assert initial['settings']['session'] == 'PRE'
    assert initial['outputs']['automationRun']['id'] == str(folder)
    assert 'PRE' in initial['sessions'] and 'Example GP' in initial['events']
    api.automation_preferences(False)
    reloaded = PortableWebApi()
    assert not reloaded.automation_state()['following']
    assert not reloaded.default_settings.post_to_discord


def test_load_uses_frozen_summary_and_context_and_keeps_every_archive_byte(roots, monkeypatch):
    local, pc = roots
    folder = forecast(pc, 'forecast', '2026-10-01T14:00:00Z')
    before = {path: path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    import portable_app.web_backend as backend
    monkeypatch.setattr(backend, 'track_layout_payload', lambda *_: {'status':'missing','message':'No telemetry'})
    monkeypatch.setattr(backend, 'session_screen_payloads', lambda *_: {})
    monkeypatch.setattr(backend, 'sector_leaders', lambda *_: {})
    monkeypatch.setattr(backend, 'fastest_lap', lambda *_: {})
    api = PortableWebApi()
    output = api.automation_load(str(folder))
    assert output['summaryTable']['rows'][0]['win_chance'] == '0.8'
    assert output['savedContext'] == {'year':2026,'event':'Example GP','session':'Q','source':'verified_frozen_forecast'}
    assert before == {path:path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='unavailable'):
        api.automation_load(str(local/'unregistered'))


def test_comparison_history_includes_pc_runs_and_verifies_again_on_read(roots):
    local, pc = roots
    folder = forecast(pc, 'forecast', '2026-10-01T14:00:00Z')
    api = PortableWebApi()
    item = next(item for item in api.workbench_history()['history'] if item['id'].startswith('pc:'))
    assert item['label'].endswith('PC forecast')
    (folder/'frozen/simulation_summary.csv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        api.workbench_compare(item['id'], item['id'])
