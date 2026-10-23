"""Explicit uncalibrated free-air stint and pit-stop scenarios.

Plans are assumptions, not predictions or verified tyre inventory. Pit losses
and tyre curves enter elapsed time once, replacing aggregate tyre/strategy
penalties. Traffic, SC/VSC pit discounts and wet tyre transitions are absent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VERSION = 'pit_scenarios_v1'
CURVES = {'SOFT': (-.35, .08), 'MEDIUM': (0., .05), 'HARD': (.35, .03)}


def assumed_plans(features, race_laps, pit_loss_seconds=22.):
    """Two declared dry scenarios with equal assumption weights per driver."""
    laps = int(round(race_laps))
    if laps < 6:
        raise ValueError('At least six race laps are required for pit scenarios.')
    rows = []
    for driver in features.Driver:
        rows.extend([{'Driver': driver, 'name': 'one_stop_MH', 'weight': .5,
                      'pit_laps': [max(1, round(laps * .45))], 'compounds': ['MEDIUM', 'HARD'],
                      'pit_loss_seconds': pit_loss_seconds},
                     {'Driver': driver, 'name': 'two_stop_MMH', 'weight': .5,
                      'pit_laps': [max(1, round(laps * .3)), round(laps * .65)],
                      'compounds': ['MEDIUM', 'MEDIUM', 'HARD'], 'pit_loss_seconds': pit_loss_seconds}])
    return rows


def plan_lap_costs(plan, race_laps, degradation_factor=1.):
    laps = int(round(race_laps))
    stops = list(plan['pit_laps']); compounds = list(plan['compounds'])
    if (len(compounds) != len(stops) + 1 or not stops or len(set(stops)) != len(stops)
            or stops != sorted(stops) or any(isinstance(x, bool) or int(x) != x or not 1 <= x < laps for x in stops)
            or any(c not in CURVES for c in compounds) or len(set(compounds)) < 2):
        raise ValueError('Invalid dry race stint plan or compound sequence.')
    pit_loss = float(plan['pit_loss_seconds'])
    if not np.isfinite(pit_loss) or pit_loss <= 0 or not np.isfinite(degradation_factor) or degradation_factor < 0:
        raise ValueError('Pit loss must be positive; degradation factor must be nonnegative and finite.')
    result = np.zeros(laps)
    ages = initial_tyre_ages(plan)
    for start, end, compound, age in zip([0, *stops], [*stops, laps], compounds, ages):
        offset, slope = CURVES[compound]
        result[start:end] = offset + slope * (np.arange(end - start) + age) * degradation_factor
    # The pit occurs after completing the specified inlap.
    result[np.asarray(stops, dtype=int) - 1] += pit_loss
    return result


def initial_tyre_ages(plan):
    ages = plan.get('tyre_ages', [0] * len(plan['compounds']))
    if (len(ages) != len(plan['compounds']) or any(isinstance(a, bool) or
            not np.isfinite(a) or int(a) != a or a < 0 for a in ages)):
        raise ValueError('Each stint requires a nonnegative integer initial tyre age.')
    return list(ages)


def inventory_plans(features, race_laps, inventory, ledger):
    """Condition the two existing scenarios on an explicitly estimated set pool.

    Stints cannot identify distinct used sets without barcodes. Allow at most
    one representative used set per compound, at the largest observed END age.
    Its continued availability is an assumption, not an official allocation.
    Never consume the same pool entry twice within a plan.
    """
    required = {'Driver', 'Compound', 'estimated_new_sets_remaining', 'inventory_confidence'}
    if inventory is None or not required.issubset(inventory):
        raise ValueError('No frozen tyre inventory estimate; arm skipped.')
    if ledger is None or not {'Driver', 'Compound', 'Session', 'end_tyre_life'}.issubset(ledger):
        raise ValueError('No frozen tyre stint ledger; arm skipped.')
    if ledger.Session.astype(str).str.upper().eq('R').any():
        raise ValueError('Target race tyre observations cannot enter pre-race plans.')
    result = []
    for driver in features.Driver:
        rows = inventory[inventory.Driver.eq(driver)]
        if rows.Compound.duplicated().any():
            raise ValueError('Duplicate driver/compound inventory.')
        pool = {}; confidence = {}
        for compound in ('MEDIUM', 'HARD'):
            row = rows[rows.Compound.eq(compound)]
            if len(row) != 1 or str(row.iloc[0].inventory_confidence).lower() not in ('low', 'medium', 'high'):
                raise ValueError(f'Insufficient tyre inventory confidence for {driver}/{compound}.')
            confidence[compound] = str(row.iloc[0].inventory_confidence)
            count = row.iloc[0].estimated_new_sets_remaining
            if isinstance(count, (bool, np.bool_)) or not np.isfinite(count) or int(count) != count or not 0 <= count <= 20:
                raise ValueError('Invalid estimated fresh set count.')
            pool[compound] = [(f'{compound}_estimated_new_{n}', 0) for n in range(int(count))]
            observed = pd.to_numeric(ledger.loc[ledger.Driver.eq(driver) & ledger.Compound.eq(compound),
                                               'end_tyre_life'], errors='coerce')
            if observed.notna().any() and observed.max() > 0:
                age = float(observed.max())
                if not np.isfinite(age) or int(age) != age:
                    raise ValueError('Invalid used set end age.')
                pool[compound].append((f'{compound}_estimated_used_availability_assumed', int(age)))
        candidates = []
        for plan in assumed_plans(pd.DataFrame({'Driver': [driver]}), race_laps):
            available = {c: list(entries) for c, entries in pool.items()}
            chosen = []
            for compound in plan['compounds']:
                if not available[compound]:
                    break
                chosen.append(available[compound].pop(0))
            if len(chosen) == len(plan['compounds']):
                candidates.append({**plan, 'tyre_ages': [age for _, age in chosen],
                    'estimated_set_ids': [identifier for identifier, _ in chosen],
                    'inventory_confidence': confidence,
                    'inventory_source': 'frozen_fastf1_estimate', 'official_inventory': False})
        if not candidates:
            raise ValueError(f'No feasible declared tyre scenario for {driver}; arm skipped.')
        total = sum(p['weight'] for p in candidates)
        result.extend({**p, 'weight': p['weight']/total} for p in candidates)
    return result


def sample_pit_costs(features, plans, race_laps, n_sims, seed, degradation_factor=1.):
    if set(str(p['Driver']) for p in plans) != set(features.Driver.astype(str)):
        raise ValueError('Pit plans must cover exactly the forecast roster.')
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6182]))
    costs = np.zeros((n_sims, len(features)))
    counts = np.zeros_like(costs, dtype=int)
    labels = np.empty(costs.shape, dtype=object)
    for index, driver in enumerate(features.Driver):
        group = [p for p in plans if str(p['Driver']) == str(driver)]
        weights = np.asarray([p['weight'] for p in group], dtype=float)
        if (not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1)
                or len({p['name'] for p in group}) != len(group)):
            raise ValueError('Unique plans require finite nonnegative weights summing to one per driver.')
        totals = np.array([plan_lap_costs(p, race_laps, degradation_factor).sum() for p in group])
        choices = rng.choice(len(group), size=n_sims, p=weights)
        costs[:, index] = totals[choices]
        counts[:, index] = np.asarray([len(p['pit_laps']) for p in group])[choices]
        labels[:, index] = np.asarray([p['name'] for p in group])[choices]
    return costs, counts, labels


def elapsed_pit_costs(features, plans, labels, completed_laps, race_laps, degradation_factor=1.):
    costs = np.zeros(completed_laps.shape)
    stops = np.zeros(completed_laps.shape, dtype=int)
    for index, driver in enumerate(features.Driver):
        for plan in (p for p in plans if str(p['Driver']) == str(driver)):
            mask = labels[:, index] == plan['name']
            prefix = np.r_[0., np.cumsum(plan_lap_costs(plan, race_laps, degradation_factor))]
            count = completed_laps[mask, index]
            costs[mask, index] = prefix[count]
            stops[mask, index] = (count[:, None] >= np.asarray(plan['pit_laps'])).sum(axis=1)
    return costs, stops
