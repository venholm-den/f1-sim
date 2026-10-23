"""Shared team luck for the aggregate race engine (opt-in candidate).

The established engine draws every driver's race noise independently, so a
car that is quicker or slower than practice suggested never moves both of its
drivers together. This adds one normal draw per team per simulated race to
both drivers' race time. With the default spreads (about 4.5-8 s per driver)
a 3-second team term gives a teammate correlation of roughly 0.15-0.3.

The spread is a stated assumption, not a fitted value. It widens outcomes as
well as correlating them; scripts.benchmark_safety_car --arms compares it.
"""
from __future__ import annotations

import numpy as np

VERSION = 'team_noise_v1'

# Separate stream so the default engine's random sequence is untouched.
_STREAM = 7311


def apply_team_noise(projected_times, teams, seed, *, team_noise_seconds=3.0,
                     uncertainty_factor=1.0):
    """Return (adjusted times, per-sim team offsets for each driver)."""
    times = np.asarray(projected_times, dtype=float)
    if times.ndim != 2:
        raise ValueError('Projected times must be a sims x drivers matrix.')
    teams = np.asarray(teams).astype(str)
    if teams.shape != (times.shape[1],):
        raise ValueError('Supply one team per driver column.')
    scale = float(team_noise_seconds) * float(uncertainty_factor)
    if not np.isfinite(scale) or scale < 0:
        raise ValueError('Team noise must be finite and non-negative.')

    _, team_index = np.unique(teams, return_inverse=True)
    rng = np.random.default_rng(np.random.SeedSequence([seed, _STREAM]))
    team_draws = rng.normal(0.0, scale, size=(times.shape[0], team_index.max() + 1))
    offsets = team_draws[:, team_index]
    return times + offsets, offsets
