"""Write and later score prospective ensemble trials outside frozen/live reports."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.app_services.beta import verified_snapshot
from src.stage_ensemble import (COMPONENTS, FORECAST_COLUMNS, STAGES, build_components,
                                blend, metrics, validate_forecast)
from src.stage_ensemble_benchmark import digest, dump_new


def capture_shadow(root, forecast_folder, *, now=None):
    root, forecast_folder = Path(root), Path(forecast_folder)
    config_path = root/'config/stage_ensemble_shadow.json'
    if not config_path.is_file():
        return {'status':'disabled'}
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if not config.get('enabled'):
        return {'status':'disabled'}
    model_path = root/config['candidate_path']
    if digest(model_path) != config['candidate_sha256']:
        raise ValueError('Shadow candidate checksum differs.')
    model = json.loads(model_path.read_text(encoding='utf-8'))
    if (model.get('model') != 'stage_ensemble_v1' or model.get('schema_version') != 1
            or model.get('activated') is not False or model.get('promotion_approved') is not False):
        raise ValueError('Only an explicitly inactive ensemble can run in shadow mode.')
    for name, expected in model['source_sha256'].items():
        if name not in {'stage_ensemble.py','stage_ensemble_benchmark.py'} or digest(root/'src'/name) != expected:
            raise ValueError('Shadow model source differs; rebuild the candidate.')
    original = verified_snapshot(forecast_folder)
    context = original['context']
    stage = context['session']
    if stage not in STAGES:
        return {'status':'unsupported_stage','session':stage}
    created = pd.Timestamp(now or datetime.now(timezone.utc))
    if created.tzinfo is None:
        raise ValueError('Shadow timestamp must be timezone aware.')
    if original['category'] != 'prospective' or created >= pd.Timestamp(context['race_start_utc']):
        return {'status':'ineligible','reason':'race_started_or_retrospective'}
    if (created < pd.Timestamp(original['created_at_utc'])
            or created < pd.Timestamp(model['created_at_utc'])
            or created < pd.Timestamp(context['data_cutoff_utc'])):
        raise ValueError('Cannot backdate a shadow prediction.')
    target = (int(context['year']),int(context['round']))
    fitted = model['stages'][stage]
    training = fitted['train_races'] + fitted['calibration']['calibration_races']
    if not training or any(tuple(key) >= target for key in training):
        raise ValueError('Shadow model includes target or future race outcomes.')
    if fitted['status'] != 'fitted':
        return {'status':'insufficient_history','session':stage}
    manifest_path = forecast_folder/'frozen/manifest.json'
    snapshot_sha = digest(manifest_path)
    identity = f'{snapshot_sha[:16]}_{config["candidate_sha256"][:16]}'
    destination = root/'outputs/stage_ensemble_shadow'/identity
    if (destination/'manifest.json').is_file():
        saved = json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
        for name, expected in saved['files'].items():
            if name not in {'learned_blend.csv','calibration_comparison.csv','simulation.csv','qualifying_order.csv'} or digest(destination/name) != expected:
                raise ValueError('Existing shadow output checksum differs.')
        return {'status':'already_captured','folder':str(destination)}
    datasets = {}
    for key in ('results_path','practice_path'):
        path = (root/config[key]).resolve()
        if model['input_sha256'].get(str(path)) != digest(path):
            raise ValueError('Shadow feature archive differs from fitted provenance.')
        datasets[key] = pd.read_csv(path)
    base = pd.read_csv(forecast_folder/'frozen/simulation_summary.csv')
    drivers, components, dnf, availability = build_components(base,target,stage,
        datasets['results_path'], datasets['practice_path'],
        n_sims=model['assumptions']['component_simulations'])
    weights = [fitted['weights'][name] for name in COMPONENTS]
    raw = blend(components,weights)
    calibrated = blend(components,weights,fitted['calibration']['uniform_mass'])
    destination.mkdir(parents=True,exist_ok=False)
    files = {}
    variants = {'learned_blend':raw,'calibration_comparison':calibrated,'simulation':components[0]}
    if availability['qualifying']['available']:
        grid = np.asarray(availability['qualifying']['classification'])
        variants['qualifying_order'] = validate_forecast(np.column_stack([grid,grid<=1,grid<=3,grid<=10]))
    for name, values in variants.items():
        frame = pd.DataFrame(values,columns=FORECAST_COLUMNS)
        frame['Driver'] = drivers
        frame['dnf_chance'] = dnf
        frame.to_csv(destination/f'{name}.csv',index=False)
        files[f'{name}.csv'] = digest(destination/f'{name}.csv')
    dump_new(destination/'manifest.json',{'schema_version':1,'category':'prospective_shadow',
        'created_at_utc':created.isoformat(),'context':context,'candidate_sha256':config['candidate_sha256'],
        'candidate_path':str(model_path.resolve()),'source_forecast':str(forecast_folder.resolve()),
        'source_manifest_sha256':snapshot_sha,'files':files,'weights':fitted['weights'],
        'train_races':fitted['train_races'],'calibration':fitted['calibration'],
        'availability':availability,'activated':False,'sent_to_discord':False,
        'source_sha256':{name:digest(root/'src'/name) for name in ('stage_ensemble.py','stage_ensemble_benchmark.py')},
        'service_sha256':digest(Path(__file__)),
        'input_sha256':{str((root/config[k]).resolve()):digest(root/config[k]) for k in datasets},
        'limitations':['Local timestamp is unattested.','Archived practice may be absent for the current race.',
                       'Static historical archives can become stale; older than three rounds falls back.']})
    return {'status':'captured','folder':str(destination)}


def try_capture_shadow(root, forecast_folder):
    """Experimental failures cannot interrupt an established forecast or delivery."""
    try:
        return capture_shadow(root,forecast_folder)
    except Exception as exc:
        return {'status':'capture_failed','error_type':type(exc).__name__,'error':str(exc)}


def score_shadow_queue(root, *, now=None):
    """Reuse completed official scoring jobs, never fetch or post anything."""
    root = Path(root)
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    reports = []
    for manifest_path in sorted((root/'outputs/stage_ensemble_shadow').glob('*/manifest.json')):
        folder = manifest_path.parent
        if (folder/'score.json').exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            context = manifest['context']
            if now < pd.Timestamp(context['race_start_utc']) + timedelta(hours=8):
                continue
            original = verified_snapshot(manifest['source_forecast'])
            if digest(Path(manifest['source_forecast'])/'frozen/manifest.json') != manifest['source_manifest_sha256']:
                raise ValueError('Shadow source forecast changed.')
            if (manifest['category'] != 'prospective_shadow' or original['context'] != context
                    or pd.Timestamp(manifest['created_at_utc']) >= pd.Timestamp(context['race_start_utc'])):
                raise ValueError('Shadow is not an eligible prospective prediction.')
            scoring = None
            for job_path in sorted((root/'outputs/app_runs').glob('*/job.json')):
                job = json.loads(job_path.read_text(encoding='utf-8'))
                if job.get('kind') != 'score' or job.get('status') != 'completed':
                    continue
                scored_source = Path(job['forecast_folder'])
                scored = verified_snapshot(scored_source)
                sc = scored['context']
                if (sc['year'],sc['round'],sc['event']) != (context['year'],context['round'],context['event']):
                    continue
                score = json.loads((job_path.parent/'score.json').read_text(encoding='utf-8'))
                if score['snapshot_sha256'] != digest(scored_source/'frozen/manifest.json'):
                    raise ValueError('Official scoring job source checksum differs.')
                scoring = job_path.parent
                break
            if scoring is None:
                continue
            actual = pd.read_csv(scoring/'actual_results.csv').sort_values('Driver')
            if (actual.Driver.duplicated().any() or not actual.actual_result_source.eq('fastf1_results').all()
                    or sorted(actual.actual_position) != list(range(1,len(actual)+1))):
                raise ValueError('Complete official classification required.')
            actual_dnf = actual.actual_dnf.map({True:1.,False:0.,'True':1.,'False':0.}).to_numpy(float)
            scores = {}
            for name, expected in manifest['files'].items():
                if name not in {'learned_blend.csv','calibration_comparison.csv','simulation.csv','qualifying_order.csv'} or digest(folder/name) != expected:
                    raise ValueError('Shadow output changed.')
                frame = pd.read_csv(folder/name).sort_values('Driver')
                if frame.Driver.tolist() != actual.Driver.tolist():
                    raise ValueError('Shadow and actual driver coverage differ.')
                scores[name.removesuffix('.csv')] = metrics(validate_forecast(frame[list(FORECAST_COLUMNS)]),
                    actual.actual_position.to_numpy(float),frame.dnf_chance.to_numpy(float),actual_dnf)
            dump_new(folder/'score.json',{'scored_at_utc':now.isoformat(),'metrics':scores,
                'shadow_manifest_sha256':digest(manifest_path),
                'actual_results_sha256':digest(scoring/'actual_results.csv'),'official_score_folder':str(scoring),
                'activated':False,'promotion_approved':False})
            reports.append({'folder':str(folder),'status':'scored'})
        except Exception as exc:
            reports.append({'folder':str(folder),'status':'score_failed','error_type':type(exc).__name__})
    return reports
