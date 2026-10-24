"""Pick a Fantasy team from simulated points and the latest market prices.

The game's team rules: five drivers and two constructors within the budget,
and one driver's points doubled by the boost. Every legal team is scored, so
the best one is exact rather than a greedy guess. Given a current team, each
change beyond the free transfers costs the penalty, so a planned team is only
worth making when its extra points beat that cost. Points are the run's
simulated expectations; prices come from the archived official market.
"""
from __future__ import annotations

from itertools import combinations
import re
from typing import Any

import numpy as np
import pandas as pd

from src.model_config import FANTASY_SCORING


def team_key(name: Any) -> str:
    """'Haas F1 Team' and 'Haas' match; so do case and punctuation variants."""
    text = re.sub(r'[^a-z0-9]', '', str(name or '').casefold())
    return re.sub(r'(f1team|formula1team|f1)$', '', text) or text


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def market_assets(
    market: list[dict],
    drivers: pd.DataFrame,
    constructors: pd.DataFrame,
) -> tuple[list[dict], list[dict], list[str]]:
    """Join priced market assets to simulated points.

    drivers needs Driver, Team, avg_fantasy_points; constructors needs Team,
    avg_constructor_points. Returns priced drivers, priced constructors and the
    names of simulated assets that had no price.
    """
    driver_prices = {row['code']: row for row in market
                     if row.get('asset_type') == 'driver' and _number(row.get('price')) is not None}
    team_prices = {team_key(row.get('name')): row for row in market
                   if row.get('asset_type') == 'constructor' and _number(row.get('price')) is not None}
    missing = []

    priced_drivers = []
    for row in drivers.itertuples():
        quote = driver_prices.get(str(row.Driver))
        points = _number(row.avg_fantasy_points)
        if quote is None or points is None:
            missing.append(str(row.Driver))
            continue
        priced_drivers.append({'code': str(row.Driver), 'team': str(row.Team),
                               'price': float(quote['price']), 'points': points,
                               'floor': _number(getattr(row, 'fantasy_floor_p10', None)),
                               'ceiling': _number(getattr(row, 'fantasy_ceiling_p90', None))})

    priced_teams = []
    for row in constructors.itertuples():
        key = team_key(row.Team)
        quote = team_prices.get(key) or next(
            (q for k, q in team_prices.items() if k and (k.startswith(key) or key.startswith(k))), None)
        points = _number(row.avg_constructor_points)
        if quote is None or points is None:
            missing.append(str(row.Team))
            continue
        priced_teams.append({'code': str(quote.get('code') or row.Team), 'team': str(row.Team),
                             'price': float(quote['price']), 'points': points,
                             'floor': _number(getattr(row, 'constructor_floor_p10', None)),
                             'ceiling': _number(getattr(row, 'constructor_ceiling_p90', None))})
    return priced_drivers, priced_teams, missing


def _combos(assets: list[dict], size: int, include: set[str], exclude: set[str], label: str):
    forced = [i for i, a in enumerate(assets) if a['code'] in include]
    if len(forced) > size:
        raise ValueError(f'At most {size} {label} can be locked in.')
    free = [i for i, a in enumerate(assets)
            if a['code'] not in include and a['code'] not in exclude]
    if len(forced) + len(free) < size:
        raise ValueError(f'Only {len(forced) + len(free)} priced {label} are available; '
                         f'a team needs {size}.')
    picks = [tuple(forced) + rest for rest in combinations(free, size - len(forced))]
    return np.array(picks, dtype=int).reshape(len(picks), size)


def pick_teams(
    drivers: list[dict],
    constructors: list[dict],
    *,
    budget: float | None = None,
    include: list[str] | tuple = (),
    exclude: list[str] | tuple = (),
    boost: bool = True,
    top: int = 5,
    rules: dict | None = None,
    current: list[str] | tuple | None = None,
    bank: float | None = None,
    free_transfers: int | None = None,
) -> list[dict]:
    """The best legal teams by expected points after transfer penalties, best first.

    With a current team the budget is its value at today's prices plus the
    bank, unless a budget is given.
    """
    rules = {**FANTASY_SCORING['team'], **(rules or {})}
    multiplier = float(rules['boost_multiplier']) if boost else 1.0
    include, exclude = set(include or ()), set(exclude or ())
    if include & exclude:
        raise ValueError('An asset cannot be both locked in and left out.')
    known = {a['code'] for a in drivers} | {a['code'] for a in constructors}
    if include - known:
        raise ValueError('No price or projection for ' + ', '.join(sorted(include - known)) + '.')
    owned = set(current or ())
    if owned:
        if owned - known:
            raise ValueError('No price or projection for ' + ', '.join(sorted(owned - known))
                             + ' in your team.')
        owned_drivers = sum(a['code'] in owned for a in drivers)
        if owned_drivers != int(rules['drivers']) or len(owned) - owned_drivers != int(rules['constructors']):
            raise ValueError(f"Your team needs {rules['drivers']} drivers and "
                             f"{rules['constructors']} constructors.")
        if budget is None:
            value = sum(a['price'] for a in drivers + constructors if a['code'] in owned)
            budget = value + float(bank or 0.0)
    budget = float(rules['budget'] if budget is None else budget)
    free = int(rules['free_transfers'] if free_transfers is None else free_transfers)
    penalty = float(rules['transfer_penalty'])

    driver_sets = _combos(drivers, int(rules['drivers']), include, exclude, 'drivers')
    team_sets = _combos(constructors, int(rules['constructors']), include, exclude, 'constructors')
    driver_price = np.array([a['price'] for a in drivers])
    driver_points = np.array([a['points'] for a in drivers])
    team_price = np.array([a['price'] for a in constructors])
    team_points = np.array([a['points'] for a in constructors])

    set_points = driver_points[driver_sets]
    set_cost = driver_price[driver_sets].sum(axis=1)
    # The boost goes on the best expected driver in the set.
    set_score = set_points.sum(axis=1) + (multiplier - 1.0) * set_points.max(axis=1)
    pair_cost = team_price[team_sets].sum(axis=1)
    pair_score = team_points[team_sets].sum(axis=1)
    driver_owned = np.array([a['code'] in owned for a in drivers])
    team_owned = np.array([a['code'] in owned for a in constructors])
    set_changes = (~driver_owned[driver_sets]).sum(axis=1) if owned else np.zeros(len(driver_sets), int)
    pair_changes = (~team_owned[team_sets]).sum(axis=1) if owned else np.zeros(len(team_sets), int)

    candidates = []
    for pair in range(len(team_sets)):
        valid = np.flatnonzero(set_cost <= budget - pair_cost[pair] + 1e-9)
        if not len(valid):
            continue
        changes = set_changes[valid] + pair_changes[pair]
        net = set_score[valid] + penalty * np.maximum(changes - free, 0)
        order = np.argsort(-net, kind='stable')[:top]
        candidates.extend((float(net[j] + pair_score[pair]), pair, int(valid[j])) for j in order)
    if not candidates:
        raise ValueError(f'No legal team fits a ${budget:.1f}m budget.')
    candidates.sort(key=lambda item: -item[0])

    teams = []
    for score, pair, index in candidates[:top]:
        chosen = [drivers[i] for i in driver_sets[index]]
        boosted = max(chosen, key=lambda a: a['points'])['code'] if multiplier != 1.0 else None
        chosen = sorted(chosen, key=lambda a: -a['points'])
        pair_assets = sorted((constructors[i] for i in team_sets[pair]), key=lambda a: -a['points'])
        cost = float(set_cost[index] + pair_cost[pair])
        codes = {a['code'] for a in chosen + pair_assets}
        changes = len(codes - owned) if owned else 0
        teams.append({
            'expected_points': round(score, 2),
            'transfers_in': sorted(codes - owned) if owned else [],
            'transfers_out': sorted(owned - codes),
            'transfer_penalty': round(penalty * max(changes - free, 0), 2) if owned else 0.0,
            'cost': round(cost, 2),
            'budget_left': round(budget - cost, 2),
            'boost': boosted,
            'drivers': [{**a, 'boosted': a['code'] == boosted} for a in chosen],
            'constructors': pair_assets,
        })
    return teams


def team_distribution(
    team: dict,
    driver_sims: pd.DataFrame,
    constructor_sims: pd.DataFrame,
    multiplier: float | None = None,
) -> dict[str, float] | None:
    """P10/P50/P90 of the team's total across sims, when per-sim rows exist."""
    if driver_sims.empty or constructor_sims.empty:
        return None
    multiplier = float(FANTASY_SCORING['team']['boost_multiplier'] if multiplier is None else multiplier)
    weights = {a['code']: (multiplier if a.get('boosted') else 1.0) for a in team['drivers']}
    rows = driver_sims[driver_sims['Driver'].isin(weights)]
    totals = (rows['fantasy_points'] * rows['Driver'].map(weights)).groupby(rows['sim_id']).sum()
    names = {a['team'] for a in team['constructors']}
    teams = constructor_sims[constructor_sims['Team'].isin(names)]
    totals = totals.add(teams.groupby('sim_id')['constructor_fantasy_points'].sum(), fill_value=0.0)
    if totals.empty:
        return None
    return {'p10': float(totals.quantile(0.10)), 'p50': float(totals.quantile(0.50)),
            'p90': float(totals.quantile(0.90)), 'sims': int(len(totals))}
