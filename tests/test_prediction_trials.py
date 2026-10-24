import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.app_services.beta import freeze_snapshot
from src.app_services.practice_collection import collect_weekend
from src.app_services.prediction_trials import (CONFIG, SOURCES, capture_trial,
    comparison_report, register_suite, renew_suite, read_suite, score_trials, simulation_inputs)
from src.simulate import simulate_races
from src.stage_ensemble import validate_forecast, FORECAST_COLUMNS
from src.stage_ensemble_benchmark import digest
from src.venues import resolve_venue


def test_grid_candidate_is_pinned_and_captured_with_matched_control(workspace):
    root, forecast = workspace
    candidate = {'model': 'grid_influence_v1', 'activated': False, 'promotion_approved': False,
        'created_at_utc': '2026-06-08T13:01:30Z', 'history_observations': [],
        'selected_on_development': {'PRE': 'active_profile', 'FP2': 'uniform_055', 'Q': 'active_times_125'},
        'source_sha256': {n: digest(root/'src'/n) for n in ('grid_influence.py', 'circuit_calibration.py', 'venues.py')}}
    path = root/'grid_candidate.json'; path.write_text(json.dumps(candidate))
    config = register_suite(root, root/'ensemble_config.json', now='2026-06-08T13:02:00Z', grid_candidate_path=path)
    (root/CONFIG).write_text(json.dumps(config))
    result = capture_trial(root, forecast, now='2026-06-08T13:03:00Z', loader=loader)
    assert result['status'] == 'captured'
    folder = Path(result['folder'])
    manifest = json.loads((folder/'manifest.json').read_text())
    assert 'grid_influence.csv' in manifest['files']
    inputs = json.loads((folder/'grid_influence_inputs.json').read_text())
    assert inputs['simulation_inputs']['overtaking_difficulty'] == pytest.approx(.875)
    assert inputs['evidence']['mapping'] == 'active_times_125'
    assert manifest['activated'] is False and manifest['sent_to_discord'] is False
    simulation = pd.read_csv(folder/'simulation.csv')
    mapped = pd.read_csv(folder/'grid_influence.csv')
    assert simulation.Driver.tolist() == mapped.Driver.tolist()
    assert not np.allclose(simulation.avg_finish, mapped.avg_finish)


def context(stage='Q'):
    return {'year':2026,'round':8,'event':'British Grand Prix','session':stage,
        'available_sessions':['FP1','FP2','Q'] if stage=='Q' else ['FP2'],
        'race_start_utc':'2026-06-09T12:00:00Z','data_cutoff_utc':'2026-06-08T13:00:00Z',
        'venue':resolve_venue(2026,'British Grand Prix')}


def session():
    rows=[]
    for driver in range(12):
        for lap in range(1,9):
            seconds=90+driver*.1+lap*.02
            rows.append({'Driver':f'D{driver:02}','LapNumber':lap,'Stint':1,'Compound':'MEDIUM',
                'TyreLife':lap,'LapTime':pd.Timedelta(seconds=seconds),
                'LapStartTime':pd.Timedelta(seconds=lap*95),
                'Time':pd.Timedelta(seconds=lap*95+seconds),'TrackStatus':'1',
                'IsAccurate':True,'Deleted':False,'PitInTime':pd.NaT,'PitOutTime':pd.NaT})
    return SimpleNamespace(event=pd.Series({'RoundNumber':8,'EventName':'British Grand Prix',
        'Location':'Silverstone','Session4':'Qualifying','Session4DateUtc':pd.Timestamp('2026-06-08T12:00:00')}),
        t0_date=pd.Timestamp('2026-06-07T12:00:00'),session_info={},laps=pd.DataFrame(rows),
        session_status=pd.DataFrame({'Time':pd.to_timedelta([0,3600,3610],unit='s'),
                                     'Status':['Started','Finished','Finalised']}))


def loader(*args):
    return session()


@pytest.fixture
def workspace(tmp_path):
    source=Path(__file__).resolve().parents[1]
    for name in SOURCES:
        path=tmp_path/'src'/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((source/'src'/name).read_bytes())
    f=pd.DataFrame({'Driver':[f'D{i:02}' for i in range(12)],'Team':['T'+str(i//2) for i in range(12)],
        'grid_position':range(1,13),'grid_source':'actual_session_results','grid_confidence':1.,
        'quali_pace_score':np.arange(12)*.05,'race_pace_score':np.arange(12)[::-1]*.1,
        'long_run_pace_score':np.arange(12)[::-1]*.1,'tyre_deg_score':.01,'strategy_score':.2,
        'reliability_score':.1,'performance_uncertainty':1.8,'estimated_race_laps':52,
        'base_winner_race_time_seconds':5400.,'current_relative_pace_capped':np.arange(12)*.1,
        'baseline_relative_pace':np.arange(12)[::-1]*.1,'current_signal_quality':.8,
        'projected_lap_time':90.+np.arange(12)*.1})
    inputs={'overtaking_difficulty':.7,'weather_modifiers':{'chaos_factor':1.1,'rainfall_flag':False}}
    summary,_,_=simulate_races(f,n_sims=300,seed=42,**inputs)
    forecast=tmp_path/'outputs/app_runs/forecast';forecast.mkdir(parents=True)
    f.to_csv(forecast/'features.csv',index=False);summary.to_csv(forecast/'simulation_summary.csv',index=False)
    (forecast/'simulation_inputs.json').write_text(json.dumps(inputs))
    (forecast/'forecast_config.json').write_text(json.dumps({'run':{'n_sims':300,'random_seed':42}}))
    freeze_snapshot(forecast,context(),now='2026-06-08T13:01:00Z')
    model={'schema_version':1,'model':'stage_ensemble_v1','activated':False,'promotion_approved':False,
        'created_at_utc':'2026-06-08T10:00:00Z','stages':{s:{'status':'fitted','train_races':[[2026,r] for r in range(1,7)],
            'weights':{'simulation':.4,'qualifying':.3,'recent_form':.1,'practice':.2},
            'calibration':{'calibration_races':[[2026,7]],'uniform_mass':0.}} for s in ('PRE','FP2','Q')},
        'assumptions':{'component_simulations':300},
        'source_sha256':{n:digest(tmp_path/'src'/n) for n in ('stage_ensemble.py','stage_ensemble_benchmark.py')}}
    pd.DataFrame([{'Year':2026,'Round':r,'DriverCode':d,'Position':i+1}
        for r in range(1,8) for i,d in enumerate(f.Driver)]).to_csv(tmp_path/'results.csv',index=False)
    pd.DataFrame(columns=['Year','Round','DriverCode','fp2_long_run_relative_pace','fp2_long_run_confidence']).to_csv(tmp_path/'practice.csv',index=False)
    model['input_sha256']={str((tmp_path/n).resolve()):digest(tmp_path/n) for n in ('results.csv','practice.csv')}
    (tmp_path/'candidate.json').write_text(json.dumps(model))
    config={'candidate_path':'candidate.json','candidate_sha256':digest(tmp_path/'candidate.json'),
        'results_path':'results.csv','practice_path':'practice.csv'}
    (tmp_path/'ensemble_config.json').write_text(json.dumps(config))
    registered=register_suite(tmp_path,tmp_path/'ensemble_config.json',now='2026-06-08T13:02:00Z')
    (tmp_path/'config').mkdir();(tmp_path/CONFIG).write_text(json.dumps(registered))
    return tmp_path,forecast


def test_collection_downloads_only_eligible_sessions_and_reuses_immutable_evidence(tmp_path):
    calls=[]
    def record(root,c,code):
        calls.append(code);return session()
    c=context(); c['available_sessions']=['FP2','Q']
    result=collect_weekend(tmp_path,c,now='2026-06-08T13:03:00Z',loader=record)
    assert result['status']=='completed' and calls==['FP2']
    folder=Path(result['folder']); features=pd.read_csv(folder/'practice_features.csv')
    assert len(features)==12 and features.fp2_long_run_confidence.gt(0).all()
    hashes={p.name:digest(p) for p in folder.iterdir()}
    assert collect_weekend(tmp_path,c,now='2026-06-08T14:00:00Z',loader=record)['reused']
    assert calls==['FP2'] and hashes=={p.name:digest(p) for p in folder.iterdir()}
    (folder/'laps.csv').write_text('modified')
    with pytest.raises(ValueError,match='checksum'):
        collect_weekend(tmp_path,c,now='2026-06-08T15:00:00Z',loader=record)


@pytest.mark.parametrize('change',['live','future','identity','missing_accuracy','venue'])
def test_collection_fails_closed_on_unavailable_or_wrong_evidence(tmp_path,change):
    def altered(*args):
        s=session()
        if change=='live':s.session_status.loc[2,'Status']='Started'
        if change=='future':s.t0_date=pd.Timestamp('2026-06-09T12:00:00')
        if change=='identity':s.event['RoundNumber']=9
        if change=='missing_accuracy':s.laps=s.laps.drop(columns='IsAccurate')
        if change=='venue':s.event['Location']='Monza'
        return s
    result=collect_weekend(tmp_path,context(),now='2026-06-08T13:03:00Z',loader=altered)
    assert result['status']=='awaiting_data'
    assert pd.read_csv(Path(result['folder'])/'practice_features.csv').empty


def test_post_qualifying_practice_and_pre_forecast_do_not_gain_practice(tmp_path):
    def post_q(*args):
        s=session();s.event['Session4DateUtc']=pd.Timestamp('2026-06-07T11:00:00');return s
    result=collect_weekend(tmp_path,context(),now='2026-06-08T13:03:00Z',loader=post_q)
    assert result['status']=='completed'
    assert pd.read_csv(Path(result['folder'])/'practice_features.csv').empty
    result=collect_weekend(tmp_path,context('PRE'),now='2026-06-08T13:03:00Z',loader=lambda *a:pytest.fail('PRE downloaded practice'))
    assert pd.read_csv(Path(result['folder'])/'practice_features.csv').empty


def test_transient_collection_failure_can_retry_without_replacing_failed_packet(tmp_path):
    c=context();c['available_sessions']=['FP2']
    failed=collect_weekend(tmp_path,c,now='2026-06-08T13:03:00Z',loader=lambda *a: (_ for _ in ()).throw(OSError('offline')))
    sha=digest(Path(failed['folder'])/'manifest.json')
    succeeded=collect_weekend(tmp_path,c,now='2026-06-08T14:00:00Z',loader=loader)
    assert failed['status']=='awaiting_data' and succeeded['status']=='completed'
    assert failed['folder']!=succeeded['folder'] and digest(Path(failed['folder'])/'manifest.json')==sha


@pytest.mark.parametrize('deleted',[True,None])
def test_deleted_or_unknown_deletion_status_is_not_clean_practice(tmp_path,deleted):
    def marked(*args):
        s=session();s.laps['Deleted']=deleted;return s
    result=collect_weekend(tmp_path,context(),now='2026-06-08T13:03:00Z',loader=marked)
    assert result['status']=='completed'
    assert pd.read_csv(Path(result['folder'])/'practice_features.csv').empty


def test_three_candidates_use_live_practice_and_preserve_frozen_forecast(workspace):
    root,forecast=workspace;before={p.name:digest(p) for p in (forecast/'frozen').iterdir()}
    result=capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader)
    folder=Path(result['folder']);manifest=json.loads((folder/'manifest.json').read_text())
    assert result['status']=='captured' and manifest['availability']['practice']['coverage']==1.
    assert manifest['activated'] is False and manifest['stronger_grid_applicable']
    for name in ('simulation','stage_blend','stronger_grid','single_pace'):
        f=pd.read_csv(folder/(name+'.csv'));validate_forecast(f[list(FORECAST_COLUMNS)])
        assert f.Driver.nunique()==12
    assert not pd.read_csv(folder/'stronger_grid.csv').equals(pd.read_csv(folder/'simulation.csv'))
    assert not pd.read_csv(folder/'single_pace.csv').equals(pd.read_csv(folder/'simulation.csv'))
    assert before=={p.name:digest(p) for p in (forecast/'frozen').iterdir()}
    assert capture_trial(root,forecast,now='2026-06-08T14:00:00Z',loader=lambda *a:pytest.fail('Redownload'))['status']=='already_captured'
    assert comparison_report(root)['captures']==1


def test_trials_reject_late_backdated_source_changes_and_future_outcomes(workspace):
    root,forecast=workspace
    assert capture_trial(root,forecast,now='2026-06-09T12:00:00Z',loader=loader)['status']=='ineligible'
    with pytest.raises(ValueError,match='backdate'):
        capture_trial(root,forecast,now='2026-06-08T12:00:00Z',loader=loader)
    (root/'src/simulate.py').write_text('changed')
    with pytest.raises(ValueError,match='source changed'):
        capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader)


def test_frozen_simulation_reproduction_is_required(workspace):
    root,forecast=workspace
    from src.app_services.beta import verified_snapshot
    m=verified_snapshot(forecast)
    # Deliberately modify the source-side packet then construct a different new
    # frozen forecast, proving semantic mismatch is rejected beyond hash checks.
    p=root/'outputs/app_runs/wrong';p.mkdir()
    for file in (forecast/'frozen').iterdir():
        if file.name!='manifest.json':(p/file.name).write_bytes(file.read_bytes())
    wrong=json.loads((p/'simulation_inputs.json').read_text());wrong['overtaking_difficulty']=.1
    (p/'simulation_inputs.json').write_text(json.dumps(wrong))
    freeze_snapshot(p,m['context'],now='2026-06-08T13:01:00Z')
    with pytest.raises(ValueError,match='reproduce'):
        simulation_inputs(root,p,verified_snapshot(p))


def official_job(root,forecast):
    folder=root/'outputs/app_runs/score';folder.mkdir()
    (folder/'job.json').write_text(json.dumps({'kind':'score','status':'completed','forecast_folder':str(forecast)}))
    (folder/'score.json').write_text(json.dumps({'snapshot_sha256':digest(forecast/'frozen/manifest.json')}))
    pd.DataFrame({'Driver':[f'D{i:02}' for i in range(12)],'actual_position':range(1,13),
        'actual_dnf':[False]*11+[True],'actual_result_source':'fastf1_results'}).to_csv(folder/'actual_results.csv',index=False)
    return folder


def test_scoring_uses_official_complete_results_all_requested_metrics_and_no_rewrites(workspace):
    root,forecast=workspace
    result=capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader);folder=Path(result['folder'])
    assert score_trials(root,now='2026-06-09T18:00:00Z')==[]
    assert score_trials(root,now='2026-06-10T12:00:00Z')==[]
    official_job(root,forecast)
    assert score_trials(root,now='2026-06-10T12:00:00Z')[0]['status']=='scored'
    score=json.loads((folder/'score.json').read_text());sha=digest(folder/'score.json')
    assert set(score['metrics'])=={'simulation','stage_blend','stronger_grid','single_pace','frozen_simulation','qualifying_order'}
    assert all({'finish_mae','win_brier','podium_brier','top10_brier'}.issubset(v) for v in score['metrics'].values())
    report=comparison_report(root);r=json.loads((Path(report['folder'])/'report.json').read_text())
    assert len(r['paired_comparisons'])==3 and all(v['paired_races']==1 and not v['eligible_for_review'] for v in r['paired_comparisons'])
    assert score_trials(root,now='2026-06-11T12:00:00Z')==[] and digest(folder/'score.json')==sha


def test_corrupted_predictions_or_partial_official_results_never_score(workspace):
    root,forecast=workspace
    result=capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader);folder=Path(result['folder'])
    actual=official_job(root,forecast)/'actual_results.csv'
    pd.read_csv(actual).iloc[:-1].to_csv(actual,index=False)
    assert score_trials(root,now='2026-06-10T12:00:00Z')[0]['status']=='score_failed'
    assert not (folder/'score.json').exists()
    (folder/'single_pace.csv').write_text('changed')
    assert score_trials(root,now='2026-06-10T12:00:00Z')[0]['status']=='score_failed'


def test_existing_forecast_scheduler_attempts_three_way_shadow_on_every_check(tmp_path,monkeypatch):
    from src.app_services import forecast_automation, prediction_trials
    from tests.test_forecast_automation import sample_context, fake_forecast
    monkeypatch.setattr(forecast_automation,'next_race',lambda root:sample_context())
    monkeypatch.setattr(forecast_automation,'run_forecast',fake_forecast)
    calls=[]
    monkeypatch.setattr(prediction_trials,'try_capture_trial',lambda root,forecast:calls.append(forecast) or {'status':'captured'})
    collected=[]
    monkeypatch.setattr(prediction_trials,'try_collect_current_practice',lambda root,c:collected.append(dict(c)) or {'status':'completed'})
    a=forecast_automation.run_automated_forecast(tmp_path,n_sims=100)
    latest=sample_context();latest['data_cutoff_utc']='2026-06-05T18:00:00+00:00'
    monkeypatch.setattr(forecast_automation,'next_race',lambda root:latest)
    b=forecast_automation.run_automated_forecast(tmp_path,n_sims=100)
    assert a['prediction_trial']['status']=='captured' and b['prediction_trial']['status']=='captured' and len(calls)==2
    assert a['current_practice']['status']=='completed' and collected[-1]['data_cutoff_utc']==latest['data_cutoff_utc']


def test_interrupted_capture_is_preserved_and_retry_uses_new_directory(workspace):
    root,forecast=workspace
    config=json.loads((root/CONFIG).read_text())
    abandoned=root/'outputs/prediction_trials/captures'/f"{config['suite_sha256'][:16]}_2026_08_Q"
    abandoned.mkdir(parents=True);(abandoned/'simulation.csv').write_text('interrupted evidence')
    result=capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader)
    assert result['status']=='captured' and Path(result['folder'])!=abandoned
    assert (abandoned/'simulation.csv').read_text()=='interrupted evidence'
    assert capture_trial(root,forecast,now='2026-06-08T14:00:00Z',loader=loader)['status']=='already_captured'


def test_report_rejects_practice_tampering_after_capture(workspace):
    root,forecast=workspace
    result=capture_trial(root,forecast,now='2026-06-08T13:03:00Z',loader=loader)
    manifest=json.loads((Path(result['folder'])/'manifest.json').read_text())
    (Path(manifest['practice_manifest_path']).parent/'laps.csv').write_text('altered evidence')
    report=comparison_report(root)
    assert report['failures'] and report['captures']==0


def test_new_suite_carries_prior_inspections_and_old_suite_is_immutable(workspace):
    root, _ = workspace
    before = (root/CONFIG).read_bytes()
    old = json.loads(before)
    old_path = root/old['suite_path']
    old_bytes = old_path.read_bytes()
    inspected = root/'new_benchmark.json'
    inspected.write_text(json.dumps({'attempted_races': [[2026, 8], [2026, 9]]}))
    new = register_suite(root, root/'ensemble_config.json', now='2026-06-08T13:02:30Z',
                         inspected_reports=[inspected])
    suite = json.loads((root/new['suite_path']).read_text())
    assert [2026, 9] in suite['inspected_races']
    assert suite['inspection_reports_sha256'][str(inspected.resolve())] == digest(inspected)
    assert (root/CONFIG).read_bytes() == before and old_path.read_bytes() == old_bytes
    assert not suite['activated'] and not suite['promotion_approved']


def test_review_gate_requires_six_paired_races_and_no_probability_regression(tmp_path,monkeypatch):
    # Isolate the promotion arithmetic from capture integrity, tested above.
    from src.app_services import prediction_trials
    monkeypatch.setattr(prediction_trials,'verify_capture',lambda *a:None)
    actual=tmp_path/'official/actual_results.csv';actual.parent.mkdir();actual.write_text('fixture official evidence')
    baseline={'finish_mae':4.,'win_brier':.04,'podium_brier':.1,'top10_brier':.2,'dnf_brier':.1,'loss':4.2}
    candidate={**baseline,'finish_mae':3.,'win_brier':.03,'podium_brier':.11,'top10_brier':.15,'loss':3.15}
    scores=[]
    for number in range(6):
        folder=tmp_path/'outputs/prediction_trials/captures'/str(number);folder.mkdir(parents=True)
        manifest={'context':{'year':2026,'round':number+8,'session':'Q','event':'GP'},
            'suite_sha256':'suite','created_at_utc':'2026-06-08T13:03:00Z','availability':{'practice':{'coverage':1}},
            'stronger_grid_applicable':True}
        (folder/'manifest.json').write_text(json.dumps(manifest))
        payload={'manifest_sha256':digest(folder/'manifest.json'),'actual_results_sha256':digest(actual),
            'official_score_folder':str(actual.parent),
            'metrics':{'simulation':baseline,'stage_blend':dict(candidate),'qualifying_order':{**baseline,'finish_mae':3.5}}}
        (folder/'score.json').write_text(json.dumps(payload));scores.append((folder,payload))
    result=comparison_report(tmp_path);report=json.loads((Path(result['folder'])/'report.json').read_text())
    comparison=report['paired_comparisons'][0]
    assert comparison['paired_races']==6 and comparison['loss_improvement']>.05
    assert comparison['q_beats_qualifying_order'] and not comparison['eligible_for_review']
    for folder,payload in scores:
        payload['metrics']['stage_blend']['podium_brier']=.09
        (folder/'score.json').write_text(json.dumps(payload))
    result=comparison_report(tmp_path);report=json.loads((Path(result['folder'])/'report.json').read_text())
    assert report['paired_comparisons'][0]['eligible_for_review']
    assert report['paired_comparisons'][0]['threshold_rps_improvement']>.05
    assert report['activated'] is False and report['promotion_approved'] is False
    # Finish error alone no longer qualifies; the threshold RPS must improve by 5%.
    for folder,payload in scores:
        payload['metrics']['stage_blend'].update(win_brier=.04,podium_brier=.1,top10_brier=.195)
        (folder/'score.json').write_text(json.dumps(payload))
    result=comparison_report(tmp_path);report=json.loads((Path(result['folder'])/'report.json').read_text())
    comparison=report['paired_comparisons'][0]
    assert comparison['loss_improvement']>.05 and comparison['threshold_rps_improvement']<.05
    assert not comparison['eligible_for_review']
    for folder,payload in scores:
        payload['metrics']['stage_blend'].update(win_brier=.03,podium_brier=.09,top10_brier=.15,finish_mae=4.1)
        (folder/'score.json').write_text(json.dumps(payload))
    result=comparison_report(tmp_path);report=json.loads((Path(result['folder'])/'report.json').read_text())
    assert not report['paired_comparisons'][0]['eligible_for_review']



def enable_extended(root):
    old = json.loads((root/CONFIG).read_text())
    config = register_suite(root, root/'ensemble_config.json', extended_models=True,
        now='2026-06-08T13:02:30Z', inspected_reports=[root/old['suite_path']])
    (root/CONFIG).write_text(json.dumps(config))
    return config


def test_extended_candidates_freeze_replay_inputs_score_and_use_matched_budget(workspace, monkeypatch):
    from src.app_services import prediction_trials as trials
    from src.app_services.shadow_candidates import CANDIDATES, CONTROL
    root, forecast = workspace
    config = enable_extended(root)
    suite = json.loads((root/config['suite_path']).read_text())
    assert set(CANDIDATES).issubset(suite['variants'])
    assert suite['candidate_protocol']['simulations_per_seed'] == 1000
    # Exercise orchestration/scoring independently of expensive model kernels.
    monkeypatch.setattr(trials, 'prepare_candidate', lambda name, frame, inputs, *a:
        (frame.copy(), dict(inputs), {'test_candidate': name}))
    result = capture_trial(root, forecast, now='2026-06-08T13:03:00Z', loader=loader)
    folder = Path(result['folder']); manifest = json.loads((folder/'manifest.json').read_text())
    assert all(manifest['candidate_runs'][n]['status'] == 'completed' for n in (CONTROL, *CANDIDATES))
    assert all(manifest['candidate_runs'][n]['simulations_per_seed'] == 1000 for n in (CONTROL, *CANDIDATES))
    for name in CANDIDATES:
        packet = json.loads((folder/(name+'_inputs.json')).read_text())
        assert packet['seeds'] == [42,123,777] and packet['simulations_per_seed'] == 1000
        assert (name+'_features.csv') in manifest['files']
    official_job(root, forecast)
    assert score_trials(root, now='2026-06-10T12:00:00Z')[0]['status'] == 'scored'
    report = comparison_report(root)
    payload = json.loads((Path(report['folder'])/'report.json').read_text())
    extended = [r for r in payload['paired_comparisons'] if r['candidate'] in CANDIDATES]
    from src.app_services.shadow_candidates import BASELINES
    assert len(extended) == len(CANDIDATES)
    assert all(r['baseline'] == BASELINES.get(r['candidate'], CONTROL) for r in extended)
    assert len(payload['candidate_status']) == len(CANDIDATES) + 1
    (folder/(CANDIDATES[0]+'_inputs.json')).write_text('{}')
    assert comparison_report(root)['failures']


def test_missing_history_skips_only_affected_arms_and_retry_preserves_capture(workspace, monkeypatch):
    from src.app_services import prediction_trials as trials
    from src.app_services.shadow_candidates import prepare_candidate
    root, forecast = workspace; enable_extended(root)
    def prepare(name, frame, inputs, *args):
        if name == 'agent_laps_v1':
            return frame, inputs, {}  # Kernel covered separately; keep integration test fast.
        return prepare_candidate(name, frame, inputs, *args)
    monkeypatch.setattr(trials, 'prepare_candidate', prepare)
    result = capture_trial(root, forecast, now='2026-06-08T13:03:00Z', loader=loader)
    folder = Path(result['folder']); manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['candidate_runs']['pit_scenarios_v1']['status'] == 'completed'
    for name in ('survival_dnf_v1','qualifying_partial_pooling_v1'):
        assert manifest['candidate_runs'][name]['status'] == 'skipped'
        assert 'history' in manifest['candidate_runs'][name]['reason']
        assert not (folder/(name+'.csv')).exists()
    sha = digest(folder/'manifest.json')
    assert capture_trial(root, forecast, now='2026-06-08T14:00:00Z', loader=loader)['status'] == 'already_captured'
    assert digest(folder/'manifest.json') == sha


def test_extended_trial_failure_cannot_block_main_discord_delivery(tmp_path, monkeypatch):
    from src.app_services import forecast_automation, prediction_trials
    from tests.test_forecast_automation import sample_context, fake_forecast
    monkeypatch.setattr(forecast_automation, 'next_race', lambda root: sample_context())
    monkeypatch.setattr(forecast_automation, 'run_forecast', fake_forecast)
    calls = []
    monkeypatch.setattr(forecast_automation, 'post_frozen_forecast', lambda path: calls.append('delivery') or {})
    monkeypatch.setattr(prediction_trials, 'try_capture_trial', lambda *a: calls.append('trial') or {'status':'capture_failed'})
    forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    assert calls == ['delivery','trial']
    calls.clear()
    forecast_automation.run_automated_forecast(tmp_path, n_sims=100, discord_enabled=True)
    assert calls[-1] == 'trial' and all(c == 'delivery' for c in calls[:-1])


def test_renewal_preserves_old_suite_and_carries_all_inspections(workspace):
    root, _ = workspace
    old_config = json.loads((root/CONFIG).read_text())
    old_path = root/old_config['suite_path']
    old_bytes = old_path.read_bytes()
    # Simulate the merge which invalidated the enabled source-pinned cohort.
    source = root/'src/simulate.py'
    source.write_bytes(source.read_bytes() + b'\n# source changed\n')
    with pytest.raises(ValueError, match='source changed'):
        read_suite(root)
    inspected = root/'outputs/multi_score_tuning/run/report.json'
    inspected.parent.mkdir(parents=True)
    inspected.write_text(json.dumps({'holdout_races_evaluated': [[2026, 8]]}))
    config = renew_suite(root, root/'ensemble_config.json', now='2026-06-08T13:03:00Z')
    assert old_path.read_bytes() == old_bytes
    new = json.loads((root/config['suite_path']).read_text())
    old = json.loads(old_bytes)
    assert new['variants'] == old['variants']
    assert new['assumptions'] == old['assumptions']
    assert new['predecessor']['suite_sha256'] == old_config['suite_sha256']
    assert [2026, 8] in new['inspected_races']
    assert set(map(tuple, old['inspected_races'])) <= set(map(tuple, new['inspected_races']))
    (root/CONFIG).write_text(json.dumps(config))
    assert read_suite(root)[2] == config['suite_sha256']


def test_renewal_refuses_tampered_predecessor_inputs(workspace):
    root, _ = workspace
    path, _, _ = read_suite(root)
    (path.parent/'results.csv').write_text('tampered')
    with pytest.raises(ValueError, match='input checksum'):
        renew_suite(root, root/'ensemble_config.json')
