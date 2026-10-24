"""Write a local comparison of the active independent form-shadow cohort."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.app_services.beta import verified_snapshot
from src.app_services.form_shadow import ROOT,read_suite,verify_files,digest,write_new


def report(root):
    root=Path(root);registered=read_suite(root)
    if registered is None:return {'status':'disabled'}
    _,suite,sha=registered;captures=[];rows=[];failures=[]
    for file in sorted((root/ROOT/'captures').glob('*/manifest.json')):
        try:
            manifest=json.loads(file.read_text(encoding='utf-8'))
            if manifest['suite_sha256']!=sha:continue
            verify_files(file.parent,manifest['files'])
            original=verified_snapshot(manifest['source_forecast'])
            if (original['context']!=manifest['context'] or original['category']!='prospective'
                    or digest(Path(manifest['source_forecast'])/'frozen/manifest.json')!=manifest['source_manifest_sha256']):
                raise ValueError('Frozen source changed.')
            c=manifest['context']
            captures.append({'year':c['year'],'round':c['round'],'session':c['session'],
                             'folder':str(file.parent),'runs':manifest['runs']})
            score=file.parent/'score.json'
            if not score.exists():continue
            scored=json.loads(score.read_text(encoding='utf-8'))
            if (scored['manifest_sha256']!=digest(file)
                    or scored['actual_results_sha256']!=digest(Path(scored['official_folder'])/'actual_results.csv')):
                raise ValueError('Scored evidence changed.')
            for arm,values in scored['metrics'].items():
                rows.append({'year':c['year'],'round':c['round'],'session':c['session'],'arm':arm,**values})
        except (ValueError,OSError,KeyError) as exc:
            failures.append({'folder':str(file.parent),'error':str(exc)[:250]})
    keys=[(c['year'],c['round'],c['session']) for c in captures]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate race/stage captures cannot count twice.')
    frame=pd.DataFrame(rows);pairs=[]
    if not frame.empty:
        if frame.duplicated(['year','round','session','arm']).any():raise ValueError('Duplicate scores.')
        for stage,part in frame.groupby('session'):
            control=part[part.arm.eq('legacy')]
            for arm in sorted(set(part.arm)-{'legacy'}):
                pair=part[part.arm.eq(arm)].merge(control,on=['year','round'],suffixes=('_new','_old'),validate='one_to_one')
                reasons=[]
                if len(pair)<6:reasons.append('fewer_than_six_fresh_races')
                gain=float(1-pair.loss_new.mean()/pair.loss_old.mean()) if not pair.empty and pair.loss_old.mean()>0 else None
                if gain is None or gain<.05:reasons.append('loss_gain_below_5_percent')
                delta={}
                for metric in ('finish_mae','win_brier','podium_brier','top10_brier','dnf_brier','rps'):
                    value=pair[metric+'_new'].mean()-pair[metric+'_old'].mean()
                    delta[metric+'_delta']=None if pd.isna(value) else float(value)
                    if metric.endswith('brier') and (pd.isna(value) or value>0):reasons.append(metric+'_missing_or_regressed')
                if stage=='Q':reasons.append('independent_qualifying_order_comparison_required')
                pairs.append({'stage':stage,'arm':arm,'paired_races':len(pair),'loss_improvement':gain,
                    **delta,'passes_existing_fresh_review_gate':not reasons,'reasons':reasons,
                    'activated':False,'promotion_approved':False})
    folder=root/ROOT/'reports'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    payload={'suite_sha256':sha,'stage_arms':suite['stage_arms'],'captures':captures,'race_metrics':rows,
        'comparisons':pairs,'failures':failures,'activated':False,'promotion_approved':False,
        'policy':'Equal weight per unique race/stage. Seeds are not independent observations. '
                 'Risk research screens do not replace the existing live promotion gates.'}
    write_new(folder/'report.json',payload)
    frame.to_csv(folder/'race_metrics.csv',index=False)
    table=pd.DataFrame(pairs).to_html(index=False,border=0) if pairs else '<p>Awaiting independently completed official race scoring.</p>'
    (folder/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Form shadows</title>'
        '<style>body{font:15px/1.6 system-ui;margin:30px}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd}</style>'
        f'<h1>Form and retirement shadows</h1><p>{len(captures)} captured race/stage trials. No live activation.</p>'
        +table+'<p><a href="report.json">Metrics and evidence</a></p>',encoding='utf-8')
    return {'status':'completed','folder':str(folder),'captures':len(captures),
            'scored_race_stages':len(set(zip(frame.year,frame['round'],frame.session))) if not frame.empty else 0,
            'failures':failures,'activated':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    print(json.dumps(report(parser.parse_args().workspace),indent=2))
