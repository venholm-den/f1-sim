from __future__ import annotations

import hashlib
from unittest.mock import Mock

import pandas as pd
import pytest

from src.app_services import simulation_jobs as module
from src.app_services.simulation_jobs import SimulationJobs, write_json
from portable_app.instance_lock import workspace_lock


@pytest.fixture
def jobs(tmp_path):
    return SimulationJobs(tmp_path)


@pytest.mark.parametrize('payload', [
    {'kind': 'unknown'}, {'scenario': 'unknown'}, {'n_sims': 0},
    {'seed': -1}, {'overtaking_difficulty': float('nan')},
    {'overtaking_difficulty': 1.1}, {'source_dir': '..'},
])
def test_invalid_launch_is_rejected_without_creating_run(jobs, payload):
    with pytest.raises(ValueError):
        jobs.start(payload)
    assert jobs.history() == []


def test_invalid_result_paths_are_rejected(jobs):
    for path in ['../', '../../README.md', 'unknown']:
        with pytest.raises(ValueError):
            jobs.results(path)


def test_results_filter_chart_and_verification_tampering(jobs):
    folder = jobs.root/'outputs/matlab/experiments'
    folder.mkdir(parents=True)
    pd.DataFrame({'Driver': ['A','A','B'], 'scenario': ['baseline','stops_2','baseline'],
                  'simulated_rank': [1,1,2]}).to_csv(folder/'scenario_comparison.csv', index=False)
    pd.DataFrame({'Driver': ['A','A','B'], 'scenario': ['baseline','stops_2','baseline'],
                  'lap': [1,1,1], 'lap_time_seconds': [80,82,83]}).to_csv(folder/'lap_dynamics_results.csv', index=False)
    (folder/'experiment_inputs.csv').write_text('input')
    (folder/'lap_dynamics_summary.csv').write_text('summary')
    check = {'status':'PASS', 'cases_verified':3}
    for name, key in [('experiment_inputs.csv','inputs_sha256'),
                      ('lap_dynamics_results.csv','detail_sha256'),
                      ('lap_dynamics_summary.csv','summary_sha256')]:
        check[key] = hashlib.sha256((folder/name).read_bytes()).hexdigest()
    write_json(folder/'verification.json', check)
    result = jobs.results('existing-experiments', 'A', 'stops_2')
    assert len(result['rows']) == 1
    assert result['drivers'] == ['A','B']
    assert {row['scenario'] for row in result['laps']} == {'baseline','stops_2'}
    assert result['verification']['status'] == 'PASS'
    exported = jobs.export('existing-experiments', 'A', 'stops_2')
    assert exported['rows'] == 1
    assert pd.read_csv(exported['path']).scenario.tolist() == ['stops_2']
    assert jobs.export('existing-experiments', 'A', 'stops_2')['path'] != exported['path']
    (folder/'experiment_inputs.csv').write_text('changed')
    assert jobs.results('existing-experiments')['verification']['status'] == 'STALE'


def test_launch_snapshots_inputs_and_rejects_concurrent_run(jobs, monkeypatch):
    source = jobs.root/'outputs'
    (source/'driver_model_features.csv').write_text('Driver,Team\nA,T\n')
    process = Mock(pid=123)
    process.poll.return_value = None
    monkeypatch.setattr(module.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(module.threading, 'Thread', Mock())
    monkeypatch.setattr(module, 'matlab_executable', lambda: None)
    run = jobs.start({'kind':'monte_carlo'})
    folder = jobs._folder(run['id'])
    assert (folder/'features.csv').read_text() == (source/'driver_model_features.csv').read_text()
    assert jobs.state()['active_id'] == run['id']
    with pytest.raises(ValueError, match='already running'):
        jobs.start({})
    process.poll.return_value = 0
    process.wait.return_value = 0
    jobs._wait(run['id'], process)
    assert jobs.status(run['id'])['status'] == 'completed'
    assert jobs.state()['active_id'] is None


def test_cancel_updates_status_and_wait_marks_cancelled(jobs, monkeypatch):
    folder = jobs.run_root/'20260907T000000Z_1234abcd'
    folder.mkdir()
    write_json(folder/'job.json', {'id':folder.name, 'status':'running', 'created_at':'2026-09-07'})
    jobs.active_id = folder.name
    jobs.process = Mock(pid=123)
    jobs.process.poll.return_value = None
    jobs.process.wait.return_value = 1
    monkeypatch.setattr(module.subprocess, 'run', Mock())
    assert jobs.cancel()
    assert jobs.status(folder.name)['status'] == 'cancelled'
    jobs._wait(folder.name, jobs.process)
    assert jobs.status(folder.name)['status'] == 'cancelled'


def test_failed_job_shows_the_worker_reason(jobs):
    folder = jobs.run_root/'20260907T000000Z_5678abcd'
    folder.mkdir()
    write_json(folder/'job.json', {'id':folder.name, 'status':'running', 'created_at':'2026-09-07'})
    write_json(folder/'failure.json', {'message':'FastF1 could not load this session.', 'session_load':True})
    jobs._wait(folder.name, Mock(wait=Mock(return_value=1)))
    status = jobs.status(folder.name)
    assert status['status'] == 'failed'
    assert status['error'] == 'FastF1 could not load this session.'


def test_workspace_lock_rejects_second_instance_and_releases(tmp_path):
    with workspace_lock(tmp_path):
        with pytest.raises(RuntimeError, match='already open'):
            with workspace_lock(tmp_path):
                pass
    with workspace_lock(tmp_path):
        pass


def test_desktop_bridge_does_not_expose_native_window_or_job_internals(tmp_path, monkeypatch):
    from portable_app import web_backend
    monkeypatch.setattr(web_backend, 'project_root', lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    api = web_backend.PortableWebApi()
    native = object()
    api.set_window(native)
    public = [name for name in dir(api) if not name.startswith('_')]
    assert 'window' not in public
    assert 'jobs' not in public
    assert api._window is native


@pytest.mark.parametrize('content', ['{', '[]', '{}', '{"id":1,"status":null,"created_at":[]}'])
def test_bad_history_does_not_block_startup_or_modify_evidence(tmp_path, content):
    folder = tmp_path/'outputs/app_runs/20261011T000000Z_1234abcd'
    folder.mkdir(parents=True)
    path = folder/'job.json'
    path.write_text(content)
    jobs = SimulationJobs(tmp_path)
    assert jobs.history()[0]['status'] == 'unreadable'
    assert jobs.status(folder.name)['metadata_error']
    assert path.read_text() == content
