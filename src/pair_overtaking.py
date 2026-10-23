"""Per-pair pass probability for the agent engine (opt-in candidate).

The established agent rule scales one logistic curve by a single track factor,
``passability = 1 - overtaking_difficulty``. This candidate instead fits the
per-lap probability that a close follower is ahead at the next timing line:

    logit p = intercept + pace * pace_delta + tyre_age * age_delta
              + compound * softness_delta + track * (difficulty - 0.55)

Deltas are follower advantage: leader minus follower clean race pace (s/lap),
leader minus follower tyre age (laps) and follower minus leader compound
softness (HARD 0, MEDIUM 1, SOFT 2). Difficulty is the calibrated
OvertakingDifficulty from track_calibration_v1.

Fitted on 2026 races only, so DRS (dropped for 2026) is never assumed; the
electrical aid available to both cars is absorbed into the coefficients.
Inspired by the per-pair overtaking model in F1-StratLab (Apache-2.0); no code
is adapted from it.

Observation unit: adjacent cars on the same lap number whose line gap at the
start of the lap is within ``MAX_GAP_SECONDS``, both on green, non-pit laps.
A pass is a reversed crossing order at the end of that lap. Within-lap passes
that are reversed again before the line are missed, so this is a timing proxy
for real overtakes, not an official count.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = 'pair_overtaking_v1'
DEFAULT_PATH = Path('data/pair_overtaking/pair_overtaking_v1.json')
FEATURES = ('pace_delta', 'tyre_age_delta', 'softness_delta', 'track')
COEFFICIENTS = ('intercept', 'pace', 'tyre_age', 'compound', 'track')
SOFTNESS = {'HARD': 0, 'MEDIUM': 1, 'SOFT': 2}
DIFFICULTY_CENTRE = .55
MAX_GAP_SECONDS = 1.0
# Ridge on non-intercept terms: weak, so it only matters for collinear tracks.
RIDGE = 1.0


def _flag(series):
    return series.astype(str).str.strip().str.lower().isin(['true', '1', '1.0'])


def clean_race_pace(laps: pd.DataFrame) -> pd.Series:
    """Median green, non-pit lap after lap 1 for each driver in one race."""
    green = laps.TrackStatus.astype(str).str.strip().str.removesuffix('.0').eq('1')
    ok = green & ~_flag(laps.PitIn) & ~_flag(laps.PitOut) & laps.LapNumber.gt(1)
    times = laps[ok].groupby('Driver').LapTimeSeconds
    pace = times.median()
    # Fewer than five clean laps is too noisy to rank a car.
    return pace[times.count() >= 5]


def pair_laps(laps: pd.DataFrame, difficulty: float) -> pd.DataFrame:
    """Close adjacent pair-laps from one race, with features and outcome."""
    d = laps.copy()
    for col in ('LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds', 'TyreLife'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=['LapNumber', 'LapStartTimeSeconds', 'LapTimeSeconds'])
    d = d[d.LapTimeSeconds > 0].drop_duplicates(['Driver', 'LapNumber'], keep=False)
    pace = clean_race_pace(d)
    d['eligible'] = (d.TrackStatus.astype(str).str.strip().str.removesuffix('.0').eq('1')
                     & ~_flag(d.PitIn) & ~_flag(d.PitOut) & d.LapNumber.ge(2)
                     & d.Driver.isin(pace.index) & d.TyreLife.notna()
                     & d.Compound.isin(list(SOFTNESS)))
    d['end'] = d.LapStartTimeSeconds + d.LapTimeSeconds
    rows = []
    for _, lap in d.groupby('LapNumber'):
        lap = lap.sort_values('LapStartTimeSeconds')
        for (_, front), (_, back) in zip(lap.iterrows(), lap.iloc[1:].iterrows()):
            gap = back.LapStartTimeSeconds - front.LapStartTimeSeconds
            if not (front.eligible and back.eligible and 0 < gap <= MAX_GAP_SECONDS):
                continue
            rows.append({'leader': front.Driver, 'follower': back.Driver, 'lap': int(front.LapNumber),
                         'gap_seconds': gap,
                         'pace_delta': pace[front.Driver] - pace[back.Driver],
                         'tyre_age_delta': front.TyreLife - back.TyreLife,
                         'softness_delta': SOFTNESS[back.Compound] - SOFTNESS[front.Compound],
                         'track': difficulty - DIFFICULTY_CENTRE,
                         'passed': int(back.end < front.end)})
    return pd.DataFrame(rows, columns=['leader', 'follower', 'lap', 'gap_seconds', *FEATURES, 'passed'])


def build_dataset(laps: pd.DataFrame, calibration: pd.DataFrame) -> pd.DataFrame:
    """Pair-laps for every race in a packet's laps table (race sessions only)."""
    lookup = calibration.set_index(['CircuitId', 'LayoutId']).OvertakingDifficulty
    frames = []
    for (year, round_), race in laps[laps.Session.eq('R')].groupby(['Year', 'Round']):
        key = (race.source_circuit_id.iloc[0], race.source_layout_id.iloc[0])
        difficulty = float(lookup.get(key, DIFFICULTY_CENTRE))
        frame = pair_laps(race, difficulty)
        frames.append(frame.assign(year=int(year), round=int(round_), event=race.Event.iloc[0],
                                   difficulty=difficulty))
    return pd.concat(frames, ignore_index=True)


def _design(data, columns):
    return np.column_stack([np.ones(len(data)), *(data[c].to_numpy(float) for c in columns)])


def fit_logistic(data: pd.DataFrame, columns=FEATURES, ridge=RIDGE, iterations=50):
    """Ridge-penalised logistic regression by Newton steps; returns (beta, se)."""
    x = _design(data, columns)
    y = data.passed.to_numpy(float)
    penalty = np.diag([0.] + [ridge] * len(columns))
    beta = np.zeros(x.shape[1])
    beta[0] = np.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6))
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-x @ beta))
        hessian = x.T @ (x * (p * (1 - p))[:, None]) + penalty
        step = np.linalg.solve(hessian, x.T @ (y - p) - penalty @ beta)
        beta += step
        if np.abs(step).max() < 1e-9:
            break
    p = 1 / (1 + np.exp(-x @ beta))
    covariance = np.linalg.inv(x.T @ (x * (p * (1 - p))[:, None]) + penalty)
    return beta, np.sqrt(np.diag(covariance))


def predict(data: pd.DataFrame, beta, columns=FEATURES) -> np.ndarray:
    return 1 / (1 + np.exp(-_design(data, columns) @ np.asarray(beta, float)))


def fit_model(data: pd.DataFrame) -> dict:
    beta, se = fit_logistic(data)
    return {'version': VERSION, **dict(zip(COEFFICIENTS, map(float, beta))),
            'standard_errors': dict(zip(COEFFICIENTS, map(float, se))),
            'difficulty_centre': DIFFICULTY_CENTRE, 'max_gap_seconds': MAX_GAP_SECONDS,
            'pair_laps': int(len(data)), 'passes': int(data.passed.sum()),
            'races': sorted({f'{y}-{r:02d}' for y, r in zip(data['year'], data['round'])})}


def validate_model(model: dict) -> dict:
    if not isinstance(model, dict) or any(k not in model for k in COEFFICIENTS):
        raise ValueError('Pair pass model needs intercept, pace, tyre_age, compound and track.')
    values = np.array([model[k] for k in COEFFICIENTS], dtype=float)
    if not np.isfinite(values).all() or np.abs(values).max() > 50:
        raise ValueError('Pair pass model coefficients must be finite and modest.')
    difficulty = float(model.get('track_difficulty', DIFFICULTY_CENTRE))
    if not 0 <= difficulty <= 1:
        raise ValueError('Pair pass track difficulty must be between 0 and 1.')
    return model


def load_model(path: str | Path = DEFAULT_PATH) -> dict:
    from src.app_services.app_paths import resource_path
    return validate_model(json.loads(Path(resource_path(path)).read_text(encoding='utf-8')))


def lap_probability(model, pace_delta, tyre_age_delta, softness_delta):
    """Vectorised per-lap pass probability for follower-minus-leader arrays."""
    track = float(model.get('track_difficulty', DIFFICULTY_CENTRE)) - float(
        model.get('difficulty_centre', DIFFICULTY_CENTRE))
    logit = (model['intercept'] + model['pace'] * pace_delta + model['tyre_age'] * tyre_age_delta
             + model['compound'] * softness_delta + model['track'] * track)
    return 1 / (1 + np.exp(-np.clip(logit, -50, 50)))
