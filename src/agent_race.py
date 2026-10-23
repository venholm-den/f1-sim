"""Experimental shared-clock car agents. Parameters are assumptions, not fits.

Progress is unwrapped laps at a common time; classification uses completed laps
and actual interpolated crossings. Pit loss is a net delay at the control line,
not a geometric pit-lane model. No energy storage, wet transitions or generated
red-flag recovery is claimed. Optional empirical SC/VSC schedules remain a
separate shadow candidate. Keep this candidate out of live forecasts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

VERSION = 'agent_laps_v1'


@dataclass(frozen=True)
class AgentSettings:
    step_seconds: float = 2.0
    initial_fuel_kg: float = 70.0  # sensitivity assumption; NOT a regulatory limit
    fuel_seconds_per_kg: float = .035
    fuel_reference_fraction: float = .5  # mean-race pace, rather than zero-fuel pace
    grid_spacing_seconds: float = .25
    dirty_air_range_seconds: float = 1.5
    dirty_air_slope: float = .5
    minimum_gap_seconds: float = .15
    passability: float = .45  # larger means easier, unlike overtaking_difficulty
    pass_intercept: float = -2.0
    pass_pace_slope: float = 2.0
    following_laps: float = 1.0
    fight_delay_seconds: float = .4
    blue_flag_yield_seconds: float = 1.5
    blue_flag_leader_seconds: float = .1
    thermal_response_laps: float = 2.0
    thermal_penalty_seconds: float = .2
    thermal_wear_seconds_per_lap: float = .02
    maximum_thermal_wear_seconds: float = 2.0
    tyre_quadratic_seconds: float = 0.0
    lap_noise_seconds: float = .15
    overtaking_aid: str = 'none'
    aid_lap_gain_seconds: float = 0.0
    season_year: int | None = None
    neutralised_windows: tuple = ()  # [start, end] seconds; prescribed, not sampled SC
    neutralised_lap_multiplier: float = 1.5
    neutralisation_model: dict | None = None
    neutralisation_events: tuple = ()
    sc_lap_multiplier: float = 1.6
    sc_catchup_multiplier: float = 1.15
    vsc_lap_multiplier: float = 1.4
    sc_queue_gap_seconds: float = 1.0
    restart_seconds: float = 15.0
    restart_slowdown_fraction: float = .1
    sc_pit_loss_fraction: float = .6
    vsc_pit_loss_fraction: float = .8
    pit_stationary_seconds: float = 2.5
    # Fitted per-pair pass model (src/pair_overtaking.py); replaces passability
    # and the pass logistic when set. The version name loads the saved fit.
    pair_pass_model: dict | str | None = None

    def __post_init__(self):
        if self.pair_pass_model is not None:
            from src.pair_overtaking import VERSION as PAIR_VERSION, load_model, validate_model
            model = self.pair_pass_model
            if isinstance(model, str):
                if model != PAIR_VERSION:
                    raise ValueError('Unknown pair pass model.')
                model = load_model()
            object.__setattr__(self, 'pair_pass_model', dict(validate_model(model)))
        for key, value in asdict(self).items():
            if key in {'overtaking_aid', 'season_year', 'neutralised_windows',
                       'neutralisation_model', 'neutralisation_events', 'pair_pass_model'}:
                continue
            if isinstance(value, bool) or not np.isfinite(value):
                raise ValueError(f'Invalid agent setting: {key}.')
            if key != 'pass_intercept' and value < 0:
                raise ValueError(f'Agent setting must be nonnegative: {key}.')
        if not 0 < self.step_seconds <= 5 or not 0 < self.minimum_gap_seconds < self.dirty_air_range_seconds:
            raise ValueError('Use steps in (0, 5] seconds and a positive minimum following gap.')
        if not 0 <= self.passability <= 1 or not 0 <= self.fuel_reference_fraction <= 1:
            raise ValueError('Passability and fuel reference fraction must be in [0, 1].')
        if self.thermal_response_laps <= 0 or self.neutralised_lap_multiplier < 1:
            raise ValueError('Thermal response must be positive; neutralised pace cannot be faster.')
        if (min(self.sc_lap_multiplier, self.vsc_lap_multiplier, self.sc_catchup_multiplier) < 1
                or self.sc_catchup_multiplier > self.sc_lap_multiplier
                or not 0 <= self.sc_pit_loss_fraction <= 1 or not 0 <= self.vsc_pit_loss_fraction <= 1):
            raise ValueError('Invalid SC/VSC speed or pit discount.')
        if self.neutralised_windows and (self.neutralisation_model is not None or self.neutralisation_events):
            raise ValueError('Legacy neutralisation windows cannot be combined with SC/VSC schedules.')
        from src.neutralisation import validate_events
        validate_events(self.neutralisation_events)
        if self.overtaking_aid not in {'none', 'legacy_drs_proxy', 'electrical_proxy'}:
            raise ValueError('Unknown overtaking aid.')
        if self.overtaking_aid != 'none':
            if self.season_year is None or isinstance(self.season_year, bool) or int(self.season_year) != self.season_year:
                raise ValueError('An overtaking aid requires an explicit season year.')
            if ((self.overtaking_aid == 'legacy_drs_proxy' and not 2011 <= self.season_year < 2026)
                    or (self.overtaking_aid == 'electrical_proxy' and self.season_year < 2026)):
                raise ValueError('Overtaking aid does not match the regulation era.')
        elif self.aid_lap_gain_seconds:
            raise ValueError('Aid gain requires an explicit era-specific proxy.')
        previous_end = -1.
        for start, end in self.neutralised_windows:
            if not np.isfinite([start, end]).all() or start < previous_end or not 0 <= start < end:
                raise ValueError('Neutralised windows must be finite, ordered and disjoint.')
            previous_end = end


def physical_ahead(progress, on_track):
    """Nearest physical car ahead on a ring, independent of classification laps."""
    shape = progress.shape
    phase = np.where(on_track, progress % 1, np.inf)
    order = np.argsort(phase, axis=1, kind='stable')
    ranks = np.empty_like(order)
    rows = np.arange(shape[0])[:, None]
    ranks[rows, order] = np.arange(shape[1])
    count = on_track.sum(axis=1, keepdims=True)
    ahead_rank = (ranks + 1) % np.maximum(count, 1)
    ahead = np.take_along_axis(order, ahead_rank, axis=1)
    gap = (np.take_along_axis(progress, ahead, axis=1) - progress) % 1
    valid = on_track & (count > 1)
    return ahead, np.where(valid, gap, np.inf)


def _plan_tables(plans, race_laps):
    from src.pit_scenarios import CURVES, plan_lap_costs, initial_tyre_ages
    offset = []; slope = []; ages = []; stops = []
    for plan in plans:
        plan_lap_costs(plan, race_laps)  # common dry-plan validation
        historic_ages = initial_tyre_ages(plan)
        a = np.zeros(race_laps + 1, dtype=int)
        o = np.zeros(race_laps + 1); s = o.copy(); p = o.copy()
        for start, end, compound, age in zip([0, *plan['pit_laps']],
                [*plan['pit_laps'], race_laps], plan['compounds'], historic_ages):
            a[start:end] = np.arange(end - start) + age
            o[start:end], s[start:end] = CURVES[compound]
        a[-1] = a[-2] + 1
        p[plan['pit_laps']] = float(plan['pit_loss_seconds'])
        ages.append(a); offset.append(o); slope.append(s); stops.append(p)
    return tuple(np.asarray(x) for x in (offset, slope, ages, stops))


def _plan_softness(plans, race_laps):
    """Compound softness [plan, lap] for the pair pass model (HARD 0 .. SOFT 2)."""
    from src.pair_overtaking import SOFTNESS
    table = np.ones((len(plans), race_laps + 1))
    for row, plan in zip(table, plans):
        for start, end, compound in zip([0, *plan['pit_laps']], [*plan['pit_laps'], race_laps],
                                        plan['compounds']):
            row[start:end] = SOFTNESS.get(compound, 1)
        row[-1] = row[-2]
    return table


def run_agents(lap_pace, grid, race_laps, plans, plan_ids, retirement_laps, *,
               settings=None, seed=42, record_trace=False):
    """Vectorised independent races with synchronous, two-phase position updates.

    lap_pace is mean-fuel clean pace [simulation, car]; retirement_laps is the
    sampled maximum completed distance (race_laps for survivors). A retirement
    at zero occurs at the start; other retirements occur at that lap crossing.
    A trace is intentionally limited to one race to avoid enormous artifacts.
    """
    cfg = settings if isinstance(settings, AgentSettings) else AgentSettings(**(settings or {}))
    pace = np.asarray(lap_pace, dtype=float)
    grid = np.asarray(grid, dtype=float)
    plan_ids = np.asarray(plan_ids)
    limit = np.asarray(retirement_laps)
    if (pace.ndim != 2 or not pace.size or grid.shape != (pace.shape[1],)
            or plan_ids.shape != pace.shape or limit.shape != pace.shape
            or not np.isfinite(pace).all() or np.any((pace < 30) | (pace > 300))
            or not np.isfinite(grid).all() or sorted(grid) != list(range(1, pace.shape[1] + 1))
            or isinstance(race_laps, bool) or int(race_laps) != race_laps or race_laps < 2
            or not np.isfinite(limit).all() or np.any((limit < 0) | (limit > race_laps))
            or np.any(limit != limit.astype(int)) or not np.issubdtype(plan_ids.dtype, np.integer)
            or np.any((plan_ids < 0) | (plan_ids >= len(plans)))):
        raise ValueError('Invalid car state, race distance, pace, grid or plan IDs.')
    if record_trace and pace.shape[0] != 1:
        raise ValueError('Record a trace for one race at a time.')
    offset, slope, ages, pit_after = _plan_tables(plans, race_laps)
    softness = _plan_softness(plans, race_laps) if cfg.pair_pass_model is not None else None
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6183]))
    shape = pace.shape
    from src.neutralisation import sample_schedules
    event_start, event_end, event_kind = sample_schedules(cfg.neutralisation_model,
        cfg.neutralisation_events, pace.min(axis=1) * race_laps, seed)
    previous_phase = np.zeros(shape[0], dtype=int)
    restart_until = np.zeros(shape[0]); restart_count = np.zeros(shape[0], dtype=int)
    neutralised_seconds = np.zeros(shape[0])
    progress = np.broadcast_to(-(grid - 1) * cfg.grid_spacing_seconds / pace, shape).copy()
    completed = np.zeros(shape, dtype=int)
    last_crossing = np.zeros(shape)
    minimum_lap = np.full(shape, np.inf)
    fuel = np.full(shape, cfg.initial_fuel_kg)
    heat = np.zeros(shape); wear = heat.copy(); pit_wait = heat.copy(); fight_wait = heat.copy()
    follow = heat.copy(); previous_ahead = np.full(shape, -1, dtype=int)
    pass_target = np.full(shape, -1, dtype=int)
    noise = rng.normal(0, cfg.lap_noise_seconds, shape)
    terminal = limit == 0
    dnf = terminal.copy()
    winner_time = np.full(shape[0], np.inf)
    passes = np.zeros(shape, dtype=int); blue = passes.copy(); stops = passes.copy()
    traffic_loss = heat.copy(); pit_loss = heat.copy()
    trace = []
    clock = 0.
    # Finite guard catches accidental deadlocks rather than silently ranking an unfinished run.
    deadline = (race_laps + 2) * (pace.max() + 150) * max(2., cfg.neutralised_lap_multiplier, cfg.sc_lap_multiplier, cfg.vsc_lap_multiplier)
    while not terminal.all():
        if clock > deadline:
            raise RuntimeError('Agent race did not finish within its integration bound.')
        dt = cfg.step_seconds
        # Split exactly at prescribed neutralisation boundaries.
        boundaries = [x for window in cfg.neutralised_windows for x in window if clock < x < clock + dt]
        boundaries.extend(x for e in cfg.neutralisation_events for x in
                          (e['start_seconds'], e['end_seconds']) if clock < x < clock+dt)
        if boundaries:
            dt = min(boundaries) - clock
        legacy_neutralised = any(start <= clock < end for start, end in cfg.neutralised_windows)
        # Sampled boundaries have at most one integration-step timing error.
        phase = np.max(np.where((event_start <= clock) & (clock < event_end), event_kind, 0), axis=1,
                       initial=0)
        restarting = (previous_phase == 1) & (phase == 0) & ~terminal.all(axis=1)
        restart_count += restarting
        restart_until = np.where(restarting, clock + cfg.restart_seconds, restart_until)
        previous_phase = phase.copy()
        neutralised = (phase[:, None] > 0) | legacy_neutralised
        neutralised_seconds += dt * (phase > 0) * ~terminal.all(axis=1)
        active = ~terminal
        # Returning cars participate immediately, with the time left after their pit delay.
        on_track = active & (pit_wait < dt)
        available = np.maximum(0., dt - pit_wait - fight_wait) * active
        pit_wait = np.maximum(0., pit_wait - dt)
        fight_wait = np.maximum(0., fight_wait - dt)
        age = ages[plan_ids, completed]
        # Midlap mass centres the full-distance fuel contribution at the chosen reference.
        mass = np.maximum(0., fuel - cfg.initial_fuel_kg / race_laps / 2)
        clean = (pace + cfg.fuel_seconds_per_kg * (mass - cfg.initial_fuel_kg * cfg.fuel_reference_fraction)
                 + offset[plan_ids, completed] + slope[plan_ids, completed] * age
                 + cfg.tyre_quadratic_seconds * age ** 2 + cfg.thermal_penalty_seconds * heat + wear + noise)
        clean = np.clip(clean, 20., 600.)
        ahead, gap_laps = physical_ahead(progress, on_track)
        ahead_clean = np.take_along_axis(clean, ahead, axis=1)
        gap_seconds = gap_laps * ahead_clean
        close = on_track & (gap_seconds <= cfg.dirty_air_range_seconds) & ~neutralised
        aid = (close & (gap_seconds <= 1.) & (cfg.overtaking_aid != 'none')
               & (completed >= (1 if cfg.overtaking_aid == 'electrical_proxy' else 2)))
        dirty = cfg.dirty_air_slope * np.where(close, cfg.dirty_air_range_seconds - gap_seconds, 0.)
        effective = np.maximum(20., clean + dirty - aid * cfg.aid_lap_gain_seconds)
        if legacy_neutralised:
            effective = np.broadcast_to(pace.min(axis=1, keepdims=True) * cfg.neutralised_lap_multiplier, shape)
        reference = pace.min(axis=1, keepdims=True)
        leader = np.argmax(np.where(on_track, progress, -np.inf), axis=1)
        is_leader = np.arange(shape[1])[None, :] == leader[:, None]
        # VSC retains physical gaps. SC followers close at a capped catch-up pace
        # until the queue gap is reached; the blocking rule still forbids passes.
        sc_pace = np.where(is_leader | (gap_seconds <= cfg.sc_queue_gap_seconds),
                           reference * cfg.sc_lap_multiplier, reference * cfg.sc_catchup_multiplier)
        effective = np.where(phase[:, None] == 1, sc_pace, effective)
        effective = np.where(phase[:, None] == 2, reference * cfg.vsc_lap_multiplier, effective)
        restart = np.clip((restart_until-clock) / max(cfg.restart_seconds, 1e-9), 0., 1.)[:, None]
        effective = np.where(phase[:, None] == 0,
            effective * (1 + cfg.restart_slowdown_fraction * restart * ~is_leader), effective)
        movement = available / effective
        movement = np.where(active, movement, 0.)
        follow = np.where(close & (gap_seconds <= 1.),
                          np.where(ahead == previous_ahead, follow, 0.) + available, 0.)
        previous_ahead = ahead.copy()
        ahead_move = np.take_along_axis(movement, ahead, axis=1)
        contact = on_track & (movement > gap_laps + ahead_move - cfg.minimum_gap_seconds / ahead_clean)
        lapping = progress - np.take_along_axis(progress, ahead, axis=1) > .5
        # Per-lap probability converted to the step's time exposure (no timestep lottery).
        if cfg.pair_pass_model is None:
            advantage = ahead_clean - clean
            p_lap = cfg.passability / (1 + np.exp(-np.clip(cfg.pass_intercept + cfg.pass_pace_slope * advantage, -50, 50)))
        else:
            from src.pair_overtaking import lap_probability
            # Same follower-advantage deltas the model was fitted on.
            soft = softness[plan_ids, completed]
            p_lap = lap_probability(cfg.pair_pass_model, np.take_along_axis(pace, ahead, axis=1) - pace,
                                    np.take_along_axis(age, ahead, axis=1) - age,
                                    soft - np.take_along_axis(soft, ahead, axis=1))
        p_step = -np.expm1(np.log1p(-np.minimum(p_lap, 1 - 1e-12)) * available / clean)
        approve = close & ~neutralised & ((pass_target == ahead) | (contact &
            (lapping | ((follow >= cfg.following_laps * clean) & (rng.random(shape) < p_step)))))
        # Disjoint adjacent moves prevent a car participating in two fights in one step.
        approve &= ~np.take_along_axis(approve, ahead, axis=1)
        # Propagate blocking through a train. All proposals use the same starting state.
        for _ in range(shape[1]):
            front_move = np.take_along_axis(movement, ahead, axis=1)
            margin = cfg.minimum_gap_seconds / ahead_clean
            cap = gap_laps + front_move + np.where(approve, margin * .5, -margin)
            updated = np.where(on_track, np.minimum(movement, np.maximum(0., cap)), movement)
            if np.array_equal(updated, movement):
                break
            movement = updated
        actual_pass = approve & (movement > gap_laps + np.take_along_axis(movement, ahead, axis=1))
        pass_target = np.where(approve & ~actual_pass, ahead, -1)
        racing_pass = actual_pass & ~lapping
        blue_pass = actual_pass & lapping
        passes += racing_pass; blue += blue_pass
        # Fight/yield costs are charged once on a completed encounter, via future clock delay.
        fight_wait += racing_pass * cfg.fight_delay_seconds + blue_pass * cfg.blue_flag_leader_seconds
        for sim, car in np.argwhere(actual_pass):
            front = ahead[sim, car]
            fight_wait[sim, front] += (cfg.blue_flag_yield_seconds if blue_pass[sim, car] else cfg.fight_delay_seconds)
        traffic_loss += np.where(active & ~neutralised, np.maximum(0., available - movement * clean), 0.)
        target_heat = close.astype(float)
        response = -np.expm1(-dt / (clean * cfg.thermal_response_laps))
        heat = np.where(active, np.clip(heat + (target_heat - heat) * response, 0, 1), heat)
        wear = np.where(active, np.minimum(cfg.maximum_thermal_wear_seconds,
                           wear + heat * cfg.thermal_wear_seconds_per_lap * available / clean), wear)
        proposed = progress + movement
        crossing = active & (proposed >= completed + 1)
        fraction = np.divide(completed + 1 - progress, movement, out=np.ones(shape), where=movement > 0)
        crossing_time = clock + dt - available + np.clip(fraction, 0, 1) * available
        leader_cross = crossing & (completed + 1 >= race_laps)
        winner_time = np.minimum(winner_time, np.min(np.where(leader_cross, crossing_time, np.inf), axis=1))
        finish = crossing & (crossing_time >= winner_time[:, None])
        retire = crossing & (completed + 1 >= limit) & ~finish
        minimum_lap = np.where(crossing, np.minimum(minimum_lap, crossing_time - last_crossing), minimum_lap)
        last_crossing = np.where(crossing, crossing_time, last_crossing)
        completed += crossing
        fuel = np.where(crossing, np.maximum(0., cfg.initial_fuel_kg * (1 - completed / race_laps)), fuel)
        planned_stop = pit_after[plan_ids, completed]
        fraction_loss = np.where(phase[:, None] == 1, cfg.sc_pit_loss_fraction,
                                 np.where(phase[:, None] == 2, cfg.vsc_pit_loss_fraction, 1.))
        stationary = np.minimum(planned_stop, cfg.pit_stationary_seconds)
        planned_stop = stationary + (planned_stop-stationary) * fraction_loss
        pit = crossing & (planned_stop > 0) & ~finish & ~retire
        # Integrate the net pit delay from the exact crossing, retaining this tick's remainder.
        remaining = clock + dt - crossing_time
        progress = np.where(crossing & (pit | finish | retire), completed, proposed)
        pit_wait += np.where(pit, np.maximum(0., planned_stop - remaining), 0.)
        progress += np.where(pit, np.maximum(0., remaining - planned_stop) / effective, 0.)
        stops += pit; pit_loss += pit * planned_stop
        heat = np.where(pit, 0., heat); wear = np.where(pit, 0., wear)
        new_noise = rng.normal(0, cfg.lap_noise_seconds, shape)
        noise = np.where(crossing, new_noise, noise)
        terminal |= finish | retire
        dnf |= retire
        clock += dt
        if record_trace:
            for car in range(shape[1]):
                trace.append({'clock_seconds': clock, 'car': car, 'progress_laps': progress[0, car],
                    'completed_laps': completed[0, car], 'crossing_time_seconds': last_crossing[0, car],
                    'fuel_kg': fuel[0, car], 'tyre_age': int(ages[plan_ids[0, car], completed[0, car]]),
                    'thermal_heat': heat[0, car], 'thermal_wear_seconds': wear[0, car],
                    'pit_wait_seconds': pit_wait[0, car], 'overtakes': passes[0, car],
                    'neutralisation_phase': int(phase[0]), 'restart_active': bool(restart[0, 0] > 0),
                    'blue_flag_passes': blue[0, car], 'terminal': terminal[0, car]})
    return {'elapsed_seconds': last_crossing, 'completed_laps': completed, 'dnf': dnf,
        'minimum_lap_seconds': minimum_lap, 'fuel_kg': fuel,
        'tyre_age': ages[plan_ids, completed], 'thermal_heat': heat, 'thermal_wear_seconds': wear,
        'overtakes': passes, 'blue_flag_passes': blue, 'completed_pit_stops': stops,
        'traffic_loss_seconds': traffic_loss, 'pit_loss_seconds': pit_loss,
        'neutralised_seconds': neutralised_seconds, 'sc_restarts': restart_count,
        'trace': pd.DataFrame(trace), 'settings': asdict(cfg)}


def simulate_agent_races(base, n_sims, seed, *, pit_plans=None, settings=None,
                         sample_pace_posterior=False, weather_modifiers=None, overtaking_difficulty=.55):
    """Adapt the candidate to the existing forecast tables; no aggregate penalties."""
    from src.model_config import DEFAULT_PIT_AND_RACE_ALLOWANCE
    from src.pit_scenarios import assumed_plans, sample_pit_costs
    from src.retirement_progress import PROGRESS_COLUMNS, distance_order, sample_completed_laps
    from src.simulate import _points_for_positions, summarise_results
    values = dict(settings or {})
    values.setdefault('passability', 1. - float(overtaking_difficulty))
    if values.get('pair_pass_model') is not None:
        from src.pair_overtaking import VERSION as PAIR_VERSION, load_model
        model = values['pair_pass_model']
        model = dict(load_model() if model == PAIR_VERSION else model)
        # The track term uses this race's difficulty unless the caller fixed one.
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
    if sample_pace_posterior:
        from src.qualifying_pace import sample_pace
        gap = sample_pace(base, n_sims, seed)
    # Existing absolute reference is a mean-race estimate, already including fuel effects.
    reference = (float(base.base_winner_race_time_seconds.median()) - DEFAULT_PIT_AND_RACE_ALLOWANCE) / laps
    pace = reference + gap + rng.normal(0., base.performance_uncertainty.to_numpy(float) * 3.8 / laps, gap.shape)
    risk = np.clip(base.reliability_score.to_numpy(float) * (weather_modifiers or {}).get('dnf_factor', 1.), 0, .45)
    if not np.isfinite(risk).all():
        raise ValueError('Invalid retirement probability modifier.')
    retired = rng.random(gap.shape) < risk
    distance_base = base.copy()
    if not set(PROGRESS_COLUMNS).issubset(base):
        # Explicit uniform fallback, independent of pace; never inferred from poor lap samples.
        distance_base[PROGRESS_COLUMNS] = .1
    distance = sample_completed_laps(distance_base, retired, laps, rng)
    state = run_agents(pace, base.grid_position.to_numpy(int), laps, plans, plan_ids, distance,
                       settings=cfg, seed=seed)
    order = distance_order(state['elapsed_seconds'], state['completed_laps'])
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
            'projected_race_time_seconds': state['elapsed_seconds'][:, i],
            'classified_race_time_seconds': state['elapsed_seconds'][:, i],
            'performance_score': state['elapsed_seconds'][:, i], 'dnf': state['dnf'][:, i], 'DNF': state['dnf'][:, i],
            'red_flag': False, 'red_flag_probability': 0., 'positions_gained': row.grid_position - position,
            'fastest_lap': fastest[:, i], 'dotd': False, 'classified': classified[:, i],
            'retirement_classification': 'agent_completed_laps_v1', 'race_engine': VERSION,
            'sc_restarts': state['sc_restarts'], 'neutralised_seconds': state['neutralised_seconds'],
            'pit_scenario': labels[:, i], 'planned_pit_stops': planned_stops[:, i]})
        for key in ('completed_laps', 'fuel_kg', 'tyre_age', 'thermal_heat', 'thermal_wear_seconds',
                    'overtakes', 'blue_flag_passes', 'completed_pit_stops', 'traffic_loss_seconds', 'pit_loss_seconds'):
            data[key] = state[key][:, i]
        records.append(data)
    return summarise_results(base, pd.concat(records, ignore_index=True), grid_loss_multiplier=0.)
