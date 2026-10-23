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


# --- multi_sc_v1: several safety cars and VSCs per race (opt-in candidate) ---
#
# Structure follows the probabilistic race-simulation approach published by
# TU Munich (Heilmeier et al., 2020): a per-race count of SC and VSC phases,
# each with a start lap and a length in laps, with the race start weighted
# separately. Re-implemented from that description; no code is taken from it.
# The numbers below were measured from 131 archived races (2021-2026, FastF1
# TrackStatus 4 for SC and 6/7 for VSC; a VSC upgraded to an SC counts as one
# SC) and are fixed assumptions, not fitted per run.
MULTI_VERSION = 'multi_sc_v1'
_MULTI_STREAM = 7241
MAX_PHASES = 3
# The chance of any phase rises with retirements: 1 - exp(-m(1 + w * retirements)),
# with w from a Poisson fit on the archive (rate a + b * retirements, b / a =
# 1.40 for SC and 1.30 for VSC). m is solved per run so that the average
# chance of at least one SC is the track's SafetyCarChance.
SC_RETIREMENT_WEIGHT = 1.40
VSC_RETIREMENT_WEIGHT = 1.30
# 52 of 131 archived races had at least one VSC; there is no per-track VSC rate.
VSC_CHANCE = 0.40
# 21% of archived SCs started on lap 1; the rest are close to uniform.
SC_LAP_ONE_SHARE = 0.21
# Races with at least one phase: how many they had (VSC 3 includes one 4).
SC_COUNT_GIVEN_ANY = {1: 52, 2: 16, 3: 5}
VSC_COUNT_GIVEN_ANY = {1: 33, 2: 14, 3: 5}
SC_LENGTH_LAPS = {1: .15, 2: .20, 3: .29, 4: .19, 5: .11, 6: .03, 7: .02, 8: .01}
# Lengths count leader laps started under the phase (SC median 520 s).
VSC_LENGTH_LAPS = {1: .74, 2: .23, 3: .03}


def _rate_scale(target, shape):
    """Scale m so the mean of 1 - exp(-m * shape) equals target."""
    if target <= 0:
        return 0.0
    low, high = 0.0, 1.0
    while np.mean(1 - np.exp(-high * shape)) < target:
        high *= 2
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if np.mean(1 - np.exp(-mid * shape)) < target else (low, mid)
    return (low + high) / 2


def _phase_counts(rng, probability, shape, extra_table):
    """Whether a race has any phase follows the retirement-shaped rate; how
    many it has, given at least one, follows the archive's counts."""
    if probability >= 1:
        any_phase = np.ones(len(shape), dtype=bool)
    else:
        chance = 1 - np.exp(-_rate_scale(probability, shape) * shape)
        any_phase = rng.random(len(shape)) < chance
    return np.where(any_phase, _lengths(rng, extra_table, len(shape)), 0)


def _lengths(rng, table, size):
    laps, weights = zip(*table.items())
    return rng.choice(np.array(laps), size=size, p=np.array(weights) / sum(weights))


def apply_neutralisations(projected_times, retired, sc_probability, race_laps, seed, *,
                          vsc_probability=VSC_CHANCE, gap_retention=0.10,
                          sc_restart_noise_seconds=1.50, vsc_restart_noise_seconds=0.50,
                          sc_pit_saving_seconds=10.0, vsc_pit_saving_seconds=5.0,
                          pit_window=(0.15, 0.80), pit_take_rate=0.60):
    """Return (adjusted times, SC count per sim, VSC count per sim).

    Each SC erases the gaps built before it down to the queue residual
    (gap_retention); gaps accrue only on green laps. A VSC keeps time gaps.
    Each driver takes at most one discounted stop, at the first SC or VSC
    inside the pit window, with pit_take_rate. Phases are not tied to the lap
    a car retires on, and overlapping phases are not merged.
    """
    times = np.asarray(projected_times, dtype=float)
    retired = np.asarray(retired, dtype=bool)
    if times.ndim != 2 or retired.shape != times.shape:
        raise ValueError('Projected times and retirements must be matching sims x drivers matrices.')
    for value in (sc_probability, vsc_probability):
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Safety-car and VSC probabilities must be finite and between 0 and 1.')
    if not 0 <= gap_retention <= 1 or not 0 <= pit_take_rate <= 1:
        raise ValueError('Invalid safety-car assumptions.')

    n_sims, n_drivers = times.shape
    laps = max(4, int(round(float(race_laps))))
    rng = np.random.default_rng(np.random.SeedSequence([seed, _MULTI_STREAM]))
    retirements = retired.sum(axis=1)
    n_sc = _phase_counts(rng, float(sc_probability), 1 + SC_RETIREMENT_WEIGHT * retirements,
                         SC_COUNT_GIVEN_ANY)
    n_vsc = _phase_counts(rng, float(vsc_probability), 1 + VSC_RETIREMENT_WEIGHT * retirements,
                          VSC_COUNT_GIVEN_ANY)

    slots = np.arange(MAX_PHASES)
    sc_on = slots < n_sc[:, None]
    vsc_on = slots < n_vsc[:, None]
    shape = (n_sims, MAX_PHASES)
    sc_start = np.where(rng.random(shape) < SC_LAP_ONE_SHARE, 1, rng.integers(2, laps - 1, size=shape))
    sc_end = np.minimum(sc_start + _lengths(rng, SC_LENGTH_LAPS, shape) - 1, laps)
    vsc_start = rng.integers(1, laps, size=shape)
    vsc_end = np.minimum(vsc_start + _lengths(rng, VSC_LENGTH_LAPS, shape) - 1, laps)

    lap = np.arange(1, laps + 1).reshape(1, 1, laps)
    neutral = (((lap >= sc_start[..., None]) & (lap <= sc_end[..., None]) & sc_on[..., None]).any(axis=1)
               | ((lap >= vsc_start[..., None]) & (lap <= vsc_end[..., None]) & vsc_on[..., None]).any(axis=1))
    # Gap built on a green lap survives each later SC only as the queue residual.
    later_sc = ((sc_start[..., None] > lap) & sc_on[..., None]).sum(axis=1)
    green = ~neutral
    share = np.where(green, gap_retention ** later_sc, 0.0).sum(axis=1)
    green_laps = green.sum(axis=1)
    weight = np.where(green_laps > 0, share / np.maximum(green_laps, 1), gap_retention)

    leader = times.min(axis=1, keepdims=True)
    adjusted = leader + (times - leader) * weight.reshape(n_sims, 1)

    # Chronological pass over phases for the one discounted stop per driver.
    starts = np.concatenate([np.where(sc_on, sc_start, laps + 1), np.where(vsc_on, vsc_start, laps + 1)], axis=1)
    savings = np.concatenate([np.full(shape, sc_pit_saving_seconds), np.full(shape, vsc_pit_saving_seconds)], axis=1)
    fraction = (starts - 1) / laps
    eligible = (starts <= laps) & (fraction >= pit_window[0]) & (fraction <= pit_window[1])
    order = np.argsort(starts, axis=1, kind='stable')
    rows = np.arange(n_sims)[:, None]
    eligible, savings = eligible[rows, order], savings[rows, order]
    takes = rng.random((n_sims, n_drivers, 2 * MAX_PHASES)) < pit_take_rate
    pit_saving = np.zeros((n_sims, n_drivers))
    stopped = np.zeros((n_sims, n_drivers), dtype=bool)
    for k in range(2 * MAX_PHASES):
        stop = eligible[:, k:k + 1] & takes[:, :, k] & ~stopped
        pit_saving = np.where(stop, savings[:, k:k + 1], pit_saving)
        stopped |= stop

    noise_sd = np.sqrt(n_sc * sc_restart_noise_seconds ** 2 + n_vsc * vsc_restart_noise_seconds ** 2)
    restart_noise = rng.normal(0.0, 1.0, size=(n_sims, n_drivers)) * noise_sd.reshape(n_sims, 1)
    return adjusted - pit_saving + restart_noise, n_sc, n_vsc
