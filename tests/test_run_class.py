import json

import pytest

from scripts import publication_rehearsal as rehearsal
from src.app_services.accuracy import accuracy_state
from src.app_services.publication import build_publication
from src.app_services.run_class import OFFICIAL_PROTOCOL, classify, protocol_changes
from src.app_services.simulation_jobs import SimulationJobs


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def forecast(runs, name, **settings):
    context = {'year': 2026, 'event': 'Monaco Grand Prix', 'session': 'Q', 'race_start_utc': '2026-06-07T13:00:00Z'}
    write(runs/name/'job.json', {'id': name, 'kind': 'forecast', 'status': 'completed', 'created_at': name,
                                 **OFFICIAL_PROTOCOL, **settings})
    write(runs/name/'frozen/manifest.json', {'context': context, 'category': 'prospective'})


def test_only_protocol_forecasts_are_official(tmp_path):
    forecast(tmp_path, 'f1')
    forecast(tmp_path, 'f2', overtaking_difficulty=0.7)
    assert classify(tmp_path/'f1')['run_class'] == 'official'
    personal = classify(tmp_path/'f2')
    assert personal['run_class'] == 'personal'
    assert personal['reasons'] == ['Changed from the official protocol: Overtaking difficulty 0.55 → 0.7']
    write(tmp_path/'m/job.json', {'id': 'm', 'kind': 'manual_run', 'status': 'completed', 'created_at': 'm'})
    assert classify(tmp_path/'m')['reasons'][:2] == ['Not a forecast run (Race setup, what-if or replay)',
                                                    'No frozen pre-race snapshot']
    # Older records without a setting are not treated as changed.
    assert protocol_changes({'kind': 'forecast'}) == []


def test_personal_runs_stay_out_of_the_accuracy_record(tmp_path):
    runs = tmp_path/'outputs/app_runs'
    forecast(runs, 'f1')
    forecast(runs, 'f2', seed=7)
    forecast(runs, 'f3', n_sims=2000)
    for score, source in (('s1', 'f1'), ('s2', 'f2')):
        write(runs/score/'job.json', {'id': score, 'kind': 'score', 'status': 'completed', 'created_at': score,
                                      'forecast_id': source, 'forecast_folder': str(runs/source)})
        write(runs/score/'score.json', {'drivers': 20, 'finish_mae': 3.0})
    state = accuracy_state(tmp_path)
    assert [row['forecast_id'] for row in state['scored']] == ['f1']
    assert state['pending'] == []
    assert sorted(row['id'] for row in state['excluded']) == ['f3', 's2']
    assert all(row['reasons'] for row in state['excluded'])


def test_official_forecast_jobs_refuse_changed_settings(tmp_path):
    jobs = SimulationJobs(tmp_path)
    with pytest.raises(ValueError, match='fixed protocol'):
        jobs.start({'kind': 'forecast', **OFFICIAL_PROTOCOL, 'overtaking_difficulty': 0.8})
    assert not any((tmp_path/'outputs/app_runs').iterdir())


def test_personal_snapshot_cannot_be_published(tmp_path):
    folder = rehearsal.fixture_snapshot(tmp_path/'q', 'Q', '2024-07-06T16:30:00Z')
    job = json.loads((folder/'job.json').read_text())
    (folder/'job.json').write_text(json.dumps({**job, 'seed': 7}))
    with pytest.raises(ValueError, match='personal simulation'):
        build_publication(folder, 'established')
    (folder/'job.json').write_text(json.dumps({**job, 'kind': 'manual_run'}))
    with pytest.raises(ValueError, match='Not a forecast run'):
        build_publication(folder, 'established')
