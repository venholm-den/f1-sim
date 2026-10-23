"""Practice pace comparisons from sustained, matched stints.

Observed stint trends combine tyre wear, fuel burn and track evolution. They
are not estimates of fuel loads or pure tyre degradation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LONG_RUN_COLUMNS = ['long_run_relative_pace', 'long_run_laps', 'long_run_confidence']


def _robust_stint(group: pd.DataFrame) -> pd.DataFrame:
    x = group['TyreLife'].to_numpy(dtype=float)
    y = group['LapTimeSeconds'].to_numpy(dtype=float)
    dx = x[:, None] - x[None, :]
    dy = y[:, None] - y[None, :]
    valid = np.triu(np.abs(dx) > 0, k=1)
    if valid.sum() == 0:
        return group.iloc[:0]
    trend = float(np.clip(np.median(dy[valid] / dx[valid]), -0.15, 0.30))
    residual = y - trend * x
    median = np.median(residual)
    mad = np.median(np.abs(residual - median))
    keep = np.abs(residual - median) <= max(1.0, 3.0 * 1.4826 * mad)
    output = group.loc[keep].copy()
    # Compare at a common tyre age without pretending to know fuel load.
    output['stint_adjusted_time'] = output['LapTimeSeconds'] - trend * (output['TyreLife'] - 10.0)
    return output


def estimate_long_run_pace(clean_laps: pd.DataFrame, min_laps: int = 5) -> pd.DataFrame:
    columns = ['Driver', *LONG_RUN_COLUMNS]
    required = {'Driver', 'Compound', 'Stint', 'LapNumber', 'TyreLife', 'LapTimeSeconds'}
    if clean_laps.empty or not required.issubset(clean_laps):
        return pd.DataFrame(columns=columns)
    laps = clean_laps.copy()
    laps = laps[laps['Compound'].isin({'SOFT', 'MEDIUM', 'HARD'})].dropna(
        subset=['Stint', 'LapNumber', 'TyreLife', 'LapTimeSeconds']
    )
    if 'LapStartTimeSeconds' in laps:
        times = pd.to_numeric(laps['LapStartTimeSeconds'], errors='coerce')
    elif 'LapStartTime' in laps:
        times = pd.to_timedelta(laps['LapStartTime'], errors='coerce').dt.total_seconds()
    else:
        # Missing session timestamps do not support time-matched comparisons.
        return pd.DataFrame(columns=columns)
    laps['time_bucket'] = (times / 900).floordiv(1)
    laps = laps.dropna(subset=['time_bucket'])
    runs = []
    for _, stint in laps.groupby(['Driver', 'Compound', 'Stint'], sort=False):
        stint = stint.sort_values('LapNumber')
        segment = stint['LapNumber'].diff().gt(1).cumsum()
        for _, continuous in stint.groupby(segment):
            if len(continuous) < min_laps:
                continue
            robust = _robust_stint(continuous)
            if len(robust) >= min_laps:
                runs.append(robust)
    if not runs:
        return pd.DataFrame(columns=columns)
    runs = pd.concat(runs, ignore_index=True)
    # Each driver contributes once to each compound/time comparison. Otherwise
    # a driver with a longer run would dominate its own reference median.
    matched = runs.groupby(['Driver', 'Compound', 'time_bucket'], as_index=False).agg(
        pace=('stint_adjusted_time', 'median'), laps=('LapTimeSeconds', 'size')
    )
    peers = matched.groupby(['Compound', 'time_bucket'])['Driver'].transform('nunique')
    matched = matched[peers >= 2].copy()
    if matched.empty:
        return pd.DataFrame(columns=columns)
    reference = matched.groupby(['Compound', 'time_bucket'])['pace'].transform('median')
    matched['gap'] = matched['pace'] - reference
    output = matched.groupby('Driver', as_index=False).agg(
        long_run_relative_pace=('gap', 'median'), long_run_laps=('laps', 'sum')
    )
    output['long_run_relative_pace'] -= output['long_run_relative_pace'].min()
    # Fuel is unobserved, so even large practice samples remain uncertain.
    output['long_run_confidence'] = (output['long_run_laps'] / 20.0).clip(0.0, 0.65)
    return output[columns]


def attach_long_run_pace(features: pd.DataFrame, clean_laps: pd.DataFrame) -> pd.DataFrame:
    output = features.drop(columns=LONG_RUN_COLUMNS, errors='ignore').merge(
        estimate_long_run_pace(clean_laps), on='Driver', how='left', validate='one_to_one'
    )
    output['long_run_laps'] = pd.to_numeric(output['long_run_laps'], errors='coerce').fillna(0).astype(int)
    output['long_run_confidence'] = pd.to_numeric(output['long_run_confidence'], errors='coerce').fillna(0.0)
    return output
