"""Offline exploratory factor analysis; never trains or activates production models.

All committed session pointers are inventoried and their files verified. Car
telemetry is reduced to session summaries; position streams are integrity-only.
Whole later seasons are diagnostic folds, not new prospective confirmation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.long_run_pace import estimate_long_run_pace
from src.qualifying_features import build_qualifying_features
from src.result_status import classify_result_status, retirement_label

BASE_TABLES = {'laps', 'results', 'weather', 'weather_samples', 'track_status',
               'race_control', 'race_control_messages', 'session_status', 'strategy'}
KEYS = ['Year', 'Round', 'DriverCode']
TELEMETRY_COLUMNS = ['Year','Round','Session','DriverNumber','samples','moving_samples',
                     'telemetry_speed_p95','telemetry_full_throttle','telemetry_braking','telemetry_drs']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def truth(series):
    return series.astype(str).str.lower().isin(['true', '1', '1.0'])


def clean_laps(laps):
    frame = laps.copy()
    for col in ('IsAccurate',):
        if col not in frame:
            return frame.iloc[:0]
        frame = frame[truth(frame[col])]
    for col in ('Deleted', 'PitIn', 'PitOut'):
        if col in frame:
            frame = frame[~truth(frame[col])]
    if 'TrackStatus' not in frame:
        return frame.iloc[:0]
    frame = frame[frame.TrackStatus.astype(str).str.removesuffix('.0').eq('1')]
    return frame[pd.to_numeric(frame.LapTimeSeconds, errors='coerce').gt(0)]


def session_end(laps):
    if not {'LapStartUtc', 'LapTimeSeconds'}.issubset(laps):
        return pd.NaT
    return (pd.to_datetime(laps.LapStartUtc, utc=True, errors='coerce')
            + pd.to_timedelta(laps.LapTimeSeconds, unit='s')).max()


def utc_bounds(session):
    """Conservative UTC envelope from archived laps and race-control messages.

    Older Q exports omit absolute lap times but preserve UTC control messages,
    the same alternate evidence used by the repository's enrichment pipeline.
    This is retrospective ordering evidence, not attested publication timing.
    """
    starts, ends, sources = [], [], []
    laps = session['laps']
    if 'LapStartUtc' in laps:
        times = pd.to_datetime(laps.LapStartUtc,utc=True,errors='coerce').dropna()
        if not times.empty:
            starts.append(times.min());ends.append(session_end(laps));sources.append('lap_utc')
    messages = session.get('race_control_messages',pd.DataFrame())
    if 'Time' in messages:
        times = pd.to_datetime(messages.Time,utc=True,errors='coerce').dropna()
        if not times.empty:
            starts.append(times.min());ends.append(times.max());sources.append('control_message_utc')
    return (min(starts) if starts else pd.NaT,
            max(t for t in ends if not pd.isna(t)) if ends else pd.NaT,
            '+'.join(sources) or 'unavailable')


def load_archive(workspace, output, telemetry_cache=None):
    archive = Path(workspace)/'data/historical_library'
    sessions, inventory, telemetry, exclusions = {}, [], [], []
    files, lap_count, telemetry_rows = 0, 0, 0
    pointers = sorted(archive.glob('*/detailed/*/session.json'))
    cached_inventory, cached_telemetry = {}, pd.DataFrame()
    if telemetry_cache is not None:
        cache = Path(telemetry_cache)
        manifest = json.loads((cache/'telemetry_cache.json').read_text(encoding='utf-8'))
        if manifest['parser_version'] != 1 or any(digest(cache/name) != sha for name,sha in manifest['files'].items()):
            raise ValueError('Telemetry summary cache checksum/version mismatch.')
        cached_inventory = pd.read_csv(cache/'session_inventory.csv').set_index('manifest').to_dict('index')
        cached_telemetry = pd.read_csv(cache/'telemetry_summary.csv',dtype={'DriverNumber':str})
    for index, pointer in enumerate(pointers):
        meta = json.loads(pointer.read_text(encoding='utf-8'))
        row = {k: meta.get(k) for k in ('year', 'round', 'event', 'session', 'status')}
        row.update(manifest=str(pointer), manifest_sha256=digest(pointer), files=0, bytes=0)
        tables, session_telemetry = {}, []
        cached = cached_inventory.get(str(pointer), {})
        reuse = bool(cached.get('verified')) and cached.get('manifest_sha256') == row['manifest_sha256']
        if reuse:
            cached_rows = cached_telemetry[(cached_telemetry.Year==meta['year'])
                & (cached_telemetry.Round==meta['round']) & (cached_telemetry.Session==meta['session'])]
            expected = {info['table'][4:] for info in meta['files'].values() if info.get('table','').startswith('car_')}
            reuse = set(cached_rows.DriverNumber) == expected and not cached_rows.DriverNumber.duplicated().any()
            if reuse:
                session_telemetry = cached_rows.to_dict('records')
                telemetry_rows += int(cached_rows.get('samples',pd.Series(dtype=float)).sum())
        try:
            if meta.get('status') != 'complete':
                raise ValueError('Session pointer is incomplete.')
            for name, info in meta.get('files', {}).items():
                path = (pointer.parent/name).resolve()
                if (not path.is_relative_to(pointer.parent.resolve()) or not path.is_file()
                        or path.stat().st_size != info['bytes'] or digest(path) != info['sha256']):
                    raise ValueError(f'File integrity failure: {name}')
                row['files'] += 1; row['bytes'] += info['bytes']; files += 1
                kind = info.get('table', '')
                if kind in BASE_TABLES:
                    if kind in tables:
                        raise ValueError('Duplicate base table: '+kind)
                    tables[kind] = pd.read_csv(path)
                elif kind.startswith('car_'):
                    if reuse:
                        continue  # Raw files still passed their original checksum above.
                    data = pd.read_csv(path, usecols=lambda c: c in {'Speed', 'Throttle', 'Brake', 'DRS'})
                    telemetry_rows += len(data)
                    moving = data[pd.to_numeric(data.Speed, errors='coerce').gt(50)]
                    summary = {'Year': meta['year'], 'Round': meta['round'], 'Session': meta['session'],
                               'DriverNumber': str(kind[4:]), 'samples': len(data), 'moving_samples': len(moving)}
                    if not moving.empty:
                        summary.update(telemetry_speed_p95=moving.Speed.quantile(.95),
                            telemetry_full_throttle=truth(moving.Throttle.ge(98)).mean(),
                            telemetry_braking=truth(moving.Brake).mean(),
                            telemetry_drs=pd.to_numeric(moving.DRS, errors='coerce').isin([10, 12, 14]).mean())
                    session_telemetry.append(summary)
            if 'laps' not in tables or 'results' not in tables:
                raise ValueError('Missing base laps or classification.')
            lap_count += len(tables['laps'])
            key = meta['year'], meta['round'], meta['session']
            if key in sessions:
                raise ValueError('Duplicate session identity.')
            sessions[key] = {'meta': meta, **tables}
            telemetry.extend(session_telemetry)
            row['laps'] = len(tables['laps']); row['verified'] = True
        except (ValueError, OSError, KeyError) as exc:
            exclusions.append({**row, 'reason': str(exc)})
            row['verified'] = False
        inventory.append(row)
        if index % 25 == 0:
            print(f'Archive {index+1}/{len(pointers)}; {files} verified files; {telemetry_rows:,} car samples', flush=True)
    pd.DataFrame(inventory).to_csv(output/'session_inventory.csv', index=False)
    pd.DataFrame(telemetry,columns=TELEMETRY_COLUMNS).to_csv(output/'telemetry_summary.csv', index=False)
    (output/'telemetry_cache.json').write_text(json.dumps({'parser_version':1,'files':{
        name:digest(output/name) for name in ('session_inventory.csv','telemetry_summary.csv')}},indent=2),encoding='utf-8')
    return sessions, pd.DataFrame(telemetry,columns=TELEMETRY_COLUMNS), inventory, exclusions, lap_count, telemetry_rows


def relative_race_pace(laps):
    clean = clean_laps(laps)
    clean = clean[clean.Compound.isin(['SOFT', 'MEDIUM', 'HARD'])].dropna(subset=['LapNumber','TyreLife']).copy()
    clean['bucket'] = (clean.LapNumber/5).astype(int)
    clean['age_bucket'] = (clean.TyreLife/5).floordiv(1)
    groups = clean.groupby(['Compound', 'bucket', 'age_bucket'])
    peers = groups.Driver.transform('nunique')
    clean['residual'] = clean.LapTimeSeconds/groups.LapTimeSeconds.transform('median') - 1
    clean = clean[peers.ge(3)]
    return (clean.groupby('Driver').residual.median()*100).to_dict()


def build_features(sessions, telemetry):
    frames, race_context, exclusions = [], [], []
    driver_history, team_history, layout_history = defaultdict(list), defaultdict(list), defaultdict(list)
    for year, round_ in sorted({(y, r) for y, r, s in sessions if s == 'R'}):
        race = sessions[year, round_, 'R']; results = race['results'].copy()
        meta = race['meta']; event = meta['event']; n = len(results)
        for col in ('Position', 'GridPosition'):
            results[col] = pd.to_numeric(results[col], errors='coerce')
        results['DriverCode'] = results.Abbreviation.astype(str)
        results['actual_dnf'] = results.Status.map(retirement_label)
        results['outcome_class'] = results.Status.map(classify_result_status)
        eligible_race = meta.get('venue', {}).get('race_quality', {}).get('training_eligible', True)
        # The aborted 2021 Belgian classification is not a normal raced outcome.
        eligible_race = eligible_race and not (year == 2021 and event == 'Belgian Grand Prix')
        weather = race.get('weather', pd.DataFrame())
        wet = None if weather.empty else weather.iloc[0].get('rainfall_flag')
        track = race.get('track_status', pd.DataFrame())
        codes = set(track.Status.astype(str).str.removesuffix('.0')) if 'Status' in track else set()
        race_context.append(dict(Year=year, Round=round_, Event=event, drivers=n, race_eligible=eligible_race,
            actual_wet=None if wet is None or pd.isna(wet) else str(wet).lower()=='true',
            actual_sc='4' in codes, actual_vsc=bool(codes & {'6','7'}), actual_red='5' in codes,
            track_status_available=not track.empty, grid_mae=(results.Position-results.GridPosition).abs().mean()))
        q = sessions.get((year, round_, 'Q'))
        layout = meta.get('venue', {}).get('layout_id') or 'unknown:'+event
        previous_layout = layout_history[layout]
        row_frame = None
        if q is not None and eligible_race:
            qfeatures = build_qualifying_features(q['laps'], q['results'])
            if not qfeatures.empty:
                frame = results.merge(qfeatures.drop(columns=['Event', 'Year', 'Round']), on='DriverCode', how='inner', validate='one_to_one')
                frame = frame[~frame.outcome_class.isin(['did_not_start', 'disqualified']) & frame.Position.notna()].copy()
                frame['field_size'] = n; frame['q_percentile'] = (frame.q_rank-.5)/n
                frame['finish_residual'] = frame.Position-frame.q_rank
                frame['Year'] = year; frame['Round'] = round_; frame['Event'] = event
                frame['actual_finish'] = frame.Position
                q_start,_,q_timing_source = utc_bounds(q)
                frame['timing_q_source'] = q_timing_source
                for col in ['q_best_lap', 'q_best_s1', 'q_best_s2', 'q_best_s3']:
                    frame[col+'_pct'] = 100*(frame[col]/frame[col].median()-1)
                frame['q_speed_relative'] = frame.q_best_speed_trap-frame.q_best_speed_trap.median()
                qw = q.get('weather', pd.DataFrame())
                for col in ('air_temp_avg','track_temp_avg','humidity_avg','wind_speed_avg'):
                    frame['q_'+col] = qw.iloc[0].get(col, np.nan) if not qw.empty else np.nan
                frame['q_wet'] = float(truth(qw.rainfall_flag).any()) if 'rainfall_flag' in qw else np.nan
                for code in ('FP1','FP2','FP3'):
                    practice = sessions.get((year, round_, code))
                    if practice is None:
                        continue
                    _,practice_end,method = utc_bounds(practice)
                    available = not pd.isna(q_start) and not pd.isna(practice_end) and practice_end < q_start
                    frame['timing_'+code.lower()+'_source'] = method
                    frame['timing_'+code.lower()+'_eligible'] = available
                    if not available:
                        continue
                    laps = clean_laps(practice['laps'])
                    pace = estimate_long_run_pace(laps)
                    for source, suffix in [('long_run_relative_pace','pace'), ('long_run_laps','laps'), ('long_run_confidence','confidence')]:
                        frame[code.lower()+'_'+suffix] = frame.DriverCode.map(pace.set_index('Driver')[source])
                    frame[code.lower()+'_pace_rank'] = frame[code.lower()+'_pace'].rank(pct=True)
                    frame[code.lower()+'_clean_laps'] = frame.DriverCode.map(laps.groupby('Driver').size())
                qt = telemetry[(telemetry.Year==year)&(telemetry.Round==round_)&(telemetry.Session=='Q')].copy()
                if not qt.empty:
                    qt.DriverNumber = qt.DriverNumber.astype(str).str.removesuffix('.0')
                    lookup = qt.set_index('DriverNumber')
                    numbers = frame.DriverNumber.astype(str).str.removesuffix('.0')
                    for col in ('telemetry_speed_p95','telemetry_full_throttle','telemetry_braking','telemetry_drs'):
                        frame[col] = numbers.map(lookup[col])
                        frame[col] -= frame[col].median()
                for i, row in frame.iterrows():
                    history = driver_history[row.DriverCode][-5:]
                    current_team = team_history[year, str(row.TeamName)]
                    current_driver = [h for h in driver_history[row.DriverCode] if h['year']==year]
                    frame.loc[i, 'prior_driver_form'] = np.mean([h['finish_pct'] for h in history]) if history else np.nan
                    frame.loc[i, 'prior_driver_grid_residual'] = np.mean([h['grid_residual'] for h in history]) if history else np.nan
                    frame.loc[i, 'prior_race_pace'] = np.nanmean([h['pace'] for h in history]) if history and any(np.isfinite(h['pace']) for h in history) else np.nan
                    for prefix, hs in [('driver',current_driver), ('team', current_team)]:
                        known = [h['dnf'] for h in hs if np.isfinite(h['dnf'])]
                        frame.loc[i,'prior_'+prefix+'_dnf'] = (1+sum(known))/(10+len(known))
                        frame.loc[i,'prior_'+prefix+'_starts'] = len(known)
                    frame.loc[i,'prior_team_form'] = (sum(h['finish_pct'] for h in current_team[-10:])+5*.5)/(5+len(current_team[-10:]))
                frame['prior_layout_sc'] = (1+sum(h['sc'] for h in previous_layout))/(4+len(previous_layout))
                frame['prior_layout_grid_error'] = np.mean([h['error'] for h in previous_layout]) if previous_layout else np.nan
                frames.append(frame)
                row_frame = frame
            else:
                exclusions.append(dict(year=year,round=round_,event=event,reason='Incomplete official Q rank contract'))
        else:
            exclusions.append(dict(year=year,round=round_,event=event,reason='No Q session or abnormal race'))
        # Update histories AFTER assembling the target's predictors.
        if eligible_race:
            pace = relative_race_pace(race['laps'])
            for row in results.itertuples():
                if row.outcome_class in ('did_not_start','disqualified') or not np.isfinite(row.Position):
                    continue
                item = dict(year=year, round=round_, finish_pct=(row.Position-.5)/n,
                            grid_residual=(row.Position-row.GridPosition)/n if row.GridPosition>0 else np.nan,
                            dnf=row.actual_dnf, pace=pace.get(row.DriverCode,np.nan))
                driver_history[row.DriverCode].append(item)
                team_history[year,str(row.TeamName)].append(item)
            error=(results.Position-results.GridPosition).abs().mean()
            if np.isfinite(error) and not track.empty:
                layout_history[layout].append(dict(sc='4' in codes,error=error))
    if not frames:
        raise ValueError('No eligible race/qualifying pairs.')
    return pd.concat(frames,ignore_index=True), pd.DataFrame(race_context), exclusions


def bootstrap(values, repetitions=3000):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return [None, None]
    means = np.random.default_rng(20261024).choice(values,(repetitions,len(values)),replace=True).mean(axis=1)
    return [float(x) for x in np.quantile(means,[.025,.975])]


def families(frame):
    names = {'qualifying_timing':[c for c in frame if c.endswith('_pct') and c.startswith('q_')]+['q_speed_relative'],
             'practice':[c for c in frame if c.startswith(('fp1_','fp2_','fp3_'))],
             'recent_form':['prior_driver_form','prior_driver_grid_residual','prior_race_pace','prior_team_form'],
             'reliability':['prior_driver_dnf','prior_team_dnf','prior_driver_starts','prior_team_starts'],
             'circuit_history':['prior_layout_sc','prior_layout_grid_error'],
             'q_weather':[c for c in frame if c.startswith('q_') and c.endswith(('_avg','_wet'))],
             'q_telemetry':[c for c in frame if c.startswith('telemetry_')]}
    return {k:[c for c in v if c in frame and frame[c].notna().any()] for k,v in names.items()}


def evaluate(frame, output, groups=None):
    groups = families(frame) if groups is None else groups
    forbidden = {'actual_finish','actual_dnf','Position','GridPosition','Points','finish_residual','outcome_class'}
    if forbidden & {column for columns in groups.values() for column in columns}:
        raise ValueError('Outcome or later race-grid columns cannot be predictors.')
    variants = {'anchor_only':[], **groups, 'all_factors':list(dict.fromkeys(c for cols in groups.values() for c in cols))}
    rows, predictions, coefficients = [], [], []
    for year in (2024,2025,2026):
        train, test = frame[frame.Year<year],frame[frame.Year==year]
        if train.empty or test.empty:
            continue
        base=['q_rank','q_percentile','field_size']
        for name,extra in variants.items():
            cols=list(dict.fromkeys(base+extra))
            model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),Ridge(alpha=100.))
            weights=1/train.groupby(['Year','Round']).DriverCode.transform('size')
            weights=weights/weights.mean()
            model.fit(train[cols],train.finish_residual,ridge__sample_weight=weights)
            residual=model.predict(test[cols])
            predicted=np.clip(test.q_rank.to_numpy()+residual,1,test.field_size.to_numpy())
            known_train=train[train.actual_dnf.notna()]
            known_test=test[test.actual_dnf.notna()]
            clf=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(C=.1,max_iter=2000))
            clf.fit(known_train[cols],known_train.actual_dnf)
            probabilities=pd.Series(clf.predict_proba(known_test[cols])[:,1],index=known_test.index)
            part=test[KEYS+['Event','actual_finish','actual_dnf','q_rank']].copy()
            part['prediction']=predicted;part['dnf_probability']=probabilities.reindex(test.index)
            part['dnf_prior']=known_train.actual_dnf.mean();part['variant']=name
            predictions.append(part)
            for (y,r),race in part.groupby(['Year','Round']):
                known=race.actual_dnf.notna()
                mae=(race.prediction-race.actual_finish).abs().mean()
                anchor=(race.q_rank-race.actual_finish).abs().mean()
                brier=((race.loc[known,'dnf_probability']-race.loc[known,'actual_dnf'])**2).mean()
                prior=((race.loc[known,'dnf_prior']-race.loc[known,'actual_dnf'])**2).mean()
                rows.append(dict(Year=y,Round=r,variant=name,drivers=len(race),mae=mae,q_mae=anchor,
                                 delta=mae-anchor,dnf_brier=brier,dnf_prior_brier=prior,dnf_delta=brier-prior))
            for col,coef in zip(model.named_steps['simpleimputer'].get_feature_names_out(cols),model.named_steps['ridge'].coef_):
                coefficients.append(dict(test_year=year,variant=name,feature=col,standardized_coefficient=coef))
            print(f'Scored {year} {name}: {len(test)} driver outcomes',flush=True)
    metrics=pd.DataFrame(rows)
    summaries=[]
    for name,part in metrics.groupby('variant'):
        summaries.append(dict(variant=name,races=len(part),mae=part.mae.mean(),q_mae=part.q_mae.mean(),
            delta=part.delta.mean(),delta_ci_low=bootstrap(part.delta)[0],delta_ci_high=bootstrap(part.delta)[1],
            dnf_brier=part.dnf_brier.mean(),dnf_prior_brier=part.dnf_prior_brier.mean(),
            dnf_delta=part.dnf_delta.mean(),dnf_delta_ci_low=bootstrap(part.dnf_delta)[0],dnf_delta_ci_high=bootstrap(part.dnf_delta)[1]))
    metrics.to_csv(output/'race_metrics.csv',index=False)
    pd.concat(predictions).to_csv(output/'predictions.csv',index=False)
    pd.DataFrame(coefficients).to_csv(output/'coefficients.csv',index=False)
    summary=pd.DataFrame(summaries).sort_values('mae');summary.to_csv(output/'factor_family_scores.csv',index=False)
    fold=metrics.groupby(['Year','variant'],as_index=False)[['mae','q_mae','delta','dnf_brier','dnf_prior_brier','dnf_delta']].mean()
    fold.to_csv(output/'year_scores.csv',index=False)
    correlation=[]
    for feature in list(dict.fromkeys(c for cols in groups.values() for c in cols))+['q_rank']:
        values=[];residuals=[]
        for _,race in frame.groupby(['Year','Round']):
            part=race[[feature,'actual_finish','finish_residual']].dropna()
            if len(part)>=8 and part[feature].nunique()>1:
                values.append(part[feature].corr(part.actual_finish,method='spearman'))
                residuals.append(part[feature].corr(part.finish_residual,method='spearman'))
        correlation.append(dict(feature=feature,drivers=int(frame[feature].notna().sum()),races=len(values),
            mean_within_race_finish_correlation=float(np.nanmean(values)) if values else None,
            mean_within_race_residual_correlation=float(np.nanmean(residuals)) if residuals else None))
    pd.DataFrame(correlation).to_csv(output/'factor_correlations.csv',index=False)
    return summary,fold


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--telemetry-cache',type=Path,
                        help='Reuse checksum-verified summaries; every raw file is still reverified.')
    args=parser.parse_args();output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    protocol={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':digest(Path(__file__)),
        'hypotheses':['Q timing beyond rank','pre-Q practice long runs','earlier driver/team form and pace',
                      'earlier reliability','earlier circuit results','Q observed weather','Q car telemetry'],
        'folds':'Train earlier seasons; score 2024, 2025, 2026 independently. No hyperparameter search.',
        'settings':{'ridge_alpha':100.,'logistic_C':.1,'bootstrap_race_draws':3000},
        'interpretation':'Exploratory historical diagnostics only; multiple comparisons; not causal or prospective evidence.',
        'raw_position_telemetry':'Integrity verification only; not fitted as a predictive signal.',
        'activated':False}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    sessions,telemetry,inventory,failures,laps,car_rows=load_archive(args.workspace,output,args.telemetry_cache)
    frame,context,exclusions=build_features(sessions,telemetry)
    frame.to_csv(output/'features.csv',index=False);context.to_csv(output/'race_context.csv',index=False)
    summary,fold=evaluate(frame,output)
    coverage=pd.DataFrame({'feature':frame.columns,'observed_rows':frame.notna().sum().to_numpy(),
                           'coverage':frame.notna().mean().to_numpy()})
    coverage.to_csv(output/'feature_coverage.csv',index=False)
    keys=sorted({(y,r) for y,r,s in sessions if s=='R'})
    report={**protocol,'inspected_races':[list(k) for k in keys], 'fresh_validation_races':[],
        'sessions':len(sessions),'archive_lap_rows':laps,'car_telemetry_rows':car_rows,
        'race_sessions':sum(s=='R' for y,r,s in sessions),'feature_races':frame.groupby(['Year','Round']).ngroups,
        'feature_rows':len(frame),'verified_files':sum(i['files'] for i in inventory),
        'verified_bytes':sum(i['bytes'] for i in inventory),'integrity_failures':failures,
        'model_exclusions':exclusions,'summary':summary.to_dict('records'),
        'artifact_sha256':{p.name:digest(p) for p in output.glob('*.csv')}}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['sessions','archive_lap_rows','car_telemetry_rows','feature_races','feature_rows','summary']},indent=2))


if __name__=='__main__':
    main()
