"""Sprint races for sprint weekends (opt-in candidate sprint_v1).

The established run simulates the Grand Prix only, so Fantasy projections
leave out sprint points on sprint weekends. This draws a short race per sim
from the same driver features: about 100 km, no pit stops or tyre-wear
penalty, the race grid as the sprint grid, and race noise and retirement risk
scaled to the shorter distance. Sprint points go 8-1 to the top eight.

Stated assumptions, not fitted values: the sprint grid is the forecast's grid
(an SQ classification when the run has one), noise scales with the square
root of distance, and no sprint fastest lap is drawn (Fantasy estimates the
sprint overtakes; see src/fantasy.py).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

VERSION = 'sprint_v1'

SPRINT_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

# Separate stream so the race simulation's random sequence is untouched.
_STREAM = 7523


def sprint_laps(race_laps: float) -> int:
    """Sprint distance is the fewest laps exceeding 100 km of a ~305 km race."""
    return max(1, math.ceil(float(race_laps) * 100.0 / 305.0))


def simulate_sprints(features: pd.DataFrame, n_sims: int, seed: int, *,
                     overtaking_difficulty: float = 0.55,
                     weather_modifiers: dict | None = None,
                     grid_loss_multiplier: float | None = None) -> pd.DataFrame:
    """Return one row per sim and driver with sprint result columns."""
    from src.simulate import _prepare_features, _sim_param, _weather_value

    base = _prepare_features(features)
    n_drivers = len(base)
    race_laps = float(base['estimated_race_laps'].median())
    laps = sprint_laps(race_laps)
    share = laps / race_laps

    uncertainty_factor = _weather_value(weather_modifiers, 'uncertainty_factor', 1.0)
    chaos_factor = _weather_value(weather_modifiers, 'chaos_factor', 1.0)
    dnf_factor = _weather_value(weather_modifiers, 'dnf_factor', 1.0)
    if grid_loss_multiplier is None:
        grid_loss_multiplier = _sim_param('grid_loss_multiplier', 1.65)

    pace = base['race_pace_score'].to_numpy(dtype=float)
    grid = base['grid_position'].to_numpy(dtype=float)
    confidence = base['grid_confidence'].to_numpy(dtype=float)
    uncertainty = base['performance_uncertainty'].to_numpy(dtype=float)
    dnf_prob = base['reliability_score'].to_numpy(dtype=float)

    deterministic = (pace * laps * _sim_param('race_pace_seconds_multiplier', 0.20)
                     + (grid - 1) * float(overtaking_difficulty) * confidence * grid_loss_multiplier)

    rng = np.random.default_rng(np.random.SeedSequence([seed, _STREAM]))
    shape = (n_sims, n_drivers)
    noise_scale = uncertainty * _sim_param('race_noise_multiplier', 3.80) * uncertainty_factor * math.sqrt(share)
    times = (deterministic.reshape(1, n_drivers)
             + rng.normal(0.0, 1.0, size=shape) * noise_scale
             + rng.normal(0.0, _sim_param('start_noise_seconds', 1.15), size=shape)
             + rng.normal(0.0, _sim_param('chaos_noise_seconds', 1.25) * chaos_factor * math.sqrt(share), size=shape))

    dnf = rng.random(shape) < np.clip(dnf_prob * dnf_factor * share, 0.001, 0.20).reshape(1, n_drivers)
    # Retirements finish behind every classified car, in a random order.
    times = np.where(dnf, 1e6 + rng.random(shape), times)

    order = np.argsort(times, axis=1)
    positions = np.empty_like(order)
    positions[np.arange(n_sims)[:, None], order] = np.arange(1, n_drivers + 1)

    points = np.zeros(shape)
    for position, value in SPRINT_POINTS.items():
        points[positions == position] = value
    points = np.where(dnf, 0.0, points)

    return pd.DataFrame({
        'sim_id': np.repeat(np.arange(n_sims), n_drivers),
        'Driver': np.tile(base['Driver'].to_numpy(), n_sims),
        'sprint_grid_position': np.tile(grid.astype(int), n_sims),
        'sprint_position': positions.reshape(-1),
        'sprint_points': points.reshape(-1),
        'sprint_dnf': dnf.reshape(-1),
        'sprint_positions_gained': (grid.reshape(1, n_drivers) - positions).reshape(-1),
        'sprint_laps': laps,
        'sprint_model': VERSION,
    })


def add_sprints(results: pd.DataFrame, sprints: pd.DataFrame) -> pd.DataFrame:
    """Join sprint columns to raw race results on sim and driver."""
    return results.merge(sprints, on=['sim_id', 'Driver'], how='left', validate='one_to_one')


def is_sprint_weekend(year: int, event, laps_say_sprint: bool = False) -> bool:
    """Sprint format from the FastF1 schedule; SQ/S laps also count."""
    if laps_say_sprint:
        return True
    try:
        import fastf1
        event_format = str(fastf1.get_event(int(year), event).get('EventFormat', ''))
    except Exception:
        return False
    return event_format.lower().startswith('sprint')
