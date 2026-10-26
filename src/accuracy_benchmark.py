"""Reconstruct pre-race inputs and evaluate whole races chronologically.

This is a retrospective feature-cutoff benchmark. Cached feeds can contain
later corrections; it does not assert historical publication timestamps.
"""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from src.features import build_driver_features, _prepare_laps
from src.accuracy_candidates import (SUPPORTED_VARIANTS, decouple_feature_dnf,
    normalise_historical_pace, target_reference_lap, single_pace_blend, candidate_grid_multiplier,
    single_degradation)
from src.retirement_risk import apply_retirement_risk
from src.retirement_progress import attach_retirement_progress
from src.accuracy_candidates import candidate_simulation_options
from src.forecast_roster import session_roster, validate_roster
from src.grid import build_grid_features
from src.long_run_pace import attach_long_run_pace
from src.model import build_model_features
from src.performance import add_performance_profile
from src.reliability import infer_reliability_profile, apply_reliability_profile
from src.simulate import simulate_races
from src.track import load_track_profile
from src.weather import summarize_weather
from src.venues import venue_for_context


@dataclass
class ReplayRace:
    year: int
    round: int
    event: str
    sessions: dict

    @property
    def key(self):
        return self.year, self.round


def session_input_frame(session, name):
    try:
        return getattr(session, name, pd.DataFrame())
    except Exception:
        if name != 'weather_data':
            raise
        return pd.DataFrame()


def empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=['Driver', 'Team', 'relative_pace', 'race_pace',
        'best_lap', 'lap_std', 'deg_per_lap', 'clean_laps', 'raw_laps', 'dnf_prob'])


def build_replay_inputs(current, previous: list[ReplayRace], *, metadata: dict,
                        practice=None, candidate=False, feature_variant='legacy',
                        n_baseline_races=2, retirement_history_races=30):
    """The target race's results, laps and weather are never arguments here."""
    metadata = {**metadata, 'venue': venue_for_context(metadata, session=current)}
    cutoff = int(metadata['year']), int(metadata['round'])
    if n_baseline_races < 1 or retirement_history_races < 1:
        raise ValueError('History lengths must be positive.')
    previous = sorted(previous, key=lambda race: race.key)
    if len({race.key for race in previous}) != len(previous):
        raise ValueError('Duplicate baseline race keys.')
    if any(race.key >= cutoff for race in previous):
        raise ValueError('A baseline race is at or after the target cutoff.')
    if feature_variant not in SUPPORTED_VARIANTS or (candidate and feature_variant != 'legacy'):
        raise ValueError('Choose one independent feature variant; combinations are not supported.')
    frames = []
    recent = []
    for age, race in enumerate(reversed(previous[-n_baseline_races:])):
        session = race.sessions['R']
        frame = build_driver_features(session.laps, use_stint_pace=candidate)
        frame['baseline_age'] = age
        frame['source_round'] = race.round
        frames.append(frame)
        recent.append((session, {'year': race.year, 'event': race.event, 'round': race.round}))
    if not frames:
        raise ValueError('No prior race baselines available.')
    baseline = pd.concat(frames, ignore_index=True)
    current_features = empty_features() if current is None else build_driver_features(
        current.laps, use_stint_pace=candidate
    )
    reference, reference_source = None, None
    if feature_variant == 'decoupled_dnf_v1':
        current_features = decouple_feature_dnf(current_features)
        baseline = decouple_feature_dnf(baseline)
    elif feature_variant == 'normalised_history_v1':
        reference, reference_source = target_reference_lap(
            current_features, previous, metadata['event'], build_driver_features)
        # Each source session must use its own denominator before concatenation.
        baseline = pd.concat([normalise_historical_pace(frame, reference) for frame in frames],
                             ignore_index=True)
    if candidate and metadata['session'] == 'Q':
        laps = _prepare_laps(practice.laps) if practice is not None else pd.DataFrame()
        clean = laps[laps['TruePaceEligible']] if not laps.empty else laps
        current_features = attach_long_run_pace(current_features, clean)
    roster = session_roster(current if current is not None else recent[0][0])
    features = validate_roster(build_model_features(current_features, baseline, metadata['session']), roster)
    features = build_grid_features(features, current_features, metadata['session'], current)
    features = apply_reliability_profile(features, infer_reliability_profile(recent))
    features = add_performance_profile(features, current_features, baseline,
                                        metadata['session'], metadata)
    if feature_variant in {'all_cause_dnf_v2', 'retirement_progress_v1', 'single_pace_retirement_v1'}:
        history = []
        for race in previous[-retirement_history_races:]:
            context = {'year': race.year, 'round': race.round, 'event': race.event}
            context['venue'] = venue_for_context(context, session=race.sessions['R'])
            history.append((race.sessions['R'], context))
        features = apply_retirement_risk(features, history, metadata)
        if feature_variant in {'retirement_progress_v1', 'single_pace_retirement_v1'}:
            features = attach_retirement_progress(features, history, metadata)
    if feature_variant in {'single_pace_blend_v1', 'single_pace_retirement_v1'}:
        features = single_pace_blend(features, metadata['session'])
    if feature_variant == 'single_degradation_v1':
        features = single_degradation(features)
    if feature_variant == 'qualifying_partial_pooling_v1':
        if metadata['session'] != 'Q':
            raise ValueError('Qualifying pace candidate is available only after Q.')
        from src.qualifying_features import attach_current_qualifying
        from src.qualifying_pace import fit_qualifying_pace, apply_qualifying_pace
        history = []
        for race in previous:
            context = {'year': race.year, 'round': race.round, 'event': race.event}
            context['venue'] = venue_for_context(context, session=race.sessions['R'])
            history.append((race.sessions.get('Q'), race.sessions['R'], context))
        artifact = fit_qualifying_pace(history, metadata)
        features = attach_current_qualifying(features, current, metadata)
        features = apply_qualifying_pace(features, artifact, metadata)
    if feature_variant == 'season_dnf_v1':
        from src.retirement_season import apply_season_retirement_risk
        history = [(r.sessions['R'], {'year': r.year, 'round': r.round, 'event': r.event})
                   for r in previous[-retirement_history_races:]]
        features = apply_season_retirement_risk(features, history, metadata)
    if feature_variant == 'survival_dnf_v1':
        from src.retirement_survival import attach_survival_risk
        history = [(r.sessions['R'], {'year': r.year, 'round': r.round, 'event': r.event})
                   for r in previous[-retirement_history_races:]]
        features = attach_survival_risk(features, history, metadata)
    if feature_variant != 'legacy':
        features['accuracy_feature_variant'] = feature_variant
    if reference is not None:
        features['historical_reference_lap_seconds'] = reference
        features['historical_reference_source'] = reference_source
    track = load_track_profile(metadata['event'], metadata=metadata)
    weather = {} if current is None else summarize_weather(current, use_forecast=False, allow_load=False)
    return features, track, weather


def build_replay_forecast(current, previous: list[ReplayRace], *, metadata: dict,
                          practice=None, candidate=False, n_sims=5000, seed=42,
                          feature_variant='legacy', n_baseline_races=2, retirement_history_races=30):
    features, track, weather = build_replay_inputs(current, previous, metadata=metadata,
        practice=practice, candidate=candidate, feature_variant=feature_variant,
        n_baseline_races=n_baseline_races, retirement_history_races=retirement_history_races)
    forecast, _, _ = simulate_races(features, n_sims=n_sims, seed=seed,
        overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather,
        grid_loss_multiplier=candidate_grid_multiplier(feature_variant, metadata['session']),
        **candidate_simulation_options(feature_variant, features))
    return forecast, features


def simple_baseline(features: pd.DataFrame, previous: list[ReplayRace], mode: str, *, n_baseline_races=2):
    output = features[['Driver', 'Team', 'grid_position']].copy()
    if mode == 'grid_order':
        score = output['grid_position']
    elif mode == 'recent_form':
        observations = []
        for race in previous[-n_baseline_races:]:
            frame = race.sessions['R'].results
            observations.append(pd.DataFrame({'Driver': frame.Abbreviation,
                'position': pd.to_numeric(frame.Position, errors='coerce')}))
        form = pd.concat(observations).groupby('Driver')['position'].mean()
        score = output.Driver.map(form).fillna((len(output) + 1) / 2)
    else:
        raise ValueError('Unknown baseline.')
    output['avg_finish'] = score.rank(method='first')
    for column, threshold in [('win_chance', 1), ('podium_chance', 3), ('points_chance', 10)]:
        output[column] = output.avg_finish.le(threshold).astype(float)
    return output


def evaluate_forecast(prediction: pd.DataFrame, actual: pd.DataFrame):
    actual = actual[['Abbreviation', 'Position']].rename(
        columns={'Abbreviation': 'Driver', 'Position': 'actual_position'})
    actual['actual_position'] = pd.to_numeric(actual.actual_position, errors='coerce')
    if actual.Driver.duplicated().any() or prediction.Driver.duplicated().any():
        raise ValueError('Duplicate driver identifiers.')
    if set(prediction.Driver) != set(actual.Driver) or actual.actual_position.isna().any():
        raise ValueError('Forecast and actual driver coverage differ; scoring skipped.')
    data = prediction.merge(actual, on='Driver', validate='one_to_one')
    metrics = {'finish_mae': float((data.avg_finish - data.actual_position).abs().mean())}
    for column, metric, threshold in [('win_chance', 'win_brier', 1),
        ('podium_chance', 'podium_brier', 3), ('points_chance', 'top10_brier', 10)]:
        metrics[metric] = float(((data[column] - data.actual_position.le(threshold)) ** 2).mean())
    metrics['loss'] = metrics['finish_mae'] + metrics['top10_brier']
    return metrics, data


def calibration_bins(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, threshold in [('win_chance', 1), ('podium_chance', 3), ('points_chance', 10)]:
        for keys, group in predictions.groupby(['variant', 'session', 'split']):
            bucket = (group[column] * 10).astype(int).clip(0, 9)
            for number, part in group.groupby(bucket):
                rows.append(dict(zip(['variant', 'session', 'split'], keys),
                    outcome=column, bucket=int(number), count=len(part),
                    predicted=float(part[column].mean()),
                    observed=float(part.actual_position.le(threshold).mean())))
    return pd.DataFrame(rows)


def chronological_partitions(keys: list[tuple[int, int]], development_fraction=.6):
    keys = sorted(set(keys))
    if len(keys) < 4:
        raise ValueError('At least four evaluable races are required; no training-data fallback.')
    boundary = max(2, min(len(keys) - 2, int(len(keys) * development_fraction)))
    return set(keys[:boundary]), set(keys[boundary:])


def benchmark(races: list[ReplayRace], output_dir: Path, *, n_sims=5000, seed=42,
              sessions=('PRE', 'FP2', 'Q'), load_failures=None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    races = sorted(races, key=lambda race: race.key)
    metrics, predictions, skipped = [], [], []
    # Two earlier races initialise baselines; all later eligible races are evaluated.
    for index, race in enumerate(races[2:], start=2):
        previous = races[:index]
        for code in sessions:
            print(f'Evaluating {race.year} R{race.round} {race.event} {code}', flush=True)
            current = None if code == 'PRE' else race.sessions.get(code)
            if code != 'PRE' and current is None:
                skipped.append({'year': race.year, 'round': race.round, 'session': code,
                                'reason': 'session_not_cached'})
                continue
            metadata = {'year': race.year, 'round': race.round, 'event': race.event, 'session': code}
            stage_metrics, stage_predictions = [], []
            try:
                for variant, candidate in [('legacy', False), ('matched_stints_v2', True)]:
                    forecast, features = build_replay_forecast(current, previous, metadata=metadata,
                        practice=race.sessions.get('FP2'), candidate=candidate, n_sims=n_sims, seed=seed)
                    scores, data = evaluate_forecast(forecast, race.sessions['R'].results)
                    identity = dict(metadata, variant=variant)
                    stage_metrics.append(dict(identity, **scores))
                    stage_predictions.append(data.assign(**identity))
                    if variant == 'legacy':
                        for baseline in ('grid_order', 'recent_form'):
                            scores, data = evaluate_forecast(simple_baseline(features, previous, baseline),
                                                             race.sessions['R'].results)
                            identity = dict(metadata, variant=baseline)
                            stage_metrics.append(dict(identity, **scores))
                            stage_predictions.append(data.assign(**identity))
                metrics.extend(stage_metrics)
                predictions.extend(stage_predictions)
            except (ValueError, KeyError) as exc:
                # Use identical episodes for every variant; never silently score a
                # subset of drivers or compare different sessions.
                skipped.append(dict(metadata, reason=str(exc)))
    scores = pd.DataFrame(metrics)
    if scores.empty:
        raise ValueError('No complete benchmark episodes; inspect cached data coverage.')
    development, holdout = chronological_partitions(list(zip(scores.year, scores['round'])))
    scores['split'] = ['development' if key in development else 'holdout'
                       for key in zip(scores.year, scores['round'])]
    predictions = pd.concat(predictions, ignore_index=True)
    predictions['split'] = ['development' if key in development else 'holdout'
                           for key in zip(predictions.year, predictions['round'])]
    summary = scores.groupby(['variant', 'session', 'split'], as_index=False).agg(
        races=('round', 'count'), finish_mae=('finish_mae', 'mean'),
        win_brier=('win_brier', 'mean'), podium_brier=('podium_brier', 'mean'),
        top10_brier=('top10_brier', 'mean'), loss=('loss', 'mean'))
    # Select only on development races. Report later-race results separately.
    candidates = scores[scores.variant.isin(['legacy', 'matched_stints_v2'])]
    dev_loss = candidates[candidates.split.eq('development')].groupby('variant').loss.mean()
    selected = str(dev_loss.idxmin())
    test_loss = candidates[candidates.split.eq('holdout')].groupby('variant').loss.mean()
    gain = 1 - float(test_loss['matched_stints_v2'] / test_loss['legacy'])
    stage_coverage = summary[summary.variant.eq('legacy')][['session', 'split', 'races']].to_dict('records')
    adequate_coverage = all(
        len(candidates[(candidates.variant == 'legacy') & (candidates.session == code)
                       & (candidates.split == split)]) >= minimum
        for code in sessions for split, minimum in [('development', 6), ('holdout', 6)]
    )
    probability_nonregression = all(
        candidates[candidates.split.eq('holdout')].groupby('variant')[metric].mean()['matched_stints_v2']
        <= candidates[candidates.split.eq('holdout')].groupby('variant')[metric].mean()['legacy']
        for metric in ['win_brier', 'podium_brier', 'top10_brier']
    )
    root = Path(__file__).resolve().parents[1]
    source_files = ['src/accuracy_benchmark.py', 'src/features.py', 'src/long_run_pace.py',
                    'src/model.py', 'src/performance.py', 'src/model_config.py', 'src/simulate.py',
                    'src/reliability.py', 'src/grid.py', 'src/forecast_roster.py',
                    'src/weather.py', 'src/track.py', 'data/track_profiles.csv']
    input_hashes = {}
    for race in races:
        for code, session in race.sessions.items():
            for name in ['laps', 'results', 'weather_data']:
                frame = session_input_frame(session, name)
                # Serialized values include column names and indices. This hashes
                # loaded inputs, not unverifiable original publication versions.
                data = frame.to_csv(index=True).encode('utf-8')
                input_hashes[f'{race.year}/{race.round}/{code}/{name}'] = hashlib.sha256(data).hexdigest()
    report = {
        'schema_version': 2, 'n_sims': n_sims, 'seed': seed, 'sessions': list(sessions),
        'input_sha256': input_hashes,
        'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in source_files if (root / name).is_file()},
        'load_failures': list(load_failures or []), 'stage_coverage': stage_coverage,
        'development_races': [list(key) for key in sorted(development)],
        'holdout_races': [list(key) for key in sorted(holdout)],
        'selected_on_development': selected,
        'candidate_holdout_loss_improvement': gain,
        'promotion_gate_passed': selected == 'matched_stints_v2' and gain >= .05
                                 and adequate_coverage and probability_nonregression,
        'promotion_gate': 'development selection, >=6 development and holdout races per requested stage, '
                          '>=5% lower MAE+top10 Brier, no aggregate probability Brier regression',
        'limitations': ['Retrospective reconstruction, not attested prospective snapshots.',
            'Cached feeds may contain later corrections.',
            'Only cached sessions and the two most recent cached prior races are used.',
            'Current circuit defaults are reused; final race grid is excluded.',
            'No claim of calibration or generalisation across regulatory eras.'],
        'skipped': skipped,
    }
    scores.to_csv(output_dir / 'race_metrics.csv', index=False)
    predictions.to_csv(output_dir / 'predictions.csv', index=False)
    summary.to_csv(output_dir / 'summary.csv', index=False)
    calibration_bins(predictions).to_csv(output_dir / 'calibration_bins.csv', index=False)
    report['artifact_sha256'] = {name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in ('race_metrics.csv', 'predictions.csv', 'summary.csv', 'calibration_bins.csv')}
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def load_cached_races(cache_dir: Path, years: list[int]) -> tuple[list[ReplayRace], list[dict]]:
    import fastf1
    fastf1.set_log_level('ERROR')
    enable_cache(str(cache_dir))
    fastf1.Cache.offline_mode(True)
    races, failures = [], []
    for year in sorted(years):
        for event_path in sorted((cache_dir / str(year)).glob('*')):
            if not event_path.is_dir():
                continue
            cached = [path.name for path in event_path.iterdir() if path.is_dir()]
            if not any(name.endswith('_Race') for name in cached):
                continue
            event = event_path.name[11:].replace('_', ' ')
            loaded = {}
            for code, suffix in [('R', '_Race'), ('FP2', '_Practice_2'), ('Q', '_Qualifying')]:
                if not any(name.endswith(suffix) for name in cached):
                    continue
                try:
                    print(f'Loading cached {year} {event} {code}', flush=True)
                    session = fastf1.get_session(year, event, code)
                    session.load(laps=True, telemetry=False, weather=True, messages=False)
                    if session.laps.empty or session.results.empty:
                        raise ValueError('Empty session data.')
                    loaded[code] = session
                except Exception as exc:
                    failures.append({'year': year, 'event': event, 'session': code, 'reason': str(exc)})
            if 'R' in loaded:
                race = loaded['R']
                races.append(ReplayRace(year, int(race.event.RoundNumber), event, loaded))
    return races, failures
