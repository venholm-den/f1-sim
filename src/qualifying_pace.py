"""Experimental Gaussian partial-pooling model for post-Q race pace.

The response is a clean race pace gap as a percentage of the reference lap.
Driver, team and circuit effects have zero-centred Gaussian priors. This is
not an identified fuel correction: observed race pace still contains traffic,
tyre and operational effects. Nothing in this module activates a live model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.features import build_driver_features
from src.qualifying_features import attach_current_qualifying

VERSION = 'qualifying_partial_pooling_v1'
FACTOR_PREFIX = 'pace_posterior_factor_'


def _context(metadata):
    venue = metadata.get('venue') or {}
    # Event name is an explicit fallback, never a silently guessed circuit.
    return str(venue.get('layout_id') or venue.get('circuit_id') or metadata['event']).casefold()


def _design(frame, levels):
    n = len(frame)
    rank = pd.to_numeric(frame.q_rank, errors='coerce')
    if n < 2 or rank.isna().any() or sorted(rank) != list(range(1, n + 1)):
        raise ValueError('Pace candidate requires complete official qualifying ranks.')
    reference = pd.to_numeric(frame.q_best_lap, errors='coerce').min()
    if not np.isfinite(reference) and 'pace_reference_lap_seconds' in frame:
        reference = pd.to_numeric(frame.pace_reference_lap_seconds, errors='coerce').min()
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError('Pace candidate requires at least one valid qualifying lap.')
    gap = pd.to_numeric(frame.q_gap_to_best, errors='coerce') / reference * 100
    # Missing timing uses rank alone, with a separate missingness indicator.
    columns = [np.ones(n), (rank.to_numpy() - 1) / (n - 1),
               gap.fillna(0).clip(0, 5).to_numpy(), gap.isna().to_numpy(dtype=float)]
    for name in ('Driver', 'Team', 'circuit'):
        for value in levels[name]:
            indicator = frame[name].astype(str).eq(value).to_numpy(dtype=float)
            # Circuit-specific Q-to-race slopes affect relative performance;
            # a common circuit intercept would cancel in field-relative pace.
            columns.append(indicator * ((rank.to_numpy() - 1) / (n - 1) if name == 'circuit' else 1))
    return np.column_stack(columns)


def fit_qualifying_pace(history, metadata):
    """Fit only strictly earlier races with Q and usable dry race laps.

    The likelihood has a declared 0.5 percentage-point observation SD, not a
    hyperparameter selected against inspected holdouts. Older seasons receive
    less weight. Coefficient uncertainty is retained, including covariance.
    """
    target = int(metadata['year']), int(metadata['round'])
    keys = [(int(context['year']), int(context['round'])) for _, _, context in history]
    if len(keys) != len(set(keys)) or any(key >= target for key in keys):
        raise ValueError('Pace training races must be unique and strictly before the target cutoff.')
    rows, responses, weights, used = [], [], [], []
    for q_session, race_session, context in sorted(history, key=lambda item: (item[2]['year'], item[2]['round'])):
        if q_session is None:
            continue
        weather = getattr(race_session, 'weather_data', pd.DataFrame())
        if 'Rainfall' in weather and weather.Rainfall.astype(str).str.lower().isin(['true', '1']).any():
            continue
        race_features = build_driver_features(race_session.laps)
        if len(race_features) < 2 or 'true_pace' not in race_features:
            continue
        reference = pd.to_numeric(race_features.true_pace, errors='coerce').min()
        if not np.isfinite(reference) or reference <= 0:
            continue
        roster = q_session.results[['Abbreviation', 'TeamName']].rename(
            columns={'Abbreviation': 'Driver', 'TeamName': 'Team'})
        q = attach_current_qualifying(roster, q_session,
                                     {**context, 'session': 'Q'})
        q['circuit'] = _context(context)
        q['pace_reference_lap_seconds'] = reference
        try:
            _design(q, {'Driver': [], 'Team': [], 'circuit': []})
        except (ValueError, AttributeError):
            continue
        response = q.Driver.map(pd.to_numeric(race_features.set_index('Driver').relative_pace,
                                             errors='coerce')).to_numpy() / reference * 100
        valid = np.isfinite(response) & (response >= 0) & (response <= 5)
        if valid.sum() < 2:
            continue
        rows.append(q)
        responses.extend(response)
        age_weight = .5 ** (max(0, target[0] - int(context['year'])) / 2)
        weights.extend(np.where(valid, age_weight, 0))
        used.append([int(context['year']), int(context['round'])])
    if not rows:
        raise ValueError('No eligible earlier Q/race pairs for pace training.')
    frame = pd.concat(rows, ignore_index=True)
    levels = {name: sorted(frame[name].astype(str).unique()) for name in ('Driver', 'Team', 'circuit')}
    # Rank must be normalised inside its own race, not across the concatenation.
    x = np.vstack([_design(row, levels) for row in rows])
    y = np.nan_to_num(np.asarray(responses))
    weight = np.asarray(weights) / .5 ** 2
    prior_mean = np.zeros(x.shape[1]); prior_mean[1:3] = [1., .25]
    prior_sd = np.r_[1., 1., .5, .5,
                     np.full(len(levels['Driver']), .25),
                     np.full(len(levels['Team']), .5), np.full(len(levels['circuit']), .25)]
    precision = np.diag(1 / prior_sd ** 2)
    covariance = np.linalg.solve(precision + x.T @ (weight[:, None] * x), np.eye(x.shape[1]))
    mean = covariance @ (precision @ prior_mean + x.T @ (weight * y))
    return {'version': VERSION, 'target': list(target), 'training_races': used,
            'observations': int(np.count_nonzero(weight)), 'levels': levels,
            'mean': mean.tolist(), 'covariance': covariance.tolist(),
            'observation_sd_pct': .5, 'activated': False}


def apply_qualifying_pace(features, model, metadata):
    if metadata.get('session') != 'Q':
        raise ValueError('Qualifying pace is available only after Q.')
    target = [int(metadata['year']), int(metadata['round'])]
    if model.get('version') != VERSION or model.get('target') != target:
        raise ValueError('Pace artifact version/target does not match this forecast.')
    if any(tuple(key) >= tuple(target) for key in model['training_races']):
        raise ValueError('Pace artifact contains a race at or after the cutoff.')
    output = features.copy()
    output['circuit'] = _context(metadata)
    q_reference = pd.to_numeric(output.q_best_lap, errors='coerce').min()
    if np.isfinite(q_reference):
        reference = q_reference
        reference_source = 'verified_Q_timing'
    else:
        reference = pd.to_numeric(output.projected_lap_time - output.race_pace_score, errors='coerce').median()
        reference_source = 'existing_model_base_lap_estimate_missing_Q_timing'
    output['pace_reference_lap_seconds'] = reference
    output['pace_reference_source'] = reference_source
    x = _design(output, model['levels'])
    mean = x @ np.asarray(model['mean']) * reference / 100
    covariance = np.asarray(model['covariance'])
    factor = x @ np.linalg.cholesky((covariance + covariance.T) / 2) * reference / 100
    # An unseen group draws from its population prior instead of receiving
    # unjustified certainty at zero. Members of the same new team share a draw.
    unknown_factors = []
    for name, sd in [('Driver', .25), ('Team', .5), ('circuit', .25)]:
        for value in sorted(set(output[name].astype(str)) - set(model['levels'][name])):
            indicator = output[name].astype(str).eq(value).to_numpy(dtype=float)
            if name == 'circuit':
                indicator *= (output.q_rank.to_numpy() - 1) / (len(output) - 1)
            unknown_factors.append(indicator * sd * reference / 100)
    if unknown_factors:
        factor = np.column_stack([factor, *unknown_factors])
    old = output.race_pace_score.copy()
    output['race_pace_score'] = mean - mean.min()
    output['long_run_pace_score'] = output.long_run_pace_score - old + output.race_pace_score
    output['projected_lap_time'] = output.get('projected_lap_time', reference + old) - old + output.race_pace_score
    output = pd.concat([output, pd.DataFrame(factor, index=output.index,
        columns=[FACTOR_PREFIX + str(i) for i in range(factor.shape[1])])], axis=1)
    output['pace_posterior_sd_seconds'] = np.sqrt((factor ** 2).sum(axis=1))
    output['pace_observation_sd_seconds'] = float(model['observation_sd_pct']) * reference / 100
    output['race_pace_blend_version'] = VERSION + '_experimental'
    output['pace_training_races'] = len(model['training_races'])
    return output


def load_qualifying_pace(path):
    model = json.loads(Path(path).read_text(encoding='utf-8'))
    root = Path(__file__).resolve().parents[1]
    hashes = model.get('source_sha256', {})
    if 'src/qualifying_pace.py' not in hashes or any(
            hashlib.sha256((root / name).read_bytes()).hexdigest() != digest for name, digest in hashes.items()):
        raise ValueError('Pace artifact source provenance is missing or stale; refit into a new artifact.')
    return model


def sample_pace(features, n_sims, seed):
    """Shared coefficient draws retain team/driver/circuit covariance."""
    columns = sorted((c for c in features if c.startswith(FACTOR_PREFIX)),
                     key=lambda c: int(c.removeprefix(FACTOR_PREFIX)))
    if not columns:
        raise ValueError('Missing pace posterior factors.')
    factor = features[columns].to_numpy(dtype=float)
    if not np.isfinite(factor).all():
        raise ValueError('Non-finite pace posterior.')
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6181]))
    samples = features.race_pace_score.to_numpy()[None, :] + rng.normal(size=(n_sims, len(columns))) @ factor.T
    observation_sd = features.pace_observation_sd_seconds.to_numpy(dtype=float)
    if not np.isfinite(observation_sd).all() or (observation_sd <= 0).any():
        raise ValueError('Invalid predictive pace observation variance.')
    samples += rng.normal(size=(n_sims, len(features))) * observation_sd
    return samples - samples.min(axis=1, keepdims=True)
