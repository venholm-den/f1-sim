"""One qualifying feature contract for archived training and current inference."""
from __future__ import annotations

import numpy as np
import pandas as pd

QUALIFYING_CONTRACT = 'official_q_classification_v1'
QUALIFYING_COLUMNS = ['q_rank', 'q_gap_to_best', 'q_best_lap', 'q_best_s1',
                      'q_best_s2', 'q_best_s3', 'q_best_speed_trap']
KEYS = ['Year', 'Round', 'Event']


def build_qualifying_features(laps: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Anchor on a complete Q classification, never fastest-lap or Sunday grid rank.

    Timing predictors are fastest valid laps/sectors over the whole Q session.
    They describe observed one-lap performance, not segment-adjusted race pace.
    An entrant without valid timing retains their official rank and missing times.
    """
    columns = KEYS + ['DriverCode', *QUALIFYING_COLUMNS]
    required = {*KEYS, 'Session', 'Abbreviation', 'Position'}
    if results.empty or not required.issubset(results):
        return pd.DataFrame(columns=columns)
    q = results.loc[results.Session.eq('Q')].copy()
    q['q_rank'] = pd.to_numeric(q.Position, errors='coerce')
    q = q.rename(columns={'Abbreviation': 'DriverCode'})
    if q.duplicated(KEYS + ['DriverCode']).any():
        raise ValueError('Duplicate qualifying classifications; select one archive version.')
    complete = []
    for _, group in q.groupby(KEYS, dropna=False):
        ranks = group.q_rank
        if ranks.notna().all() and sorted(ranks) == list(range(1, len(group) + 1)):
            complete.append(group[KEYS + ['DriverCode', 'q_rank']])
    if not complete:
        return pd.DataFrame(columns=columns)
    q = pd.concat(complete, ignore_index=True)
    required_laps = {*KEYS, 'Session', 'Driver'}
    if laps.empty or not required_laps.issubset(laps):
        return q.reindex(columns=columns)
    clean = laps.loc[laps.Session.eq('Q')].copy()
    for name in ('CleanPushLap', 'IsAccurate'):
        if name in clean:
            clean = clean.loc[clean[name].astype(str).str.lower().isin(['true', '1'])]
    if 'Deleted' in clean:
        clean = clean.loc[clean.Deleted.astype(str).str.lower().isin(['false', '0'])]
    for name in ('PitInTime', 'PitOutTime'):
        if name in clean:
            clean = clean.loc[clean[name].isna()]
    for name in ('PitIn', 'PitOut'):
        if name in clean:
            clean = clean.loc[clean[name].astype(str).str.lower().isin(['false', '0'])]
    if 'TrackStatus' in clean:
        clean = clean.loc[~clean.TrackStatus.astype(str).str.contains('[24567]', regex=True)]
    for source, target in [('LapTime', 'LapTimeSeconds'), ('Sector1Time', 'Sector1Seconds'),
                           ('Sector2Time', 'Sector2Seconds'), ('Sector3Time', 'Sector3Seconds')]:
        if target not in clean and source in clean:
            clean[target] = pd.to_timedelta(clean[source], errors='coerce').dt.total_seconds()
    if 'LapTimeSeconds' not in clean:
        return q.reindex(columns=columns)
    clean['LapTimeSeconds'] = pd.to_numeric(clean.LapTimeSeconds, errors='coerce')
    clean = clean.loc[np.isfinite(clean.LapTimeSeconds) & clean.LapTimeSeconds.gt(0)]
    aggregations = {'q_best_lap': ('LapTimeSeconds', 'min')}
    for source, target in [('Sector1Seconds', 'q_best_s1'), ('Sector2Seconds', 'q_best_s2'),
                           ('Sector3Seconds', 'q_best_s3'), ('SpeedST', 'q_best_speed_trap')]:
        if source in clean:
            clean[source] = pd.to_numeric(clean[source], errors='coerce').replace([np.inf, -np.inf], np.nan)
            aggregations[target] = (source, 'max' if source == 'SpeedST' else 'min')
    timing = clean.groupby(KEYS + ['Driver'], as_index=False).agg(**aggregations)
    timing = timing.rename(columns={'Driver': 'DriverCode'})
    q = q.merge(timing, on=KEYS + ['DriverCode'], how='left', validate='one_to_one')
    q['q_gap_to_best'] = q.q_best_lap - q.groupby(KEYS).q_best_lap.transform('min')
    return q.reindex(columns=columns)


def attach_current_qualifying(features: pd.DataFrame, session, metadata: dict) -> pd.DataFrame:
    """Attach raw Q evidence before any historical calibration or grid penalties."""
    output = features.drop(columns=QUALIFYING_COLUMNS, errors='ignore').copy()
    if metadata.get('session') != 'Q' or session is None:
        return output
    context = {'Year': metadata['year'], 'Round': metadata['round'], 'Event': metadata['event'], 'Session': 'Q'}
    laps = pd.DataFrame(getattr(session, 'laps', pd.DataFrame())).assign(**context)
    results = pd.DataFrame(getattr(session, 'results', pd.DataFrame())).assign(**context)
    q = build_qualifying_features(laps, results)
    output = output.merge(q.drop(columns=KEYS), left_on='Driver', right_on='DriverCode',
                          how='left', validate='one_to_one').drop(columns='DriverCode')
    output['qualifying_feature_contract'] = QUALIFYING_CONTRACT
    return output
