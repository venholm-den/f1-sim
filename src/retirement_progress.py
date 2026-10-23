"""Conditional retirement distance, fitted only to earlier race observations.

This remains an approximation: surviving cars complete the planned distance;
traffic, lapping, correlated incidents and shortened races are not simulated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.result_status import NONFINISH_CLASSES, classify_result_status

PROGRESS_COLUMNS = [f'retirement_progress_bin_{index}' for index in range(10)]


def attach_retirement_progress(features, recent_races, metadata):
    """A recency-weighted histogram with ten uniform pseudo-observations.

    Only explicitly known retirement outcomes contribute. Completed distance
    uses classification Laps when supplied, else the last timed lap. Without
    lap-time evidence the fallback subtracts one from the last recorded lap
    because that may be an incomplete synthetic FastF1 retirement lap.
    """
    target = int(metadata['year']), int(metadata['round'])
    races = sorted(recent_races, key=lambda item: (int(item[1]['year']), int(item[1]['round'])), reverse=True)
    keys = [(int(meta['year']), int(meta['round'])) for _, meta in races]
    if len(set(keys)) != len(keys) or any(key >= target for key in keys):
        raise ValueError('Retirement timing history must be unique and strictly before the target cutoff.')
    counts = np.ones(10, dtype=float)
    observations = 0
    for age, (session, _) in enumerate(races):
        results = getattr(session, 'results', pd.DataFrame())
        if not {'Abbreviation', 'Status'}.issubset(results):
            continue
        if results.Abbreviation.duplicated().any():
            raise ValueError('Duplicate retirement timing observations.')
        laps = getattr(session, 'laps', pd.DataFrame())
        completed = pd.Series(dtype=float)
        if {'Driver', 'LapNumber', 'LapTime'}.issubset(laps):
            # Require a recorded lap time: generated retirement laps lack one.
            valid = laps.loc[laps.LapTime.notna()]
            completed = pd.to_numeric(valid.LapNumber, errors='coerce').groupby(valid.Driver).max()
        elif {'Driver', 'LapNumber'}.issubset(laps):
            completed = (pd.to_numeric(laps.LapNumber, errors='coerce').groupby(laps.Driver).max() - 1).clip(lower=0)
        distances = pd.to_numeric(results['Laps'], errors='coerce') if 'Laps' in results else results.Abbreviation.map(completed)
        distance = float(distances.max()) if distances.notna().any() else np.nan
        if not np.isfinite(distance) or distance <= 0:
            continue
        for status, value in zip(results.Status, distances):
            if classify_result_status(status) in NONFINISH_CLASSES and pd.notna(value) and 0 <= value <= distance:
                index = min(int(float(value) / distance * 10), 9)
                counts[index] += .5 ** (age / 8.)
                observations += 1
    output = features.copy()
    for column, probability in zip(PROGRESS_COLUMNS, counts / counts.sum()):
        output[column] = probability
    output['retirement_progress_observations'] = observations
    output['retirement_progress_version'] = 'prior_distance_histogram_v1_experimental'
    return output


def sample_completed_laps(features, retired, race_laps, rng):
    """Draw distance conditional on retirement; occurrence is sampled separately."""
    laps = int(round(race_laps))
    if laps < 1:
        raise ValueError('Race distance must be positive.')
    if not set(PROGRESS_COLUMNS).issubset(features):
        raise ValueError('Retirement progress requires prior distance probabilities.')
    probabilities = features[PROGRESS_COLUMNS].to_numpy(dtype=float)
    if (not np.isfinite(probabilities).all() or (probabilities < 0).any()
            or not np.allclose(probabilities.sum(axis=1), 1)):
        raise ValueError('Invalid retirement distance probabilities.')
    draw = rng.random(retired.shape)
    bins = (draw[..., None] > probabilities.cumsum(axis=1)[None, ...]).sum(axis=2).clip(0, 9)
    fraction = (bins + rng.random(retired.shape)) / 10
    return np.where(retired, np.minimum(np.floor(fraction * laps).astype(int), laps - 1), laps)


def distance_order(projected_times, completed_laps):
    """More completed laps first, then projected crossing time, stable on ties."""
    return np.lexsort((np.broadcast_to(np.arange(projected_times.shape[1]), projected_times.shape),
                       projected_times, -completed_laps), axis=1)
