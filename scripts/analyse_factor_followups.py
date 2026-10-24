"""Exploratory attribution and earlier-stage checks on saved historical features.

Fixed retrospective roster, not an operational PRE roster reconstruction.
No target Q columns enter PRE/FP2 predictors. Selection remains diagnostic.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from scripts.analyse_historical_factors import bootstrap, digest, evaluate


STAGE_COLUMNS = {
    'PRE':['prior_driver_form','prior_team_form','prior_race_pace','prior_driver_grid_residual',
           'prior_driver_dnf','prior_team_dnf','prior_driver_starts','prior_team_starts'],
    'FP2':['prior_driver_form','prior_team_form','prior_race_pace','prior_driver_grid_residual',
           'prior_driver_dnf','prior_team_dnf','prior_driver_starts','prior_team_starts',
           'fp1_pace_rank','fp1_confidence','fp1_clean_laps',
           'fp2_pace_rank','fp2_confidence','fp2_clean_laps'],
}


def stable_order(scores, drivers):
    order=np.lexsort((np.asarray(drivers,dtype=str),np.asarray(scores,dtype=float)))
    ranks=np.empty(len(order),dtype=int);ranks[order]=np.arange(1,len(order)+1)
    return ranks


def stage_checks(frame):
    rows=[]
    for year in (2024,2025,2026):
        train=frame[frame.Year<year];test=frame[frame.Year==year].copy()
        if train.empty or test.empty:
            continue
        for stage,cols in STAGE_COLUMNS.items():
            cols=[c for c in cols if c in frame]
            learner=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
                                  StandardScaler(),Ridge(alpha=100.))
            target=(train.actual_finish-.5)/train.field_size
            weights=1/train.groupby(['Year','Round']).DriverCode.transform('size');weights/=weights.mean()
            learner.fit(train[cols],target,ridge__sample_weight=weights)
            test['estimate']=learner.predict(test[cols])
            for (y,r),race in test.groupby(['Year','Round']):
                form=race.prior_driver_form.fillna(race.prior_team_form)
                baseline=stable_order(form,race.DriverCode)
                predicted=stable_order(race.estimate,race.DriverCode)
                rows.append(dict(Year=y,Round=r,stage=stage,drivers=len(race),
                    baseline_mae=float(np.abs(baseline-race.actual_finish).mean()),
                    model_mae=float(np.abs(predicted-race.actual_finish).mean())))
    return pd.DataFrame(rows)


def run(folder,output):
    folder,output=Path(folder),Path(output);output.mkdir(parents=True,exist_ok=False)
    frame=pd.read_csv(folder/'features.csv')
    frame['wet_grid_interaction']=(frame.q_percentile-.5)*frame.q_wet
    frame['circuit_grid_interaction']=(frame.q_percentile-.5)*frame.prior_layout_grid_error
    groups={'driver_form_only':['prior_driver_form'], 'team_form_only':['prior_team_form'],
            'historical_pace_only':['prior_race_pace'], 'previous_grid_residual_only':['prior_driver_grid_residual'],
            'driver_and_team_form':['prior_driver_form','prior_team_form'],
            'form_and_pace':['prior_driver_form','prior_team_form','prior_race_pace'],
            'fp2_only':[c for c in frame if c.startswith('fp2_')],
            'grid_interactions':['wet_grid_interaction','circuit_grid_interaction']}
    protocol={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':digest(Path(__file__)),
        'feature_table_sha256':digest(folder/'features.csv'),'post_q_groups':groups,'stage_columns':STAGE_COLUMNS,
        'interpretation':'Post-hoc exploratory follow-up on inspected history. No fresh confirmation or live promotion.',
        'roster_limit':'Fixed eligible historical roster; not a reconstruction of published PRE entry lists.',
        'prior_race_baseline':'Mean last five available driver finish percentiles, team prior for new drivers; lexical tie breaks.',
        'activated':False}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    summary,folds=evaluate(frame,output,groups=groups)
    stages=stage_checks(frame);stages['delta']=stages.model_mae-stages.baseline_mae
    stages.to_csv(output/'stage_race_metrics.csv',index=False)
    stage_summary=[]
    for stage,part in stages.groupby('stage'):
        ci=bootstrap(part.delta)
        stage_summary.append(dict(stage=stage,races=len(part),baseline_mae=part.baseline_mae.mean(),
            model_mae=part.model_mae.mean(),delta=part.delta.mean(),ci_low=ci[0],ci_high=ci[1]))
    pd.DataFrame(stage_summary).to_csv(output/'stage_summary.csv',index=False)
    stages.groupby(['Year','stage'],as_index=False)[['model_mae','baseline_mae','delta']].mean().to_csv(output/'stage_year_scores.csv',index=False)
    result={**protocol,'inspected_races':[list(k) for k in sorted(set(zip(frame.Year,frame.Round)))],
            'fresh_validation_races':[],'summary':summary.to_dict('records'),'stage_summary':stage_summary,
            'artifact_sha256':{p.name:digest(p) for p in output.glob('*.csv')}}
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(summary.round(5).to_string(index=False));print(pd.DataFrame(stage_summary).round(5).to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();run(args.folder,args.output_dir)
