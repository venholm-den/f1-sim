import json
from datetime import datetime,timezone
from pathlib import Path
import shutil

import pandas as pd
import pytest

from tests.test_prediction_trials import workspace
from tests.test_form_adjustment import packet
from src.form_adjustment import training_table
from src.app_services import form_shadow as shadow
from src.app_services.automation_health import summarize


def setup_suite(workspace):
    root,forecast=workspace
    source=Path(__file__).resolve().parents[1]
    for name in ('src/form_adjustment.py','src/app_services/form_shadow.py','src/race_scores.py',
                 'src/app_services/automation_health.py','scripts/form_shadow.py','scripts/auto_forecast.py'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,path)
    benchmark=root/'benchmark';benchmark.mkdir()
    history=packet();history.to_csv(benchmark/'history.csv',index=False)
    training_table(history).to_csv(benchmark/'form_training.csv',index=False)
    report={'activated':False,'promotion_approved':False,'source_sha256':{'src/form_adjustment.py':shadow.digest(root/'src/form_adjustment.py')},
        'summary':[dict(session='Q',split='development',arm='simple_retirement_prior_v1',loss=4.)],
        'screening':[dict(stage='Q',arm='simple_retirement_prior_v1',passes_diagnostic_screen=True)],
        'seeds':[1,2],'n_sims':100,'inspected_races':[[2025,10]],
        'artifact_sha256':{name:shadow.digest(benchmark/name) for name in ('history.csv','form_training.csv')}}
    (benchmark/'report.json').write_text(json.dumps(report))
    shadow.register(root,benchmark,now='2026-06-08T13:02:30Z')
    return root,forecast


def test_capture_is_immutable_idempotent_and_never_changes_source(workspace):
    root,forecast=setup_suite(workspace)
    before=shadow.digest(forecast/'frozen/manifest.json')
    result=shadow.capture(root,forecast,now='2026-06-08T13:03:00Z')
    assert result['status']=='captured' and result['sent_to_discord'] is False
    folder=Path(result['folder']);manifest=folder/'manifest.json';checksum=shadow.digest(manifest)
    summary=pd.read_csv(folder/'legacy_summary.csv')
    assert summary.win_chance.sum()==pytest.approx(1)
    repeated=shadow.capture(root,forecast,now='2026-06-08T13:04:00Z')
    assert repeated['status']=='reused' and shadow.digest(manifest)==checksum
    assert shadow.digest(forecast/'frozen/manifest.json')==before
    (folder/'legacy_features.csv').write_text('changed')
    with pytest.raises(ValueError,match='checksum'):
        shadow.capture(root,forecast,now='2026-06-08T13:05:00Z')


def test_score_reuses_official_jobs_and_counts_unknown_labels_once(workspace):
    root,forecast=setup_suite(workspace)
    result=shadow.capture(root,forecast,now='2026-06-08T13:03:00Z')
    official=root/'outputs/app_runs/official';official.mkdir()
    (official/'job.json').write_text(json.dumps({'kind':'score','status':'completed','forecast_folder':str(forecast)}))
    (official/'score.json').write_text(json.dumps({'snapshot_sha256':shadow.digest(forecast/'frozen/manifest.json')}))
    summary=pd.read_csv(Path(result['folder'])/'legacy_summary.csv')
    pd.DataFrame({'Driver':summary.Driver,'actual_position':range(1,len(summary)+1),
        'actual_dnf':[False]*(len(summary)-1)+[None],'actual_result_source':'fastf1_results'}).to_csv(official/'actual_results.csv',index=False)
    assert shadow.score(root,now='2026-06-09T19:00:00Z')==[]
    scores=shadow.score(root,now='2026-06-09T21:00:00Z')
    assert scores[0]['status']=='scored'
    file=Path(result['folder'])/'score.json';first=shadow.digest(file)
    saved=json.loads(file.read_text())
    assert saved['metrics']['legacy']['known_dnf_drivers']==len(summary)-1
    assert saved['metrics']['legacy']['unknown_dnf_drivers']==1
    assert shadow.score(root,now='2026-06-09T22:00:00Z')==[] and shadow.digest(file)==first
    from scripts.report_form_shadows import report
    output=report(root)
    saved=json.loads((Path(output['folder'])/'report.json').read_text())
    assert output['scored_race_stages']==1
    assert saved['comparisons'][0]['paired_races']==1
    assert not saved['comparisons'][0]['passes_existing_fresh_review_gate']
    assert shadow.digest(file)==first


def test_failed_new_capture_does_not_starve_completed_scoring(workspace,monkeypatch):
    root,forecast=setup_suite(workspace)
    monkeypatch.setattr(shadow,'score',lambda root:[{'status':'scored'}])
    def fail(*args,**kwargs):raise ValueError('source changed')
    monkeypatch.setattr(shadow,'capture',fail)
    result=shadow.run_enabled(root,forecast)
    assert result['scoring']==[{'status':'scored'}]
    assert result['capture']['status']=='capture_failed'
    assert summarize({'form_shadow':result})['status']=='warning'


def test_optional_arm_failure_retains_control_and_records_the_skip(workspace,monkeypatch):
    root,forecast=setup_suite(workspace)
    def fail(*args,**kwargs):raise ValueError('risk evidence unavailable')
    monkeypatch.setattr(shadow,'apply_retirement_prior',fail)
    result=shadow.capture(root,forecast,now='2026-06-08T13:03:00Z')
    assert result['status']=='captured'
    assert result['runs']['legacy']['status']=='completed'
    assert result['runs']['simple_retirement_prior_v1']['status']=='skipped'


def test_report_rejects_duplicate_race_stage_captures(workspace):
    from scripts.report_form_shadows import report
    root,forecast=setup_suite(workspace)
    result=shadow.capture(root,forecast,now='2026-06-08T13:03:00Z')
    folder=Path(result['folder'])
    shutil.copytree(folder,folder.parent/(folder.name+'_duplicate'))
    with pytest.raises(ValueError,match='Duplicate race/stage'):
        report(root)
