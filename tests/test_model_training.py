import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from src.app_services import historical_library as library, model_training as training, simulation_jobs
from src.historical_model import build_historical_feature_table


def archive(root, rounds=4, year=2025):
    config = library.options({'years': [year], 'sessions': ['Q', 'R']})
    for number in range(1, rounds+1):
        for session in ('Q', 'R'):
            task = {'year': year, 'round': number, 'event': f'GP {number}', 'session': session}
            metadata = {'Year': [year]*4, 'Round': [number]*4, 'Event': [task['event']]*4, 'Session': [session]*4}
            if session == 'Q':
                frame = pd.DataFrame({**metadata, 'Driver': ['AAA','BBB','CCC','DDD'], 'Team': ['A','B','C','D'],
                                      'LapTimeSeconds': [80,81,82,83], 'CleanPushLap': [True]*4})
                classification = pd.DataFrame({**metadata, 'Abbreviation': ['AAA','BBB','CCC','DDD'],
                    'TeamName': ['A','B','C','D'], 'Position': [1,2,3,4]})
                tables = {'laps': frame, 'results': classification}
            else:
                frame = pd.DataFrame({**metadata, 'Abbreviation': ['AAA','BBB','CCC','DDD'], 'TeamName': ['A','B','C','D'],
                                      'Position': [2,1,3,4], 'Status': ['Finished','Finished','Finished','Gearbox']})
                tables = {'results': frame}
            library.save_partition(library.library_root(root)/str(year)/'detailed'/f'{number}_{session}', task, config, tables, {}, [])


def test_train_candidate_uses_archive_and_keeps_active_models(tmp_path):
    archive(tmp_path)
    active = tmp_path/'data/models'
    active.mkdir()
    (active/'historical_finish_model.joblib').write_bytes(b'active artifact')
    job = tmp_path/'job'
    job.mkdir()
    plan = training.prepare(tmp_path, {'years': [2025]})
    result = training.train(tmp_path, job, plan)
    metrics = result['metrics']
    assert metrics['train_races'][-1]['Round'] < metrics['validation_races'][0]['Round']
    assert metrics['rows'] == 16 and metrics['validation_rows'] == 4
    assert metrics['qualifying_baseline_mae'] == .5
    assert len(result['sources']) == 12
    assert not result['activated'] and training.result(job)['verified']
    assert (active/'historical_finish_model.joblib').read_bytes() == b'active artifact'
    (job/'candidate/validation_predictions.csv').write_text('changed')
    assert not training.result(job)['verified']


def test_aborted_classified_archive_is_preserved_but_excluded_from_training(tmp_path):
    archive(tmp_path)
    pointer = library.library_root(tmp_path)/'2025/detailed/1_R/session.json'
    data = library.read_json(pointer)
    data['venue']['race_quality'] = {'training_eligible': False, 'aborted_classified': True}
    pointer.write_text(json.dumps(data))
    selected = training.selection(tmp_path, [2025])
    assert len(selected['races']) == 3
    assert 'Aborted classified' in selected['skipped'][0]['reason']
    assert pointer.exists()


def test_changed_version_after_selection_fails_without_candidate(tmp_path):
    archive(tmp_path)
    plan = training.prepare(tmp_path, {'years': [2025]})
    partition = plan['races'][0]['sessions']['Q']
    name = next(iter(partition['manifest']['files']))
    file = Path(partition['folder'])/name
    content = bytearray(file.read_bytes())
    content[-1] ^= 1
    file.write_bytes(content)
    job = tmp_path/'job'
    job.mkdir()
    with pytest.raises(ValueError, match='checksum'):
        training.train(tmp_path, job, plan)
    assert not (job/'training_result.json').exists()


def test_saved_session_pointer_can_advance_without_changing_pinned_training(tmp_path):
    archive(tmp_path)
    plan = training.prepare(tmp_path, {'years': [2025]})
    partition = plan['races'][0]['sessions']['Q']
    pointer = Path(partition['folder'])/'session.json'
    pointer.write_text('{}')
    job = tmp_path/'job'
    job.mkdir()
    assert training.train(tmp_path, job, plan)['status'] == 'complete'


def test_classifications_and_partial_pairs_cannot_train(tmp_path):
    archive(tmp_path, rounds=2)
    assert training.state(tmp_path)['seasons'][0]['paired_races'] == 2
    with pytest.raises(ValueError, match='three matched'):
        training.prepare(tmp_path, {'years': [2025]})
    with pytest.raises(ValueError):
        training.prepare(tmp_path, {'years': [1950]})


def test_archive_session_metadata_mismatch_fails(tmp_path):
    archive(tmp_path)
    pointer = next(library.library_root(tmp_path).glob('*/detailed/*/session.json'))
    manifest = library.read_json(pointer)
    manifest['event'] = 'Incorrect GP'
    library.write_json(pointer, manifest)
    with pytest.raises(ValueError, match='identities disagree'):
        training.prepare(tmp_path, {'years': [2025]})


def test_training_job_does_not_need_simulation_features_and_cancel_hides_result(tmp_path, monkeypatch):
    archive(tmp_path)
    process = Mock(pid=123)
    process.poll.return_value = None
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    jobs = simulation_jobs.SimulationJobs(tmp_path)
    job = jobs.start({'kind': 'historical_training', 'training': {'years': [2025]}})
    folder = jobs._folder(job['id'])
    assert (folder/'training_selection.json').is_file()
    training.train(tmp_path, folder, library.read_json(folder/'training_selection.json'))
    data = library.read_json(folder/'job.json')
    data['status'] = 'cancelled'
    library.write_json(folder/'job.json', data)
    assert 'training_result' not in jobs.status(job['id'])


def test_feature_builder_excludes_sprint_outcomes(tmp_path):
    from tests.test_historical_model import _write_fixture
    _write_fixture(tmp_path)
    file = tmp_path/'fastf1_race_results.csv'
    frame = pd.read_csv(file)
    sprint = frame.copy()
    sprint['Session'] = 'S'
    pd.concat([frame,sprint]).to_csv(file,index=False)
    assert len(build_historical_feature_table(tmp_path)) == frame.Session.eq('R').sum()
