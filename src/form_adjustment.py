"""Experimental form-to-pace adjustment and separate all-cause retirement prior.

No live configuration imports this module. The form candidate maps a strongly
regularised finishing estimate onto the existing field's pace distribution,
then blends a small amount into race pace. Actual grid facts remain unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from src.result_status import classify_result_status, retirement_label

FORM_WEIGHTS = {'PRE': .35, 'FP2': .25, 'Q': .15}
FORM_COLUMNS = ['driver_form','team_form','historical_pace','driver_count','team_count','pace_count']
PACKET_COLUMNS = ['Year','Round','Driver','Team','FieldSize','Position','QPosition','PacePct','Status']


def before(frame, cutoff):
    year, round_ = map(int, cutoff)
    return frame[(frame.Year < year) | (frame.Year.eq(year) & frame.Round.lt(round_))]


def validate_packet(packet):
    if set(PACKET_COLUMNS)-set(packet):
        raise ValueError('History packet lacks required fields.')
    if packet.duplicated(['Year','Round','Driver']).any() or packet[['Driver','Team']].isna().any().any():
        raise ValueError('History identities must be unique and known.')
    for _,race in packet.groupby(['Year','Round']):
        if race.FieldSize.nunique()!=1 or int(race.FieldSize.iloc[0])!=len(race):
            raise ValueError('History field size differs from its roster.')
        if sorted(race.Position)!=list(range(1,len(race)+1)):
            raise ValueError('History requires complete official race positions.')
        q=race.QPosition
        if q.notna().any() and (q.isna().any() or sorted(q)!=list(range(1,len(race)+1))):
            raise ValueError('Qualifying ranks must be a complete permutation or wholly unavailable.')


def summarise_race_pace(laps):
    required={'Driver','IsAccurate','TrackStatus','LapTimeSeconds','LapNumber','TyreLife','Compound'}
    if not required.issubset(laps):
        return {}
    clean=laps.copy()
    clean=clean[clean.IsAccurate.astype(str).str.lower().isin(['true','1','1.0'])]
    clean=clean[clean.TrackStatus.astype(str).str.removesuffix('.0').eq('1')]
    for name in ('Deleted','PitIn','PitOut'):
        if name in clean:
            clean=clean[~clean[name].astype(str).str.lower().isin(['true','1','1.0'])]
    clean=clean[clean.Compound.isin(['SOFT','MEDIUM','HARD'])].dropna(
        subset=['LapTimeSeconds','LapNumber','TyreLife']).copy()
    clean=clean[clean.LapTimeSeconds.gt(0)]
    clean['lap_bucket']=(clean.LapNumber/5).astype(int)
    clean['age_bucket']=(clean.TyreLife/5).floordiv(1)
    group=clean.groupby(['Compound','lap_bucket','age_bucket'])
    clean['gap']=100*(clean.LapTimeSeconds/group.LapTimeSeconds.transform('median')-1)
    clean=clean[group.Driver.transform('nunique').ge(3)]
    return clean.groupby('Driver').gap.median().to_dict()


def packet_from_races(races):
    rows=[];exclusions=[]
    for race in sorted(races,key=lambda r:r.key):
        if race.year==2021 and race.event=='Belgian Grand Prix':
            continue
        result=race.sessions['R'].results
        positions=pd.to_numeric(result.Position,errors='coerce')
        if (result.Abbreviation.isna().any() or result.Abbreviation.duplicated().any()
                or sorted(positions.dropna())!=list(range(1,len(result)+1))):
            exclusions.append(dict(year=race.year,round=race.round,event=race.event,
                                   reason='Incomplete or non-unique official race classification; not imputed.'))
            continue
        pace=summarise_race_pace(race.sessions['R'].laps)
        q=race.sessions.get('Q')
        qpositions={}
        if q is not None and set(q.results.Abbreviation)==set(result.Abbreviation):
            positions=pd.to_numeric(q.results.Position,errors='coerce')
            if sorted(positions.dropna())==list(range(1,len(result)+1)):
                qpositions=dict(zip(q.results.Abbreviation,positions))
        for row in result.itertuples():
            rows.append(dict(Year=race.year,Round=race.round,Driver=str(row.Abbreviation),
                Team=str(row.TeamName),FieldSize=len(result),Position=float(row.Position),
                QPosition=qpositions.get(str(row.Abbreviation),np.nan),
                PacePct=pace.get(str(row.Abbreviation),np.nan),Status=row.Status))
    packet=pd.DataFrame(rows,columns=PACKET_COLUMNS)
    validate_packet(packet)
    packet.attrs['excluded_races']=exclusions
    return packet


def form_inputs(history, roster, cutoff):
    """Target outcomes are never accepted. Team assignment comes from the caller's roster."""
    history=before(history,cutoff).sort_values(['Year','Round','Driver'])
    eligible=history[~history.Status.map(classify_result_status).isin(['did_not_start','disqualified'])].copy()
    eligible['finish_pct']=(eligible.Position-.5)/eligible.FieldSize
    rows=[]
    for row in roster[['Driver','Team']].itertuples(index=False):
        driver=eligible[eligible.Driver.eq(str(row.Driver))].tail(5)
        team=eligible[eligible.Year.eq(int(cutoff[0])) & eligible.Team.eq(str(row.Team))].tail(10)
        pace=driver.PacePct.dropna()
        rows.append(dict(Driver=str(row.Driver),driver_form=driver.finish_pct.mean() if len(driver) else .5,
            team_form=(team.finish_pct.sum()+2.5)/(len(team)+5),
            historical_pace=pace.mean() if len(pace) else 0.,driver_count=len(driver),
            team_count=len(team),pace_count=len(pace)))
    return pd.DataFrame(rows)


def training_table(packet):
    validate_packet(packet)
    parts=[]
    for key,race in packet.groupby(['Year','Round'],sort=True):
        predictors=form_inputs(packet,race,key)
        rows=race.merge(predictors,on='Driver',validate='one_to_one')
        rows['target']=(rows.Position-.5)/rows.FieldSize
        rows['q_percentile']=(rows.QPosition-.5)/rows.FieldSize
        rows=rows[~rows.Status.map(classify_result_status).isin(['did_not_start','disqualified'])]
        parts.append(rows)
    return pd.concat(parts,ignore_index=True)


def fit_form(table,cutoff,stage):
    if stage not in FORM_WEIGHTS:
        raise ValueError('Form adjustment supports PRE, FP2 and Q only.')
    train=before(table,cutoff).copy()
    columns=list(FORM_COLUMNS)
    if stage=='Q':
        train=train[train.q_percentile.notna()]
        columns.append('q_percentile')
    races=train.groupby(['Year','Round']).ngroups
    if races<6 or len(train)<60:
        return {'status':'insufficient_history','races':races,'rows':len(train),'stage':stage}
    x=train[columns].to_numpy(float)
    mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1.
    y=train.target.to_numpy(float)
    if stage=='Q':
        y=y-train.q_percentile.to_numpy(float)
    weights=1/train.groupby(['Year','Round']).Driver.transform('size')
    weights=weights/weights.mean()
    model=Ridge(alpha=100.).fit((x-mean)/scale,y,sample_weight=weights)
    return {'status':'fitted','stage':stage,'races':races,'rows':len(train),'columns':columns,
        'mean':mean.tolist(),'scale':scale.tolist(),'coefficients':model.coef_.tolist(),
        'intercept':float(model.intercept_),'alpha':100.,'cutoff':list(map(int,cutoff)),
        'last_training_race':list(max(zip(train.Year,train.Round)))}


def apply_form(features,history,model,cutoff,stage,*,q_positions=None,weight=None):
    weight=FORM_WEIGHTS[stage] if weight is None else float(weight)
    if not np.isfinite(weight) or not 0<=weight<=.35:
        raise ValueError('Form weight must be finite and between 0 and 0.35.')
    output=features.copy()
    if weight==0 or model['status']!='fitted':
        return output
    if model['stage']!=stage or list(map(int,cutoff))!=model['cutoff']:
        raise ValueError('Form model stage/cutoff differs from this forecast.')
    if tuple(model['last_training_race'])>=tuple(cutoff):
        raise ValueError('Form model includes target or future race outcomes.')
    current=form_inputs(history,output,cutoff).set_index('Driver').loc[output.Driver].copy()
    if stage=='Q':
        if q_positions is None or set(q_positions)!=set(output.Driver) or sorted(q_positions.values())!=list(range(1,len(output)+1)):
            raise ValueError('Form Q requires complete official qualifying ranks, not an estimated or final grid.')
        current['q_percentile']=(output.Driver.map(q_positions).to_numpy(float)-.5)/len(output)
    x=current[model['columns']].to_numpy(float)
    prediction=((x-np.array(model['mean']))/np.array(model['scale']))@np.array(model['coefficients'])+model['intercept']
    if stage=='Q':
        prediction+=current.q_percentile.to_numpy(float)
    prediction=np.clip(prediction,.5/len(output),1-.5/len(output))
    original=pd.to_numeric(output.race_pace_score,errors='raise').to_numpy(float)
    if not np.isfinite(original).all():
        raise ValueError('Form adjustment requires finite race pace.')
    implied=np.interp(prediction,(np.arange(len(output))+.5)/len(output),np.sort(original))
    adjusted=(1-weight)*original+weight*implied
    # Keep long-run minus race pace unchanged, so this does not add another wear path.
    delta=adjusted-original-adjusted.min()
    output['race_pace_score']=original+delta
    for name in ('long_run_pace_score','projected_lap_time'):
        if name in output:
            output[name]=output[name]+delta
    output['form_implied_percentile']=prediction
    output['form_weight']=weight
    output['form_model']='stage_form_v1_experimental'
    return output


def apply_retirement_prior(features,history,cutoff):
    """Beta(1,9), equal driver/team mix; unknown labels do not imply health."""
    earlier=before(history,cutoff)
    earlier=earlier[earlier.Year.eq(int(cutoff[0]))].copy()
    earlier['label']=earlier.Status.map(retirement_label)
    output=features.copy()
    for i,row in output.iterrows():
        driver=earlier[earlier.Driver.eq(str(row.Driver))].label
        team=earlier[earlier.Team.eq(str(row.Team))].label
        driver_rate=(1+driver.sum())/(10+driver.notna().sum())
        team_rate=(1+team.sum())/(10+team.notna().sum())
        raw=.5*(driver_rate+team_rate)
        output.loc[i,'retirement_prior_raw']=raw
        output.loc[i,'reliability_score']=np.clip(raw,.005,.30)
        output.loc[i,'retirement_prior_driver_known']=driver.notna().sum()
        output.loc[i,'retirement_prior_team_known']=team.notna().sum()
        output.loc[i,'retirement_prior_unknown']=driver.isna().sum()
    output['retirement_prior_model']='simple_all_cause_v1_experimental'
    return output
