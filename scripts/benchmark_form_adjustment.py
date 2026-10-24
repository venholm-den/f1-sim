"""Matched offline simulation ablations for form, wear and retirement risk."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.benchmark_grid_influence import load_archive
from src.accuracy_benchmark import build_replay_inputs, simple_baseline, evaluate_forecast, calibration_bins
from src.accuracy_candidates import single_degradation, SINGLE_DEGRADATION_MULTIPLIER
from src.app_services.prediction_trials import sources
from src.feature_ablation_benchmark import evaluate_with_dnf
from src.form_adjustment import (FORM_WEIGHTS, packet_from_races, training_table, fit_form,
                                 apply_form, apply_retirement_prior)
from src.race_scores import race_scores
from src.simulate import simulate_races

ARMS=('legacy','stage_form_v1','single_degradation_v1','form_degradation_v1','simple_retirement_prior_v1')
METRICS=('finish_mae','win_brier','podium_brier','top10_brier','dnf_brier','loss','rps','log_score','pair_brier')


def screening(metrics,baselines):
    decisions=[]
    for stage in ('PRE','FP2','Q'):
        later=metrics[metrics.session.eq(stage)&metrics['split'].eq('previously_seen_diagnostic')]
        control=later[later.arm.eq('legacy')]
        for arm in ARMS[1:]:
            pair=later[later.arm.eq(arm)].merge(control,on=['year','round'],suffixes=('_new','_old'),validate='one_to_one')
            reasons=[]
            if len(pair)<6:
                reasons.append('fewer_than_six_matched_diagnostic_races')
            loss_gain=float(1-pair.loss_new.mean()/pair.loss_old.mean()) if not pair.empty else None
            risk_gain=float(1-pair.dnf_brier_new.mean()/pair.dnf_brier_old.mean()) if not pair.empty else None
            if arm=='simple_retirement_prior_v1':
                if risk_gain is None or risk_gain<.02:reasons.append('dnf_brier_gain_below_2_percent')
                if loss_gain is None or loss_gain<-.01:reasons.append('finish_loss_regression_above_1_percent')
                checks=('win_brier','podium_brier','top10_brier')
            else:
                if loss_gain is None or loss_gain<.05:reasons.append('loss_gain_below_5_percent')
                checks=('win_brier','podium_brier','top10_brier','dnf_brier')
            for metric in checks:
                if pair.empty or pair[metric+'_new'].isna().any() or pair[metric+'_old'].isna().any():
                    reasons.append(metric+'_missing')
                elif pair[metric+'_new'].mean()>pair[metric+'_old'].mean():reasons.append(metric+'_regressed')
            grid=None
            if stage=='Q':
                q=baselines[baselines.session.eq(stage)&baselines['split'].eq('previously_seen_diagnostic')]
                qpair=pair.merge(q[['year','round','finish_mae']],on=['year','round'],validate='one_to_one')
                grid=float(qpair.finish_mae.mean()) if not qpair.empty else None
                if arm!='simple_retirement_prior_v1' and (len(qpair)!=len(pair) or qpair.empty
                        or qpair.finish_mae_new.mean()>=qpair.finish_mae.mean()):
                    reasons.append('does_not_beat_qualifying_order')
            dev=metrics[metrics.session.eq(stage)&metrics['split'].eq('development')]
            candidate=dev[dev.arm.eq(arm)];old=dev[dev.arm.eq('legacy')]
            primary='dnf_brier' if arm=='simple_retirement_prior_v1' else 'loss'
            if candidate.empty or candidate[primary].mean()>=old[primary].mean():
                reasons.append('not_selected_on_development')
            decisions.append(dict(stage=stage,arm=arm,paired_races=len(pair),loss_improvement=loss_gain,
                retirement_brier_improvement=risk_gain,qualifying_mae=grid,
                passes_diagnostic_screen=not reasons,reasons=reasons,
                fresh_races=0,promotion_approved=False,activated=False))
    return decisions


def run(workspace,output,*,years,n_sims=2000,seeds=(42,123,777)):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    hashes=sources(root)
    hashes.update({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
        'src/form_adjustment.py','src/accuracy_benchmark.py','src/race_scores.py',
        'scripts/benchmark_form_adjustment.py','scripts/benchmark_grid_influence.py')})
    protocol=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),arms=list(ARMS),
        form_weights=FORM_WEIGHTS,ridge_alpha=100.,degradation_multiplier=SINGLE_DEGRADATION_MULTIPLIER,
        retirement_prior='Beta(1,9); equal same-season driver/team mix; known labels only; engine clipping retained',
        fit_policy='Refit stage-specific models on strictly earlier completed races; fixed settings, no search.',
        n_sims=n_sims,seeds=list(seeds),source_sha256=hashes,
        split='2021-2024 development; 2025-2026 previously inspected diagnostics; no fresh validation',
        screening='Form: dev selection, >=6 matched later races, >=5% loss gain, no Brier regression, Q beats Q order. '
                  'Risk: dev selection, >=2% DNF Brier gain, <=1% loss regression and no win/podium/top10 regression.',
        activated=False,promotion_approved=False)
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    races,_,inputs,failures,q_audit=load_archive(workspace,years)
    packet=packet_from_races(races);table=training_table(packet)
    packet.to_csv(output/'history.csv',index=False);table.to_csv(output/'form_training.csv',index=False)
    rows,predictions,baselines,skipped,fit_records=[],[],[],[],[]
    for index,race in enumerate(races):
        if index<2 or (race.year==2021 and race.event=='Belgian Grand Prix'):continue
        split='development' if race.year<=2024 else 'previously_seen_diagnostic'
        cutoff=(race.year,race.round)
        for stage in ('PRE','FP2','Q'):
            current=None if stage=='PRE' else race.sessions.get(stage)
            if stage!='PRE' and current is None:
                skipped.append(dict(year=race.year,round=race.round,stage=stage,reason='session_unavailable'))
                continue
            metadata=dict(year=race.year,round=race.round,event=race.event,session=stage)
            try:
                base,track,weather=build_replay_inputs(current,races[:index],metadata=metadata)
                actual=race.sessions['R'].results
                grid_metrics,_=evaluate_forecast(simple_baseline(base,races[:index],'grid_order'),actual)
                fit=fit_form(table,cutoff,stage)
                qpositions=dict(zip(current.results.Abbreviation,current.results.Position)) if stage=='Q' else None
                form=apply_form(base,packet,fit,cutoff,stage,q_positions=qpositions)
                variants={'legacy':(base,{}),'stage_form_v1':(form,{}),
                    'single_degradation_v1':(single_degradation(base),{'single_degradation_multiplier':SINGLE_DEGRADATION_MULTIPLIER}),
                    'form_degradation_v1':(single_degradation(form),{'single_degradation_multiplier':SINGLE_DEGRADATION_MULTIPLIER}),
                    'simple_retirement_prior_v1':(apply_retirement_prior(base,packet,cutoff),{})}
                episode_rows,episode_predictions=[],[]
                print(f'Form replay {race.year} R{race.round} {stage}; fit {fit["races"]} earlier races',flush=True)
                for arm,(features,options) in variants.items():
                    for seed in seeds:
                        summary,matrix,sims=simulate_races(features,n_sims=n_sims,seed=seed,
                            overtaking_difficulty=track['overtaking_difficulty'],weather_modifiers=weather,**options)
                        scores,data=evaluate_with_dnf(summary,actual)
                        scores.update(race_scores(summary,matrix,sims,actual.rename(columns={'Abbreviation':'Driver'})))
                        identity=dict(year=race.year,round=race.round,event=race.event,session=stage,split=split,arm=arm,seed=seed)
                        episode_rows.append({**identity,**scores});episode_predictions.append(data.assign(**identity))
                rows.extend(episode_rows);predictions.extend(episode_predictions)
                baselines.append(dict(year=race.year,round=race.round,session=stage,split=split,**grid_metrics))
                fit_records.append(dict(year=race.year,round=race.round,stage=stage,model=fit))
            except (ValueError,KeyError) as exc:
                skipped.append(dict(year=race.year,round=race.round,stage=stage,reason=str(exc)))
    if not rows:raise ValueError('No complete matched simulation episodes.')
    seed_metrics=pd.DataFrame(rows)
    metrics=seed_metrics.groupby(['year','round','session','split','arm'],as_index=False)[list(METRICS)].mean()
    baselines=pd.DataFrame(baselines)
    summary=metrics.groupby(['arm','session','split'],as_index=False).agg(races=('round','size'),
        **{name:(name,'mean') for name in METRICS})
    pred=pd.concat(predictions,ignore_index=True)
    pooled=pred.groupby(['arm','session','split','year','round','Driver'],as_index=False)[
        ['avg_finish','win_chance','podium_chance','points_chance','dnf_chance','actual_position','actual_dnf']].mean()
    pooled=pooled.rename(columns={'arm':'variant'})
    bins=calibration_bins(pooled)
    risk_bins=[]
    for key,part in pooled[pooled.actual_dnf.notna()].groupby(['variant','session','split']):
        part=part.copy();part['bucket']=(part.dnf_chance*10).astype(int).clip(0,9)
        for bucket,group in part.groupby('bucket'):
            risk_bins.append(dict(zip(['variant','session','split'],key),bucket=int(bucket),
                count=len(group),predicted=float(group.dnf_chance.mean()),observed=float(group.actual_dnf.mean())))
    decisions=screening(metrics,baselines)
    for name,frame in [('seed_metrics',seed_metrics),('race_metrics',metrics),('simple_baselines',baselines),
                       ('summary',summary),('predictions',pooled),('calibration_bins',bins),
                       ('retirement_calibration_bins',pd.DataFrame(risk_bins))]:
        frame.to_csv(output/(name+'.csv'),index=False)
    (output/'fitted_models.json').write_text(json.dumps(fit_records,indent=2),encoding='utf-8')
    # Pin both the existing trial sources and this experiment's independent code.
    current_hashes=sources(root)
    for name,sha in hashes.items():
        path=root/'src'/name if name in current_hashes else root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('Benchmark source changed during replay.')
    report={**protocol,'inspected_races':[list(r.key) for r in races],'fresh_validation_races':[],
        'history_exclusions':packet.attrs.get('excluded_races',[]),
        'input_sources':inputs,'load_failures':failures,'qualifying_audit':q_audit,'skipped':skipped,
        'summary':summary.to_dict('records'),'screening':decisions,
        'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*') if p.is_file()}}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(summary.round(5).to_string(index=False));print(json.dumps(decisions,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--years',type=int,nargs='+',default=list(range(2021,2027)))
    args=parser.parse_args();run(args.workspace,args.output_dir,years=args.years)
