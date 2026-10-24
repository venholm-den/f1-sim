"""Promotion lanes, power checks and a sequential test for model candidates.

Two lanes, because two kinds of change reach the model:

- correctness: the candidate gives the model a fact it was missing (announced
  grid penalties, that a sprint race happens).
  It must not make replays worse beyond simulation noise, and it is not
  expected to win a fresh-race contest by a margin.
- accuracy: the candidate changes model judgement (fitted or assumed
  parameters, new mechanisms). It needs at least six fresh races per stage,
  at least 5% lower paired RPS, no Brier regression, and no finish MAE
  regression beyond twice the seed noise. RPS
  replaced the MAE-dominated loss as the primary metric on 24 October 2026;
  the loss is still reported.

Power: the spread of per-race paired differences decides the smallest gain a
number of races can detect. Reports state it so a gate that cannot decide is
visible before any races are spent.

Sequential test: a betting e-process on clipped paired loss differences. It
stays valid however often it is checked, so a season-long challenger can be
looked at after every race without inflating false positives.

Nothing here activates a model. Every decision says activated: False.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

LANES = ('correctness', 'accuracy')

# (config key, value) -> why it is a correctness change. Everything else is accuracy.
CORRECTNESS = {
    ('grid_penalty_model', 'announced_v1'):
        "Applies stewards' published grid penalties, so the grid matches the one the race starts from.",
    ('sprint_model', 'sprint_v1'):
        'Simulates and scores the sprint race that actually takes place on a sprint weekend.',
}

# Full RPS needs a position matrix; threshold RPS is the fallback for rows
# that only carry win/podium/top-10 chances.
ACCURACY_GATE = {'min_races': 6, 'primary_metrics': ('rps', 'threshold_rps'), 'min_primary_improvement': 0.05,
                 'no_regression': ('win_brier', 'podium_brier', 'top10_brier', 'dnf_brier'),
                 # Finish MAE may not get worse beyond simulation noise; same rule as the correctness lane.
                 'noise_tolerant_no_regression': ('finish_mae',)}
CORRECTNESS_GATE = {'min_races': 6, 'noise_multiple': 2.0, 'tolerance_floor': 1e-4,
                    'metrics': ('finish_mae', 'win_brier', 'podium_brier', 'top10_brier', 'rps')}
LOSS = ('finish_mae', 'top10_brier')
# Pair counts describe the race, not forecast quality.
COUNT_COLUMNS = {'pairs', 'teammate_pairs'}
# Declared clip bounds for the sequential test: a plausible largest per-race
# paired difference. Assumptions, set before looking at any challenger result.
SEQUENTIAL_BOUNDS = {'loss': 1.0, 'rps': 0.05, 'pair_brier': 0.05, 'log_score': 1.0}


def lane_for(key: str, value: str) -> str:
    return 'correctness' if (str(key), str(value)) in CORRECTNESS else 'accuracy'


def lane_reason(key: str, value: str) -> str:
    return CORRECTNESS.get((str(key), str(value)),
                           'Changes model judgement, so it needs fresh-race evidence.')


def paired_races(seed_rows: pd.DataFrame, candidate: str, baseline: str,
                 race_keys=('round',)) -> pd.DataFrame:
    """Average seeds within each race, then pair candidate and baseline by race.

    seed_rows is the long format the offline benchmarks write: one row per race,
    seed and arm, with metric columns. Each race counts once.
    """
    keys = [k for k in race_keys if k in seed_rows]
    if not keys:
        raise ValueError('Metric rows need a race key such as round.')
    metrics = [c for c in seed_rows.select_dtypes('number').columns
               if c not in {*keys, 'seed', *COUNT_COLUMNS}]
    means = seed_rows.groupby(keys + ['arm'], as_index=False)[metrics].mean()
    left = means[means.arm.eq(candidate)].drop(columns='arm')
    right = means[means.arm.eq(baseline)].drop(columns='arm')
    if left.empty or right.empty:
        raise ValueError(f'Need rows for both {candidate} and {baseline}.')
    pair = left.merge(right, on=keys, suffixes=('_candidate', '_baseline'))
    for metric in metrics:
        if metric + '_candidate' in pair:
            pair[metric + '_delta'] = pair[metric + '_candidate'] - pair[metric + '_baseline']
    if all(m + '_delta' in pair for m in LOSS):
        pair['loss_delta'] = sum(pair[m + '_delta'] for m in LOSS)
        pair['loss_baseline'] = sum(pair[m + '_baseline'] for m in LOSS)
    return pair


def seed_noise(seed_rows: pd.DataFrame, arm: str, metric: str, race_keys=('round',)) -> float:
    """Standard error of an arm's race-averaged metric that comes from simulation seeds alone."""
    keys = [k for k in race_keys if k in seed_rows]
    rows = seed_rows[seed_rows.arm.eq(arm) & seed_rows.seed.notna()]
    if rows.empty or metric not in rows:
        return 0.0
    spread = rows.groupby(keys)[metric].agg(['std', 'count'])
    spread = spread[spread['count'] > 1]
    if spread.empty:
        return 0.0
    per_race = spread['std'] / np.sqrt(spread['count'])
    return float(np.sqrt((per_race ** 2).sum()) / len(per_race))


def minimum_detectable_effect(sd: float, races: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest true mean paired improvement a one-sided test detects with this power."""
    if races < 2 or not np.isfinite(sd):
        return float('inf')
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(power)
    return float(z * sd / np.sqrt(races))


def races_needed(sd: float, effect: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Races required to detect a true mean paired improvement of `effect`."""
    if effect <= 0 or not np.isfinite(sd):
        raise ValueError('Effect must be positive and spread finite.')
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(power)
    return max(2, int(np.ceil((z * sd / effect) ** 2)))


def power_table(pair: pd.DataFrame, races=(6, 12, 24), alpha: float = 0.05,
                power: float = 0.8) -> pd.DataFrame:
    """Per metric: spread of race-level differences and what each race count can detect."""
    rows = []
    for column in [c for c in pair if c.endswith('_delta')]:
        deltas = pair[column].dropna().to_numpy(float)
        if len(deltas) < 2:
            continue
        sd, mean = float(deltas.std(ddof=1)), float(deltas.mean())
        observed_needed = races_needed(sd, -mean, alpha, power) if mean < 0 and sd > 0 else None
        rows.append({'metric': column[:-len('_delta')], 'races_observed': len(deltas),
                     'mean_delta': mean, 'sd_delta': sd,
                     'improvement_in_sds': -mean / sd if sd > 0 else None,
                     'races_to_detect_observed_gain': observed_needed,
                     **{f'detectable_with_{n}': minimum_detectable_effect(sd, n, alpha, power) for n in races}})
    return pd.DataFrame(rows)


def betting_e_value(deltas, bound: float, alpha: float = 0.05,
                    bets=(0.05, 0.1, 0.2, 0.3, 0.5)) -> dict:
    """Anytime-valid evidence that the candidate lowers the loss.

    deltas are per-race (candidate minus baseline) loss differences in race
    order; lower is better. Null hypothesis: the candidate is no better, so
    the mean of -delta is at most zero. Each difference is clipped to
    [-bound, bound] (a declared assumption) and the e-value is the mean
    wealth over a fixed grid of bets, which is itself a test supermartingale.
    Reject the null when the e-value reaches 1 / alpha. Checking after every
    race is allowed.
    """
    if bound <= 0:
        raise ValueError('Bound must be positive.')
    gains = -np.clip(np.asarray(deltas, dtype=float), -bound, bound) / bound
    wealth = np.ones(len(bets))
    path = []
    for gain in gains:
        wealth *= 1 + np.asarray(bets) * gain
        path.append(float(wealth.mean()))
    e_value = path[-1] if path else 1.0
    return {'races': int(len(gains)), 'e_value': e_value, 'threshold': 1 / alpha,
            'max_e_value': max(path, default=1.0), 'evidence_path': path,
            'candidate_better': bool(max(path, default=1.0) >= 1 / alpha),
            'clip_bound': float(bound), 'alpha': alpha}


def correctness_decision(seed_rows: pd.DataFrame, candidate: str, baseline: str,
                         race_keys=('round',)) -> dict:
    """Pass when no metric is worse than simulation noise allows, on enough replays."""
    gate = CORRECTNESS_GATE
    pair = paired_races(seed_rows, candidate, baseline, race_keys)
    reasons, checks = [], {}
    if len(pair) < gate['min_races']:
        reasons.append(f"Only {len(pair)} paired races; at least {gate['min_races']} are required.")
    for metric in gate['metrics']:
        if metric + '_delta' not in pair:
            continue
        noise = np.hypot(seed_noise(seed_rows, candidate, metric, race_keys),
                         seed_noise(seed_rows, baseline, metric, race_keys))
        tolerance = max(gate['noise_multiple'] * noise, gate['tolerance_floor'])
        delta = float(pair[metric + '_delta'].mean())
        checks[metric] = {'mean_delta': delta, 'tolerance': tolerance, 'passed': delta <= tolerance}
        if delta > tolerance:
            reasons.append(f'{metric} is worse by {delta:.4f}, beyond the {tolerance:.4f} noise tolerance.')
    if not checks:
        reasons.append('No comparable metrics.')
    return {'lane': 'correctness', 'candidate': candidate, 'baseline': baseline,
            'paired_races': len(pair), 'checks': checks, 'passed': not reasons,
            'reasons': reasons, 'activated': False, 'promotion_approved': False}


def sequential_tests(pair: pd.DataFrame, bounds=None) -> dict:
    """One e-value per scored metric with a declared bound, in race order."""
    bounds = SEQUENTIAL_BOUNDS if bounds is None else bounds
    order = pair.sort_values([c for c in ('year', 'round') if c in pair])
    return {metric: betting_e_value(order[metric + '_delta'], bound)
            for metric, bound in bounds.items() if metric + '_delta' in order}


def accuracy_decision(seed_rows: pd.DataFrame, candidate: str, baseline: str,
                      race_keys=('round',), bounds=None) -> dict:
    """The fresh-race gate, with power and the sequential tests alongside."""
    gate = ACCURACY_GATE
    pair = paired_races(seed_rows, candidate, baseline, race_keys)
    reasons = []
    if len(pair) < gate['min_races']:
        reasons.append(f"Only {len(pair)} paired races; at least {gate['min_races']} are required.")
    primary = next((m for m in gate['primary_metrics'] if m + '_delta' in pair), None)
    improvement = None
    if primary is None:
        reasons.append('RPS or threshold RPS is needed for the primary metric.')
    elif float(pair[primary + '_baseline'].mean()) > 0:
        improvement = float(-pair[primary + '_delta'].mean() / pair[primary + '_baseline'].mean())
        if improvement < gate['min_primary_improvement']:
            reasons.append(f'{primary} improvement {improvement:.1%} is below 5%.')
    else:
        reasons.append(f'Baseline {primary} is zero; improvement is undefined.')
    loss_improvement = None
    if 'loss_delta' in pair and float(pair.loss_baseline.mean()) > 0:
        loss_improvement = float(-pair.loss_delta.mean() / pair.loss_baseline.mean())
    for metric in gate['no_regression']:
        if metric + '_delta' in pair and float(pair[metric + '_delta'].mean()) > 0:
            reasons.append(f'{metric} regressed.')
    for metric in gate['noise_tolerant_no_regression']:
        if metric + '_delta' not in pair:
            continue
        noise = np.hypot(seed_noise(seed_rows, candidate, metric, race_keys),
                         seed_noise(seed_rows, baseline, metric, race_keys))
        tolerance = max(CORRECTNESS_GATE['noise_multiple'] * noise, CORRECTNESS_GATE['tolerance_floor'])
        delta = float(pair[metric + '_delta'].mean())
        if delta > tolerance:
            reasons.append(f'{metric} regressed by {delta:.4f}, beyond the {tolerance:.4f} noise tolerance.')
    return {'lane': 'accuracy', 'candidate': candidate, 'baseline': baseline,
            'paired_races': len(pair), 'primary_metric': primary, 'primary_improvement': improvement,
            'loss_improvement': loss_improvement, 'power': power_table(pair).to_dict('records'), 'sequential': sequential_tests(pair, bounds),
            'passed': not reasons, 'reasons': reasons, 'activated': False, 'promotion_approved': False}
