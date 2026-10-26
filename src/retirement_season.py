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

from src.result_status import NONFINISH_CLASSES, classify_result_status

VERSION = 'season_outcomes_v1_experimental'
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


def retirement_outcome(row) -> float:
    """1 retired, 0 finished, NaN when the result says nothing about it."""
    if str(getattr(row, 'ClassifiedPosition', '')).strip().upper() == 'R':
        return 1.0
    outcome = classify_result_status(getattr(row, 'Status', None))
    if outcome in NONFINISH_CLASSES:
        return 1.0
    return 0.0 if outcome == 'finished' else np.nan


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
        if results.Abbreviation.duplicated().any():
            raise ValueError('Retirement history has duplicate driver/race observations.')
        laps = pd.to_numeric(results['Laps'], errors='coerce') if 'Laps' in results else None
        for index, row in enumerate(results.itertuples()):
            label = retirement_outcome(row)
            # A car classified after stopping (over 90% distance) still retired.
            if label == 0 and laps is not None and laps.iloc[index] < laps.max() - 3:
                label = 1.0
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
