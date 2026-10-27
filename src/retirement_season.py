"""Experimental all-cause retirement risk from this season's real outcomes.

Shrinkage is set from the data rather than declared: each level (team, driver)
is shrunk toward the season's field rate by a beta-binomial method-of-moments
estimate of how much its rates really differ. When retirements are spread
evenly, as in 2022-2025, that strength is large and every driver gets close to
the field rate. When a few cars fail far more often, as in 2026, it is small
and their own record dominates. Earlier seasons only set the starting field
rate, because reliability resets with new cars.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.result_status import retirement_outcome
from src.retirement_evidence import apply_outcome_evidence

VERSION = 'season_outcomes_v2_experimental'
# Declared starting values, not fitted: the field rate before any earlier
# season is cached, and how many entries (about three races) it counts for.
FALLBACK_FIELD_RATE = 0.13
FIELD_PRIOR_ENTRIES = 60.0
PRIOR_SEASONS = 2
# Bounds on the estimated shrinkage strength, in race entries. The upper bound
# is effectively "pool everyone"; the lower bound stops one race deciding a rate.
MIN_STRENGTH, MAX_STRENGTH = 2.0, 400.0
# Too few units or entries make the overdispersion estimate meaningless.
MIN_UNITS, MIN_ENTRIES = 3, 40
TEAM_WEIGHT = 0.5
# The engine's established 30% retirement cap is far below 2026 reality, so
# this model declares its own ceiling for the aggregate engine to honour.
PROBABILITY_CAP = 0.75


def _observations(recent_races, target):
    rows, keys = [], set()
    for session, meta in recent_races:
        key = int(meta['year']), int(meta['round'])
        if key >= target or key in keys:
            raise ValueError('Retirement history must contain unique races strictly before the target cutoff.')
        keys.add(key)
        results = getattr(session, 'results', pd.DataFrame())
        if not {'Abbreviation', 'TeamName'}.issubset(results):
            continue
        results = apply_outcome_evidence(results, meta)
        if results.Abbreviation.duplicated().any():
            raise ValueError('Retirement history has duplicate driver/race observations.')
        for row in results.itertuples():
            label = retirement_outcome(row)
            rows.append({'year': key[0], 'Driver': str(row.Abbreviation),
                         'Team': str(row.TeamName).strip().casefold(), 'label': label})
    return pd.DataFrame(rows, columns=['year', 'Driver', 'Team', 'label'])


def shrinkage_strength(events, entries, field_rate) -> float:
    """Beta-binomial method of moments: prior entries implied by real spread."""
    events, entries = np.asarray(events, float), np.asarray(entries, float)
    observed = entries > 0
    if observed.sum() < MIN_UNITS or entries.sum() < MIN_ENTRIES or not 0 < field_rate < 1:
        return MAX_STRENGTH
    rates, weights = events[observed] / entries[observed], entries[observed]
    spread = float(np.sum(weights * (rates - field_rate) ** 2) / weights.sum())
    sampling = field_rate * (1 - field_rate) * float(np.mean(1 / entries[observed]))
    between = spread - sampling
    if between <= 1e-6:
        return MAX_STRENGTH
    return float(np.clip(field_rate * (1 - field_rate) / between - 1, MIN_STRENGTH, MAX_STRENGTH))


def apply_season_retirement_risk(features, recent_races, metadata):
    target = int(metadata['year']), int(metadata['round'])
    history = _observations(recent_races, target)
    known = history[history.label.notna()]
    current = known[known.year.eq(target[0])]
    earlier = known[known.year.between(target[0] - PRIOR_SEASONS, target[0] - 1)]
    long_run = float(earlier.label.mean()) if len(earlier) else FALLBACK_FIELD_RATE
    field = float((current.label.sum() + long_run * FIELD_PRIOR_ENTRIES)
                  / (len(current) + FIELD_PRIOR_ENTRIES))
    output = features.copy()
    levels = {}
    for level, column, keys in [('team', 'Team', output.Team.astype(str).str.strip().str.casefold()),
                                ('driver', 'Driver', output.Driver.astype(str))]:
        counts = current.groupby(column).label.agg(['sum', 'count'])
        strength = shrinkage_strength(counts['sum'], counts['count'], field)
        events = keys.map(counts['sum']).fillna(0.0)
        entries = keys.map(counts['count']).fillna(0.0)
        levels[level] = (events + strength * field) / (entries + strength)
        output[f'retirement_{level}_prob'] = levels[level].to_numpy()
        output[f'retirement_{level}_shrinkage_entries'] = strength
        output[f'retirement_{level}_season_starts'] = entries.to_numpy()
        output[f'retirement_{level}_season_retirements'] = events.to_numpy()
    probability = (TEAM_WEIGHT * levels['team'] + (1 - TEAM_WEIGHT) * levels['driver']).clip(.005, PROBABILITY_CAP)
    output['dnf_prob'] = probability.to_numpy()
    output['reliability_score'] = output['dnf_prob']
    output['retirement_probability_cap'] = PROBABILITY_CAP
    output['retirement_field_prob'] = field
    output['retirement_long_run_prob'] = long_run
    output['retirement_season_observations'] = len(current)
    output['retirement_model_version'] = VERSION
    return output


GRID_VERSION = 'season_grid_outcomes_v1_experimental'
# Declared prior on the grid slope, in log-odds from pole to the last slot.
# 2022-2025 front rows retired about 5% of the time and the back rows about
# 25%, roughly 1.8 log-odds; the prior is rounded down and kept loose so each
# window's own earlier seasons decide it.
GRID_SLOPE_PRIOR, GRID_SLOPE_PRIOR_SD = 1.5, 0.75
GRID_FIT_MIN_ENTRIES = 100


def _grid_fraction(grid, field_size):
    """Grid slot scaled to 0 (pole) .. 1 (last); pit-lane starts count as last."""
    grid = pd.to_numeric(pd.Series(grid), errors='coerce').to_numpy(dtype=float)
    grid = np.where(~np.isfinite(grid) | (grid < 1), field_size, grid)
    return (np.clip(grid, 1, field_size) - 1) / max(field_size - 1, 1)


def fit_grid_slope(x, y):
    """Penalised logistic slope of retirement on grid fraction (Newton steps)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(y) < GRID_FIT_MIN_ENTRIES or y.min() == y.max():
        return GRID_SLOPE_PRIOR
    beta = np.array([np.log(y.mean() / (1 - y.mean())) - GRID_SLOPE_PRIOR / 2, GRID_SLOPE_PRIOR])
    design = np.column_stack([np.ones_like(x), x])
    penalty = np.diag([0.0, 1 / GRID_SLOPE_PRIOR_SD ** 2])
    for _ in range(25):
        p = 1 / (1 + np.exp(-design @ beta))
        gradient = design.T @ (y - p) - penalty @ (beta - [0.0, GRID_SLOPE_PRIOR])
        hessian = design.T @ (design * (p * (1 - p))[:, None]) + penalty
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.abs(step).max() < 1e-8:
            break
    return float(beta[1])


def _grid_multiplier(x, slope):
    """Relative risk at grid fraction x, averaging 1 over an evenly spread field."""
    slots = np.linspace(0, 1, 21)
    return np.exp(slope * np.asarray(x, float)) / np.exp(slope * slots).mean()


def _grid_observations(recent_races, target):
    rows = []
    for session, meta in recent_races:
        key = int(meta['year']), int(meta['round'])
        if key >= target:
            raise ValueError('Retirement history must contain unique races strictly before the target cutoff.')
        results = getattr(session, 'results', pd.DataFrame())
        if not {'Abbreviation', 'TeamName'}.issubset(results):
            continue
        results = apply_outcome_evidence(results, meta)
        grid = results['GridPosition'] if 'GridPosition' in results else pd.Series(np.nan, index=results.index)
        fraction = _grid_fraction(grid.to_numpy(), len(results))
        for row, x in zip(results.itertuples(), fraction):
            rows.append({'year': key[0], 'Driver': str(row.Abbreviation),
                         'Team': str(row.TeamName).strip().casefold(), 'label': retirement_outcome(row),
                         'grid_fraction': x})
    return pd.DataFrame(rows, columns=['year', 'Driver', 'Team', 'label', 'grid_fraction'])


def apply_season_grid_retirement_risk(features, recent_races, metadata):
    """Season retirements, standardised for where each car starts.

    Front-runners retire far less often than the midfield and back, so a raw
    season rate overstates a front-running team's risk and understates a
    backmarker's. The grid slope is fitted on earlier seasons (reliability
    resets with new cars, and within a season the slope is confounded with
    which teams break down). This season's team and driver records are then
    compared with what their own grid slots would predict (observed over
    expected), shrunk by the same data-driven strength as season_dnf_v1, and
    applied at this race's grid slot.
    """
    target = int(metadata['year']), int(metadata['round'])
    output = apply_season_retirement_risk(features, recent_races, metadata)
    history = _grid_observations(recent_races, target)
    known = history[history.label.notna()]
    current = known[known.year.eq(target[0])].copy()
    earlier = known[known.year.between(target[0] - PRIOR_SEASONS, target[0] - 1)]
    slope = fit_grid_slope(earlier.grid_fraction, earlier.label)
    field = float(output['retirement_field_prob'].iloc[0]) if len(output) else FALLBACK_FIELD_RATE
    current['expected'] = field * _grid_multiplier(current.grid_fraction, slope)
    grid = output['grid_position'] if 'grid_position' in output else pd.Series(np.nan, index=output.index)
    target_multiplier = _grid_multiplier(_grid_fraction(grid.to_numpy(), len(output)), slope)
    ratios = {}
    for level, column, keys in [('team', 'Team', output.Team.astype(str).str.strip().str.casefold()),
                                ('driver', 'Driver', output.Driver.astype(str))]:
        counts = current.groupby(column).agg(events=('label', 'sum'), expected=('expected', 'sum'))
        # Expected counts in field-rate units, so the season model's strength applies.
        effective = counts['expected'] / field if field > 0 else counts['expected']
        strength = shrinkage_strength(counts['events'], effective, field)
        events = keys.map(counts['events']).fillna(0.0)
        expected = keys.map(counts['expected']).fillna(0.0)
        ratios[level] = (events + strength * field) / (expected + strength * field)
        output[f'retirement_{level}_observed_over_expected'] = ratios[level].to_numpy()
        output[f'retirement_{level}_shrinkage_entries'] = strength
    ratio = TEAM_WEIGHT * ratios['team'] + (1 - TEAM_WEIGHT) * ratios['driver']
    probability = (field * target_multiplier * ratio).clip(.005, PROBABILITY_CAP)
    output['dnf_prob'] = probability.to_numpy()
    output['reliability_score'] = output['dnf_prob']
    output['retirement_grid_slope'] = slope
    output['retirement_grid_multiplier'] = target_multiplier
    output['retirement_model_version'] = GRID_VERSION
    return output
