import json
from unittest.mock import Mock

import pytest

from portable_app import job_worker
from src.app_services import forecast_automation
from src.app_services.discord_settings import local_webhook
from src.app_services.simulation_jobs import SimulationJobs
from tests.test_forecast_automation import fake_forecast


def test_local_webhook_precedence(tmp_path):
    assert local_webhook(tmp_path) == ''
    (tmp_path / '.env').write_text('DISCORD_WEBHOOK_URL=https://discord.invalid/manual')
    (tmp_path / '.env.automation').write_text('DISCORD_WEBHOOK_URL=https://discord.invalid/auto')
    assert local_webhook(tmp_path).endswith('/auto')
    (tmp_path / '.env.discord').write_text('DISCORD_WEBHOOK_URL=https://discord.invalid/app')
    assert local_webhook(tmp_path).endswith('/app')


def test_upload_job_requires_configuration_and_keeps_secret_out_of_job(tmp_path, monkeypatch):
    jobs = SimulationJobs(tmp_path)
    forecast = jobs.run_root / '20261003T000000Z_1234abcd'
    forecast.mkdir()
    fake_forecast(forecast, {})
    (forecast / 'job.json').write_text(json.dumps({'id': forecast.name, 'status': 'completed',
                                                'kind': 'forecast', 'created_at': '2026-10-03'}))
    with pytest.raises(ValueError, match='not configured'):
        jobs.start({'kind': 'discord', 'forecast_id': forecast.name})
    (tmp_path / '.env.discord').write_text('DISCORD_WEBHOOK_URL=https://discord.invalid/secret')
    monkeypatch.setattr('src.app_services.simulation_jobs.subprocess.Popen', Mock(return_value=Mock()))
    monkeypatch.setattr('src.app_services.simulation_jobs.threading.Thread', Mock())
    job = jobs.start({'kind': 'discord', 'forecast_id': forecast.name})
    assert 'secret' not in (jobs._folder(job['id']) / 'job.json').read_text()
    assert json.loads((jobs._folder(job['id']) / 'job.json').read_text())['forecast_folder'] == str(forecast)


def test_upload_worker_uses_explicit_local_webhook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env.discord').write_text('DISCORD_WEBHOOK_URL=https://discord.invalid/local')
    folder = tmp_path / 'upload'
    folder.mkdir()
    (folder / 'job.json').write_text(json.dumps({'kind': 'discord', 'forecast_folder': str(tmp_path)}))
    post = Mock(return_value={'ok': True, 'posted_files': ['simulation_summary.csv']})
    monkeypatch.setattr(forecast_automation, 'post_frozen_forecast', post)
    job_worker.run(folder)
    assert post.call_args.kwargs['webhook_url'] == 'https://discord.invalid/local'
    assert json.loads((folder / 'upload_result.json').read_text())['ok']
