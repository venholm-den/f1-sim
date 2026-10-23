"""Small, chronological forecast blends. Experimental; never a live override.

Each component describes a complete field. One set of nonnegative weights is
used for the whole race, preserving probability totals and nested events.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

COMPONENTS = ('simulation', 'qualifying', 'recent_form', 'practice')
FORECAST_COLUMNS = ('avg_finish', 'win_chance', 'podium_chance', 'points_chance')
STAGES = ('PRE', 'FP2', 'Q')
MIN_RACES = 6
RANK_NOISE = 3.0  # Declared sensitivity assumption, not a fitted lap-time error.
MIN_COVERAGE = 0.60


@dataclass
class Episode:
    key: tuple[int, int]
    stage: str
    event: str
    drivers: list[str]
    components: np.ndarray  # component, driver, forecast column
    actual: np.ndarray
    dnf: np.ndarray
    actual_dnf: np.ndarray
    availability: dict


def validate_forecast(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(FORECAST_COLUMNS) or len(values) < 3:
        raise ValueError('A complete field with forecast columns is required.')
    n = len(values)
    if not np.isfinite(values).all() or not ((values[:, 0] >= 1) & (values[:, 0] <= n)).all():
        raise ValueError('Invalid forecast values.')
    probabilities = values[:, 1:]
    if not ((probabilities >= -1e-8) & (probabilities <= 1 + 1e-8)).all():
        raise ValueError('Probabilities must lie between zero and one.')
    if (np.diff(probabilities, axis=1) < -1e-8).any():
        raise ValueError('Win, podium and top-10 probabilities must be nested.')
    if not np.allclose(values.sum(axis=0), [n*(n+1)/2, 1, 3, min(10, n)], atol=1e-5):
        raise ValueError('Forecast does not describe a complete field.')
    return values


def ranking_forecast(score, dnf, *, n_sims=20_000, seed=314159):
    """Rank full simulated fields, including the established DNF probabilities."""
    score, dnf = np.asarray(score, float), np.asarray(dnf, float)
    if not np.isfinite(score).all() or not np.isfinite(dnf).all() or not ((dnf >= 0) & (dnf <= 1)).all():
        raise ValueError('Ranking scores and retirement probabilities must be finite.')
    if n_sims < 100 or len(score) != len(dnf):
        raise ValueError('Use at least 100 complete-field simulations.')
    rng = np.random.default_rng(seed)
    times = score + rng.normal(0, RANK_NOISE, (n_sims, len(score)))
    times += (rng.random(times.shape) < dnf) * len(score) * 2
    ranks = times.argsort(axis=1, kind='stable').argsort(axis=1, kind='stable') + 1
    return validate_forecast(np.column_stack([ranks.mean(axis=0),
        (ranks <= 1).mean(axis=0), (ranks <= 3).mean(axis=0), (ranks <= 10).mean(axis=0)]))


def _rank_scores(values):
    """Equal unknown values share a midfield score; no alphabetical tie advantage."""
    return pd.Series(values).rank(method='average').to_numpy(float)


def build_components(frame, key, stage, results, practice, *, n_sims=20_000):
    """Only explicit predictor columns enter the calculation; target outcomes ignored.

    Results supply recent form from up to five earlier races in the same season.
    Practice inputs must come from the timestamp-filtered enrichment exporter.
    Its FP2 values precede Q, also excluding post-Q sprint practice in FP2 replay.
    """
    if stage not in STAGES or frame.Driver.isna().any() or frame.Driver.duplicated().any():
        raise ValueError('Unsupported stage or duplicate driver identifiers.')
    if results.duplicated(['Year','Round','DriverCode']).any():
        raise ValueError('Duplicate historical race/driver results.')
    frame = frame.sort_values('Driver').reset_index(drop=True)
    base = validate_forecast(frame[list(FORECAST_COLUMNS)].to_numpy(float))
    drivers = frame.Driver.tolist()
    dnf = pd.to_numeric(frame.dnf_chance, errors='raise').to_numpy(float)
    if not np.isfinite(dnf).all() or not ((dnf >= 0) & (dnf <= 1)).all():
        raise ValueError('Invalid retirement probabilities.')
    output = [base]
    availability = {'simulation': {'available': True, 'coverage': 1.0}}

    def add(name, scores, observed, reason, extra=None, eligible=True):
        coverage = float(np.mean(observed))
        available = coverage >= MIN_COVERAGE and bool(eligible)
        output.append(ranking_forecast(scores, dnf, n_sims=n_sims) if available else base.copy())
        availability[name] = {'available': available, 'coverage': coverage,
            'fallback': None if available else 'simulation', 'reason': reason, **(extra or {})}

    grid = pd.to_numeric(frame.get('grid_position', pd.Series(np.nan, index=frame.index)), errors='coerce')
    source = frame.get('grid_source', pd.Series('', index=frame.index))
    # An estimated practice/PRE grid is not qualifying evidence.
    observed = grid.between(1, len(frame)) & source.eq('actual_session_results') & (stage == 'Q')
    valid_grid = observed.all() and sorted(grid) == list(range(1,len(frame)+1))
    add('qualifying', grid.fillna((len(frame)+1)/2).to_numpy(),
        observed, 'Requires a complete Q classification; later grid penalties excluded',
        {'classification':grid.astype(int).tolist() if valid_grid else None}, eligible=valid_grid)

    previous = results[results.Year.eq(key[0]) & results.Round.lt(key[1])].copy()
    rounds = sorted(previous.Round.unique())[-5:]
    previous = previous[previous.Round.isin(rounds)]
    # Do not silently call an obsolete archive "recent".
    if rounds and key[1] - max(rounds) > 3:
        previous = previous.iloc[:0]
    means = previous.groupby('DriverCode').Position.mean() if not previous.empty else pd.Series(dtype=float)
    recent = frame.Driver.map(means)
    add('recent_form', _rank_scores(recent.fillna((len(frame)+1)/2)), recent.notna(),
        'Mean classified finish in up to five earlier same-season archived races',
        {'source_races': [[key[0], int(r)] for r in rounds] if not previous.empty else []})

    practice_rows = practice[practice.Year.eq(key[0]) & practice.Round.eq(key[1])]
    if practice_rows.DriverCode.duplicated().any():
        raise ValueError('Duplicate practice driver identities.')
    values = practice_rows.set_index('DriverCode')
    gap = frame.Driver.map(values.fp2_long_run_relative_pace)
    confidence = frame.Driver.map(values.fp2_long_run_confidence)
    observed = gap.notna() & confidence.gt(0) & (stage != 'PRE')
    neutral = gap[observed].median() if observed.any() else 0.0
    add('practice', _rank_scores(gap.where(observed).fillna(neutral)), observed,
        'Timestamp-filtered FP2 matched long runs; unknown drivers use median pace')
    return drivers, np.stack(output), dnf, availability


def fit_weights(episodes, stage, before):
    history = sorted([e for e in episodes if e.stage == stage and e.key < before], key=lambda e:e.key)
    if len({e.key for e in history}) != len(history):
        raise ValueError('One independent episode per race and stage is required.')
    counts = {name: sum(e.availability[name]['available'] for e in history) for name in COMPONENTS}
    allowed = [i for i, name in enumerate(COMPONENTS) if i == 0 or counts[name] >= MIN_RACES]
    prior = np.zeros(len(COMPONENTS)); prior[0] = 1.0
    metadata = {'train_races': [list(e.key) for e in history], 'component_races': counts,
                'status': 'insufficient_history', 'weights': dict(zip(COMPONENTS, prior.tolist()))}
    if len(history) < MIN_RACES or len(allowed) == 1:
        return prior, metadata

    def objective(w):
        losses = []
        for e in history:
            p = np.einsum('c,cdf->df', w, e.components)
            losses.append(np.abs(p[:, 0] - e.actual).mean() +
                          ((p[:, 3] - (e.actual <= 10))**2).mean())
        return float(np.mean(losses) + 0.10 * np.square(w-prior).sum())

    result = minimize(objective, prior, method='SLSQP',
        bounds=[(0, 1) if i in allowed else (0, 0) for i in range(len(COMPONENTS))],
        constraints=[{'type':'eq', 'fun':lambda w: w.sum()-1}],
        options={'maxiter':500, 'ftol':1e-9})
    if not result.success or not np.isfinite(result.fun):
        metadata['status'] = 'optimizer_failed_use_simulation'
        return prior, metadata
    weights = np.maximum(result.x, 0); weights /= weights.sum()
    metadata.update(status='fitted', weights=dict(zip(COMPONENTS, weights.tolist())),
                    objective=float(result.fun))
    return weights, metadata


def uniform_forecast(n):
    return np.tile([(n+1)/2, 1/n, 3/n, min(10,n)/n], (n, 1))


def fit_calibration(history, stage, before):
    """Fit only on earlier out-of-sample blends, never fitted training predictions."""
    rows = [row for row in history if row['stage'] == stage and row['key'] < before]
    if len({row['key'] for row in rows}) != len(rows):
        raise ValueError('Repeated seeds are not independent calibration races.')
    metadata = {'calibration_races': [list(row['key']) for row in rows],
                'status': 'insufficient_out_of_sample_history', 'uniform_mass': 0.0}
    if len(rows) < MIN_RACES:
        return 0.0, metadata

    def objective(alpha):
        losses = []
        for row in rows:
            p = (1-alpha)*row['prediction'] + alpha*uniform_forecast(len(row['actual']))
            y = row['actual'][:, None] <= np.array([1, 3, 10])
            losses.append(np.square(p[:, 1:]-y).mean())
        return float(np.mean(losses) + 0.01*alpha*alpha)

    result = minimize_scalar(objective, bounds=(0, .35), method='bounded')
    alpha = float(result.x) if result.success and result.fun < objective(0) else 0.0
    metadata.update(status='fitted', uniform_mass=alpha)
    return alpha, metadata


def blend(components, weights, uniform_mass=0.0):
    weights = np.asarray(weights, float)
    if weights.shape != (len(COMPONENTS),) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(),1):
        raise ValueError('Blend weights must be nonnegative and sum to one.')
    if not np.isfinite(uniform_mass) or not 0 <= uniform_mass <= .35:
        raise ValueError('Invalid calibration mass.')
    p = np.einsum('c,cdf->df', weights, components)
    return validate_forecast((1-uniform_mass)*p + uniform_mass*uniform_forecast(len(p)))


def metrics(prediction, actual, dnf=None, actual_dnf=None):
    output = {'finish_mae': float(np.abs(prediction[:, 0]-actual).mean())}
    for i, name in enumerate(('win_brier','podium_brier','top10_brier'), 1):
        output[name] = float(np.square(prediction[:, i]-(actual <= (1,3,10)[i-1])).mean())
    output['loss'] = output['finish_mae'] + output['top10_brier']
    if dnf is not None and actual_dnf is not None:
        known = np.isfinite(actual_dnf)
        output['dnf_brier'] = float(np.square(dnf[known]-actual_dnf[known]).mean()) if known.any() else None
    return output
