"""Unpromoted ensemble weather sensitivity using the existing simulation engine."""
from __future__ import annotations

import math

import pandas as pd

from src.simulate import simulate_races
from src.weather import _calculate_modifiers

METRICS = ['avg_finish', 'win_chance', 'podium_chance', 'points_chance', 'dnf_chance']


def simulate_weather_windows(features: pd.DataFrame, report: dict, *, sims_per_member: int = 200,
                             seed: int = 42, overtaking_difficulty: float = .55,
                             delay_weights: list[float] | None = None) -> tuple[pd.DataFrame, dict]:
    """Each coherent member gets equal simulations; never combine hourly marginals.

    Optional start weights are explicit user assumptions, not estimated delay
    probabilities. Uniform member weights conditional on each delay do not model
    race-control selection of safer weather; output is sensitivity only.
    """
    if sims_per_member < 1:
        raise ValueError('At least one simulation per ensemble member is required.')
    scenarios = report.get('scenarios', [])
    if not scenarios:
        raise ValueError('No race weather windows are available.')
    if delay_weights is not None and (len(delay_weights) != len(scenarios)
            or any(not math.isfinite(w) or w < 0 for w in delay_weights)
            or not math.isclose(sum(delay_weights), 1, abs_tol=1e-8)):
        raise ValueError('Delay weights must be finite, nonnegative and sum to one, one per window.')
    frames = []
    for scenario in scenarios:
        members = scenario['members']
        if len(members) < 2 or not all(m['simulation_usable'] for m in members):
            raise ValueError('Complete ensemble member weather is required; no missing members are dropped.')
        parts = []
        for index, member in enumerate(members):
            modifiers = _calculate_modifiers(member['air_temp_avg'], None, member['humidity_avg'],
                                             member['wind_speed_avg'], member['wet_hour'])
            summary, _, _ = simulate_races(features, n_sims=sims_per_member, seed=seed + index,
                                            overtaking_difficulty=overtaking_difficulty,
                                            weather_modifiers=modifiers)
            parts.append(summary[['Driver', *METRICS]])
        mixture = pd.concat(parts).groupby('Driver', sort=False)[METRICS].mean().reset_index()
        mixture['delay_minutes'] = scenario['delay_minutes']
        mixture['simulations'] = len(members) * sims_per_member
        frames.append(mixture)
    predictions = pd.concat(frames, ignore_index=True)
    if delay_weights is not None:
        weighted = []
        for frame, weight in zip(frames, delay_weights):
            part = frame[['Driver', *METRICS]].copy()
            part[METRICS] *= weight
            weighted.append(part)
        combined = pd.concat(weighted).groupby('Driver', sort=False)[METRICS].sum().reset_index()
        combined['delay_minutes'] = 'assumed_weight_mixture'
        combined['simulations'] = sum(frame['simulations'].iloc[0] for frame in frames)
        predictions = pd.concat([predictions, combined], ignore_index=True)
    metadata = {'category': 'weather_shadow_unvalidated', 'applied_to_live_predictions': False,
                'sims_per_member': sims_per_member, 'seed': seed,
                'delay_weights': delay_weights,
                'delay_weight_source': 'explicit_user_assumption' if delay_weights is not None else 'unavailable_no_blended_prediction',
                'limitations': ['Sensitivity experiment; no accuracy uplift demonstrated.',
                    'Uses existing uncalibrated weather modifiers; no driver-specific wet skill model.',
                    'Full race distance retained; shortened races, interruptions and tyre transitions are not modelled.',
                    'Weather averaged within each member window; intra-race transitions are not simulated.',
                    'Weather and delay selection dependence is not calibrated.']}
    return predictions, metadata
