"""Announced grid penalties and per-sim pre-qualifying grids (opt-in candidates).

announced_v1: verified stewards' decisions for the race (grid drops, back of
grid, pit-lane starts) move drivers on a grid that does not already include
them: the estimated grid, or the qualifying classification. An FIA starting
grid already has them and is left alone. The qualifying order is kept as
qualifying_position so Fantasy qualifying points are not lost to a penalty.

estimated_grid_v1: before qualifying the estimated grid is one guess, but the
established engine uses it unchanged in every simulated race. This draws a
qualifying order per sim (positional noise around the estimate), then applies
any announced penalties to it.

Approximations: grid drops are applied together rather than in order of
infringement, and a pit-lane start is placed at the back like a back-of-grid
penalty. The positional spread is a stated assumption, not a fitted value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PENALTY_VERSION = 'announced_v1'
SAMPLING_VERSION = 'estimated_grid_v1'

BACK_OF_GRID_TYPES = {'back_of_grid', 'pit_lane'}
PLACE_DROP_TYPES = {'grid_drop'}

# Separate stream so the default engine's random sequence is untouched.
_STREAM = 7417


def penalty_columns(penalties: pd.DataFrame | None, drivers) -> pd.DataFrame:
    """Per-driver grid_penalty_places and grid_penalty_back from decisions."""
    drivers = pd.Index(pd.Series(list(drivers), dtype=str), name='Driver')
    output = pd.DataFrame({'grid_penalty_places': 0.0, 'grid_penalty_back': False}, index=drivers)
    if penalties is None or penalties.empty or not {'driver', 'penalty_type'}.issubset(penalties):
        return output.reset_index()

    frame = penalties.copy()
    frame['Driver'] = frame['driver'].astype(str).str.strip().str.upper()
    if 'target_session' in frame:
        frame = frame[frame['target_session'].fillna('R').astype(str).str.upper().eq('R')]
    if 'status' in frame:
        frame = frame[frame['status'].fillna('verified_decision').eq('verified_decision')]
    kind = frame['penalty_type'].astype(str).str.lower()
    places = pd.to_numeric(frame.get('penalty_value'), errors='coerce').fillna(0).clip(lower=0)

    drops = places[kind.isin(PLACE_DROP_TYPES)].groupby(frame['Driver']).sum()
    back = set(frame.loc[kind.isin(BACK_OF_GRID_TYPES), 'Driver'])
    output['grid_penalty_places'] = drops.reindex(output.index).fillna(0.0).astype(float)
    output['grid_penalty_back'] = output.index.isin(back)
    return output.reset_index()


def penalised_grid(qualifying, places, back):
    """Rank a qualifying order (n or sims x n) after drops and back-of-grid moves.

    A penalised driver lands behind an unpenalised driver at the same slot;
    back-of-grid drivers keep their qualifying order among themselves.
    """
    qualifying = np.asarray(qualifying, dtype=float)
    places = np.asarray(places, dtype=float)
    back = np.asarray(back, dtype=bool)
    penalised = (places > 0) | back
    key = qualifying + places + np.where(penalised, 0.5, 0.0) + np.where(back, 1000.0, 0.0)
    order = np.argsort(key, axis=-1, kind='stable')
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, key.shape[-1] + 1)
                      * np.ones_like(order), axis=-1)
    return ranks


def apply_announced_penalties(features: pd.DataFrame, penalties: pd.DataFrame | None) -> pd.DataFrame:
    """Return features with penalties applied to a grid that lacks them."""
    output = features.copy()
    columns = penalty_columns(penalties, output['Driver'])
    output = output.drop(columns=[c for c in ['grid_penalty_places', 'grid_penalty_back']
                                  if c in output], errors='ignore').merge(columns, on='Driver', how='left')
    output['grid_penalty_places'] = output['grid_penalty_places'].fillna(0.0)
    output['grid_penalty_back'] = output['grid_penalty_back'].fillna(False).astype(bool)
    output['qualifying_position'] = output['grid_position'].astype(int)
    official = output.get('grid_source', pd.Series('', index=output.index)).astype(str).eq('fia_official_grid')
    if official.any():
        # An official grid already includes them; never apply them twice.
        output['grid_penalty_model'] = 'not_applied_official_grid'
        return output
    output['grid_position'] = penalised_grid(output['qualifying_position'],
                                             output['grid_penalty_places'], output['grid_penalty_back'])
    output['grid_penalty_model'] = PENALTY_VERSION
    return output.sort_values(['grid_position', 'Driver']).reset_index(drop=True)


def sample_grids(qualifying, places, back, n_sims, seed, *, spread_positions=2.0):
    """Return (qualifying, grid) matrices, sims x drivers, around an estimate."""
    qualifying = np.asarray(qualifying, dtype=float)
    if not np.isfinite(spread_positions) or spread_positions < 0:
        raise ValueError('Grid spread must be finite and non-negative.')
    rng = np.random.default_rng(np.random.SeedSequence([seed, _STREAM]))
    noisy = qualifying.reshape(1, -1) + rng.normal(0.0, spread_positions, size=(n_sims, qualifying.size))
    order = np.argsort(noisy, axis=1, kind='stable')
    sampled = np.empty_like(order)
    np.put_along_axis(sampled, order, np.broadcast_to(np.arange(1, qualifying.size + 1), order.shape), axis=1)
    grid = penalised_grid(sampled, np.broadcast_to(places, sampled.shape), np.broadcast_to(back, sampled.shape))
    return sampled, grid
