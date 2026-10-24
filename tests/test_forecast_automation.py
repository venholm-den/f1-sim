import json
from pathlib import Path

import pandas as pd
import pytest

from src.app_services import forecast_automation


def sample_context(session="FP1"):
    return {
        "year": 2026,
        "event": "Example GP",
        "round": 1,
        "session": session,
        "available_sessions": [session],
        "race_start_utc": "2026-06-07T14:00:00+00:00",
        "data_cutoff_utc": "2026-06-05T16:00:00+00:00",
        "session_policy": "test",
    }


def fake_forecast(folder: Path, job: dict, context=None) -> None:
    selected = context or sample_context()
    (folder / "forecast_context.json").write_text(json.dumps(selected), encoding="utf-8")
    pd.DataFrame({"Driver": ["A"], "avg_finish": [1.0]}).to_csv(
        folder / "simulation_summary.csv", index=False
    )
    (folder / "features.csv").write_text("Driver,Team\nA,T\n", encoding="utf-8")
    from src.app_services.beta import freeze_snapshot

    freeze_snapshot(folder, selected, now="2026-06-05T16:01:00Z")


def test_runs_once_then_skips_valid_frozen_session(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, "next_race", lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, "run_forecast", fake_forecast)

    first = forecast_automation.run_automated_forecast(tmp_path, n_sims=100)
    second = forecast_automation.run_automated_forecast(tmp_path, n_sims=100)

    assert first["status"] == "completed"
    assert second["status"] == "skipped"
    assert second["reason"] == "already_completed"
    jobs = list((tmp_path / "outputs" / "app_runs").glob("*/job.json"))
    assert len(jobs) == 1
    assert json.loads(jobs[0].read_text(encoding="utf-8"))["status"] == "completed"


def test_post_race_queue_runs_even_when_next_forecast_already_exists(tmp_path, monkeypatch):
    from src.app_services import post_race_automation
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, 'run_forecast', fake_forecast)
    forecast_automation.run_automated_forecast(tmp_path, n_sims=100)
    calls = []

    def queue(root, *, discord_enabled):
        calls.append((root, discord_enabled))
        return [{'status': 'completed', 'discord': None}]

    monkeypatch.setattr(post_race_automation, 'run_post_race_queue', queue)
    result = forecast_automation.run_automated_forecast(tmp_path, n_sims=100, post_race_enabled=True)
    assert result['reason'] == 'already_completed'
    assert result['post_race'][0]['status'] == 'completed'
    assert calls == [(tmp_path, False)]


def test_new_session_creates_another_forecast(tmp_path, monkeypatch):
    selected = sample_context()
    monkeypatch.setattr(forecast_automation, "next_race", lambda root: selected)
    monkeypatch.setattr(forecast_automation, "run_forecast", fake_forecast)
    forecast_automation.run_automated_forecast(tmp_path, n_sims=100)

    selected["session"] = "FP2"
    selected["available_sessions"] = ["FP1", "FP2"]

    def fp2_forecast(folder, job, context=None):
        (folder / "forecast_context.json").write_text(json.dumps(selected), encoding="utf-8")
        pd.DataFrame({"Driver": ["A"], "avg_finish": [1.0]}).to_csv(
            folder / "simulation_summary.csv", index=False
        )
        from src.app_services.beta import freeze_snapshot

        freeze_snapshot(folder, selected, now="2026-06-05T19:01:00Z")

    monkeypatch.setattr(forecast_automation, "run_forecast", fp2_forecast)
    result = forecast_automation.run_automated_forecast(tmp_path, n_sims=100)

    assert result["status"] == "completed"
    assert len(list((tmp_path / "outputs" / "app_runs").glob("*/job.json"))) == 2


def test_failure_is_recorded_and_retried_next_time(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, "next_race", lambda root: sample_context())

    def fail(folder, job, context=None):
        raise RuntimeError("FastF1 data unavailable")

    monkeypatch.setattr(forecast_automation, "run_forecast", fail)
    with pytest.raises(RuntimeError, match="FastF1"):
        forecast_automation.run_automated_forecast(tmp_path, n_sims=100)

    failed_job = next((tmp_path / "outputs" / "app_runs").glob("*/job.json"))
    assert json.loads(failed_job.read_text(encoding="utf-8"))["status"] == "failed"

    monkeypatch.setattr(forecast_automation, "run_forecast", fake_forecast)
    result = forecast_automation.run_automated_forecast(tmp_path, n_sims=100)
    assert result["status"] == "completed"
    assert len(list((tmp_path / "outputs" / "app_runs").glob("*/job.json"))) == 2


def test_discord_posts_frozen_forecast_once(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, "next_race", lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, "run_forecast", fake_forecast)
    calls = []

    def post(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "status": 204, "posted_files": kwargs["file_paths"]}

    monkeypatch.setattr(forecast_automation, "post_files_to_discord", post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/test")

    first = forecast_automation.run_automated_forecast(
        tmp_path, n_sims=100, discord_enabled=True
    )
    second = forecast_automation.run_automated_forecast(
        tmp_path, n_sims=100, discord_enabled=True
    )

    assert first["discord"]["ok"]
    assert second["discord"]["skipped"]
    assert len(calls) == 1
    assert calls[0]["file_paths"][0].name == "race_outlook.png"
    assert 'simulation_summary.csv' in [p.name for p in calls[0]['file_paths']]


def test_complete_bundle_batches_and_does_not_resend(tmp_path, monkeypatch):
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'full')
    fake_forecast(tmp_path, {})
    paths = ['report/race_dashboard.png', 'report/tyre_strategy_timeline.png',
             'report/fantasy_risk_reward.png', 'report/simulated_race_times.png',
             'probabilities.png', 'fantasy_expected_points.png', 'fantasy_value.png',
             'detailed_report.png', 'strategy/predicted_tyre_strategy.png',
             'season/latest_season_projection.png']
    for name in paths:
        path = tmp_path / 'source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'image')
    calls = []

    def post(**kwargs):
        calls.append(kwargs['file_paths'])
        return {'ok': True, 'status': 204, 'posted_files': kwargs['file_paths']}

    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', post)
    result = forecast_automation.post_frozen_forecast(tmp_path, 'https://discord.invalid/test')
    assert result['ok'] and result['batches'] == 2
    assert [len(batch) for batch in calls] == [10, 2]
    assert 'fantasy_value.png' in [path.name for batch in calls for path in batch]
    assert forecast_automation.post_frozen_forecast(tmp_path)['skipped']
    assert len(calls) == 2


def test_partial_batch_failure_keeps_successful_batch(tmp_path, monkeypatch):
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'full')
    fake_forecast(tmp_path, {})
    report = tmp_path / 'source/report'
    report.mkdir(parents=True)
    for index in range(10):
        (report / f'{index}.png').write_bytes(b'image')
    calls = []

    def post(**kwargs):
        calls.append(kwargs['file_paths'])
        return {'ok': len(calls) != 2, 'status': 204 if len(calls) != 2 else 429,
                'posted_files': kwargs['file_paths']}

    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', post)
    with pytest.raises(RuntimeError):
        forecast_automation.post_frozen_forecast(tmp_path, 'https://discord.invalid/test')
    receipt = tmp_path / 'discord_batch_2_result.json'
    data = json.loads(receipt.read_text())
    data['next_attempt_at'] = '2000-01-01T00:00:00+00:00'
    receipt.write_text(json.dumps(data))
    result = forecast_automation.post_frozen_forecast(tmp_path, 'https://discord.invalid/test')
    assert result['ok'] and len(calls) == 3
    assert len(calls[-1]) == 2


def test_uncertain_batch_is_not_blindly_retried(tmp_path, monkeypatch):
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'full')
    fake_forecast(tmp_path, {})
    report = tmp_path / 'source/report'
    report.mkdir(parents=True)
    for index in range(10):
        (report / f'{index}.png').write_bytes(b'image')
    calls = []

    def post(**kwargs):
        calls.append(kwargs['file_paths'])
        return {'ok': len(calls) == 1, 'status': 204 if len(calls) == 1 else 'url_error',
                'posted_files': kwargs['file_paths']}

    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', post)
    with pytest.raises(RuntimeError):
        forecast_automation.post_frozen_forecast(tmp_path, 'https://discord.invalid/test')
    result = forecast_automation.post_frozen_forecast(tmp_path, 'https://discord.invalid/test')
    assert result['requires_review'] and len(calls) == 2


def test_discord_requires_local_webhook_after_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, "next_race", lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, "run_forecast", fake_forecast)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    with pytest.raises(ValueError, match="DISCORD_WEBHOOK_URL"):
        forecast_automation.run_automated_forecast(
            tmp_path, n_sims=100, discord_enabled=True
        )

    job_path = next((tmp_path / "outputs" / "app_runs").glob("*/job.json"))
    assert json.loads(job_path.read_text(encoding="utf-8"))["status"] == "completed"
    assert (job_path.parent / "frozen" / "manifest.json").is_file()


def test_queue_retries_old_session_after_next_session_becomes_eligible(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, 'run_forecast', fake_forecast)
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.invalid/test')
    monkeypatch.setattr(forecast_automation, 'post_files_to_discord',
                        lambda **kwargs: {'ok': False, 'status': 503})
    with pytest.raises(RuntimeError, match='Discord post failed'):
        forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    job_path = next((tmp_path / 'outputs/app_runs').glob('*/job.json'))
    receipt_path = job_path.parent / 'discord_post_result.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['next_attempt_at'] = '2000-01-01T00:00:00+00:00'
    receipt_path.write_text(json.dumps(receipt))
    calls = []

    def post(**kwargs):
        calls.append(kwargs)
        return {'ok': True, 'status': 204}

    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', post)
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context('FP2'))
    result = forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    assert result['deliveries'][0]['ok']
    assert len(calls) == 2


def test_uncertain_delivery_is_not_automatically_reposted(tmp_path, monkeypatch):
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, 'run_forecast', fake_forecast)
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.invalid/test')
    calls = []

    def post(**kwargs):
        calls.append(kwargs)
        return {'ok': False, 'status': 'url_error'}

    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', post)
    with pytest.raises(RuntimeError):
        forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    second = forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    assert second['discord']['requires_review']
    assert len(calls) == 1


def test_discord_failure_still_captures_trials_and_checks(tmp_path, monkeypatch):
    from src.app_services import classification_checks, prediction_trials
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, 'run_forecast', fake_forecast)
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.invalid/test')
    monkeypatch.setattr(forecast_automation, 'post_files_to_discord', lambda **kwargs: {'ok': False, 'status': 503})
    captured = []
    monkeypatch.setattr(prediction_trials, 'try_capture_trial', lambda root, folder: captured.append('trial'))
    monkeypatch.setattr(classification_checks, 'try_capture_checks', lambda root, folder: captured.append('checks'))
    with pytest.raises(RuntimeError, match='Discord post failed'):
        forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    assert captured == ['trial', 'checks']
