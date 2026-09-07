import json
from contextlib import redirect_stdout
from unittest.mock import Mock

import pandas as pd
import pytest

from src.app_services.historical_runs import events_from_schedule, replay_config, validate_selection
from src.app_services.simulation_jobs import SimulationJobs
from src.app_services import simulation_jobs
from portable_app import job_worker


@pytest.mark.parametrize('selection', [
    {'year':2017,'event':'British Grand Prix'},
    {'year':2099,'event':'British Grand Prix'},
    {'year':2024,'event':'latest'},
    {'year':2024,'event':''},
    {'year':2024,'event':'British Grand Prix','session':'PRE'},
])
def test_reject_invalid_historical_selection(selection):
    with pytest.raises(ValueError):
        validate_selection(selection)


def test_calendar_excludes_testing_future_and_same_day_sessions():
    schedule = pd.DataFrame([
        {'RoundNumber':0,'EventName':'Testing','Session1':'Practice 1','Session1DateUtc':'2024-01-01'},
        {'RoundNumber':1,'EventName':'Past GP','Session1':'Qualifying','Session1DateUtc':'2024-06-01',
         'Session2':'Race','Session2DateUtc':'2024-06-02'},
        {'RoundNumber':2,'EventName':'Today GP','Session1':'Qualifying','Session1DateUtc':'2024-06-09',
         'Session2':'Race','Session2DateUtc':'2024-06-10'},
        {'RoundNumber':3,'EventName':'Future GP','Session1':'Race','Session1DateUtc':'2024-07-01'},
    ])
    assert events_from_schedule(schedule, '2024-06-10T12:00:00Z') == [
        {'event':'Past GP','sessions':['Q','R']}, {'event':'Today GP','sessions':['Q']}]


def test_historical_config_disables_live_services_and_isolates_output(tmp_path):
    config = replay_config({'year':2024,'event':'British Grand Prix','session':'Q'}, tmp_path, 100, 7, .6)
    assert config['run']['year'] == 2024
    assert config['run']['n_sims'] == 100
    assert config['outputs']['output_dir'] == str(tmp_path)
    assert not config['outputs']['post_to_discord']
    assert not config['model']['use_weather_forecast']
    assert not config['model']['use_historical_model_calibration']


def test_historical_launch_does_not_require_existing_features(tmp_path, monkeypatch):
    jobs = SimulationJobs(tmp_path)
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock())
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    selection = {'year':2024,'event':'British Grand Prix','session':'Q'}
    started = jobs.start({'input_source':'historical','historical':selection})
    data = jobs.status(started['id'])
    assert data['historical'] == selection
    assert '2024 British Grand Prix' in data['label']
    assert data['source_dir'] == str(jobs._folder(started['id'])/'source')


def test_prepare_historical_runs_pipeline_and_copies_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_worker, 'historical_events', lambda *args: [{'event':'British Grand Prix','sessions':['Q']}])
    def pipeline(config_path, log):
        from src.app_services.run_service import CallbackWriter
        with redirect_stdout(CallbackWriter(log)):
            print('Pipeline log output')
        config = json.loads(config_path.read_text())
        source = tmp_path/'source'
        assert config['data']['fantasy_prices_path'] == str(source/'reference/fantasy_prices.csv')
        assert (source/'reference/fantasy_prices.csv').is_file()
        (source/'driver_model_features.csv').write_text('Driver,Team\nVER,Red Bull Racing\n')
        (source/'strategy').mkdir()
        (source/'strategy/predicted_tyre_strategy.csv').write_text('Driver,expected_stops\nVER,1\n')
        assert config['run']['session'] == 'Q'
        return 0
    monkeypatch.setattr('src.app_services.run_service.run_pipeline_with_config', pipeline)
    job = {'historical':{'year':2024,'event':'British Grand Prix','session':'Q'},
           'n_sims':100,'seed':42,'overtaking_difficulty':.55}
    job_worker.prepare_historical(job, tmp_path)
    assert (tmp_path/'features.csv').is_file()
    assert (tmp_path/'strategies.csv').is_file()
    job['historical']['session'] = 'R'
    with pytest.raises(ValueError, match='completed-session calendar'):
        job_worker.prepare_historical(job, tmp_path)


def test_completed_history_exposes_reusable_source_and_preserves_event_label(tmp_path, monkeypatch):
    from src.app_services.simulation_jobs import write_json
    jobs = SimulationJobs(tmp_path)
    folder = jobs.run_root/'20260907T000000Z_1234abcd'
    source = folder/'source'
    (source/'history').mkdir(parents=True)
    (source/'driver_model_features.csv').write_text('Driver,Team\nVER,T\n')
    (source/'history/latest_prediction_snapshot.csv').write_text('year,event,session\n2024,British Grand Prix,Q\n')
    write_json(folder/'job.json', {'id':folder.name,'status':'completed','created_at':'2026-09-07'})
    relative = jobs.status(folder.name)['reusable_source']
    assert jobs.root/relative == source
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock())
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    created = jobs.start({'source_dir':relative})
    assert '2024 British Grand Prix' in jobs.status(created['id'])['label']
