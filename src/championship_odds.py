"""Drivers' and constructors' championship odds from the current standings.

Each remaining race or sprint is simulated by drawing every current driver's
result from their own completed results this season, weighted towards recent
rounds, then ranking the draws. Each team's and each driver's form follows a
random walk through the rest of the season that shifts which of their own
results is drawn (better or worse ones), so a driver can string together their
best results but is never pushed below P1 by added noise. Retirements come from
the same draws, so a driver's own reliability carries forward. Drivers with little history borrow
from their team-mates' results. This is a season-level form model; it does not
use the per-race simulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

RACE_POINTS = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
SPRINT_POINTS = (8, 7, 6, 5, 4, 3, 2, 1)
CLASSIFIED_STATUSES = {'finished', 'lapped'}


@dataclass(frozen=True)
class OddsSettings:
    n_sims: int = 20000
    seed: int = 2026
    # Rounds ago at which a result counts half as much as the latest one.
    form_half_life: float = 8.0
    sprint_weight: float = 0.5
    # Race-equivalents of team-mates' results mixed into each driver's pool.
    team_prior_weight: float = 1.0
    # 'pool' moves each driver along their own results as the season goes on. 'places' is the
    # first model, kept for backtests: it adds team and driver noise to the drawn finishing
    # place, which pulls front-runners back because nobody can finish above P1.
    pace_mode: str = 'pool'
    # Pool mode: per-round random-walk steps of each team's and each driver's form, in logits
    # of the quantile drawn from the driver's own results (positive = better results).
    pool_team_drift_sd: float = 0.3
    pool_driver_drift_sd: float = 0.45
    # Finishing places of noise that separates drivers who drew the same result.
    tiebreak_sd: float = 0.5
    # Places mode: per-session team and driver shocks and the per-round team drift, in places.
    team_shock_sd: float = 1.0
    driver_noise_sd: float = 2.0
    team_drift_sd: float = 1.0


def _text(value: Any) -> str:
    return '' if value is None or (isinstance(value, float) and np.isnan(value)) else str(value).strip()


def normalise_results(frame: pd.DataFrame) -> pd.DataFrame:
    """Map FastF1 or Jolpica classification columns onto one schema.

    Output columns: round, session (R or S), event, Driver, Team, position
    (finishing order, NaN when not classified), points, classified.
    """
    columns = ['round', 'session', 'event', 'Driver', 'Team', 'position', 'points', 'classified']
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)

    def pick(*names, default=None):
        for name in names:
            if name in frame.columns:
                return frame[name]
        return pd.Series(default, index=frame.index)

    driver = pick('Abbreviation', 'driverCode', 'Driver').map(_text).str.upper()
    status = pick('Status', 'status', default='').map(_text).str.lower()
    # Archived FastF1 classifications can give a retired car a numeric ClassifiedPosition,
    # so status decides first. Jolpica statuses include "+1 Lap"; positionText marks R/D/W/N.
    has_status = status.ne('').any()
    if has_status:
        classified = status.isin(CLASSIFIED_STATUSES) | status.str.match(r'^\+\d+ laps?$')
    else:
        classified = pd.to_numeric(pick('ClassifiedPosition', 'positionText'), errors='coerce').notna()
    position = pd.to_numeric(pick('Position', 'position'), errors='coerce')
    output = pd.DataFrame({
        'round': pd.to_numeric(pick('Round', 'round'), errors='coerce'),
        'session': pick('Session', 'session', default='R').map(_text).str.upper().replace({'': 'R'}),
        'event': pick('Event', 'event', 'raceName', default='').map(_text),
        'Driver': driver,
        'Team': pick('TeamName', 'constructorName', 'Team', default='').map(_text),
        'position': position.where(classified),
        'points': pd.to_numeric(pick('Points', 'points', default=0.0), errors='coerce').fillna(0.0),
        'classified': classified.astype(bool),
    })
    output = output[output['Driver'].ne('') & output['round'].notna() & output['session'].isin(['R', 'S'])]
    output['round'] = output['round'].astype(int)
    return output[columns].reset_index(drop=True)


def standings(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Current drivers' and constructors' points and race wins."""
    races = results[results['session'].eq('R')]
    wins = races[races['position'].eq(1)]
    drivers = results.groupby('Driver', as_index=False)['points'].sum()
    drivers['wins'] = drivers['Driver'].map(wins['Driver'].value_counts()).fillna(0).astype(int)
    teams = results.groupby('Team', as_index=False)['points'].sum()
    teams['wins'] = teams['Team'].map(wins['Team'].value_counts()).fillna(0).astype(int)
    return drivers, teams


def form_pools(results: pd.DataFrame, drivers: list[str], teams: dict[str, str],
               settings: OddsSettings) -> list[tuple[np.ndarray, np.ndarray]]:
    """Each driver's weighted pool of past finishing positions; inf marks a non-classification."""
    last_round = int(results['round'].max())
    weight = (0.5 ** ((last_round - results['round']) / settings.form_half_life)
              * np.where(results['session'].eq('S'), settings.sprint_weight, 1.0))
    frame = results.assign(weight=weight.to_numpy(), draw=results['position'].where(results['classified'], np.inf))
    pools = []
    for driver in drivers:
        own = frame[frame['Driver'].eq(driver)]
        mates = frame[frame['Team'].eq(teams[driver]) & frame['Driver'].ne(driver)]
        draws = np.concatenate([own['draw'].to_numpy(), mates['draw'].to_numpy()])
        mate_weights = mates['weight'].to_numpy()
        if mate_weights.sum() > 0:
            mate_weights = mate_weights / mate_weights.sum() * settings.team_prior_weight
        weights = np.concatenate([own['weight'].to_numpy(), mate_weights])
        if not len(draws) or weights.sum() <= 0:
            # No history at all: an anonymous back-of-the-field result.
            draws, weights = np.array([float(frame['draw'].replace(np.inf, np.nan).max() or 20)]), np.ones(1)
        pools.append((draws, weights / weights.sum()))
    return pools


def _tilted_draws(pools, tilt, rng):
    """Draw from each driver's pool at a quantile pushed towards their better results by tilt."""
    sims, n = tilt.shape
    u = rng.random((sims, n)).clip(1e-9, 1 - 1e-9)
    u = 1.0 / (1.0 + np.exp(-(np.log(u / (1.0 - u)) - tilt)))
    draws = np.empty((sims, n))
    for i, (values, weights) in enumerate(pools):
        order = np.argsort(values, kind='stable')
        cdf = np.cumsum(weights[order])
        index = np.searchsorted(cdf, u[:, i] * cdf[-1], side='right').clip(0, len(order) - 1)
        draws[:, i] = values[order][index]
    return draws


def _session_points(pools, team_of, drift, driver_drift, points_table, rng, settings):
    sims, n = settings.n_sims, len(pools)
    if settings.pace_mode == 'pool':
        draws = _tilted_draws(pools, drift[:, team_of] + driver_drift, rng)
        retired = np.isinf(draws)
        scores = -np.where(retired, 0.0, draws) + rng.normal(0.0, settings.tiebreak_sd, size=(sims, n))
    else:
        draws = np.column_stack([rng.choice(values, size=sims, p=weights) for values, weights in pools])
        retired = np.isinf(draws)
        scores = (-np.where(retired, 0.0, draws)
                  + (drift + rng.normal(0.0, settings.team_shock_sd, size=drift.shape))[:, team_of]
                  + rng.normal(0.0, settings.driver_noise_sd, size=(sims, n)))
    scores[retired] = -np.inf
    order = np.argsort(-scores, axis=1)
    table = np.zeros(n)
    table[:min(n, len(points_table))] = points_table[:n]
    points = np.zeros((sims, n))
    np.put_along_axis(points, order, np.broadcast_to(table, (sims, n)), axis=1)
    points[retired] = 0.0
    winner = order[:, 0]
    return points, np.where(retired[np.arange(sims), winner], -1, winner)


def _final_ranks(points: np.ndarray, wins: np.ndarray, rng) -> np.ndarray:
    """Rank 1 = champion. Ties go to more wins, then are split at random."""
    key = points * 1e4 + wins + rng.random(points.shape) * 0.5
    order = np.argsort(-key, axis=1)
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, points.shape[1] + 1)[None, :], axis=1)
    return ranks


def _summary(names, teams, current, current_wins, final, final_wins, ranks, remaining_max):
    leader = current.max() if len(current) else 0.0
    rows = []
    for i, name in enumerate(names):
        row = {
            'name': name,
            'current_points': float(current[i]),
            'current_wins': int(current_wins[i]),
            'expected_points': float(final[:, i].mean()),
            'points_p10': float(np.percentile(final[:, i], 10)),
            'points_p90': float(np.percentile(final[:, i], 90)),
            'expected_wins_remaining': float((final_wins[:, i] - current_wins[i]).mean()),
            'title_chance': float((ranks[:, i] == 1).mean()),
            'top3_chance': float((ranks[:, i] <= 3).mean()),
            'expected_position': float(ranks[:, i].mean()),
            # Even sweeping every remaining session cannot reach the current leader.
            'eliminated': bool(current[i] + remaining_max < leader),
            # Nobody else can reach this total any more.
            'clinched': bool(current[i] - remaining_max > np.delete(current, i).max(initial=-np.inf)),
        }
        if teams is not None:
            row['team'] = teams[i]
        rows.append(row)
    rows.sort(key=lambda row: (-row['title_chance'], -row['expected_points']))
    return rows


def simulate_championship(
    results: pd.DataFrame,
    remaining: Iterable[dict[str, Any]],
    settings: OddsSettings | None = None,
) -> dict[str, Any]:
    """Simulate the rest of the season from normalised completed results.

    remaining: one item per outstanding session group, {'round', 'event', 'race': bool, 'sprint': bool}.
    """
    settings = settings or OddsSettings()
    results = normalise_results(results) if 'classified' not in results.columns else results
    if results.empty:
        raise ValueError('No completed race classifications are available for this season.')
    remaining = [dict(item) for item in remaining]
    rng = np.random.default_rng(settings.seed)

    races = results[results['session'].eq('R')]
    if races.empty:
        raise ValueError('No completed race classifications are available for this season.')
    latest = races[races['round'].eq(races['round'].max())]
    # The latest race's entry list is the current roster, with each driver's current team.
    roster = latest.drop_duplicates('Driver')
    drivers = roster['Driver'].tolist()
    driver_team = dict(zip(roster['Driver'], roster['Team']))
    team_names = sorted(set(results['Team']) | set(driver_team.values()))
    team_of = np.array([team_names.index(driver_team[d]) for d in drivers])

    driver_table, team_table = standings(results)
    all_drivers = drivers + sorted(set(driver_table['Driver']) - set(drivers))
    current = driver_table.set_index('Driver').reindex(all_drivers).fillna(0.0)
    team_current = team_table.set_index('Team').reindex(team_names).fillna(0.0)

    pools = form_pools(results, drivers, driver_team, settings)

    n_all = len(all_drivers)
    gained = np.zeros((settings.n_sims, n_all))
    gained_wins = np.zeros((settings.n_sims, n_all))
    sims = np.arange(settings.n_sims)
    remaining_max = 0.0
    drift = np.zeros((settings.n_sims, len(team_names)))
    driver_drift = np.zeros((settings.n_sims, len(drivers)))
    pool_mode = settings.pace_mode == 'pool'
    for item in remaining:
        drift += rng.normal(0.0, settings.pool_team_drift_sd if pool_mode else settings.team_drift_sd, size=drift.shape)
        if pool_mode:
            driver_drift += rng.normal(0.0, settings.pool_driver_drift_sd, size=driver_drift.shape)
        for flag, table in (('sprint', SPRINT_POINTS), ('race', RACE_POINTS)):
            if not item.get(flag, flag == 'race'):
                continue
            points, winner = _session_points(pools, team_of, drift, driver_drift, np.array(table, float), rng, settings)
            gained[:, :len(drivers)] += points
            remaining_max += table[0]
            if flag == 'race':
                won = winner >= 0
                np.add.at(gained_wins, (sims[won], winner[won]), 1)

    final = current['points'].to_numpy() + gained
    final_wins = current['wins'].to_numpy() + gained_wins
    ranks = _final_ranks(final, final_wins, rng)
    driver_rows = _summary(all_drivers, [driver_team.get(d, '') for d in all_drivers], current['points'].to_numpy(),
                           current['wins'].to_numpy(), final, final_wins, ranks, remaining_max)
    for row in driver_rows:
        row['active'] = row['name'] in drivers
        if row['active']:
            values, weights = pools[drivers.index(row['name'])]
            row['form_dnf_rate'] = float(weights[np.isinf(values)].sum())

    # Constructors: each team's drivers' simulated points and wins, on top of the team's current total.
    membership = np.zeros((n_all, len(team_names)))
    for i, driver in enumerate(drivers):
        membership[i, team_of[i]] = 1.0
    team_final = team_current['points'].to_numpy() + gained @ membership
    team_final_wins = team_current['wins'].to_numpy() + gained_wins @ membership
    team_ranks = _final_ranks(team_final, team_final_wins, rng)
    seats = np.bincount(team_of, minlength=len(team_names))
    team_max = remaining_max + sum(
        (RACE_POINTS[1] if item.get('race', True) else 0) + (SPRINT_POINTS[1] if item.get('sprint') else 0)
        for item in remaining)
    team_rows = _summary(team_names, None, team_current['points'].to_numpy(), team_current['wins'].to_numpy(),
                         team_final, team_final_wins, team_ranks, team_max)
    team_rows = [row for row in team_rows if seats[team_names.index(row['name'])] or row['current_points']]

    completed = results.groupby(['round', 'session']).size().reset_index()[['round', 'session']]
    return {
        'drivers': driver_rows,
        'constructors': team_rows,
        'completed_rounds': int(races['round'].nunique()),
        'completed_sprints': int(results[results['session'].eq('S')]['round'].nunique()),
        'last_round': int(races['round'].max()),
        'last_event': _text(latest['event'].iloc[0]) if 'event' in latest else '',
        'remaining': remaining,
        'remaining_races': sum(1 for item in remaining if item.get('race', True)),
        'remaining_sprints': sum(1 for item in remaining if item.get('sprint')),
        'max_points_available': remaining_max,
        'sessions_used': len(completed),
        'settings': settings.__dict__.copy(),
    }
