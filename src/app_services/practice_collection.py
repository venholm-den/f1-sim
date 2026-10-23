"""Timestamped current-weekend practice evidence for prospective trials only."""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.features import _prepare_laps
from src.long_run_pace import estimate_long_run_pace
from src.prediction_data import KEYS, PRACTICE_FEATURES
from src.stage_ensemble_benchmark import digest, dump_new
from src.venues import venue_for_context


def utc(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None or pd.isna(stamp):
        raise ValueError('Practice timestamps must be timezone aware.')
    return stamp.tz_convert('UTC')


def load_session(root, context, code):
    import fastf1
    cache = Path(root)/'data/cache'
    cache.mkdir(parents=True, exist_ok=True)
    enable_cache(str(cache))
    session = fastf1.get_session(int(context['year']), int(context['round']), code)
    # FastF1 only establishes its UTC timing origin when telemetry is loaded.
    # Keep it in the normal cache; the trial packet stores lap evidence only.
    session.load(laps=True, telemetry=True, weather=False, messages=True)
    return session


def session_evidence(session, context, code, cutoff):
    """Require observed completion, actual UTC bounds and the physical venue."""
    event = session.event
    if int(event.get('RoundNumber', -1)) != int(context['round']) or event.get('EventName') != context['event']:
        raise ValueError('Practice event identity differs from the forecast.')
    actual_venue = venue_for_context({k:v for k,v in context.items() if k!='venue'}, session=session)
    expected = context.get('venue', {})
    if expected.get('circuit_id') and actual_venue.get('circuit_id') != expected['circuit_id']:
        raise ValueError('Practice physical circuit differs from the forecast.')
    if expected.get('layout_id') and actual_venue.get('layout_id') != expected['layout_id']:
        raise ValueError('Practice layout differs from the forecast.')
    # FastF1 t0_date is a naive UTC origin in some versions.
    origin = pd.to_datetime(session.t0_date, utc=True, errors='coerce')
    status = session.session_status
    if (pd.isna(origin) or status.empty or not {'Time','Status'}.issubset(status)
            or not status.Status.eq('Finished').any() or status.Status.iloc[-1] not in {'Finalised','Ends'}):
        raise ValueError('Practice lacks terminal completion and UTC evidence.')
    end = origin + pd.to_timedelta(status.Time, errors='coerce').max()
    if pd.isna(end) or end > cutoff or end.year != int(context['year']):
        raise ValueError('Practice ends after the source forecast cutoff or has an invalid year.')
    q_dates = [pd.to_datetime(event.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
               for i in range(1,6) if event.get(f'Session{i}')=='Qualifying']
    q_start = min((d for d in q_dates if pd.notna(d)), default=pd.NaT)
    if pd.isna(q_start):
        raise ValueError('Qualifying UTC schedule is unavailable.')
    laps = pd.DataFrame(session.laps).copy()
    required = {'Driver','LapTime','LapStartTime','Time','IsAccurate','TrackStatus',
                'Compound','Stint','LapNumber','TyreLife','PitInTime','PitOutTime','Deleted'}
    if laps.empty or not required.issubset(laps):
        raise ValueError('Practice lacks accurate lap, tyre or crossing evidence.')
    if laps.Driver.isna().any() or laps.duplicated(['Driver','LapNumber']).any():
        raise ValueError('Practice has missing identities or duplicate driver laps.')
    lap_end = origin + pd.to_timedelta(laps.Time, errors='coerce')
    lap_start = origin + pd.to_timedelta(laps.LapStartTime, errors='coerce')
    laps = laps[lap_end.le(end) & lap_end.le(cutoff) & lap_start.le(lap_end)].copy()
    laps['LapStartUtc'] = lap_start.loc[laps.index].astype(str)
    laps['LapEndUtc'] = lap_end.loc[laps.index].astype(str)
    laps['LapStartTimeSeconds'] = pd.to_timedelta(laps.LapStartTime).dt.total_seconds()
    for name,value in zip(KEYS,[int(context['year']),int(context['round']),context['event']]):
        laps[name] = value
    laps['Session'] = code
    clean = _prepare_laps(laps)
    clean = clean[clean.CleanPushLap & clean.TrackStatus.astype(str).isin(['1','1.0']) & clean.Deleted.notna()]
    pace = estimate_long_run_pace(clean)
    eligible = end < q_start
    rows = []
    if eligible:
        for row in pace.to_dict('records'):
            driver = row.pop('Driver')
            rows.append({**dict(zip(KEYS,[int(context['year']),int(context['round']),context['event']])),
                         'DriverCode':driver, **{f'{code.lower()}_{k}':v for k,v in row.items()}})
    return laps, rows, {'session':code, 'ended_at_utc':end.isoformat(),
        'qualifying_start_utc':q_start.isoformat(), 'eligible_pre_qualifying':eligible,
        'reason':None if eligible else 'Practice after qualifying excluded from trained practice component',
        'lap_rows':len(laps), 'clean_laps':len(clean), 'matched_drivers':len(pace),
        'timing_origin_utc':origin.isoformat(),
        'venue':actual_venue}


def collect_weekend(root, context, *, now=None, loader=None):
    root = Path(root)
    started = utc(now or datetime.now(timezone.utc))
    cutoff = utc(context['data_cutoff_utc'])
    if cutoff > started:
        raise ValueError('Cannot collect practice before the forecast cutoff.')
    if started >= utc(context['race_start_utc']):
        return {'status':'ineligible', 'reason':'race_started'}
    codes = [s for s in ('FP1','FP2','FP3') if s in context.get('available_sessions',[])]
    if context['session']=='PRE':
        codes = []
    # A successfully captured source-cutoff packet is immutable and reused.
    key = f"{int(context['year'])}_{int(context['round']):02}_{context['session']}"
    parser_sources = {n:digest(Path(__file__).parents[1]/n) for n in ('features.py','long_run_pace.py')}
    for path in sorted((root/'outputs/practice_collection'/key).glob('*/manifest.json')):
        saved = json.loads(path.read_text(encoding='utf-8'))
        if (saved['context']==context and saved['status']=='completed'
                and saved['source_sha256']==parser_sources and saved['service_sha256']==digest(Path(__file__))):
            if utc(saved['captured_at_utc'])>started:
                raise ValueError('Cannot reuse practice evidence from a future capture.')
            for name,sha in saved['files'].items():
                if name not in {'practice_features.csv','laps.csv','collection.json'} or digest(path.parent/name)!=sha:
                    raise ValueError('Saved practice evidence checksum differs.')
            return {'status':'completed','folder':str(path.parent),'reused':True, **saved}
    folder = root/'outputs/practice_collection'/key/(started.strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    frames, rows, reports = [], [], []
    for code in codes:
        try:
            session = (loader or load_session)(root,context,code)
            laps, features, evidence = session_evidence(session,context,code,cutoff)
            frames.append(laps); rows.extend(features); reports.append({'status':'completed',**evidence})
        except Exception as exc:
            reports.append({'session':code,'status':'unavailable','error_type':type(exc).__name__,'reason':str(exc)[:250]})
    features = pd.DataFrame(rows)
    columns = KEYS+['DriverCode']+PRACTICE_FEATURES
    if features.empty:
        features = pd.DataFrame(columns=columns)
    else:
        features = features.groupby(KEYS+['DriverCode'],as_index=False).first().reindex(columns=columns)
    features.to_csv(folder/'practice_features.csv',index=False)
    pd.concat(frames,ignore_index=True).to_csv(folder/'laps.csv',index=False) if frames else pd.DataFrame(columns=['Driver']).to_csv(folder/'laps.csv',index=False)
    finished = utc(now or datetime.now(timezone.utc))
    status = 'completed' if all(r['status']=='completed' for r in reports) else 'awaiting_data'
    if finished >= utc(context['race_start_utc']):
        status = 'ineligible'
    dump_new(folder/'collection.json',{'sessions':reports,'feature_drivers':len(features),
        'eligible_sessions':codes,'fuel_load_observed':False,'telemetry_loaded_for_utc_origin':bool(codes)})
    manifest = {'schema_version':1,'status':status,'context':context,
        'started_at_utc':started.isoformat(),'captured_at_utc':finished.isoformat(),
        'files':{n:digest(folder/n) for n in ('practice_features.csv','laps.csv','collection.json')},
        'source_sha256':parser_sources,
        'service_sha256':digest(Path(__file__)), 'activated':False}
    dump_new(folder/'manifest.json',manifest)
    return {**manifest,'folder':str(folder),'reused':False}
