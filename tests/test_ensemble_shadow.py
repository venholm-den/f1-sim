import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.app_services.beta import freeze_snapshot
from src.app_services.ensemble_shadow import capture_shadow, try_capture_shadow, score_shadow_queue
from src.stage_ensemble import FORECAST_COLUMNS, ranking_forecast
from src.stage_ensemble_benchmark import digest


@pytest.fixture
def shadow_workspace(tmp_path):
    from src import stage_ensemble, stage_ensemble_benchmark
    (tmp_path/'src').mkdir()
    for module in (stage_ensemble,stage_ensemble_benchmark):
        source = Path(module.__file__)
        (tmp_path/'src'/source.name).write_bytes(source.read_bytes())
    drivers = [f'D{i:02}' for i in range(12)]
    p = ranking_forecast(np.arange(12),np.full(12,.1),n_sims=300)
    frame = pd.DataFrame(p,columns=FORECAST_COLUMNS)
    frame['Driver'],frame['dnf_chance'] = drivers,.1
    frame['grid_position'],frame['grid_source'] = range(1,13),'actual_session_results'
    context = {'year':2026,'round':8,'event':'Test GP','session':'Q',
        'race_start_utc':'2026-06-09T12:00:00Z','data_cutoff_utc':'2026-06-08T11:00:00Z'}
    forecast = tmp_path/'outputs/app_runs/forecast'
    forecast.mkdir(parents=True)
    frame.to_csv(forecast/'simulation_summary.csv',index=False)
    freeze_snapshot(forecast,context,now='2026-06-08T12:00:00Z')
    results = pd.DataFrame([{'Year':2026,'Round':r,'DriverCode':driver,'Position':i+1}
                           for r in range(1,8) for i,driver in enumerate(drivers)])
    results.to_csv(tmp_path/'results.csv',index=False)
    pd.DataFrame({'Year':[2026],'Round':[8],'DriverCode':['D00'],
        'fp2_long_run_relative_pace':[0],'fp2_long_run_confidence':[.65]}).to_csv(tmp_path/'practice.csv',index=False)
    fit = {'status':'fitted','weights':{'simulation':.5,'qualifying':.5,'recent_form':0.,'practice':0.},
           'train_races':[[2026,r] for r in range(1,7)],
           'calibration':{'uniform_mass':.05,'calibration_races':[[2026,7]],'status':'fitted'}}
    model = {'schema_version':1,'model':'stage_ensemble_v1','activated':False,'promotion_approved':False,
        'created_at_utc':'2026-06-07T12:00:00Z','stages':{'Q':fit},
        'assumptions':{'component_simulations':300},
        'source_sha256':{name:digest(tmp_path/'src'/name) for name in ('stage_ensemble.py','stage_ensemble_benchmark.py')},
        'input_sha256':{str((tmp_path/name).resolve()):digest(tmp_path/name) for name in ('results.csv','practice.csv')}}
    (tmp_path/'candidate.json').write_text(json.dumps(model))
    config = {'enabled':True,'candidate_path':'candidate.json','candidate_sha256':digest(tmp_path/'candidate.json'),
              'results_path':'results.csv','practice_path':'practice.csv'}
    (tmp_path/'config').mkdir()
    (tmp_path/'config/stage_ensemble_shadow.json').write_text(json.dumps(config))
    return tmp_path,forecast,context


def test_shadow_is_prospective_idempotent_and_preserves_original(shadow_workspace):
    root,forecast,_ = shadow_workspace
    before = {p.name:digest(p) for p in (forecast/'frozen').iterdir()}
    result = capture_shadow(root,forecast,now='2026-06-08T13:00:00Z')
    assert result['status'] == 'captured'
    folder = Path(result['folder'])
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['activated'] is False and manifest['sent_to_discord'] is False
    assert not manifest['availability']['practice']['available']
    assert capture_shadow(root,forecast,now='2026-06-08T14:00:00Z')['status'] == 'already_captured'
    assert before == {p.name:digest(p) for p in (forecast/'frozen').iterdir()}
    (folder/'learned_blend.csv').write_text('changed')
    with pytest.raises(ValueError,match='checksum'):
        capture_shadow(root,forecast,now='2026-06-08T14:00:00Z')


def test_shadow_refuses_late_backdated_and_leaky_models(shadow_workspace):
    root,forecast,_ = shadow_workspace
    assert capture_shadow(root,forecast,now='2026-06-09T13:00:00Z')['status'] == 'ineligible'
    with pytest.raises(ValueError,match='backdate'):
        capture_shadow(root,forecast,now='2026-06-07T13:00:00Z')
    model_path = root/'candidate.json'
    model = json.loads(model_path.read_text())
    model['stages']['Q']['train_races'].append([2026,8])
    model_path.write_text(json.dumps(model))
    config_path = root/'config/stage_ensemble_shadow.json'
    config = json.loads(config_path.read_text())
    config['candidate_sha256'] = digest(model_path)
    config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='target or future'):
        capture_shadow(root,forecast,now='2026-06-08T13:00:00Z')
    assert not (root/'outputs/stage_ensemble_shadow').exists()


def test_changed_feature_archive_fails_closed(shadow_workspace):
    root,forecast,_ = shadow_workspace
    (root/'results.csv').write_text('changed')
    with pytest.raises(ValueError,match='archive differs'):
        capture_shadow(root,forecast,now='2026-06-08T13:00:00Z')
    assert try_capture_shadow(root,forecast)['status'] in {'capture_failed','ineligible'}


def test_scoring_waits_for_complete_official_job_and_never_rewrites(shadow_workspace):
    root,forecast,_ = shadow_workspace
    result = capture_shadow(root,forecast,now='2026-06-08T13:00:00Z')
    folder = Path(result['folder'])
    assert score_shadow_queue(root,now='2026-06-09T15:00:00Z') == []
    assert score_shadow_queue(root,now='2026-06-10T12:00:00Z') == []
    official = root/'outputs/app_runs/scoring'
    official.mkdir()
    (official/'job.json').write_text(json.dumps({'kind':'score','status':'completed','forecast_folder':str(forecast)}))
    (official/'score.json').write_text(json.dumps({'snapshot_sha256':digest(forecast/'frozen/manifest.json')}))
    pd.DataFrame({'Driver':[f'D{i:02}' for i in range(12)],'actual_position':range(1,13),
        'actual_dnf':[False]*11+[True],'actual_result_source':'fastf1_results'}).to_csv(official/'actual_results.csv',index=False)
    assert score_shadow_queue(root,now='2026-06-10T12:00:00Z')[0]['status'] == 'scored'
    saved = digest(folder/'score.json')
    payload = json.loads((folder/'score.json').read_text())
    assert 'qualifying_order' in payload['metrics']
    assert score_shadow_queue(root,now='2026-06-11T12:00:00Z') == []
    assert digest(folder/'score.json') == saved


def test_shadow_errors_do_not_interrupt_forecast(tmp_path,monkeypatch):
    from src.app_services import ensemble_shadow
    monkeypatch.setattr(ensemble_shadow,'capture_shadow',lambda *args: (_ for _ in ()).throw(ValueError('bad candidate')))
    result = ensemble_shadow.try_capture_shadow(tmp_path,tmp_path/'forecast')
    assert result == {'status':'capture_failed','error_type':'ValueError','error':'bad candidate'}
