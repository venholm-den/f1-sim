"""Fit several simulation settings jointly against several accuracy scores.

Follows the Pitwall Monte Carlo calibration objective (arXiv 2607.06495):
maximise rank correlation minus 2x Brier minus 1x expected calibration error,
with bounded differential evolution. Whole seasons are blocked: settings are
fitted on earlier seasons and scored once on later held-out seasons.

This is offline evidence for review. It never edits SIMULATION_PARAMETERS or
any config file; tuned values reach the engine only through the per-call
``parameter_overrides`` argument of ``simulate_races``.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.accuracy_benchmark import build_replay_inputs, evaluate_forecast, session_input_frame, simple_baseline
from src.model_config import SIMULATION_PARAMETERS
from src.simulate import simulate_races


# Bounds contain every live default, so the current engine is a feasible point.
TUNABLE_BOUNDS = {
    'race_pace_seconds_multiplier': (0.05, 0.60),
    'grid_loss_multiplier': (0.0, 15.0),
    'race_noise_multiplier': (1.0, 8.0),
    'start_noise_seconds': (0.25, 4.0),
    'strategy_loss_multiplier': (0.5, 6.0),
}
OBJECTIVE_WEIGHTS = {'spearman': 1.0, 'brier': 2.0, 'ece': 1.0}
OUTCOMES = [('win_chance', 1), ('podium_chance', 3), ('points_chance', 10)]
# A profile spanning less than this objective change is reported as weakly identified.
IDENTIFIABILITY_TOLERANCE = 0.005
# 2026 races are reserved for prospective trials and earlier benchmarks.
RESERVED_YEARS = (2026,)


@dataclass
class Episode:
    year: int
    round: int
    event: str
    session: str
    split: str
    features: pd.DataFrame
    track: dict
    weather: dict
    actual: pd.DataFrame
    grid_metrics: dict

    @property
    def key(self):
        return self.year, self.round


def live_parameters(names=TUNABLE_BOUNDS) -> dict[str, float]:
    return {name: float(SIMULATION_PARAMETERS[name]) for name in names}


def expected_calibration_error(probabilities, outcomes, n_bins=10) -> float:
    """Count-weighted gap between mean forecast and observed rate per bin."""
    probabilities = np.asarray(probabilities, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probabilities.size == 0:
        raise ValueError('No probabilities to calibrate.')
    bins = np.clip((probabilities * n_bins).astype(int), 0, n_bins - 1)
    error = 0.0
    for number in np.unique(bins):
        mask = bins == number
        error += mask.sum() * abs(probabilities[mask].mean() - outcomes[mask].mean())
    return float(error / probabilities.size)


def brier_decomposition(probabilities, outcomes, n_bins=10) -> dict:
    """Murphy split: Brier ~= reliability - resolution + uncertainty (binned)."""
    probabilities = np.asarray(probabilities, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    base_rate = outcomes.mean()
    bins = np.clip((probabilities * n_bins).astype(int), 0, n_bins - 1)
    reliability = resolution = 0.0
    for number in np.unique(bins):
        mask = bins == number
        weight = mask.sum() / probabilities.size
        observed = outcomes[mask].mean()
        reliability += weight * (probabilities[mask].mean() - observed) ** 2
        resolution += weight * (observed - base_rate) ** 2
    return {'brier': float(((probabilities - outcomes) ** 2).mean()), 'reliability': float(reliability),
            'resolution': float(resolution), 'uncertainty': float(base_rate * (1 - base_rate))}


def score_predictions(data: pd.DataFrame) -> dict:
    """Score merged prediction rows from one or more races.

    Rank correlation and Brier average races equally; calibration pools all
    driver-outcome probabilities, since one race has too few rows per bin.
    """
    if data.empty:
        raise ValueError('No predictions to score.')
    per_race = []
    for _, race in data.groupby(['year', 'round', 'session']):
        rho = race['avg_finish'].corr(race['actual_position'], method='spearman')
        brier = np.mean([((race[column] - race['actual_position'].le(limit)) ** 2).mean()
                         for column, limit in OUTCOMES])
        per_race.append((0.0 if pd.isna(rho) else rho, brier))
    spearman, brier = (float(value) for value in np.mean(per_race, axis=0))
    probabilities = np.concatenate([data[column].to_numpy(float) for column, _ in OUTCOMES])
    outcomes = np.concatenate([data['actual_position'].le(limit).to_numpy(float) for _, limit in OUTCOMES])
    ece = expected_calibration_error(probabilities, outcomes)
    return {'races': len(per_race), 'spearman': spearman, 'brier': brier, 'ece': ece,
            'objective': objective(spearman, brier, ece)}


def objective(spearman, brier, ece) -> float:
    return float(OBJECTIVE_WEIGHTS['spearman'] * spearman - OBJECTIVE_WEIGHTS['brier'] * brier
                 - OBJECTIVE_WEIGHTS['ece'] * ece)


def season_blocks(races, fit_years, holdout_years, reserved_years=RESERVED_YEARS):
    fit_years, holdout_years = sorted(set(fit_years)), sorted(set(holdout_years))
    if not fit_years or not holdout_years:
        raise ValueError('Choose at least one fit season and one held-out season.')
    if max(fit_years) >= min(holdout_years):
        raise ValueError('Every fit season must precede every held-out season.')
    reserved = set(reserved_years) & set(fit_years + holdout_years)
    if reserved:
        raise ValueError(f'Seasons {sorted(reserved)} are reserved for prospective validation.')
    return {race.key: 'fit' if race.year in fit_years else 'holdout'
            for race in races if race.year in fit_years + holdout_years}


def build_episodes(races, splits, *, sessions=('Q',), n_baseline_races=2, skipped=None):
    """Features never depend on tuned settings, so build them once per episode."""
    races = sorted(races, key=lambda race: race.key)
    if len({race.key for race in races}) != len(races):
        raise ValueError('Duplicate race keys.')
    skipped = [] if skipped is None else skipped
    episodes = []
    for index, race in enumerate(races):
        split = splits.get(race.key)
        if split is None:
            continue
        for code in sessions:
            metadata = dict(year=race.year, round=race.round, event=race.event, session=code)
            if index < n_baseline_races:
                skipped.append(dict(metadata, reason='insufficient_baseline_races'))
                continue
            current = None if code == 'PRE' else race.sessions.get(code)
            if (code != 'PRE' and current is None) or 'R' not in race.sessions:
                skipped.append(dict(metadata, reason='session_not_cached'))
                continue
            try:
                features, track, weather = build_replay_inputs(current, races[:index], metadata=metadata,
                                                               n_baseline_races=n_baseline_races)
                actual = race.sessions['R'].results
                grid, _ = evaluate_forecast(simple_baseline(features, races[:index], 'grid_order',
                                                            n_baseline_races=n_baseline_races), actual)
            except (ValueError, KeyError) as exc:
                skipped.append(dict(metadata, reason=str(exc)))
                continue
            episodes.append(Episode(race.year, race.round, race.event, code, split,
                                    features, track, weather, actual, grid))
    return episodes


def predict_episode(episode: Episode, parameters: dict, *, n_sims: int, seed: int) -> pd.DataFrame:
    forecast, _, _ = simulate_races(episode.features, n_sims=n_sims, seed=seed,
        overtaking_difficulty=episode.track['overtaking_difficulty'],
        weather_modifiers=episode.weather, parameter_overrides=parameters)
    _, data = evaluate_forecast(forecast, episode.actual)
    return data.assign(year=episode.year, round=episode.round, session=episode.session,
                       split=episode.split)


def predict_episodes(episodes, parameters, *, n_sims, seeds) -> pd.DataFrame:
    """Average seeds per driver so repeated seeds never inflate calibration counts."""
    rows = [predict_episode(episode, parameters, n_sims=n_sims, seed=seed)
            for episode in episodes for seed in seeds]
    data = pd.concat(rows, ignore_index=True)
    columns = ['avg_finish'] + [column for column, _ in OUTCOMES]
    keys = ['year', 'round', 'session', 'split', 'Driver']
    return data.groupby(keys, as_index=False).agg(
        {**{column: 'mean' for column in columns}, 'actual_position': 'first'})


def fit_parameters(episodes, *, bounds=TUNABLE_BOUNDS, n_sims=500, seed=42, maxiter=12,
                   popsize=6, optimizer_seed=7):
    """Bounded differential evolution on fit-season episodes only.

    One fixed simulation seed is shared by every candidate (common random
    numbers), so objective differences reflect settings, not sampling noise.
    """
    from scipy.optimize import differential_evolution

    fit = [episode for episode in episodes if episode.split == 'fit']
    if not fit:
        raise ValueError('No fit-season episodes were built.')
    names = list(bounds)
    history = []

    def loss(vector):
        parameters = dict(zip(names, (float(value) for value in vector)))
        scores = score_predictions(predict_episodes(fit, parameters, n_sims=n_sims, seeds=[seed]))
        history.append(dict(parameters, **scores))
        return -scores['objective']

    live = live_parameters(names)
    # Seeding the population with the live settings guarantees they are considered.
    rng = np.random.default_rng(optimizer_seed)
    size = max(5, popsize * len(names))
    low = np.array([bounds[name][0] for name in names])
    high = np.array([bounds[name][1] for name in names])
    population = low + rng.random((size, len(names))) * (high - low)
    population[0] = [live[name] for name in names]
    result = differential_evolution(loss, list(zip(low, high)), init=population, maxiter=maxiter,
                                    seed=optimizer_seed, polish=False, tol=0, updating='immediate')
    tuned = dict(zip(names, (float(value) for value in result.x)))
    return tuned, pd.DataFrame(history), {'nfev': int(result.nfev), 'nit': int(result.nit),
                                          'message': str(result.message)}


def identifiability_profile(episodes, tuned, *, bounds=TUNABLE_BOUNDS, n_sims=500, seed=42, points=5):
    """Vary one setting across its bounds with the rest held at the fit.

    A flat profile means the fit seasons cannot pin that setting down, so its
    tuned value should not be trusted on its own.
    """
    fit = [episode for episode in episodes if episode.split == 'fit']
    rows = []
    for name, (low, high) in bounds.items():
        for value in np.linspace(low, high, points):
            parameters = dict(tuned, **{name: float(value)})
            scores = score_predictions(predict_episodes(fit, parameters, n_sims=n_sims, seeds=[seed]))
            rows.append(dict(parameter=name, value=float(value), objective=scores['objective']))
    profile = pd.DataFrame(rows)
    spans = profile.groupby('parameter').objective.agg(lambda values: values.max() - values.min())
    return profile, {name: {'objective_span': float(span),
                            'identified': bool(span >= IDENTIFIABILITY_TOLERANCE)}
                     for name, span in spans.items()}


def calibration_table(data: pd.DataFrame, n_bins=10) -> pd.DataFrame:
    """Reliability-diagram rows per variant, split and outcome."""
    rows = []
    for (variant, split), group in data.groupby(['variant', 'split']):
        for column, limit in OUTCOMES:
            bins = np.clip((group[column] * n_bins).astype(int), 0, n_bins - 1)
            for number, part in group.groupby(bins):
                rows.append(dict(variant=variant, split=split, outcome=column, bucket=int(number),
                                 count=len(part), predicted=float(part[column].mean()),
                                 observed=float(part['actual_position'].le(limit).mean())))
    return pd.DataFrame(rows)


def promotion_decision(live, tuned, holdout_races, *, min_gain=0.01, min_holdout_races=6):
    reasons = []
    if holdout_races < min_holdout_races:
        reasons.append(f'only {holdout_races} unseen held-out races; {min_holdout_races} required')
    if tuned['objective'] - live['objective'] < min_gain:
        reasons.append(f'held-out objective gain below {min_gain}')
    for metric in ('brier', 'ece'):
        if tuned[metric] > live[metric]:
            reasons.append(f'held-out {metric} regressed')
    if tuned['spearman'] < live['spearman']:
        reasons.append('held-out rank correlation regressed')
    return not reasons, reasons


def inspected_race_keys(paths) -> set[tuple[int, int]]:
    keys = set()
    for path in paths:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
        for field in ('development_races', 'holdout_races', 'evaluated_races', 'attempted_races',
                      'fit_races'):
            keys.update(tuple(int(part) for part in key) for key in report.get(field, []))
        keys.update((int(row['year']), int(row['round'])) for row in report.get('skipped', [])
                    if 'year' in row and 'round' in row)
    return keys


def tune_multi_score(races, output_dir, *, fit_years, holdout_years, sessions=('Q',),
                     bounds=TUNABLE_BOUNDS, tune_sims=500, eval_sims=2000, seeds=(42, 123, 777),
                     maxiter=12, popsize=6, optimizer_seed=7, inspected_reports=(), load_failures=None,
                     n_baseline_races=2, min_holdout_races=6):
    import fastf1
    fastf1.Cache.offline_mode(True)
    if set(sessions) - {'PRE', 'FP2', 'Q'} or not sessions:
        raise ValueError('Choose PRE, FP2 and/or Q stages.')
    if set(bounds) - set(SIMULATION_PARAMETERS):
        raise ValueError('Only existing simulation parameters can be tuned.')
    for name, (low, high) in bounds.items():
        if not 0 <= low < high <= 50:
            raise ValueError(f'Bounds for {name} must satisfy 0 <= low < high <= 50.')
    seeds = list(dict.fromkeys(int(seed) for seed in seeds))
    if not seeds or tune_sims < 100 or eval_sims < 100:
        raise ValueError('Use at least one seed and 100 simulations.')
    splits = season_blocks(races, fit_years, holdout_years)
    inspected = inspected_race_keys(inspected_reports)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)

    skipped = []
    episodes = build_episodes(races, splits, sessions=tuple(dict.fromkeys(sessions)),
                              n_baseline_races=n_baseline_races, skipped=skipped)
    holdout = [episode for episode in episodes if episode.split == 'holdout']
    if not holdout:
        raise ValueError('No held-out episodes were built.')
    print(f'Tuning on {len(episodes) - len(holdout)} fit episodes', flush=True)
    tuned, history, optimizer = fit_parameters(episodes, bounds=bounds, n_sims=tune_sims, seed=seeds[0],
                                               maxiter=maxiter, popsize=popsize,
                                               optimizer_seed=optimizer_seed)
    profile, identifiability = identifiability_profile(episodes, tuned, bounds=bounds,
                                                       n_sims=tune_sims, seed=seeds[0])
    live = live_parameters(bounds)
    print('Scoring live and tuned settings on every split', flush=True)
    predictions = pd.concat([
        predict_episodes(episodes, parameters, n_sims=eval_sims, seeds=seeds).assign(variant=variant)
        for variant, parameters in (('live', live), ('tuned', tuned))], ignore_index=True)
    predictions['previously_inspected'] = [key in inspected for key in zip(predictions.year, predictions['round'])]

    summary, decompositions = [], []
    for (variant, split), group in predictions.groupby(['variant', 'split']):
        summary.append(dict(variant=variant, split=split, scope='all', **score_predictions(group)))
        unseen = group[~group.previously_inspected]
        if split == 'holdout' and not unseen.empty:
            summary.append(dict(variant=variant, split=split, scope='unseen', **score_predictions(unseen)))
        for column, limit in OUTCOMES:
            decompositions.append(dict(variant=variant, split=split, outcome=column,
                **brier_decomposition(group[column], group['actual_position'].le(limit))))
    grid = pd.DataFrame([dict(year=e.year, round=e.round, session=e.session, split=e.split, **e.grid_metrics)
                         for e in episodes])
    summary = pd.DataFrame(summary)

    def row(variant, scope='unseen'):
        match = summary[(summary.variant == variant) & (summary.split == 'holdout') & (summary.scope == scope)]
        return json.loads(match.iloc[0].to_json()) if not match.empty else None

    live_holdout, tuned_holdout = row('live'), row('tuned')
    if live_holdout is None:
        passed, reasons, unseen_races = False, ['every held-out race was previously inspected'], 0
    else:
        unseen_races = int(live_holdout['races'])
        passed, reasons = promotion_decision(live_holdout, tuned_holdout, unseen_races,
                                             min_holdout_races=min_holdout_races)

    root = Path(__file__).resolve().parents[1]
    source_files = ['src/multi_score_tuning.py', 'src/accuracy_benchmark.py', 'src/simulate.py',
                    'src/model_config.py', 'src/features.py', 'src/model.py', 'src/grid.py',
                    'src/performance.py', 'src/reliability.py', 'src/track.py', 'data/track_profiles.csv']
    input_hashes = {}
    for race in races:
        if race.key not in splits:
            continue
        for code, session in race.sessions.items():
            for name in ('laps', 'results'):
                data = session_input_frame(session, name).to_csv(index=True).encode('utf-8')
                input_hashes[f'{race.year}/{race.round}/{code}/{name}'] = hashlib.sha256(data).hexdigest()

    history.to_csv(output_dir / 'optimizer_history.csv', index=False)
    profile.to_csv(output_dir / 'identifiability_profile.csv', index=False)
    predictions.to_csv(output_dir / 'predictions.csv', index=False)
    summary.to_csv(output_dir / 'summary.csv', index=False)
    pd.DataFrame(decompositions).to_csv(output_dir / 'brier_decomposition.csv', index=False)
    calibration_table(predictions).to_csv(output_dir / 'calibration_bins.csv', index=False)
    grid.to_csv(output_dir / 'grid_order_baseline.csv', index=False)
    artifacts = ['optimizer_history.csv', 'identifiability_profile.csv', 'predictions.csv', 'summary.csv',
                 'brier_decomposition.csv', 'calibration_bins.csv', 'grid_order_baseline.csv']
    report = {
        'schema_version': 1,
        'objective': 'spearman - 2 x mean(win, podium, top-10 Brier) - 1 x pooled 10-bin ECE (higher is better)',
        'objective_weights': OBJECTIVE_WEIGHTS,
        'fit_years': sorted(set(fit_years)), 'holdout_years': sorted(set(holdout_years)),
        'sessions': list(sessions), 'bounds': {name: list(pair) for name, pair in bounds.items()},
        'live_parameters': live, 'tuned_parameters': tuned,
        'identifiability': identifiability, 'optimizer': dict(optimizer, method='differential_evolution',
            maxiter=maxiter, popsize=popsize, optimizer_seed=optimizer_seed, tune_sims=tune_sims,
            tune_seed=seeds[0]),
        'eval_sims': eval_sims, 'eval_seeds': seeds,
        'fit_races': [list(key) for key in sorted({e.key for e in episodes if e.split == 'fit'})],
        'holdout_races_evaluated': [list(key) for key in sorted({e.key for e in holdout})],
        'previously_inspected_holdout_races': [list(key) for key in
                                               sorted({e.key for e in holdout if e.key in inspected})],
        'unseen_holdout_race_count': unseen_races,
        'holdout_live': live_holdout, 'holdout_tuned': tuned_holdout,
        'promotion_gate_passed': passed, 'promotion_reasons': reasons,
        'promotion_gate': f'>= {min_holdout_races} unseen held-out races, >= 0.01 held-out objective gain, '
                          'no held-out Brier, ECE or rank-correlation regression',
        'live_defaults_changed': False,
        'limitations': ['Retrospective reconstruction from cached feeds, not attested snapshots.',
            'Tuning uses one shared simulation seed; held-out scoring averages several seeds.',
            'Weakly identified settings are not supported by the fit seasons on their own.',
            'Passing the gate is evidence for review, not automatic deployment.',
            f'Seasons {list(RESERVED_YEARS)} are refused to protect prospective trials.'],
        'input_sha256': input_hashes,
        'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in source_files if (root / name).is_file()},
        'inspected_reports': [str(path) for path in inspected_reports],
        'load_failures': list(load_failures or []), 'skipped': skipped,
        'artifact_sha256': {name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
                            for name in artifacts},
    }
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False, default=float),
                                            encoding='utf-8')
    return report
