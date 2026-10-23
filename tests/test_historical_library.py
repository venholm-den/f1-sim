import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from src.app_services import historical_library as library
from src.app_services import simulation_jobs


@pytest.fixture
def root(tmp_path):
    (tmp_path/'job').mkdir()
    return tmp_path


def tasks(*_):
    return [{'year': 2025, 'round': i, 'event': f'Grand Prix {i}', 'session': 'R'} for i in (1, 2)]


def fake_fetch(task, *_):
    return {'results': pd.DataFrame({'Year': [task['year']]*23, 'Event': [task['event']]*23,
                                     'Driver': [f'D{i}' for i in range(23)], 'Position': range(1,24)})}, {}, ['weather']


def run(root, **kwargs):
    return library.download(root, root/'job', {'mode':'results', 'years':[2025]},
                            discover_fn=tasks, fetch_fn=kwargs.pop('fetch_fn', fake_fetch), pause_seconds=0, **kwargs)


@pytest.mark.parametrize('payload', [{'years':[]}, {'years':[2017]}, {'years':[1949], 'mode':'results'},
                                   {'years':[2025], 'mode':'bad'}, {'years':[2025], 'sessions':[]},
                                   {'years':[2025], 'sessions':['UNKNOWN']}])
def test_invalid_download_options(payload):
    with pytest.raises(ValueError):
        library.options(payload)


def test_classifications_allow_1950_and_normalise_multiple_years():
    result = library.options({'mode':'results', 'years':[1950,2025,1950], 'telemetry':True})
    assert result['years'] == [1950,2025]
    assert not result['telemetry']
    assert result['sessions'] == ['R']


def test_discovery_excludes_future_and_unscheduled_sprint(root, monkeypatch):
    import fastf1
    schedule = pd.DataFrame([{'RoundNumber':1,'EventName':'Completed GP',
                              'Session1':'Race','Session1DateUtc':'2025-01-01',
                              'Session2':'Qualifying','Session2DateUtc':'2025-01-01'},
                             {'RoundNumber':2,'EventName':'Future GP',
                              'Session1':'Race','Session1DateUtc':'2025-12-01'},
                             {'RoundNumber':0,'EventName':'Testing'}])
    monkeypatch.setattr(fastf1,'get_event_schedule', lambda _:schedule)
    monkeypatch.setattr(fastf1.Cache,'enable_cache',lambda _:None)
    found=library.discover(root,2025,'detailed',['R','S'],now='2025-06-01T12:00:00Z')
    assert len(found)==1 and found[0]['session']=='R' and found[0]['event']=='Completed GP'


def test_download_resumes_without_rewriting_complete_sessions(root):
    assert run(root)['downloaded']==2
    pointers=list(library.library_root(root).glob('*/*/*/session.json'))
    previous={str(path):path.read_bytes() for path in pointers}
    forbidden=Mock(side_effect=AssertionError('A completed session should not be fetched again'))
    resumed=run(root,fetch_fn=forbidden)
    assert resumed['skipped']==2 and resumed['downloaded']==0
    assert all(Path(path).read_bytes()==data for path,data in previous.items())
    assert library.inventory(root)['totals']['sessions']==2


def test_stop_checkpoints_current_session_then_resume(root):
    def stopping(task,*args):
        (root/'job/stop_requested').touch()
        return fake_fetch(task,*args)
    result=run(root,fetch_fn=stopping)
    assert result['status']=='cancelled' and result['downloaded']==1
    next_job=root/'next_job'
    next_job.mkdir()
    resumed=library.download(root,next_job,{'mode':'results','years':[2025]},discover_fn=tasks,fetch_fn=fake_fetch,pause_seconds=0)
    assert resumed['status']=='completed' and resumed['skipped']==1 and resumed['downloaded']==1


def test_rate_limit_pauses_without_trying_remaining_sessions(root):
    fetch=Mock(side_effect=RuntimeError('HTTP 429 too many requests'))
    result=run(root,fetch_fn=fetch)
    assert result['status']=='paused' and result['processed']==1 and result['failed']==1
    assert fetch.call_count==1
    assert library.inventory(root)['seasons'][0]['needs_retry']==1


def test_calendar_rate_limit_pauses_before_fetching(root):
    fetch=Mock()
    def limited(*_):
        raise RuntimeError('Rate limit')
    result=library.download(root,root/'job',{'mode':'results','years':[2024,2025]},discover_fn=limited,fetch_fn=fetch,pause_seconds=0)
    assert result['status']=='paused'
    fetch.assert_not_called()


def test_empty_season_does_not_claim_a_completed_download(root):
    result=library.download(root,root/'job',{'mode':'results','years':[2025]},discover_fn=lambda *_:[],fetch_fn=Mock(),pause_seconds=0)
    assert result['status']=='no_data'
    assert library.inventory(root)['totals']['sessions']==0


def test_failed_session_is_retried_and_optional_missing_data_is_explicit(root):
    fetch=Mock(side_effect=[ValueError('Missing result'), fake_fetch(tasks()[1])])
    first=run(root,fetch_fn=fetch)
    assert first['status']=='partial' and first['downloaded']==1
    assert run(root)['downloaded']==1
    pointer=next(library.library_root(root).glob('*/*/*/session.json'))
    assert library.read_json(pointer)['unavailable_optional_tables']==['weather']


def test_corrupt_csv_is_repaired_using_new_version_and_export_checks_integrity(root):
    run(root)
    pointer=next(library.library_root(root).glob('*/*/*/session.json'))
    saved=library.read_json(pointer)
    source=pointer.parent/next(iter(saved['files']))
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='repair'):
        library.export(root,{'years':[2025],'mode':'results'})
    result=run(root)
    assert result['downloaded']==1 and result['skipped']==1
    assert source.read_bytes()==b'changed'  # Retain the previous version rather than deleting it.
    assert len(list((pointer.parent/'versions').iterdir()))==2


def test_preview_spans_session_boundaries_and_export_has_one_header(root):
    run(root)
    result=library.preview(root,2025,'results','results',2)
    assert result['total_rows']==46 and len(result['rows'])==20
    assert result['rows'][0]['Event']=='Grand Prix 1' and result['rows'][-1]['Event']=='Grand Prix 2'
    exported=library.export(root,{'years':[2025],'mode':'results'})
    rows=pd.read_csv(Path(exported['folder'])/'race_classifications.csv')
    assert len(rows)==46 and not exported['uploaded']
    assert library.read_json(Path(exported['folder'])/'export.json')['model_training_performed'] is False


def test_telemetry_requires_explicit_coverage_and_empty_data_not_committed(root):
    run(root)
    pointer=next(library.library_root(root).glob('*/*/*/session.json'))
    assert not library.complete(pointer.parent,telemetry=True)
    with pytest.raises(ValueError,match='No usable'):
        library.save_partition(root/'empty',tasks()[0],library.options({'mode':'results','years':[2025]}),{'results':pd.DataFrame()}, {}, [])
    assert not (root/'empty/session.json').exists()


def test_library_paths_and_table_whitelist_prevent_external_preview(root):
    with pytest.raises(ValueError):
        library.preview(root,'../../private','results','results')
    with pytest.raises(ValueError):
        library.preview(root,2025,'results','../secret')


def test_download_job_needs_no_simulation_features_and_cancels_gracefully(root,monkeypatch):
    jobs=simulation_jobs.SimulationJobs(root)
    process=Mock(pid=123)
    process.poll.return_value=None
    monkeypatch.setattr(simulation_jobs.subprocess,'Popen',Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading,'Thread',Mock())
    job=jobs.start({'kind':'historical_download','archive':{'years':[1950],'mode':'results'}})
    folder=jobs._folder(job['id'])
    assert library.read_json(folder/'job.json')['archive']['years']==[1950]
    assert not (folder/'features.csv').exists()
    assert jobs.cancel() and (folder/'stop_requested').exists()
    process.wait.return_value=0
    jobs._wait(job['id'],process)
    assert jobs.status(job['id'])['status']=='cancelled'


def test_paused_download_is_not_marked_completed(root,monkeypatch):
    jobs=simulation_jobs.SimulationJobs(root)
    process=Mock(pid=123)
    process.poll.return_value=None
    process.wait.return_value=0
    monkeypatch.setattr(simulation_jobs.subprocess,'Popen',Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading,'Thread',Mock())
    job=jobs.start({'kind':'historical_download','archive':{'years':[1950],'mode':'results'}})
    simulation_jobs.write_json(jobs._folder(job['id'])/'download_result.json',{'status':'paused'})
    jobs._wait(job['id'],process)
    assert jobs.status(job['id'])['status']=='paused'


def test_missing_telemetry_saves_base_data_and_retries_in_new_version(root):
    config = {'mode': 'detailed', 'years': [2025], 'sessions': ['FP2'], 'telemetry': True}
    def partial(task, *_):
        tables, venue, _ = fake_fetch(task)
        return tables, venue, ['telemetry']
    first = library.download(root, root/'job', config, discover_fn=tasks, fetch_fn=partial, pause_seconds=0)
    assert first['status'] == 'partial' and first['downloaded'] == first['incomplete_telemetry'] == 2
    pointer = next(library.library_root(root).glob('*/*/*/session.json'))
    assert library.complete(pointer.parent) and not library.complete(pointer.parent, telemetry=True)
    assert library.inventory(root)['seasons'][0]['needs_retry'] == 2
    old_version = next((pointer.parent/'versions').iterdir())
    old_bytes = {p: p.read_bytes() for p in old_version.iterdir()}
    resumed = library.download(root, root/'job', config, discover_fn=tasks, fetch_fn=fake_fetch, pause_seconds=0)
    assert resumed['downloaded'] == 2 and resumed['status'] == 'completed'
    assert library.complete(pointer.parent, telemetry=True)
    assert all(p.read_bytes() == data for p, data in old_bytes.items())


def test_repeated_provider_refusal_pauses_with_explicit_cause(root, monkeypatch):
    from src.app_services.request_meter import RequestMeter
    monkeypatch.setattr(RequestMeter, 'provider_issue', lambda _: 'Formula 1 timing access refused (HTTP 401); mirror HTTP 404')
    discovered = tasks() + [{**tasks()[0], 'round': 3}]
    fetch = Mock(side_effect=ValueError('Session.load'))
    result = library.download(root, root/'job', {'mode':'detailed', 'years':[2025]},
        discover_fn=lambda *_: discovered, fetch_fn=fetch, pause_seconds=0)
    assert result['status'] == 'paused' and result['processed'] == 2
    assert fetch.call_count == 2 and 'HTTP 401' in result['pause_reason']
    assert all('HTTP 401' in e['message'] for e in result['errors'])


def test_fetch_handles_unloaded_optional_telemetry_and_status(monkeypatch):
    import fastf1
    from fastf1.exceptions import DataNotLoadedError
    from src import lap_details, venues
    class Session:
        session_status = pd.DataFrame({'Status': ['Finished']})
        event = {}
        @property
        def car_data(self):
            raise DataNotLoadedError('not loaded')
        pos_data = {}
        def load(self, **kwargs):
            pass
    session = Session()
    monkeypatch.setattr(fastf1, 'get_session', lambda *_: session)
    monkeypatch.setattr(lap_details, 'extract_lap_details', lambda *_: pd.DataFrame({'Driver':['VER']}))
    monkeypatch.setattr(venues, 'venue_for_context', lambda *a, **kw: {})
    task = {**tasks()[0], 'session': 'FP2'}
    tables, _, missing = library.fetch(task, 'detailed', True)
    assert len(tables['laps']) == 1 and 'telemetry' in missing
    session.session_status = pd.DataFrame()
    with pytest.raises(ValueError, match='not confirmed finished'):
        library.fetch(task, 'detailed', True)


def test_provider_pause_retains_sessions_saved_without_telemetry(root, monkeypatch):
    from src.app_services.request_meter import RequestMeter
    monkeypatch.setattr(RequestMeter, 'provider_issue', lambda _: 'Formula 1 timing access refused (HTTP 401); mirror HTTP 404')
    def partial(task, *_):
        tables, venue, _ = fake_fetch(task)
        return tables, venue, ['telemetry']
    result = library.download(root, root/'job', {'mode':'detailed', 'years':[2025], 'telemetry':True},
        discover_fn=tasks, fetch_fn=partial, pause_seconds=0)
    assert result['status'] == 'paused' and result['downloaded'] == result['incomplete_telemetry'] == 2
    assert result['failed'] == 0 and library.inventory(root)['totals']['sessions'] == 2
    assert all('HTTP 401' in e['message'] for e in result['errors'])
