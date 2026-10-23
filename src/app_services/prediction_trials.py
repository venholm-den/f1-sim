"""Versioned prospective candidates, with paired official scoring."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import gzip
import html
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from src.accuracy_candidates import single_pace_blend
from src.app_services.beta import verified_snapshot
from src.app_services.practice_collection import collect_weekend, utc
from src.app_services.shadow_candidates import BASELINES, CANDIDATES, CONTROL, prepare_candidate
from src.simulate import simulate_races
from src.grid_influence import MAPPINGS, mapped_difficulty
from src.stage_ensemble import (COMPONENTS, FORECAST_COLUMNS, STAGES, blend,
                                build_components, metrics, validate_forecast)
from src.stage_ensemble_benchmark import digest, dump_new

CONFIG = 'config/prediction_trials.json'
ROOT = 'outputs/prediction_trials'
SOURCES = ('simulate.py','model_config.py','accuracy_candidates.py','stage_ensemble.py',
           'grid_influence.py','circuit_calibration.py','venues.py','track.py',
           'stage_ensemble_benchmark.py','features.py','long_run_pace.py',
           'performance.py','model.py','run_config.py','reliability.py','retirement_risk.py',
           'retirement_progress.py','qualifying_features.py','historical_calibration.py',
           'qualifying_pace.py','qualifying_archive.py','pit_scenarios.py','agent_race.py',
           'retirement_survival.py','race_window_weather.py','race_weather.py',
           'result_status.py','neutralisation.py','tyres.py','app_services/beta.py',
           'app_services/shadow_candidates.py',
           'data_sources/openf1.py','data_sources/fastf1_cache.py','app_services/classification_checks.py','app_services/post_race_automation.py',
           'app_services/forecast_automation.py',
           'app_services/practice_collection.py','app_services/prediction_trials.py')
VARIANTS = ('simulation','stage_blend','stronger_grid','single_pace','grid_influence','frozen_simulation','qualifying_order',CONTROL,*CANDIDATES)
METRICS = ('finish_mae','win_brier','podium_brier','top10_brier','dnf_brier','loss')


def sources(root):
    return {name:digest(Path(root)/'src'/name) for name in SOURCES}


def register_suite(root, ensemble_config, *, now=None, inspected_reports=(), extended_models=False, history_path=None,
                   grid_candidate_path=None):
    """Pin existing weights and predeclare comparisons; never train or activate."""
    root = Path(root)
    config = json.loads(Path(ensemble_config).read_text(encoding='utf-8'))
    candidate = root/config['candidate_path']
    if digest(candidate)!=config['candidate_sha256']:
        raise ValueError('Ensemble candidate checksum differs.')
    model = json.loads(candidate.read_text(encoding='utf-8'))
    if model.get('model')!='stage_ensemble_v1' or model.get('activated') is not False or model.get('promotion_approved') is not False:
        raise ValueError('Only an inactive stage ensemble can be compared.')
    for name,sha in model['source_sha256'].items():
        if name not in {'stage_ensemble.py','stage_ensemble_benchmark.py'} or digest(root/'src'/name)!=sha:
            raise ValueError('Fitted ensemble source differs.')
    created = utc(now or datetime.now(timezone.utc))
    if created < utc(model['created_at_utc']):
        raise ValueError('Cannot backdate a registered comparison.')
    folder = root/ROOT/'suites'/(created.strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'ensemble.json').write_bytes(candidate.read_bytes())
    for key,name in [('results_path','results.csv'),('practice_path','historical_practice.csv')]:
        path = (root/config[key]).resolve()
        if model['input_sha256'].get(str(path))!=digest(path):
            raise ValueError('Ensemble input archive differs from fitted provenance.')
        (folder/name).write_bytes(path.read_bytes())
    inspected = {tuple(key) for fit in model['stages'].values()
                 for key in fit['train_races']+fit['calibration']['calibration_races']}
    for name,sha in model['input_sha256'].items():
        if Path(name).name=='report.json':
            if digest(name)!=sha:
                raise ValueError('Benchmark inspection ledger checksum differs.')
            report=json.loads(Path(name).read_text(encoding='utf-8'))
            for field in ('development_races','inspected_races','evaluated_races','attempted_races','holdout_races'):
                inspected.update(tuple(key) for key in report.get(field,[]))
    inspection_hashes = {}
    for name in inspected_reports:
        path = Path(name)
        report = json.loads(path.read_text(encoding='utf-8'))
        for field in ('development_races','inspected_races','evaluated_races','attempted_races','holdout_races'):
            inspected.update(tuple(key) for key in report.get(field, []))
        inspection_hashes[str(path.resolve())] = digest(path)
    suite = {'schema_version':1,'created_at_utc':created.isoformat(),'activated':False,
        'inspection_reports_sha256': inspection_hashes,
        'promotion_approved':False,'ensemble_candidate_sha256':config['candidate_sha256'],
        'files':{n:digest(folder/n) for n in ('ensemble.json','results.csv','historical_practice.csv')},
        'source_sha256':sources(root),'variants':['stage_blend','stronger_grid','single_pace'],
        'inspected_races':[list(key) for key in sorted(inspected)],
        'assumptions':{'seeds':[42,123,777],'simulations_per_seed':5000,'q_grid_multiplier':3.3,
            'practice_component':'FP2 only; FP1/FP3 collected without silently substituting',
            'stage_weights':'Existing fitted weights, no online retraining',
            'cohort':'First complete prospective trial per race and stage for this suite'},
        'promotion_gate':{'fresh_races_per_stage':6,'minimum_loss_improvement':.05,
            'no_regression':['win_brier','podium_brier','top10_brier','dnf_brier'],
            'q_must_beat_qualifying_order':True,'automatic_activation':False}}
    if extended_models:
        suite['schema_version'] = 2
        suite['variants'].extend(CANDIDATES)
        suite['candidate_protocol'] = {'seeds': [42, 123, 777], 'simulations_per_seed': 1000,
            'control': CONTROL, 'incremental_baselines': BASELINES, 'agent_step_seconds': 1., 'history_policy': 'Fixed archive available by trial start; refit Q posterior on strictly earlier races, no hyperparameter tuning',
            'failures': 'Isolated arm skips, recorded permanently; no substitution or automatic activation'}
        if history_path is not None:
            path = Path(history_path)
            packet = json.loads(gzip.decompress(path.read_bytes()))
            if packet.get('schema_version') != 1 or utc(packet['captured_at_utc']) > created:
                raise ValueError('Invalid or future candidate history packet.')
            (folder/'candidate_history.json.gz').write_bytes(path.read_bytes())
            suite['files']['candidate_history.json.gz'] = digest(folder/'candidate_history.json.gz')
    if grid_candidate_path is not None:
        path = Path(grid_candidate_path)
        grid = json.loads(path.read_text(encoding='utf-8'))
        if (grid.get('model') != 'grid_influence_v1' or grid.get('activated') is not False
                or grid.get('promotion_approved') is not False
                or set(grid.get('selected_on_development', {})) != set(STAGES)
                or any(v not in MAPPINGS for v in grid['selected_on_development'].values())
                or utc(grid['created_at_utc']) > created):
            raise ValueError('Invalid inactive grid-influence candidate')
        for name in ('grid_influence.py', 'circuit_calibration.py', 'venues.py'):
            if grid['source_sha256'].get(name) != digest(root/'src'/name):
                raise ValueError('Grid-influence candidate source changed')
        (folder/'grid_candidate.json').write_bytes(path.read_bytes())
        suite['files']['grid_candidate.json'] = digest(folder/'grid_candidate.json')
        suite['schema_version'] = 3
        suite['variants'].append('grid_influence')
        suite['grid_protocol'] = {'selected_on_development': grid['selected_on_development'],
            'baseline': 'simulation', 'automatic_activation': False,
            'policy': 'Fixed stage mapping; strictly earlier circuit history; same seeds and simulations as simulation control'}
    dump_new(folder/'suite.json',suite)
    return {'enabled':True,'suite_path':str((folder/'suite.json').relative_to(root)),
            'suite_sha256':digest(folder/'suite.json')}


def read_suite(root):
    root = Path(root)
    path = root/CONFIG
    if not path.exists():
        return None
    config = json.loads(path.read_text(encoding='utf-8'))
    if not config.get('enabled'):
        return None
    suite_path = root/config['suite_path']
    if digest(suite_path)!=config['suite_sha256']:
        raise ValueError('Registered trial suite checksum differs.')
    suite = json.loads(suite_path.read_text(encoding='utf-8'))
    if suite['activated'] is not False or suite['promotion_approved'] is not False:
        raise ValueError('Prediction trials cannot activate a live model.')
    if suite['source_sha256']!=sources(root):
        raise ValueError('Prediction trial source changed; register a new versioned suite.')
    for name,sha in suite['files'].items():
        if name not in {'ensemble.json','results.csv','historical_practice.csv','candidate_history.json.gz','grid_candidate.json'} or digest(suite_path.parent/name)!=sha:
            raise ValueError('Registered trial input checksum differs.')
    return suite_path,suite,config['suite_sha256']


def verify_files(folder, manifest):
    allowed = {v+'.csv' for v in VARIANTS}|{'features.csv','simulation_inputs.json','practice_features.csv','grid_influence_inputs.json'}
    allowed |= {v+'_features.csv' for v in (CONTROL,*CANDIDATES)} | {v+'_inputs.json' for v in (CONTROL,*CANDIDATES)}
    for name,sha in manifest['files'].items():
        if name not in allowed or digest(folder/name)!=sha:
            raise ValueError('Saved prediction trial checksum differs.')


def verify_capture(folder, manifest):
    verify_files(folder,manifest)
    suite_path=Path(manifest['suite_path'])
    practice_path=Path(manifest['practice_manifest_path'])
    if digest(suite_path)!=manifest['suite_sha256'] or digest(practice_path)!=manifest['practice_manifest_sha256']:
        raise ValueError('Trial suite or practice manifest changed.')
    suite=json.loads(suite_path.read_text(encoding='utf-8'))
    for name,sha in suite['files'].items():
        if name not in {'ensemble.json','results.csv','historical_practice.csv','candidate_history.json.gz','grid_candidate.json'} or digest(suite_path.parent/name)!=sha:
            raise ValueError('Registered trial evidence changed.')
    practice=json.loads(practice_path.read_text(encoding='utf-8'))
    for name,sha in practice['files'].items():
        if name not in {'practice_features.csv','laps.csv','collection.json'} or digest(practice_path.parent/name)!=sha:
            raise ValueError('Collected practice evidence changed.')
    created=utc(manifest['created_at_utc'])
    if manifest.get('candidate_history_cutoff_utc'):
        history_cutoff = utc(manifest['candidate_history_cutoff_utc'])
        if not utc(suite['created_at_utc']) <= history_cutoff <= created:
            raise ValueError('Candidate history cutoff is outside the registered trial window.')
        if 'candidate_history.json.gz' in suite['files']:
            history_packet = json.loads(gzip.decompress((suite_path.parent/'candidate_history.json.gz').read_bytes()))
            if utc(history_packet['captured_at_utc']) > history_cutoff:
                raise ValueError('Candidate history was captured after its declared cutoff.')
    source=Path(manifest['source_forecast']); original=verified_snapshot(source)
    context=manifest['context']
    if (manifest['category']!='prospective_prediction_trial' or not manifest.get('fresh_validation')
            or created>=utc(context['race_start_utc'])
            or created<max(utc(suite['created_at_utc']),utc(practice['captured_at_utc']),utc(original['created_at_utc']))
            or practice['status']!='completed' or practice['context']!=context
            or original['category']!='prospective' or original['context']!=context
            or digest(source/'frozen/manifest.json')!=manifest['source_manifest_sha256']):
        raise ValueError('Trial is not supported by intact prospective evidence.')


def simulation_inputs(root, forecast, original):
    """Legacy inputs are accepted only if they exactly reproduce the frozen run."""
    frozen = forecast/'frozen'
    features = pd.read_csv(frozen/'features.csv')
    config = json.loads((frozen/'forecast_config.json').read_text(encoding='utf-8'))
    if 'simulation_inputs.json' in original['files']:
        inputs = json.loads((frozen/'simulation_inputs.json').read_text(encoding='utf-8'))
        provenance = 'frozen_simulation_inputs'
    else:
        path = forecast/'source/weather_context.json'
        weather = json.loads(path.read_text(encoding='utf-8'))
        context = original['context']
        if (weather.get('year'),weather.get('event'),weather.get('session'))!=(context['year'],context['event'],context['session']):
            raise ValueError('Legacy session weather identity differs.')
        if utc(weather['saved_at_utc']) > utc(original['created_at_utc']):
            raise ValueError('Legacy weather was saved after the frozen forecast.')
        venue = json.loads((frozen/'venue_context.json').read_text(encoding='utf-8'))
        inputs = {'weather_modifiers':weather,'overtaking_difficulty':venue['track_factors']['overtaking_difficulty']}
        provenance = 'legacy_inputs_verified_by_exact_frozen_reproduction'
    for name in ('simulate.py','model_config.py'):
        if original.get('model_source_hashes',{}).get(name)!=digest(Path(root)/'src'/name):
            raise ValueError('Simulation source differs from frozen forecast; paired replay refused.')
    replay,_,_ = simulate_races(features,n_sims=int(config['run']['n_sims']),
        seed=int(config['run']['random_seed']),**inputs)
    original_frame = pd.read_csv(frozen/'simulation_summary.csv').sort_values('Driver').reset_index(drop=True)
    replay = replay.sort_values('Driver').reset_index(drop=True)
    columns = [*FORECAST_COLUMNS,'dnf_chance']
    if (replay.Driver.tolist()!=original_frame.Driver.tolist()
            or not np.allclose(replay[columns],original_frame[columns],atol=1e-10,rtol=0)):
        raise ValueError('Simulation inputs do not reproduce the frozen forecast.')
    return features,inputs,provenance


def capture_trial(root, forecast_folder, *, now=None, loader=None):
    root,forecast = Path(root),Path(forecast_folder)
    registered = read_suite(root)
    if registered is None:
        return {'status':'disabled'}
    suite_path,suite,suite_sha = registered
    original = verified_snapshot(forecast)
    context = original['context']; stage = context['session']
    if stage not in STAGES:
        return {'status':'unsupported_stage','session':stage}
    started = utc(now or datetime.now(timezone.utc))
    if original['category']!='prospective' or started>=utc(context['race_start_utc']):
        return {'status':'ineligible','reason':'race_started_or_retrospective'}
    if started < max(utc(original['created_at_utc']),utc(suite['created_at_utc']),utc(context['data_cutoff_utc'])):
        raise ValueError('Cannot backdate a prospective trial.')
    target = (int(context['year']),int(context['round']))
    if suite['inspected_races'] and target<=max(tuple(key) for key in suite['inspected_races']):
        raise ValueError('Previously inspected or earlier race cannot count as fresh prospective evidence.')
    model = json.loads((suite_path.parent/'ensemble.json').read_text(encoding='utf-8'))
    fit = model['stages'][stage]
    training = fit['train_races']+fit['calibration']['calibration_races']
    if not training or any(tuple(key)>=target for key in training):
        raise ValueError('Stage blend contains target or future race outcomes.')
    if fit['status']!='fitted':
        return {'status':'insufficient_history','session':stage}
    # Lock one trial per race/stage, regardless of scheduler retries or re-runs.
    identity=f'{suite_sha[:16]}_{target[0]}_{target[1]:02}_{stage}'
    folder = root/ROOT/'captures'/identity
    for path in sorted(folder.parent.glob(identity+'*/manifest.json')):
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved['suite_sha256']==suite_sha and saved['context']['session']==stage:
            verify_capture(path.parent,saved)
            return {'status':'already_captured','folder':str(path.parent)}
    if folder.exists():
        # An interrupted write is preserved for review, never overwritten.
        folder=folder.with_name(identity+'_'+uuid4().hex[:8])
    practice = collect_weekend(root,context,now=now,loader=loader)
    if practice['status']!='completed':
        return {'status':practice['status'],'practice':practice}
    features,inputs,provenance = simulation_inputs(root,forecast,original)
    base = pd.read_csv(forecast/'frozen/simulation_summary.csv').sort_values('Driver').reset_index(drop=True)
    if features.Driver.isna().any() or features.Driver.duplicated().any() or set(features.Driver)!=set(base.Driver):
        raise ValueError('Complete unique feature roster required.')
    assumptions = suite['assumptions']
    replay_variants = {'simulation':features,'stronger_grid':features,
                       'single_pace':single_pace_blend(features,stage)}
    grid_packet = None
    if suite.get('grid_protocol'):
        grid = json.loads((suite_path.parent/'grid_candidate.json').read_text(encoding='utf-8'))
        difficulty, evidence = mapped_difficulty(grid['selected_on_development'][stage],
            inputs.get('overtaking_difficulty', .55), context, grid['history_observations'])
        grid_packet = {'simulation_inputs': {**inputs, 'overtaking_difficulty': difficulty},
            'evidence': evidence, 'candidate_sha256': suite['files']['grid_candidate.json']}
        replay_variants['grid_influence'] = features
    tables = {}
    for name,frame in replay_variants.items():
        runs = []
        for seed in assumptions['seeds']:
            kwargs = {'grid_loss_multiplier':assumptions['q_grid_multiplier']} if name=='stronger_grid' and stage=='Q' else {}
            options = grid_packet['simulation_inputs'] if name == 'grid_influence' else inputs
            summary,_,_ = simulate_races(frame,n_sims=assumptions['simulations_per_seed'],seed=seed,**{**options,**kwargs})
            runs.append(summary[['Driver',*FORECAST_COLUMNS,'dnf_chance']])
        tables[name] = pd.concat(runs).groupby('Driver',as_index=False).mean().sort_values('Driver')
    matched = base.copy()
    matched[[*FORECAST_COLUMNS,'dnf_chance']] = tables['simulation'][[*FORECAST_COLUMNS,'dnf_chance']].to_numpy()
    # The fitted qualifying component means Q classification, even if the
    # simulation itself already uses a later official FIA starting grid.
    qualifying = pd.to_numeric(features.set_index('Driver').get('actual_grid_position',pd.Series(dtype=float)),errors='coerce')
    q_positions = matched.Driver.map(qualifying)
    if stage=='Q' and sorted(q_positions.dropna())==list(range(1,len(matched)+1)):
        matched['grid_position']=q_positions
        matched['grid_source']='actual_session_results'
    practice_folder = Path(practice['folder'])
    practice_frame = pd.read_csv(practice_folder/'practice_features.csv')
    results = pd.read_csv(suite_path.parent/'results.csv')
    # The live packet replaces target practice only. Fitted weights and archives stay immutable.
    drivers,components,dnf,availability = build_components(matched,target,stage,results,practice_frame,
        n_sims=model['assumptions']['component_simulations'])
    stage_prediction = blend(components,[fit['weights'][n] for n in COMPONENTS])
    tables['stage_blend'] = pd.DataFrame(stage_prediction,columns=FORECAST_COLUMNS).assign(Driver=drivers,dnf_chance=dnf)
    tables['frozen_simulation'] = base[['Driver',*FORECAST_COLUMNS,'dnf_chance']]
    if availability['qualifying']['available']:
        grid = np.asarray(availability['qualifying']['classification'])
        tables['qualifying_order'] = pd.DataFrame(validate_forecast(np.column_stack([grid,grid<=1,grid<=3,grid<=10])),
            columns=FORECAST_COLUMNS).assign(Driver=drivers,dnf_chance=dnf)
    candidate_runs = {}; candidate_packets = {}
    protocol = suite.get('candidate_protocol')
    if protocol:
        history = suite_path.parent/'candidate_history.json.gz'
        for name in (CONTROL, *CANDIDATES):
            if name != CONTROL and name not in suite['variants']:
                continue
            try:
                if utc(now or datetime.now(timezone.utc)) >= utc(context['race_start_utc']):
                    raise ValueError('Race started before this candidate could run.')
                if name != CONTROL and candidate_runs[CONTROL]['status'] != 'completed':
                    raise ValueError('Matched candidate control unavailable.')
                tyre_inventory = tyre_ledger = None
                if name == 'pit_inventory_v1':
                    frozen = forecast/'frozen'
                    if 'tyre_inventory_estimated.csv' in original['files']:
                        tyre_inventory = pd.read_csv(frozen/'tyre_inventory_estimated.csv')
                    if 'tyre_set_ledger_estimated.csv' in original['files']:
                        tyre_ledger = pd.read_csv(frozen/'tyre_set_ledger_estimated.csv')
                frame, options, evidence = prepare_candidate(name, features, inputs,
                    {**context, 'history_cutoff_utc': started.isoformat()},
                    history if history.is_file() else None, tyre_inventory, tyre_ledger)
                predictions = [simulate_races(frame, n_sims=protocol['simulations_per_seed'], seed=seed,
                    **options)[0][['Driver', *FORECAST_COLUMNS, 'dnf_chance']] for seed in protocol['seeds']]
                table = pd.concat(predictions).groupby('Driver', as_index=False)[[*FORECAST_COLUMNS,'dnf_chance']].mean()
                validate_forecast(table[list(FORECAST_COLUMNS)])
                if not np.isfinite(table.dnf_chance).all() or not table.dnf_chance.between(0,1).all():
                    raise ValueError('Invalid candidate retirement probabilities.')
                if set(table.Driver) != set(features.Driver):
                    raise ValueError('Candidate roster differs from source forecast.')
                packet = {'simulation_inputs': options, 'evidence': evidence,
                    'source_feature_cutoff_utc': context['data_cutoff_utc'],
                    'history_cutoff_utc': started.isoformat(),
                    'seeds': protocol['seeds'], 'simulations_per_seed': protocol['simulations_per_seed']}
                json.dumps(packet, allow_nan=False)
                tables[name] = table
                candidate_packets[name] = (frame, packet)
                candidate_runs[name] = {'status':'completed','baseline':BASELINES.get(name, CONTROL),
                    'seeds':protocol['seeds'],'simulations_per_seed':protocol['simulations_per_seed']}
            except Exception as exc:
                candidate_runs[name] = {'status':'skipped','error_type':type(exc).__name__, 'reason':str(exc)[:300]}
    finished = utc(now or datetime.now(timezone.utc))
    if finished>=utc(context['race_start_utc']):
        return {'status':'ineligible','reason':'race_started_during_trial'}
    folder.mkdir(parents=True,exist_ok=False)
    for name,frame in tables.items():
        validate_forecast(frame[list(FORECAST_COLUMNS)])
        frame.to_csv(folder/f'{name}.csv',index=False)
    features.to_csv(folder/'features.csv',index=False)
    (folder/'practice_features.csv').write_bytes((practice_folder/'practice_features.csv').read_bytes())
    dump_new(folder/'simulation_inputs.json',inputs)
    files = [n+'.csv' for n in tables]+['features.csv','practice_features.csv','simulation_inputs.json']
    if grid_packet is not None:
        dump_new(folder/'grid_influence_inputs.json', grid_packet)
        files.append('grid_influence_inputs.json')
    for name, (frame, packet) in candidate_packets.items():
        frame.to_csv(folder/(name+'_features.csv'), index=False)
        dump_new(folder/(name+'_inputs.json'), packet)
        files.extend([name+'_features.csv', name+'_inputs.json'])
    finished = utc(now or datetime.now(timezone.utc))
    if finished>=utc(context['race_start_utc']):
        return {'status':'ineligible','reason':'race_started_before_trial_commit'}
    manifest = {'schema_version':1,'category':'prospective_prediction_trial','created_at_utc':finished.isoformat(),
        'context':context,'suite_path':str(suite_path.resolve()),'suite_sha256':suite_sha,
        'source_forecast':str(forecast.resolve()),'source_manifest_sha256':digest(forecast/'frozen/manifest.json'),
        'practice_manifest_path':str((practice_folder/'manifest.json').resolve()),
        'practice_manifest_sha256':digest(practice_folder/'manifest.json'),
        'files':{n:digest(folder/n) for n in files},'availability':availability,'weights':fit['weights'],
        'candidate_history_cutoff_utc':started.isoformat(),
        'candidate_runs':candidate_runs,'assumptions':assumptions,'input_provenance':provenance,'source_sha256':suite['source_sha256'],
        'fresh_validation':True,
        'stronger_grid_applicable':stage=='Q','activated':False,'sent_to_discord':False,
        'limitations':['Local timestamps are unattested.',
            'Practice observed now; session completion must precede the source forecast cutoff.',
            'FP1/FP3 are collected but the existing trained component uses FP2 only.',
            'Fitted weights and recent-form outcome archive are pinned, not automatically retrained.']}
    dump_new(folder/'manifest.json',manifest)
    return {'status':'captured','folder':str(folder),'practice':practice,'availability':availability}


def try_capture_trial(root,forecast_folder):
    try:
        return capture_trial(root,forecast_folder)
    except Exception as exc:
        return {'status':'capture_failed','error_type':type(exc).__name__,'error':str(exc)[:300]}


def try_collect_current_practice(root,context):
    """Collect at FP1/FP3/SQ too, and even when an older Q forecast is reused."""
    try:
        if read_suite(root) is None:
            return {'status':'disabled'}
        return collect_weekend(root,context)
    except Exception as exc:
        return {'status':'collection_failed','error_type':type(exc).__name__,'error':str(exc)[:300]}


def score_trials(root, *, now=None):
    """Reuse independently completed official scoring; no downloads or posting."""
    root = Path(root); current = utc(now or datetime.now(timezone.utc)); reports=[]
    for path in sorted((root/ROOT/'captures').glob('*/manifest.json')):
        folder = path.parent
        if (folder/'score.json').exists():
            continue
        try:
            manifest = json.loads(path.read_text(encoding='utf-8')); context=manifest['context']
            if current<utc(context['race_start_utc'])+timedelta(hours=8):
                continue
            if (manifest['category']!='prospective_prediction_trial'
                    or utc(manifest['created_at_utc'])>=utc(context['race_start_utc'])):
                raise ValueError('Trial was not captured before the race.')
            source = Path(manifest['source_forecast']); original=verified_snapshot(source)
            if original['category']!='prospective' or original['context']!=context or digest(source/'frozen/manifest.json')!=manifest['source_manifest_sha256']:
                raise ValueError('Trial source forecast changed.')
            verify_capture(folder,manifest)
            official = None
            for job_path in sorted((root/'outputs/app_runs').glob('*/job.json')):
                job = json.loads(job_path.read_text(encoding='utf-8'))
                if job.get('kind')!='score' or job.get('status')!='completed':
                    continue
                scored_source=Path(job['forecast_folder']); scored=verified_snapshot(scored_source)
                c=scored['context']
                if (c['year'],c['round'],c['event'])!=(context['year'],context['round'],context['event']):
                    continue
                score=json.loads((job_path.parent/'score.json').read_text(encoding='utf-8'))
                if score['snapshot_sha256']!=digest(scored_source/'frozen/manifest.json'):
                    raise ValueError('Official scoring source changed.')
                official=job_path.parent
                break
            if official is None:
                continue
            actual=pd.read_csv(official/'actual_results.csv').sort_values('Driver')
            if (actual.Driver.isna().any() or actual.Driver.duplicated().any()
                    or not actual.actual_result_source.eq('fastf1_results').all()
                    or sorted(actual.actual_position)!=list(range(1,len(actual)+1))):
                raise ValueError('Complete official results required.')
            actual_dnf=actual.actual_dnf.map({True:1.,False:0.,'True':1.,'False':0.}).to_numpy(float)
            scores={}
            for name in VARIANTS:
                if name+'.csv' not in manifest['files']:
                    continue
                frame=pd.read_csv(folder/(name+'.csv')).sort_values('Driver')
                if frame.Driver.tolist()!=actual.Driver.tolist():
                    raise ValueError('Trial and official roster differ.')
                scores[name]=metrics(validate_forecast(frame[list(FORECAST_COLUMNS)]),
                    actual.actual_position.to_numpy(float),frame.dnf_chance.to_numpy(float),actual_dnf)
            dump_new(folder/'score.json',{'created_at_utc':current.isoformat(),'metrics':scores,
                'manifest_sha256':digest(path),'official_score_folder':str(official.resolve()),
                'actual_results_sha256':digest(official/'actual_results.csv'),
                'known_dnf_drivers':int(np.isfinite(actual_dnf).sum()),
                'unknown_dnf_drivers':int((~np.isfinite(actual_dnf)).sum()),
                'activated':False,'promotion_approved':False})
            reports.append({'status':'scored','folder':str(folder)})
        except Exception as exc:
            reports.append({'status':'score_failed','folder':str(folder),'error_type':type(exc).__name__,'error':str(exc)[:250]})
    return reports


def comparison_report(root):
    """Equal weight per whole race/stage. Repeated seeds and polls count once."""
    root=Path(root); rows=[]; captures=[]; failures=[]; candidate_status=[]
    config_path=root/CONFIG
    config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    active_suite=config.get('suite_sha256') if config.get('enabled') else None
    for path in sorted((root/ROOT/'captures').glob('*/manifest.json')):
        try:
            manifest=json.loads(path.read_text(encoding='utf-8')); context=manifest['context']
            if active_suite and manifest['suite_sha256']!=active_suite:
                continue
            verify_capture(path.parent,manifest)
            captures.append({'suite':manifest['suite_sha256'],'year':context['year'],'round':context['round'],
                'session':context['session'],'event':context['event'],'captured_at_utc':manifest['created_at_utc'],
                'practice_coverage':manifest['availability']['practice']['coverage'],
                'candidate_runs':manifest.get('candidate_runs', {}),'folder':str(path.parent)})
            for name, status in manifest.get('candidate_runs', {}).items():
                candidate_status.append({'year':context['year'],'round':context['round'],
                    'session':context['session'],'candidate':name,**status})
            score_path=path.parent/'score.json'
            if not score_path.is_file():
                continue
            score=json.loads(score_path.read_text(encoding='utf-8'))
            if score['manifest_sha256']!=digest(path) or score['actual_results_sha256']!=digest(Path(score['official_score_folder'])/'actual_results.csv'):
                raise ValueError('Scored trial evidence changed.')
            for variant,values in score['metrics'].items():
                if variant=='stronger_grid' and not manifest['stronger_grid_applicable']:
                    continue
                rows.append({'suite':manifest['suite_sha256'],'year':context['year'],'round':context['round'],
                    'session':context['session'],'variant':variant,**values})
        except Exception as exc:
            failures.append({'folder':str(path.parent),'error':str(exc)[:250]})
    frame=pd.DataFrame(rows); summaries=[]; comparisons=[]
    if not frame.empty:
        if frame.duplicated(['suite','year','round','session','variant']).any():
            raise ValueError('Duplicate race/stage trials cannot count as independent evidence.')
        for (suite,stage),group in frame.groupby(['suite','session']):
            for variant,part in group.groupby('variant'):
                summaries.append({'suite':suite,'session':stage,'variant':variant,'races':len(part),
                    **{m:float(part[m].mean()) if part[m].notna().any() else None for m in METRICS}})
            for variant in ('stage_blend','stronger_grid','single_pace','grid_influence',*CANDIDATES):
                baseline_name = BASELINES.get(variant, CONTROL) if variant in CANDIDATES else 'simulation'
                baseline=group[group.variant.eq(baseline_name)]
                pair=group[group.variant.eq(variant)].merge(baseline,on=['year','round'],suffixes=('_candidate','_baseline'))
                if pair.empty:
                    continue
                differences={m:float((pair[m+'_candidate']-pair[m+'_baseline']).mean()) if pair[m+'_candidate'].notna().any() else None for m in METRICS}
                denominator=float(pair.loss_baseline.mean())
                improvement=float(1-pair.loss_candidate.mean()/denominator) if denominator>0 else None
                intervals = {'finish_delta_ci_low':None,'finish_delta_ci_high':None}
                if len(pair)>=2:
                    delta=(pair.finish_mae_candidate-pair.finish_mae_baseline).to_numpy()
                    bootstrap=np.random.default_rng(20261011).choice(delta,size=(2000,len(delta)),replace=True).mean(axis=1)
                    low,high=np.quantile(bootstrap,[.025,.975])
                    intervals={'finish_delta_ci_low':float(low),'finish_delta_ci_high':float(high)}
                q=group[group.variant.eq('qualifying_order')]
                qp=pair.merge(q[['year','round','finish_mae']],on=['year','round']) if stage=='Q' else pd.DataFrame()
                beats_q=(len(qp)==len(pair) and float(qp.finish_mae_candidate.mean())<float(qp.finish_mae.mean())) if stage=='Q' else True
                eligible=(len(pair)>=6 and improvement is not None and improvement>=.05 and beats_q
                    and all(differences[m] is not None and differences[m]<=0 for m in ('win_brier','podium_brier','top10_brier','dnf_brier')))
                comparisons.append({'suite':suite,'session':stage,'candidate':variant,'baseline':baseline_name,'paired_races':len(pair),
                    'loss_improvement':improvement,'q_beats_qualifying_order':beats_q,**intervals,
                    **{m+'_delta':v for m,v in differences.items()},'eligible_for_review':eligible,
                    'activated':False,'promotion_approved':False})
    report={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'captures':captures,'candidate_status':candidate_status,'race_metrics':rows,'summary':summaries,'paired_comparisons':comparisons,
        'failures':failures,'active_suite_sha256':active_suite,'activated':False,'promotion_approved':False,
        'policy':'At least six fresh races per stage, 5% lower paired loss, no Brier regression, Q beats qualifying. Explicit review required.'}
    folder=root/ROOT/'reports'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    dump_new(folder/'report.json',report)
    def table(records):
        return pd.DataFrame(records).to_html(index=False,border=0,float_format=lambda v:f'{v:.4f}') if records else '<p>Awaiting complete official results for prospective trials.</p>'
    body=f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Prospective prediction comparisons</title>
<style>body{{background:#10121d;color:#edf1f7;font:15px/1.6 system-ui;margin:32px}}table{{border-collapse:collapse;font-size:12px}}td,th{{padding:8px;border-bottom:1px solid #384054;text-align:left}}section{{overflow:auto;margin-bottom:28px}}a{{color:#8ee8d4}}</style>
<h1>Prospective prediction comparisons</h1><p>Shadow only · Live model unchanged · {len(captures)} captured race/stage trials</p>
<p>{html.escape(report['policy'])} Lower error and Brier scores are better. Seeds are averaged; each race counts once per stage and suite.</p>
<h2>Captured forecasts and practice coverage</h2><section>{table(captures)}</section>
<h2>Candidate execution and skipped inputs</h2><section>{table(candidate_status)}</section>
<h2>Finish error and probability accuracy</h2><section>{table(summaries)}</section>
<h2>Paired candidate minus established simulation</h2><section>{table(comparisons)}</section>
<h2>Evidence requiring attention</h2><section>{table(failures) if failures else '<p>None detected.</p>'}</section>
<p><a href="report.json">Metrics and provenance JSON</a></p></html>'''
    (folder/'report.html').write_text(body,encoding='utf-8')
    return {'folder':str(folder),'report_path':str(folder/'report.html'),'captures':len(captures),'scored_race_stages':len({(r['suite'],r['year'],r['round'],r['session']) for r in rows}), 'failures':failures,'activated':False}
