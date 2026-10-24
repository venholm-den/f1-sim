"""Proper scores that read more of each race than finish MAE and three Briers.

Win Brier has one positive per race, so most of a forecast's information is
unscored. These scores use each driver's whole position distribution and every
head-to-head pair, which the simulation already produces. Races remain the
independent unit: average a score within a race, then compare races.

- Ranked probability score (RPS): squared gap between forecast and observed
  cumulative position distributions, scaled to 0..1. Lower is better.
- Position log score: minus log of the probability given to the position each
  driver actually finished, floored so one impossible outcome cannot dominate.
- Head-to-head Brier: for every driver pair, the chance the first finishes
  ahead of the second against what happened (190 pairs for 20 drivers).
  Teammate pairs are also reported on their own.
- Threshold RPS: the RPS restricted to the win/podium/top-10 thresholds that
  older saved forecasts and prospective trials already store.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOG_SCORE_FLOOR = 1e-3
THRESHOLDS = (('win_chance', 1), ('podium_chance', 3), ('points_chance', 10))


def _actual_positions(actual: pd.DataFrame, drivers) -> np.ndarray:
    """Official finishing positions for drivers, which must be a complete 1..n order."""
    table = actual.set_index('Driver')['Position']
    if table.index.duplicated().any() or set(table.index) != set(drivers):
        raise ValueError('Forecast and actual driver coverage differ.')
    positions = pd.to_numeric(table.loc[list(drivers)], errors='coerce').to_numpy(float)
    if np.isnan(positions).any() or sorted(positions) != list(range(1, len(positions) + 1)):
        raise ValueError('A complete official finishing order is required.')
    return positions.astype(int)


def position_probabilities(position_matrix: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    """Drivers and an n x n array of P(driver finishes in position k)."""
    columns = [f'P{k}' for k in range(1, len(position_matrix) + 1)]
    missing = set(columns) - set(position_matrix.columns)
    if missing:
        raise ValueError(f'Position matrix is missing {sorted(missing)[:3]}.')
    probabilities = position_matrix[columns].to_numpy(float)
    if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError('Each driver row must sum to one.')
    return position_matrix['Driver'].astype(str).tolist(), probabilities


def ranked_probability_score(probabilities: np.ndarray, actual_positions) -> float:
    """Mean RPS over drivers; 0 is a certain, correct forecast."""
    probabilities = np.asarray(probabilities, dtype=float)
    actual_positions = np.asarray(actual_positions, dtype=int)
    n = probabilities.shape[1]
    forecast = np.cumsum(probabilities, axis=1)[:, :-1]
    observed = (np.arange(1, n)[None, :] >= actual_positions[:, None]).astype(float)
    return float(((forecast - observed) ** 2).sum(axis=1).mean() / (n - 1))


def position_log_score(probabilities: np.ndarray, actual_positions, floor: float = LOG_SCORE_FLOOR) -> float:
    """Mean of -log P(actual position); lower is better."""
    probabilities = np.asarray(probabilities, dtype=float)
    rows = np.arange(len(probabilities))
    chosen = probabilities[rows, np.asarray(actual_positions, dtype=int) - 1]
    return float(-np.log(np.maximum(chosen, floor)).mean())


def head_to_head(results: pd.DataFrame, drivers=None) -> tuple[list[str], np.ndarray]:
    """P[i, j] = chance driver i finishes ahead of driver j, from per-sim results."""
    positions = results.pivot(index='sim_id', columns='Driver', values='finish_position')
    if drivers is not None:
        positions = positions[list(drivers)]
    values = positions.to_numpy(float)
    if np.isnan(values).any():
        raise ValueError('Every simulation needs every driver.')
    ahead = np.zeros((values.shape[1], values.shape[1]))
    for i in range(values.shape[1]):
        ahead[i] = (values[:, [i]] < values).mean(axis=0)
    return [str(d) for d in positions.columns], ahead


def head_to_head_brier(ahead: np.ndarray, actual_positions, teams=None) -> dict[str, float | int | None]:
    """Brier over each unordered pair, plus the teammate subset when teams are given."""
    actual_positions = np.asarray(actual_positions, dtype=int)
    upper = np.triu_indices(len(actual_positions), k=1)
    outcome = (actual_positions[:, None] < actual_positions[None, :]).astype(float)
    errors = (ahead[upper] - outcome[upper]) ** 2
    scores: dict[str, float | int | None] = {'pair_brier': float(errors.mean()), 'pairs': int(errors.size)}
    if teams is not None:
        teams = np.asarray(teams).astype(str)
        mates = teams[upper[0]] == teams[upper[1]]
        scores['teammate_brier'] = float(errors[mates].mean()) if mates.any() else None
        scores['teammate_pairs'] = int(mates.sum())
    return scores


def threshold_rps(forecast: pd.DataFrame, actual: pd.DataFrame) -> float:
    """RPS over the win, podium and top-10 thresholds stored by every saved forecast."""
    positions = _actual_positions(actual, forecast['Driver'].astype(str))
    errors = [(pd.to_numeric(forecast[column], errors='coerce').to_numpy(float)
               - (positions <= limit)) ** 2 for column, limit in THRESHOLDS]
    return float(np.mean(errors))


def race_scores(summary: pd.DataFrame, position_matrix: pd.DataFrame, results: pd.DataFrame,
                actual: pd.DataFrame) -> dict[str, float | int | None]:
    """Every score for one race from simulate_races outputs and the official order.

    actual needs Driver and Position (a complete 1..n order).
    """
    drivers, probabilities = position_probabilities(position_matrix)
    positions = _actual_positions(actual, drivers)
    pair_drivers, ahead = head_to_head(results, drivers)
    teams = summary.set_index('Driver').loc[pair_drivers, 'Team'] if 'Team' in summary else None
    merged = summary.set_index('Driver').loc[drivers]
    return {
        'finish_mae': float(np.abs(merged['avg_finish'].to_numpy(float) - positions).mean()),
        **{metric: float(((merged[column].to_numpy(float) - (positions <= limit)) ** 2).mean())
           for (column, limit), metric in zip(THRESHOLDS, ('win_brier', 'podium_brier', 'top10_brier'))},
        'rps': ranked_probability_score(probabilities, positions),
        'log_score': position_log_score(probabilities, positions),
        'threshold_rps': threshold_rps(merged.reset_index(), actual),
        **head_to_head_brier(ahead, positions, None if teams is None else teams.to_numpy()),
    }
