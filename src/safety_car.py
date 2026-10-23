"""Track-rate safety cars for the aggregate race engine (opt-in candidate).

Each simulated race deploys a safety car with the track's SafetyCarChance,
which counts TrackStatus 4 races only (VSC is separate and not modelled here).
The deployment point is uniform over the race distance. Time gaps that built
up before it collapse to a small queue residual, and drivers still inside
their pit window may take a discounted stop. Restarts add timing noise.

These are stated assumptions, not fitted values. A single deployment per race
stands in for clustered events: only the last one decides how much of the
earlier gap is erased. No incident/DNF coupling or lapped-car handling.
"""
from __future__ import annotations

import numpy as np

VERSION = 'track_sc_v1'

# Separate stream so the default engine's random sequence is untouched.
_STREAM = 7240


def apply_safety_cars(projected_times, probability, seed, *, gap_retention=0.10,
                      restart_noise_seconds=1.50, pit_saving_seconds=10.0,
                      pit_window=(0.15, 0.80), pit_take_rate=0.60):
    """Return (adjusted times, deployed per sim, deployment race fraction)."""
    times = np.asarray(projected_times, dtype=float)
    probability = float(probability)
    if times.ndim != 2:
        raise ValueError('Projected times must be a sims x drivers matrix.')
    if not np.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError('Safety-car probability must be finite and between 0 and 1.')
    if not 0 <= gap_retention <= 1 or not 0 <= pit_take_rate <= 1 or pit_saving_seconds < 0:
        raise ValueError('Invalid safety-car assumptions.')

    n_sims, n_drivers = times.shape
    rng = np.random.default_rng(np.random.SeedSequence([seed, _STREAM]))
    deployed = rng.random(n_sims) < probability
    fraction = rng.uniform(0.03, 0.97, size=n_sims)
    takes_stop = rng.random((n_sims, n_drivers)) < pit_take_rate
    restart_noise = rng.normal(0.0, restart_noise_seconds, size=(n_sims, n_drivers))

    leader = times.min(axis=1, keepdims=True)
    gap = times - leader
    elapsed = fraction.reshape(n_sims, 1)
    # Gaps accrue roughly linearly; the share built before the SC is erased
    # except for the queue spacing, the rest accrues after the restart.
    compressed = leader + gap * (1 - elapsed) + gap * elapsed * gap_retention

    in_window = (elapsed >= pit_window[0]) & (elapsed <= pit_window[1])
    pit_saving = np.where(in_window & takes_stop, pit_saving_seconds, 0.0)

    adjusted = compressed - pit_saving + restart_noise
    deployed_rows = deployed.reshape(n_sims, 1)
    return np.where(deployed_rows, adjusted, times), deployed, np.where(deployed, fraction, np.nan)
