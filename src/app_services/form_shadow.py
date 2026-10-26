"""Independent, opt-in form/risk shadow collection; never edits or posts live runs."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from src.accuracy_candidates import single_degradation, SINGLE_DEGRADATION_MULTIPLIER
from src.app_services.beta import verified_snapshot
from src.app_services.prediction_trials import simulation_inputs, sources
from src.form_adjustment import apply_form, apply_retirement_prior, fit_form, validate_packet
from src.inspection_ledger import discover_reports, inspected_race_keys
from src.race_scores import race_scores
from src.simulate import simulate_races

CONFIG='config/form_shadow.json'
ROOT='outputs/form_shadow'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00')) if not isinstance(value,datetime) else value
    if result.tzinfo is None:raise ValueError('UTC timestamp requires a timezone.')
    return result.astimezone(timezone.utc)


def write_new(path,data):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,allow_nan=False)


def source_hashes(root):
    root=Path(root)
    result={f'src/{name}':sha for name,sha in sources(root).items()}
    for name in ('src/form_adjustment.py','src/app_services/form_shadow.py','src/race_scores.py',
                 'src/app_services/automation_health.py',
                 'scripts/form_shadow.py','scripts/auto_forecast.py'):
        result[name]=digest(root/name)
    for name in ('src/retirement_evidence.py', 'data/retirement_labels/verified_outcomes_v1.csv'):
        if (root/name).is_file():
            result[name]=digest(root/name)
    return result


def verify_files(folder,files):
    folder=Path(folder).resolve()
    for name,sha in files.items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or digest(path)!=sha:
            raise ValueError('Form shadow evidence checksum/path mismatch.')


def register(root,benchmark,*,now=None):
    root,benchmark=Path(root),Path(benchmark)
    report=json.loads((benchmark/'report.json').read_text(encoding='utf-8'))
    if report.get('activated') is not False or report.get('promotion_approved') is not False:
        raise ValueError('Only an inactive, inspected benchmark can register a shadow.')
    verify_files(benchmark,report['artifact_sha256'])
    for name,sha in report['source_sha256'].items():
        path=root/'src'/name if (root/'src'/name).is_file() else root/name
        if digest(path)!=sha:raise ValueError('Benchmark source changed; rerun before registration.')
    summary=pd.DataFrame(report['summary']);stages={}
    for stage in ('PRE','FP2','Q'):
        dev=summary[summary.session.eq(stage)&summary['split'].eq('development')
                    & summary.arm.isin(['stage_form_v1','form_degradation_v1'])]
        arms=[]
        # Selection uses development loss; later diagnostics may only reject it.
        selected=dev.sort_values(['loss','arm']).iloc[0].arm if not dev.empty else None
        checks={x['arm']:x for x in report['screening'] if x['stage']==stage}
        if selected and checks[selected]['passes_diagnostic_screen']:
            arms.extend(['single_degradation_v1',selected] if selected=='form_degradation_v1' else [selected])
        if checks.get('simple_retirement_prior_v1',{}).get('passes_diagnostic_screen'):
            arms.append('simple_retirement_prior_v1')
        if arms:stages[stage]=['legacy',*arms]
    if not stages:raise ValueError('No stage passed diagnostic screening; nothing enabled.')
    created=utc(now or datetime.now(timezone.utc))
    folder=root/ROOT/'suites'/(created.strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    for name in ('history.csv','form_training.csv','report.json'):
        (folder/name).write_bytes((benchmark/name).read_bytes())
    inspected=inspected_race_keys([benchmark/'report.json',*discover_reports(root)])
    suite={'created_at_utc':created.isoformat(),'stage_arms':stages,'seeds':report['seeds'],
        'n_sims':report['n_sims'],'source_sha256':source_hashes(root),
        'files':{name:digest(folder/name) for name in ('history.csv','form_training.csv','report.json')},
        'inspected_races':[list(k) for k in sorted(inspected)],
        'policy':'Shadow only. Separate cohorts/stages, first capture per race/stage; six fresh races, '
                 'existing promotion review and probability guardrails still required. No automatic activation.',
        'activated':False,'promotion_approved':False}
    previous=root/CONFIG
    if previous.is_file():
        predecessor=json.loads(previous.read_text(encoding='utf-8'))
        if digest(root/predecessor['suite_path'])!=predecessor['suite_sha256']:
            raise ValueError('Previous form suite checksum changed; refusing to supersede it.')
        suite['predecessor']=predecessor
    write_new(folder/'suite.json',suite)
    config={'enabled':True,'suite_path':str((folder/'suite.json').relative_to(root)),
            'suite_sha256':digest(folder/'suite.json')}
    path=root/CONFIG
    if path.exists():
        backup=root/ROOT/'config_backups'/f'{created.strftime("%Y%m%dT%H%M%S%fZ")}.json'
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    return {**config,'stage_arms':stages}


def read_suite(root):
    root=Path(root);path=root/CONFIG
    if not path.exists():return None
    config=json.loads(path.read_text(encoding='utf-8'))
    if not config.get('enabled'):return None
    file=root/config['suite_path']
    if digest(file)!=config['suite_sha256']:raise ValueError('Form shadow suite changed.')
    suite=json.loads(file.read_text(encoding='utf-8'))
    if suite['activated'] is not False or suite['promotion_approved'] is not False:
        raise ValueError('Form shadows cannot activate models.')
    verify_files(file.parent,suite['files'])
    if suite['source_sha256']!=source_hashes(root):raise ValueError('Form shadow source changed; register a new cohort.')
    return file,suite,config['suite_sha256']


def capture(root,forecast,*,now=None):
    root,forecast=Path(root),Path(forecast)
    registered=read_suite(root)
    if registered is None:return {'status':'disabled'}
    suite_path,suite,sha=registered
    original=verified_snapshot(forecast);context=original['context'];stage=context['session']
    if stage not in suite['stage_arms']:return {'status':'stage_parked','session':stage}
    started=utc(now or datetime.now(timezone.utc));race_start=utc(context['race_start_utc'])
    key=(int(context['year']),int(context['round']))
    if (original['category']!='prospective' or started>=race_start
            or started<max(utc(original['created_at_utc']),utc(suite['created_at_utc']))
            or (suite['inspected_races'] and key<=max(map(tuple,suite['inspected_races'])))):
        return {'status':'ineligible','reason':'not_new_prospective_evidence'}
    prefix=f'{sha[:16]}_{key[0]}_{key[1]}_{stage}'
    for old in sorted((root/ROOT/'captures').glob(prefix+'*/manifest.json')):
        existing=json.loads(old.read_text(encoding='utf-8'));verify_files(old.parent,existing['files'])
        return {'status':'reused','folder':str(old.parent)}
    base,inputs,provenance=simulation_inputs(root,forecast,original)
    if set(inputs)-{'weather_modifiers','overtaking_difficulty'}:
        raise ValueError('Form shadows require an established aggregate source forecast.')
    packet=pd.read_csv(suite_path.parent/'history.csv');validate_packet(packet)
    table=pd.read_csv(suite_path.parent/'form_training.csv')
    model=fit_form(table,key,stage)
    folder=root/ROOT/'captures'/(prefix+'_'+uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
    write_new(folder/'model.json',model);write_new(folder/'simulation_inputs.json',inputs)
    runs={}
    for arm in suite['stage_arms'][stage]:
        try:
            features=base.copy();options={}
            if arm in {'stage_form_v1','form_degradation_v1'}:
                if model['status']!='fitted':
                    runs[arm]={'status':'skipped','reason':'insufficient_history'};continue
                q=None
                if stage=='Q':
                    if ('q_rank' not in base or 'qualifying_feature_contract' not in base
                            or not base.qualifying_feature_contract.eq('official_q_classification_v1').all()):
                        runs[arm]={'status':'skipped','reason':'frozen_official_q_contract_unavailable'};continue
                    q=dict(zip(base.Driver,base.q_rank))
                features=apply_form(features,packet,model,key,stage,q_positions=q)
            if arm in {'single_degradation_v1','form_degradation_v1'}:
                features=single_degradation(features);options['single_degradation_multiplier']=SINGLE_DEGRADATION_MULTIPLIER
            if arm=='simple_retirement_prior_v1':features=apply_retirement_prior(features,packet,key)
            summaries,matrices,raw=[],[],[]
            for offset,seed in enumerate(suite['seeds']):
                summary,matrix,sims=simulate_races(features,n_sims=suite['n_sims'],seed=seed,**inputs,**options)
                summaries.append(summary);matrices.append(matrix)
                joint=sims[['sim_id','Driver','finish_position']].copy()
                joint['sim_id']+=offset*suite['n_sims'];raw.append(joint)
            summary=pd.concat(summaries).groupby('Driver').mean(numeric_only=True)
            summary['Team']=features.set_index('Driver').Team;summary=summary.reset_index()
            matrix=pd.concat(matrices).groupby('Driver').mean(numeric_only=True).reset_index()
            summary.to_csv(folder/f'{arm}_summary.csv',index=False)
            matrix.to_csv(folder/f'{arm}_positions.csv',index=False)
            pd.concat(raw).to_csv(folder/f'{arm}_joint.csv.gz',index=False)
            features.to_csv(folder/f'{arm}_features.csv',index=False)
            runs[arm]={'status':'completed','options':options}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            runs[arm]={'status':'skipped','reason':str(exc)[:250]}
    if runs.get('legacy',{}).get('status')!='completed':
        raise ValueError('Matched legacy control failed; no prospective capture committed.')
    completed=utc(now or datetime.now(timezone.utc))
    if completed>=race_start:raise ValueError('Shadow finished after race start; retained as uncommitted evidence.')
    manifest={'category':'prospective_form_shadow','created_at_utc':completed.isoformat(),'started_at_utc':started.isoformat(),
        'history_cutoff_utc':started.isoformat(),'context':context,'suite_path':str(suite_path.resolve()),'suite_sha256':sha,
        'source_forecast':str(forecast.resolve()),'source_manifest_sha256':digest(forecast/'frozen/manifest.json'),
        'input_provenance':provenance,'runs':runs,'seeds':suite['seeds'],'n_sims_per_seed':suite['n_sims'],
        'files':{p.name:digest(p) for p in folder.iterdir()},'activated':False,'sent_to_discord':False}
    write_new(folder/'manifest.json',manifest)
    return {'status':'captured','folder':str(folder),'runs':runs,'sent_to_discord':False}


def score(root,*,now=None):
    root=Path(root);current=utc(now or datetime.now(timezone.utc));results=[]
    for file in sorted((root/ROOT/'captures').glob('*/manifest.json')):
        folder=file.parent
        if (folder/'score.json').exists():continue
        try:
            manifest=json.loads(file.read_text(encoding='utf-8'));context=manifest['context']
            if current<utc(context['race_start_utc'])+timedelta(hours=8):continue
            verify_files(folder,manifest['files'])
            suite_path=Path(manifest['suite_path'])
            if digest(suite_path)!=manifest['suite_sha256']:raise ValueError('Captured suite changed.')
            suite=json.loads(suite_path.read_text(encoding='utf-8'));verify_files(suite_path.parent,suite['files'])
            original=verified_snapshot(manifest['source_forecast'])
            if (original['context']!=context or original['category']!='prospective'
                    or manifest['category']!='prospective_form_shadow'
                    or utc(manifest['created_at_utc'])>=utc(context['race_start_utc'])
                    or digest(Path(manifest['source_forecast'])/'frozen/manifest.json')!=manifest['source_manifest_sha256']):
                raise ValueError('Captured source/timing evidence changed.')
            official=None
            for job_path in sorted((root/'outputs/app_runs').glob('*/job.json')):
                job=json.loads(job_path.read_text(encoding='utf-8'))
                if job.get('kind')!='score' or job.get('status')!='completed':continue
                source=verified_snapshot(job['forecast_folder']);c=source['context']
                if (c['year'],c['round'],c['event'])!=(context['year'],context['round'],context['event']):continue
                scored=json.loads((job_path.parent/'score.json').read_text(encoding='utf-8'))
                if scored['snapshot_sha256']!=digest(Path(job['forecast_folder'])/'frozen/manifest.json'):
                    raise ValueError('Official result job provenance changed.')
                official=job_path.parent;break
            if official is None:continue
            actual=pd.read_csv(official/'actual_results.csv')
            if not actual.actual_result_source.eq('fastf1_results').all():raise ValueError('Official results required.')
            labels=actual.set_index('Driver').actual_dnf.map({True:1.,False:0.,'True':1.,'False':0.})
            metrics={}
            for arm,run in manifest['runs'].items():
                if run['status']!='completed':continue
                summary=pd.read_csv(folder/f'{arm}_summary.csv')
                matrix=pd.read_csv(folder/f'{arm}_positions.csv');joint=pd.read_csv(folder/f'{arm}_joint.csv.gz')
                values=race_scores(summary,matrix,joint,actual.rename(columns={'actual_position':'Position'}))
                merged=summary.set_index('Driver').join(labels.rename('label'));known=merged.label.notna()
                values['dnf_brier']=float(((merged.loc[known,'dnf_chance']-merged.loc[known,'label'])**2).mean()) if known.any() else None
                values['known_dnf_drivers']=int(known.sum())
                values['unknown_dnf_drivers']=int((~known).sum())
                values['loss']=values['finish_mae']+values['top10_brier'];metrics[arm]=values
            write_new(folder/'score.json',{'metrics':metrics,'manifest_sha256':digest(file),
                'actual_results_sha256':digest(official/'actual_results.csv'),'official_folder':str(official),
                'created_at_utc':current.isoformat(),'activated':False,'promotion_approved':False})
            results.append({'status':'scored','folder':str(folder)})
        except (ValueError,OSError,KeyError) as exc:
            results.append({'status':'score_failed','folder':str(folder),'error':str(exc)[:250]})
    return results


def run_enabled(root,forecast=None):
    if not (Path(root)/CONFIG).is_file():return {'status':'disabled'}
    from portable_app.instance_lock import workspace_lock
    try:
        with workspace_lock(Path(root)):
            try:
                scored=score(root)
            except (ValueError,OSError,KeyError) as exc:
                scored=[{'status':'score_failed','error_type':type(exc).__name__}]
            try:
                captured=capture(root,forecast) if forecast else {'status':'no_source_forecast'}
            except Exception as exc:
                captured={'status':'capture_failed','error_type':type(exc).__name__,'error':str(exc)[:250]}
            return {'capture':captured,'scoring':scored}
    except Exception as exc:
        return {'status':'capture_failed','error_type':type(exc).__name__,'error':str(exc)[:250]}
