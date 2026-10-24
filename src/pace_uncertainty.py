"""Uncertain car pace and heavy-tailed incidents for the car-agent engine (opt-in).

The multi-score tuning (docs/multi-score-tuning.md) found the established
engine wants about four times its live race noise, and that the missing
randomness is driver-specific rather than flat seconds. The likely source is
the pace estimate itself: a car's pace from three earlier races is a noisy
guess at its pace this weekend, and the error is shared by teammates.

``pace_uncertainty_v1`` draws, once per simulated race:

- one pace offset per team (s/lap), shared by both of its cars
- one pace offset per driver (s/lap), scaled by the driver's relative
  ``performance_uncertainty``
- at most one incident per driver: with a small chance, a lognormal time loss
  (spin, damage, slow stop, penalty) whose tail is much heavier than a normal

The two pace spreads can be estimated from a history table: each earlier race
is forecast from the races before it, and the misses are split into a team
part and a driver part (``estimate_pace_error``). Only races before the
target are used. The incident chance and size are stated assumptions, not
fits: a green-lap timing proxy on the 2026 packet shows a loss of 3 s or more
in about 18% of driver-races (median 4.7 s), and that proxy misses the
biggest incidents because they bring yellow flags or pit stops.

This module wraps the agent engine without changing ``src/agent_race.py`` or
``src/simulate.py``, which the enabled 2026 prospective suite pins. With
every spread at zero the result equals ``agent_laps_v1`` draw for draw.

Limitation: incident time is added to each car's elapsed time after the race
is run, so a car that loses 20 s is not then held up in traffic. Retirements
keep their sampled distance and are unaffected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

VERSION = 'pace_uncertainty_v1'

# Separate stream so the agent engine's own draws are untouched.
_STREAM = 9127


@dataclass(frozen=True)
class PaceUncertaintySettings:
    team_pace_sd: float = 0.5  # s/lap, shared by teammates
    driver_pace_sd: float = 0.3  # s/lap at median performance_uncertainty
    incident_probability: float = 0.15  # per driver per race
    incident_median_seconds: float = 6.0
    incident_log_sd: float = 1.0  # lognormal shape; 1.0 puts the 99th percentile near 10x the median
    incident_cap_seconds: float = 120.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not np.isfinite(value) or value < 0:
                raise ValueError(f'Invalid pace uncertainty setting: {key}.')
        if self.incident_probability > 0.5:
            raise ValueError('Incident probability must be at most 0.5.')
        if self.incident_probability > 0 and self.incident_median_seconds <= 0:
            raise ValueError('Incidents need a positive median loss.')


def estimate_pace_error(history: pd.DataFrame, window: int = 3, *, before_round: int | None = None,
                        prior_team_sd: float = 0.5, prior_driver_sd: float = 0.3,
                        prior_races: float = 2.0, max_miss: float = 3.0) -> dict:
    """Team and driver pace-forecast error (s/lap) from earlier races only.

    history has one row per driver and race: Driver, Team, source_round and
    relative_pace. Each race with ``window`` races before it is forecast by the
    mean of those races; misses are centred per race so only relative pace
    counts. The team variance is the spread of team-mean misses less the share
    driver misses contribute to a two-car mean. Each race adds one observation
    to a prior worth ``prior_races`` races, so early-season estimates lean on
    the prior. Misses beyond ``max_miss`` s/lap (a damaged or stranded car) are
    dropped from this estimate; the incident term covers those.
    """
    frame = history[['Driver', 'Team', 'source_round', 'relative_pace']].dropna()
    rounds = sorted(frame.source_round.unique())
    if before_round is not None:
        rounds = [r for r in rounds if r < before_round]
    team_terms, driver_terms = [], []
    for target in rounds:
        earlier = [r for r in rounds if r < target][-window:]
        if len(earlier) < window:
            continue
        forecast = frame[frame.source_round.isin(earlier)].groupby('Driver').relative_pace.mean()
        actual = frame[frame.source_round.eq(target)].set_index('Driver')
        miss = pd.DataFrame({'forecast': forecast, 'actual': actual.relative_pace, 'Team': actual.Team}).dropna()
        if len(miss) < 6:
            continue
        miss['miss'] = ((miss.actual - miss.actual.median()) - (miss.forecast - miss.forecast.median()))
        miss = miss[miss.miss.abs() <= max_miss]
        team_mean = miss.groupby('Team').miss.transform('mean')
        cars = miss.groupby('Team').miss.transform('size')
        within = miss[cars > 1]
        if within.empty:
            continue
        driver_var = float(((within.miss - team_mean[cars > 1]) ** 2).sum()
                           / max(1, len(within) - within.Team.nunique()))
        team_var = float(miss.groupby('Team').miss.mean().var(ddof=1)) - driver_var / 2
        team_terms.append(max(team_var, 0.0))
        driver_terms.append(driver_var)
    n = len(team_terms)
    team_sd = float(np.sqrt((prior_races * prior_team_sd ** 2 + sum(team_terms)) / (prior_races + n)))
    driver_sd = float(np.sqrt((prior_races * prior_driver_sd ** 2 + sum(driver_terms)) / (prior_races + n)))
    return {'team_pace_sd': team_sd, 'driver_pace_sd': driver_sd, 'races_used': n}


def sample_pace_offsets(base: pd.DataFrame, n_sims: int, seed: int, settings: PaceUncertaintySettings):
    """Per-sim pace offsets (s/lap) and incident losses (s), each [sims, drivers]."""
    teams = base.Team.astype(str).to_numpy()
    _, team_index = np.unique(teams, return_inverse=True)
    uncertainty = pd.to_numeric(base.performance_uncertainty, errors='coerce').to_numpy(float)
    if not np.isfinite(uncertainty).all() or (uncertainty <= 0).any():
        raise ValueError('performance_uncertainty must be positive and finite.')
    relative = uncertainty / np.median(uncertainty)
    rng = np.random.default_rng(np.random.SeedSequence([seed, _STREAM]))
    shape = (n_sims, len(base))
    team = rng.normal(0.0, settings.team_pace_sd, (n_sims, team_index.max() + 1))[:, team_index]
    driver = rng.normal(0.0, 1.0, shape) * settings.driver_pace_sd * relative
    hit = rng.random(shape) < settings.incident_probability
    size = settings.incident_median_seconds * np.exp(rng.normal(0.0, settings.incident_log_sd, shape))
    incidents = np.where(hit, np.minimum(size, settings.incident_cap_seconds), 0.0)
    return team + driver, incidents


def simulate_uncertain_agent_races(base, n_sims, seed, *, uncertainty=None, pit_plans=None,
                                   agent_settings=None, weather_modifiers=None,
                                   overtaking_difficulty=.55):
    """Agent-engine races with sampled team/driver pace and incidents.

    Mirrors ``src.agent_race.simulate_agent_races`` step for step, using the
    same random streams, and adds the offsets from its own stream. Returns
    the usual (summary, position matrix, raw results).
    """
    from src.agent_race import AgentSettings, run_agents
    from src.model_config import DEFAULT_PIT_AND_RACE_ALLOWANCE
    from src.pit_scenarios import assumed_plans, sample_pit_costs
    from src.retirement_progress import PROGRESS_COLUMNS, distance_order, sample_completed_laps
    from src.simulate import _points_for_positions, _prepare_features, summarise_results

    cfg_u = (uncertainty if isinstance(uncertainty, PaceUncertaintySettings)
             else PaceUncertaintySettings(**(uncertainty or {})))
    base = _prepare_features(base)
    values = dict(agent_settings or {})
    values.setdefault('passability', 1. - float(overtaking_difficulty))
    if values.get('pair_pass_model') is not None:
        from src.pair_overtaking import VERSION as PAIR_VERSION, load_model
        model = values['pair_pass_model']
        model = dict(load_model() if model == PAIR_VERSION else model)
        model.setdefault('track_difficulty', float(overtaking_difficulty))
        values['pair_pass_model'] = model
    cfg = AgentSettings(**values)
    if not isinstance(n_sims, int) or isinstance(n_sims, bool) or n_sims < 1:
        raise ValueError('n_sims must be a positive integer.')
    if base.Driver.duplicated().any():
        raise ValueError('Duplicate agent drivers.')
    if weather_modifiers and weather_modifiers.get('rainfall_flag', False):
        raise ValueError('The agent candidate currently supports dry conditions only.')
    laps = int(round(base.estimated_race_laps.median()))
    plans = pit_plans if pit_plans is not None else assumed_plans(base, laps)
    _, planned_stops, labels = sample_pit_costs(base, plans, laps, n_sims, seed)
    identifiers = {(str(p['Driver']), p['name']): i for i, p in enumerate(plans)}
    plan_ids = np.column_stack([np.array([identifiers[(str(driver), label)] for label in labels[:, i]])
                                for i, driver in enumerate(base.Driver)])
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6184]))
    gap = np.broadcast_to(base.race_pace_score.to_numpy(float), (n_sims, len(base))).copy()
    reference = (float(base.base_winner_race_time_seconds.median()) - DEFAULT_PIT_AND_RACE_ALLOWANCE) / laps
    pace = reference + gap + rng.normal(0., base.performance_uncertainty.to_numpy(float) * 3.8 / laps, gap.shape)
    risk = np.clip(base.reliability_score.to_numpy(float) * (weather_modifiers or {}).get('dnf_factor', 1.), 0, .45)
    if not np.isfinite(risk).all():
        raise ValueError('Invalid retirement probability modifier.')
    retired = rng.random(gap.shape) < risk
    distance_base = base.copy()
    if not set(PROGRESS_COLUMNS).issubset(base):
        distance_base[PROGRESS_COLUMNS] = .1
    distance = sample_completed_laps(distance_base, retired, laps, rng)

    offsets, incidents = sample_pace_offsets(base, n_sims, seed, cfg_u)
    pace =np.clip(pace + offsets, 30., 300.)
    state = run_agents(pace, base.grid_position.to_numpy(int), laps, plans, plan_ids, distance,
                       settings=cfg, seed=seed)
    incidents = np.where(state['dnf'], 0.0, incidents)
    elapsed = state['elapsed_seconds'] + incidents

    order = distance_order(elapsed, state['completed_laps'])
    positions = np.empty_like(order)
    positions[np.arange(n_sims)[:, None], order] = np.arange(1, len(base) + 1)
    classified = state['completed_laps'] >= np.floor(.9 * state['completed_laps'].max(axis=1, keepdims=True))
    classified &= state['completed_laps'] > 0
    points = np.where(classified, _points_for_positions(positions), 0.)
    fastest = np.zeros_like(retired)
    minimum = np.where(~state['dnf'], state['minimum_lap_seconds'], np.inf)
    winners = np.argmin(minimum, axis=1)
    fastest[np.arange(n_sims), winners] = np.isfinite(minimum[np.arange(n_sims), winners])
    records = []
    for i, row in enumerate(base.itertuples()):
        position = positions[:, i]
        data = pd.DataFrame({'sim_id': np.arange(n_sims), 'Driver': row.Driver, 'Team': row.Team,
            'grid_position': row.grid_position, 'finish_position': position, 'position': position, 'Position': position,
            'points': points[:, i], 'race_points': points[:, i],
            'projected_race_time_seconds': elapsed[:, i], 'classified_race_time_seconds': elapsed[:, i],
            'performance_score': elapsed[:, i], 'dnf': state['dnf'][:, i], 'DNF': state['dnf'][:, i],
            'red_flag': False, 'red_flag_probability': 0., 'positions_gained': row.grid_position - position,
            'fastest_lap': fastest[:, i], 'dotd': False, 'classified': classified[:, i],
            'retirement_classification': 'agent_completed_laps_v1', 'race_engine': 'agent_laps_v1',
            'pace_uncertainty_model': VERSION, 'pace_offset_seconds_per_lap': offsets[:, i],
            'incident_seconds': incidents[:, i],
            'sc_restarts': state['sc_restarts'], 'neutralised_seconds': state['neutralised_seconds'],
            'pit_scenario': labels[:, i], 'planned_pit_stops': planned_stops[:, i]})
        for key in ('completed_laps', 'fuel_kg', 'tyre_age', 'thermal_heat', 'thermal_wear_seconds',
                    'overtakes', 'blue_flag_passes', 'completed_pit_stops', 'traffic_loss_seconds', 'pit_loss_seconds'):
            data[key] = state[key][:, i]
        records.append(data)
    return summarise_results(base, pd.concat(records, ignore_index=True), grid_loss_multiplier=0.)
