import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.app_services import beta
from src.app_services.app_paths import initialize_user_workspace


def schedule():
    return pd.DataFrame([{'RoundNumber':1,'EventName':'Example GP',
        'Session1':'Practice 1','Session1DateUtc':'2024-07-05T12:00:00Z',
        'Session2':'Practice 2','Session2DateUtc':'2024-07-05T16:00:00Z',
        'Session3':'Practice 3','Session3DateUtc':'2024-07-06T11:00:00Z',
        'Session4':'Qualifying','Session4DateUtc':'2024-07-06T15:00:00Z',
        'Session5':'Race','Session5DateUtc':'2024-07-07T14:00:00Z'}])


@pytest.mark.parametrize('now,session,codes',[
    ('2024-07-04T12:00:00Z','PRE',[]),
    ('2024-07-05T17:00:00Z','FP1',['FP1']),
    ('2024-07-06T19:00:00Z','Q',['FP1','FP2','FP3','Q']),
])
def test_cutoff_excludes_future_and_recent_sessions(now, session, codes):
    result = beta.select_next_race(schedule(),2024,now)
    assert result['session'] == session
    assert result['available_sessions'] == codes


def test_completed_fp3_is_used_before_three_hour_delay():
    result = beta.select_next_race(schedule(), 2024, '2024-07-06T12:15:00Z',
                                  session_ready=lambda event, code: True)
    assert result['session'] == 'FP3'
    assert result['session_evidence']['FP3'] == 'completed_session_data'
    assert 'Q' not in result['available_sessions']


def test_next_race_probes_only_started_sessions_in_upcoming_event(tmp_path, monkeypatch):
    import fastf1
    from types import SimpleNamespace
    monkeypatch.setattr(beta, 'utc_now', lambda: pd.Timestamp('2024-07-06T12:15:00Z'))
    monkeypatch.setattr(fastf1.Cache, 'enable_cache', lambda _: None)
    monkeypatch.setattr(fastf1, 'get_event_schedule', lambda year: schedule())
    loaded = []

    def session(year, event, code):
        loaded.append((year, event, code))
        return SimpleNamespace(load=lambda **kwargs: None,
                               session_status=pd.DataFrame({'Status': ['Finished', 'Finalised']}),
                               results=pd.DataFrame({'Abbreviation': ['AAA']}),
                               laps=pd.DataFrame({'LapTime': [pd.Timedelta(seconds=90)]}))

    monkeypatch.setattr(fastf1, 'get_session', session)
    selected = beta.next_race(tmp_path)
    assert selected['session'] == 'FP3'
    assert [code for _, _, code in loaded] == ['FP1', 'FP2', 'FP3']


def test_known_live_session_is_not_promoted_even_after_delay():
    result = beta.select_next_race(schedule(), 2024, '2024-07-06T14:15:00Z',
                                  session_ready=lambda event, code: code != 'FP3')
    assert result['session'] == 'FP2'


def test_unavailable_readiness_uses_schedule_fallback():
    probe = lambda event, code: None
    early = beta.select_next_race(schedule(), 2024, '2024-07-06T12:15:00Z', session_ready=probe)
    late = beta.select_next_race(schedule(), 2024, '2024-07-06T14:15:00Z', session_ready=probe)
    assert early['session'] == 'FP2'
    assert late['session'] == 'FP3'
    assert late['session_evidence']['FP3'] == 'schedule_fallback_3h'


@pytest.mark.parametrize('states,has_laps,expected', [
    (['Started'], True, False),
    (['Started', 'Aborted'], True, False),
    (['Started', 'Finished', 'Started'], True, False),
    (['Started', 'Finished'], True, False),
    (['Started', 'Finished', 'Finalised', 'Ends'], True, True),
    (['Started', 'Finished', 'Finalised'], False, False),
    ([], True, None),
])
def test_readiness_requires_completed_status_and_usable_data(states, has_laps, expected):
    from types import SimpleNamespace
    session = SimpleNamespace(session_status=pd.DataFrame({'Status': states}),
                              results=pd.DataFrame({'Abbreviation': ['AAA']}),
                              laps=pd.DataFrame({'LapTime': [pd.Timedelta(seconds=90)] if has_laps else []}))
    assert beta.completed_session_data(session) is expected


def test_forecast_freezes_exact_pipeline_results_without_second_simulation(tmp_path, monkeypatch):
    from src.app_services import run_service
    from src import simulate
    context = beta.select_next_race(schedule(), 2024, '2024-07-06T19:00:00Z')
    context['race_start_utc'] = '2099-07-07T14:00:00Z'
    monkeypatch.setattr(simulate, 'simulate_races', lambda *args, **kwargs: pytest.fail('Second simulation'))

    def pipeline(config_path, callback):
        config = json.loads(config_path.read_text())
        assert config['outputs']['save_report_images'] is True
        assert config['outputs']['post_to_discord'] is False
        source = __import__('pathlib').Path(config['outputs']['output_dir'])
        (source / 'driver_model_features.csv').write_text('Driver,Team\nA,T\n')
        (source / 'baseline_race_features.csv').write_text('Driver,source_year,source_event\nA,2024,Prior GP\n')
        (source / 'simulation_summary.csv').write_text('Driver,win_chance,avg_fantasy_points\nA,1.0,42.0\n')
        (source / 'position_matrix.csv').write_text('Driver,P1\nA,1.0\n')
        (source / 'driver_roster.csv').write_text('Driver,roster_source\nA,target_session\n')
        (source / 'venue_context.json').write_text(json.dumps(context['venue']))
        return 0

    monkeypatch.setattr(run_service, 'run_pipeline_with_config', pipeline)
    # Informational weather failures must not prevent the established forecast.
    monkeypatch.setattr('src.race_weather.collect_race_weather', lambda *a, **k: (_ for _ in ()).throw(ValueError('Malformed provider response')))
    beta.run_forecast(tmp_path, {'n_sims': 100, 'seed': 42, 'overtaking_difficulty': .55}, context=context)
    assert (tmp_path / 'frozen/simulation_summary.csv').read_bytes() == (tmp_path / 'source/simulation_summary.csv').read_bytes()
    assert 'driver_roster.csv' in beta.verified_snapshot(tmp_path)['files']
    assert (tmp_path / 'frozen/baseline_race_features.csv').read_bytes() == (tmp_path / 'source/baseline_race_features.csv').read_bytes()
    assert json.loads((tmp_path / 'frozen/race_weather.json').read_text())['status'] == 'capture_failed'


def test_started_race_is_not_upcoming():
    assert beta.select_next_race(schedule(),2024,'2024-07-07T14:00:00Z') is None


@pytest.fixture
def frozen(tmp_path):
    pd.DataFrame({'Driver':['A','B'], 'avg_finish':[1.2,1.8], 'win_chance':[.8,.2],
                  'podium_chance':[1.,1.]}).to_csv(tmp_path/'simulation_summary.csv',index=False)
    (tmp_path/'features.csv').write_text('Driver,Team\nA,T\nB,T\n')
    (tmp_path/'job.json').write_text(json.dumps({'n_sims':10000,'seed':42,'overtaking_difficulty':.55,
                                               'source_dir':'PRIVATE_PATH','credentials':'NEVER_EXPORT'}))
    context = beta.select_next_race(schedule(),2024,'2024-07-06T19:00:00Z')
    beta.freeze_snapshot(tmp_path,context,now='2024-07-06T20:00:00Z')
    return tmp_path


def test_snapshot_is_write_once_and_checks_hashes(frozen):
    original = beta.verified_snapshot(frozen)
    with pytest.raises(FileExistsError):
        beta.freeze_snapshot(frozen,original['context'],now='2024-07-06T21:00:00Z')
    (frozen/'frozen/simulation_summary.csv').write_text('changed')
    with pytest.raises(ValueError,match='changed'):
        beta.verified_snapshot(frozen)


def test_late_forecast_cannot_be_frozen(tmp_path):
    context = beta.select_next_race(schedule(),2024,'2024-07-06T19:00:00Z')
    with pytest.raises(ValueError,match='race started'):
        beta.freeze_snapshot(tmp_path,context,now='2024-07-07T14:00:00Z')
    assert not (tmp_path/'frozen').exists()


def test_share_export_is_minimal_and_does_not_transmit(frozen):
    payload = beta.sharing_export(frozen)
    text = json.dumps(payload)
    assert 'PRIVATE_PATH' not in text and 'NEVER_EXPORT' not in text
    assert payload['settings']['n_sims'] == 10000
    assert payload['timestamp_authority'] == 'local_clock_unattested'


def test_probability_scores_and_partial_result_rejection():
    prediction = pd.DataFrame({'Driver':['A','B'], 'avg_finish':[1.2,1.8], 'win_chance':[.8,.2]})
    actual = pd.DataFrame({'Driver':['A','B'], 'actual_position':[1,2]})
    metrics, rows = beta.score_frames(prediction,actual)
    assert metrics['finish_mae'] == pytest.approx(.2)
    assert metrics['win_chance_brier'] == pytest.approx(.04)
    assert len(rows) == 2
    with pytest.raises(ValueError,match='coverage'):
        beta.score_frames(prediction, actual.head(1))


def test_full_field_scores_without_a_non_starter_or_substitute():
    drivers = [f'D{i:02d}' for i in range(20)]
    prediction = pd.DataFrame({'Driver':drivers, 'avg_finish':range(1,21), 'win_chance':[.05]*20})
    # D19 did not start; SUB replaced D18 after the forecast froze.
    actual = pd.DataFrame({'Driver':drivers[:18]+['SUB'], 'actual_position':range(1,20)})
    metrics, rows = beta.score_frames(prediction, actual)
    assert metrics['drivers'] == 18 and len(rows) == 18
    assert metrics['unscored_drivers'] == ['D18', 'D19', 'SUB']
    with pytest.raises(ValueError, match='coverage'):
        beta.score_frames(prediction, actual.head(12))


def test_score_worker_uses_frozen_not_mutable_outputs(frozen,tmp_path,monkeypatch):
    from src import backtest
    from types import SimpleNamespace
    monkeypatch.setattr(backtest,'_load_race_session',lambda *args: SimpleNamespace(session_status=pd.DataFrame({'Status':['Finished']})))
    monkeypatch.setattr(backtest,'_extract_actual_results_from_race_session',lambda *args:
        pd.DataFrame({'Driver':['A','B'],'actual_position':[1,2], 'actual_result_source':['fastf1_results']*2}))
    (frozen/'simulation_summary.csv').write_text('changed mutable display data')
    output = tmp_path/'score'
    output.mkdir()
    beta.run_scoring(output,frozen)
    assert json.loads((output/'score.json').read_text())['win_chance_brier'] == pytest.approx(.04)


def test_packaged_workspace_keeps_user_files_on_upgrade(tmp_path,monkeypatch):
    from src.app_services import app_paths
    bundle = tmp_path/'bundle'
    (bundle/'config').mkdir(parents=True)
    (bundle/'config/default_run_config.json').write_text('original')
    monkeypatch.setattr(app_paths,'bundled_root',lambda:bundle)
    target = initialize_user_workspace(tmp_path/'profile')
    (target/'config/default_run_config.json').write_text('user settings')
    initialize_user_workspace(target)
    assert (target/'config/default_run_config.json').read_text() == 'user settings'


def test_packaged_workspace_takes_new_bundled_data_only_for_unedited_copies(tmp_path,monkeypatch):
    from src.app_services import app_paths
    bundle = tmp_path/'bundle'
    (bundle/'data').mkdir(parents=True)
    (bundle/'data/track_profiles.csv').write_text('release 1')
    (bundle/'data/fantasy_prices.csv').write_text('release 1')
    monkeypatch.setattr(app_paths,'bundled_root',lambda:bundle)
    target = initialize_user_workspace(tmp_path/'profile')
    (target/'data/fantasy_prices.csv').write_text('edited by the user')
    (bundle/'data/track_profiles.csv').write_text('release 2')
    (bundle/'data/fantasy_prices.csv').write_text('release 2')
    initialize_user_workspace(target)
    assert (target/'data/track_profiles.csv').read_text() == 'release 2'
    assert (target/'data/fantasy_prices.csv').read_text() == 'edited by the user'


def test_workspace_without_a_seed_record_keeps_differing_files(tmp_path,monkeypatch):
    from src.app_services import app_paths
    bundle = tmp_path/'bundle'
    (bundle/'data').mkdir(parents=True)
    (bundle/'data/track_profiles.csv').write_text('release 2')
    monkeypatch.setattr(app_paths,'bundled_root',lambda:bundle)
    target = tmp_path/'profile'
    (target/'data').mkdir(parents=True)
    (target/'data/track_profiles.csv').write_text('older copy or user edit')
    initialize_user_workspace(target)
    assert (target/'data/track_profiles.csv').read_text() == 'older copy or user edit'


def test_forecast_config_ignores_environment_and_preserves_empty_allowlist(tmp_path,monkeypatch):
    from src.run_config import load_app_config, config_to_dict
    config = beta.replay_config({'year':2024,'event':'Example GP','session':'PRE'},tmp_path,100,42,.55)
    config.update(ignore_environment_overrides=True)
    config['run']['weekend_sessions'] = []
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    monkeypatch.setenv('F1_SIM_YEAR','2026')
    monkeypatch.setenv('POST_TO_DISCORD','true')
    loaded = load_app_config(path)
    assert loaded.run.year == 2024
    assert loaded.run.weekend_sessions == []
    assert not loaded.outputs.post_to_discord
    assert config_to_dict(loaded)['run']['weekend_sessions'] == []


def test_windowed_worker_logs_even_with_dummy_stdout(tmp_path, monkeypatch):
    import io
    import sys
    from portable_app import web_main, job_worker

    def failing_worker(folder):
        print('Worker started')
        raise ValueError('Expected scoring rejection')

    monkeypatch.setattr(sys, 'argv', ['app.exe','--job-worker',str(tmp_path)])
    monkeypatch.setattr(sys, 'stdout', io.StringIO())
    monkeypatch.setattr(job_worker, 'run', failing_worker)
    with pytest.raises(SystemExit) as error:
        web_main.main()
    assert error.value.code == 1
    log = (tmp_path/'run.log').read_text(encoding='utf-8')
    assert 'Worker started' in log and 'Expected scoring rejection' in log


def test_new_snapshot_records_source_and_runtime_versions(frozen):
    manifest = json.loads((frozen/'frozen/manifest.json').read_text())
    provenance = manifest['runtime_provenance']
    assert provenance['python']
    assert provenance['packages']['numpy']
    assert 'main.py' in provenance['source_sha256']
    assert 'src/collect.py' in provenance['source_sha256']
    assert 'scripts/auto_forecast.py' in provenance['source_sha256']
