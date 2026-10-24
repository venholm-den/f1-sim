import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.app_services import post_race_automation as automation
from src.app_services.beta import digest, freeze_snapshot


def forecast(root, identifier, session='Q', created='2026-10-03T11:00:00+00:00', category='prospective'):
    folder = root / 'outputs/app_runs' / identifier
    folder.mkdir(parents=True)
    context = {'year': 2026, 'event': 'Example GP', 'session': session,
               'race_start_utc': '2026-10-04T07:00:00+00:00'}
    pd.DataFrame({'Driver': ['A', 'B'], 'avg_finish': [1.2, 1.8],
                  'win_chance': [.8, .2]}).to_csv(folder / 'simulation_summary.csv', index=False)
    freeze_snapshot(folder, context, now=created, category=category)
    (folder / 'job.json').write_text(json.dumps({'id': identifier, 'kind': 'forecast',
                                                'status': 'completed', 'discord_enabled': True}))
    return folder


def fake_scoring(folder, source):
    pd.DataFrame({'Driver': ['A', 'B'], 'actual_position': [2, 1]}).to_csv(folder / 'actual_results.csv', index=False)
    pd.DataFrame({'Driver': ['A', 'B'], 'avg_finish': [1.2, 1.8], 'actual_position': [2, 1],
                  'finish_error': [-.8, .8], 'win_chance': [.8, .2]}).to_csv(folder / 'score_comparison.csv', index=False)
    (folder / 'score.json').write_text(json.dumps({'drivers': 2, 'finish_mae': .8,
        'snapshot_sha256': digest(source / 'frozen/manifest.json')}))


@pytest.fixture
def scoring(monkeypatch):
    monkeypatch.setattr(automation, 'run_scoring', fake_scoring)

    def render(folder, context):
        (folder / 'post_race_analysis.txt').write_text('Measured analysis')
        (folder / 'forecast_vs_actual.png').write_bytes(b'chart')

    monkeypatch.setattr(automation, 'render_analysis', render)
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/0/test')


def test_selects_latest_snapshot_once_per_race_and_waits_eight_hours(tmp_path):
    forecast(tmp_path, 'early', session='FP3', created='2026-10-03T08:00:00+00:00')
    latest = forecast(tmp_path, 'latest')
    forecast(tmp_path, 'replay', created='2026-10-03T12:00:00+00:00', category='retrospective')
    assert automation.eligible_forecasts(tmp_path, datetime(2026, 10, 4, 14, 59, tzinfo=timezone.utc)) == []
    ready = automation.eligible_forecasts(tmp_path, datetime(2026, 10, 4, 15, tzinfo=timezone.utc))
    assert len(ready) == 1 and ready[0][0] == latest


def test_local_preparation_then_delivery_is_once_only_and_preserves_forecast(tmp_path, monkeypatch, scoring):
    source = forecast(tmp_path, 'forecast')
    before = {path.name: path.read_bytes() for path in (source / 'frozen').iterdir()}
    calls = []
    monkeypatch.setattr(automation, 'post_files_to_discord',
                        lambda **kwargs: calls.append(kwargs) or {'ok': True, 'status': 200, 'response': 'private'})
    first = automation.run_post_race_queue(tmp_path)
    assert first[0]['status'] == 'completed' and not calls
    second = automation.run_post_race_queue(tmp_path, discord_enabled=True)
    third = automation.run_post_race_queue(tmp_path, discord_enabled=True)
    assert second[0]['discord']['ok'] and third[0]['discord']['skipped']
    assert len(calls) == 1 and len(calls[0]['file_paths']) == 5
    assert first[0]['folder'] == second[0]['folder'] == third[0]['folder']
    receipt = json.loads((Path(first[0]['folder']) / 'discord_post_result.json').read_text())
    assert 'response' not in receipt
    assert before == {path.name: path.read_bytes() for path in (source / 'frozen').iterdir()}


def test_incomplete_official_results_fail_then_retry_without_posting(tmp_path, monkeypatch, scoring):
    forecast(tmp_path, 'forecast')
    monkeypatch.setattr(automation, 'run_scoring', lambda *args: (_ for _ in ()).throw(ValueError('Official results unavailable')))
    monkeypatch.setattr(automation, 'post_files_to_discord', lambda **kwargs: pytest.fail('Unexpected upload'))
    first = automation.run_post_race_queue(tmp_path, discord_enabled=True)
    assert first[0]['status'] == 'failed'
    assert not (Path(first[0]['folder']) / 'discord_post_result.json').exists()
    monkeypatch.setattr(automation, 'run_scoring', fake_scoring)
    second = automation.run_post_race_queue(tmp_path)
    assert second[0]['status'] == 'completed' and second[0]['folder'] != first[0]['folder']
    assert json.loads((Path(first[0]['folder']) / 'job.json').read_text())['status'] == 'failed'


def test_http_failure_retries_saved_analysis_after_backoff(tmp_path, monkeypatch, scoring):
    forecast(tmp_path, 'forecast')
    calls = []
    monkeypatch.setattr(automation, 'post_files_to_discord',
                        lambda **kwargs: calls.append(kwargs) or {'ok': False, 'status': 503})
    first = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    assert first['discord']['delivery_state'] == 'pending'
    second = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    assert second['discord']['skipped'] and len(calls) == 1
    receipt_path = Path(first['folder']) / 'discord_post_result.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['next_attempt_at'] = '2000-01-01T00:00:00+00:00'
    receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setattr(automation, 'run_scoring', lambda *args: pytest.fail('Analysis should be reused'))
    monkeypatch.setattr(automation, 'post_files_to_discord', lambda **kwargs: {'ok': True, 'status': 204})
    assert automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]['discord']['ok']


@pytest.mark.parametrize('outcome', ['url_error', 'crash'])
def test_uncertain_upload_is_never_repeated(tmp_path, monkeypatch, scoring, outcome):
    forecast(tmp_path, 'forecast')
    calls = []

    def post(**kwargs):
        calls.append(kwargs)
        if outcome == 'crash':
            raise RuntimeError('Connection lost')
        return {'ok': False, 'status': outcome}

    monkeypatch.setattr(automation, 'post_files_to_discord', post)
    first = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    second = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    assert first['discord']['delivery_state'] == 'uncertain'
    assert second['discord']['requires_review'] and len(calls) == 1


def test_changed_source_cannot_be_posted(tmp_path, monkeypatch, scoring):
    source = forecast(tmp_path, 'forecast')
    automation.run_post_race_queue(tmp_path)
    manifest_path = source / 'frozen/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['limitations'].append('changed')
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(automation, 'post_files_to_discord', lambda **kwargs: pytest.fail('Unexpected upload'))
    result = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    assert result['status'] == 'failed' and 'does not match' in result['error']


def test_real_report_renders_measured_driver_comparison(tmp_path):
    source = forecast(tmp_path, 'forecast')
    report = tmp_path / 'report'
    report.mkdir()
    fake_scoring(report, source)
    automation.render_analysis(report, {'year': 2026, 'event': 'Example GP', 'session': 'Q'})
    text = (report / 'post_race_analysis.txt').read_text()
    assert 'P1 **B**' in text and '20.0%' in text and '0.80 places' in text
    payload = json.loads((report / 'post_race_embed.json').read_text())
    assert payload['embeds'][0]['title'].endswith('Post-race analysis')
    assert (report / 'forecast_vs_actual.png').read_bytes().startswith(b'\x89PNG')


def test_not_yet_available_official_results_wait_without_delivery(tmp_path, monkeypatch):
    forecast(tmp_path, 'forecast')
    def waiting(*args):
        raise automation.ResultsNotReady('Official results pending')
    monkeypatch.setattr(automation, 'run_scoring', waiting)
    monkeypatch.setattr(automation, 'post_files_to_discord', lambda **kwargs: pytest.fail('Unexpected upload'))
    result = automation.run_post_race_queue(tmp_path, discord_enabled=True)[0]
    assert result['status'] == 'waiting_for_results'
    assert json.loads((Path(result['folder'])/'job.json').read_text())['status'] == 'waiting_for_results'
    assert not (Path(result['folder'])/'discord_post_result.json').exists()
