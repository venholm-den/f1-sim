"""Local-first beta forecasts, write-once snapshots and post-race evaluation.

Local hashes detect accidental edits; they are not a trusted server timestamp or
protection against a user rewriting both the manifest and its files.
"""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.app_paths import bundled_root
from src.app_services.historical_runs import SESSION_CODES, replay_config
from src.venues import venue_for_context

APP_VERSION = '0.2.0-beta.2'


MAX_UNSCORED_DRIVERS = 2
MIN_SCORED_DRIVERS = 15


class ResultsNotReady(ValueError):
    """Official completed results are not yet available; retry without alerting."""


def utc_now():
    return datetime.now(timezone.utc)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump_new(path, data):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def select_next_race(schedule, year, now=None, session_ready=None):
    cutoff = pd.to_datetime(now or utc_now(), utc=True)
    candidates = []
    for _, row in schedule.iterrows():
        if row.get('RoundNumber', 0) <= 0:
            continue
        race_start = next((pd.to_datetime(row.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
                           for i in range(1, 6) if SESSION_CODES.get(row.get(f'Session{i}')) == 'R'), None)
        if race_start is None or pd.isna(race_start) or race_start <= cutoff:
            continue
        sessions = []
        evidence = {}
        for index in range(1, 6):
            code = SESSION_CODES.get(row.get(f'Session{index}'))
            start = pd.to_datetime(row.get(f'Session{index}DateUtc'), utc=True, errors='coerce')
            if not code or code == 'R' or pd.isna(start) or start > cutoff:
                continue
            ready = session_ready(str(row.EventName), code) if session_ready else None
            if ready is True or (ready is None and start + pd.Timedelta(hours=3) <= cutoff):
                sessions.append((start, code))
                evidence[code] = 'completed_session_data' if ready is True else 'schedule_fallback_3h'
        if race_start is not None and race_start > cutoff:
            sessions.sort()
            codes = [code for _, code in sessions]
            selected = 'Q' if 'Q' in codes else (codes[-1] if codes else 'PRE')
            candidates.append({'year':int(year), 'event':str(row.EventName),
                'round':int(row.RoundNumber), 'session':selected, 'available_sessions':codes,
                'race_start_utc':race_start.isoformat(), 'data_cutoff_utc':cutoff.isoformat(),
                'session_evidence':evidence,
                'venue': venue_for_context({'year': year, 'event': str(row.EventName)}, event_data=row),
                'session_policy':'Completed status and usable lap/driver data; schedule plus 3h only when readiness cannot be checked.'})
    return min(candidates, key=lambda item:item['race_start_utc']) if candidates else None


def completed_session_data(session) -> bool | None:
    """False blocks a known live session; None permits the conservative fallback."""
    status = session.session_status
    if status.empty or 'Status' not in status:
        return None
    states = status.Status.dropna()
    if states.empty:
        return None
    # Qualifying emits Finished between segments; only a final terminal marker
    # confirms the whole session has ended rather than just Q1/Q2.
    if not states.eq('Finished').any() or states.iloc[-1] not in {'Finalised', 'Ends'}:
        return False
    laps, drivers = session.laps, session.results
    return bool(not drivers.empty and 'Abbreviation' in drivers
                and drivers.Abbreviation.notna().any() and not laps.empty and 'LapTime' in laps
                and laps.LapTime.gt(pd.Timedelta(0)).any())


def next_race(root):
    import fastf1
    cache = Path(root)/'data/cache'
    cache.mkdir(parents=True, exist_ok=True)
    enable_cache(str(cache))
    now = utc_now()
    for year in (now.year, now.year+1):
        schedule = fastf1.get_event_schedule(year)
        selected = select_next_race(schedule, year, now)
        if selected:
            def ready(event, code):
                try:
                    session = fastf1.get_session(year, event, code)
                    session.load(laps=True, telemetry=False, weather=False, messages=False)
                    return completed_session_data(session)
                except Exception:
                    # Missing/offline data is not evidence that a session is live.
                    return None
            return select_next_race(schedule[schedule.RoundNumber.eq(selected['round'])],
                                    year, now, session_ready=ready)
    raise ValueError('No upcoming race with a published UTC start was found. Check the calendar or retry later.')


def freeze_snapshot(folder, context, now=None, category='prospective'):
    folder = Path(folder)
    created = pd.to_datetime(now or utc_now(), utc=True)
    race_start = pd.to_datetime(context['race_start_utc'], utc=True)
    if category == 'prospective' and created >= race_start:
        raise ValueError('The race started before this run finished; no pre-race snapshot was frozen.')
    # A new directory is the reservation: subsequent attempts never overwrite it.
    frozen = folder/'frozen'
    frozen.mkdir(exist_ok=False)
    hashes = {}
    for name in ('simulation_summary.csv', 'features.csv', 'forecast_config.json', 'driver_roster.csv',
                 'race_weather.json', 'race_weather_raw.json', 'venue_context.json', 'baseline_race_features.csv',
                 'fantasy_market_prices.csv', 'fia_context.json', 'simulation_inputs.json',
                 'tyre_inventory_estimated.csv', 'tyre_set_ledger_estimated.csv'):
        if (folder/name).is_file():
            shutil.copy2(folder/name, frozen/name)
            hashes[name] = digest(frozen/name)
    if 'simulation_summary.csv' not in hashes:
        raise ValueError('A completed forecast is required before freezing.')
    source_hashes = {}
    for name in ('simulate.py', 'model_config.py', 'performance.py', 'features.py', 'grid.py',
                 'long_run_pace.py', 'model.py', 'reliability.py', 'race_weather.py',
                 'venues.py', 'track.py', 'strategy_history.py', 'result_status.py',
                 'forecast_roster.py', 'historical_calibration.py', 'fantasy.py', 'fantasy_market.py',
                 'data_sources/fia_documents.py', 'data_sources/fia_extraction.py', 'data_sources/fia_asof.py'):
        path = bundled_root()/'src'/name
        if path.is_file():
            source_hashes[name] = digest(path)
    from src.app_services.provenance import runtime_provenance
    manifest = {'runtime_provenance': runtime_provenance(), 'schema_version':1, 'app_version':APP_VERSION, 'category':category,
        'created_at_utc':created.isoformat(), 'context':context, 'files':hashes,
        'model_source_hashes':source_hashes,
        'timestamp_authority':'local_clock_unattested',
        'limitations':['Experimental model; not a calibrated guarantee.',
                      'Local hashes are not a trusted submission timestamp.',
                      'Session weather modifiers; no live weather forecast in beta.']}
    if 'race_weather.json' in hashes:
        manifest['limitations'][-1] = 'Session weather modifiers; archived race forecast is informational and does not affect driver probabilities.'
    dump_new(frozen/'manifest.json', manifest)
    return manifest


def verified_snapshot(folder):
    frozen = Path(folder)/'frozen'
    manifest = json.loads((frozen/'manifest.json').read_text(encoding='utf-8'))
    required = {'simulation_summary.csv'}
    allowed = required | {'features.csv','forecast_config.json','driver_roster.csv',
                          'race_weather.json','race_weather_raw.json','venue_context.json','baseline_race_features.csv',
                          'fantasy_market_prices.csv','fia_context.json','simulation_inputs.json',
                          'tyre_inventory_estimated.csv','tyre_set_ledger_estimated.csv'}
    if not required.issubset(manifest['files']) or not set(manifest['files']).issubset(allowed):
        raise ValueError('Invalid snapshot file list.')
    for name, checksum in manifest['files'].items():
        if not (frozen/name).is_file() or digest(frozen/name) != checksum:
            raise ValueError('Frozen snapshot changed. It cannot be scored or shared.')
    return manifest


def run_forecast(folder, job, context=None):
    from src.app_services.run_service import run_pipeline_with_config
    context = dict(context or next_race(Path.cwd()))
    context['venue'] = venue_for_context(context)
    dump_new(folder/'forecast_request_context.json', context)
    print(f"Forecasting {context['year']} {context['event']} from {context['session']} inputs.", flush=True)
    print(f"Data cutoff: {context['data_cutoff_utc']}; target race: {context['race_start_utc']}", flush=True)
    source = folder/'source'
    source.mkdir()
    selection = {key:context[key] for key in ('year','event','session')}
    config = replay_config(selection, source, job['n_sims'], job['seed'], job['overtaking_difficulty'])
    config['ignore_environment_overrides'] = True
    config['run']['weekend_sessions'] = context['available_sessions']
    config['run']['feature_cutoff_utc'] = context['data_cutoff_utc']
    config['outputs']['save_prediction_snapshot'] = False
    # Automated Discord runs generate the existing report bundle, but posting
    # happens only after the frozen snapshot has been created successfully.
    config['outputs']['save_report_images'] = True
    config['outputs']['post_to_discord'] = False
    reference = source/'reference'
    reference.mkdir()
    # Copy all reference inputs for provenance and to protect editable templates.
    for key, value in config['data'].items():
        original = Path(value)
        local = reference/original.name
        if original.is_file():
            shutil.copy2(original, local)
        config['data'][key] = str(local)
    dump_new(folder/'forecast_config.json', config)
    output_stream = sys.stdout
    code = run_pipeline_with_config(folder/'forecast_config.json',
        lambda text: print(text, end='', file=output_stream, flush=True))
    if code:
        from src.app_services import run_service
        raise RuntimeError('Forecast preparation failed; no frozen prediction was created.') from run_service.last_failure
    # Archive the physical identity actually used by the pipeline, including
    # any disagreement with the calendar. It controls every downstream input.
    if not (source/'venue_context.json').is_file():
        raise ValueError('Pipeline venue provenance is missing; forecast cannot be frozen.')
    context['venue'] = json.loads((source/'venue_context.json').read_text(encoding='utf-8'))
    shutil.copy2(source/'venue_context.json', folder/'venue_context.json')
    dump_new(folder/'forecast_context.json', context)
    shutil.copy2(source/'driver_model_features.csv', folder/'features.csv')
    if (source/'simulation_inputs.json').is_file():
        shutil.copy2(source/'simulation_inputs.json', folder/'simulation_inputs.json')
    if (source/'fia_context.json').is_file():
        shutil.copy2(source/'fia_context.json', folder/'fia_context.json')
    if (source/'fantasy_market_prices.csv').is_file():
        shutil.copy2(source/'fantasy_market_prices.csv', folder/'fantasy_market_prices.csv')
    if (source/'baseline_race_features.csv').is_file():
        shutil.copy2(source/'baseline_race_features.csv', folder/'baseline_race_features.csv')
    strategy = source/'strategy/predicted_tyre_strategy.csv'
    for name in ('tyre_inventory_estimated.csv', 'tyre_set_ledger_estimated.csv'):
        if (source/'tyres'/name).is_file():
            shutil.copy2(source/'tyres'/name, folder/name)
    if strategy.is_file():
        shutil.copy2(strategy, folder/'strategies.csv')
    # The pipeline already simulated and rendered these exact results. Reuse
    # them so frozen probabilities, fantasy metrics and charts cannot diverge.
    for name in ('simulation_summary.csv', 'position_matrix.csv', 'driver_roster.csv'):
        shutil.copy2(source/name, folder/name)
    if (source/'sampled_races.csv').is_file():
        shutil.copy2(source/'sampled_races.csv', folder/'sampled_races.csv')
    # Informational race forecast for new runs only. Driver rankings remain on
    # the established session-weather model until the candidate passes validation.
    from src.race_weather import collect_race_weather
    from src.track import load_track_profile
    try:
        profile = load_track_profile(context['event'], config['data']['track_profiles_path'], metadata=context)
        weather, raw = collect_race_weather(context['race_start_utc'], profile['latitude'], profile['longitude'])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        weather, raw = {'status': 'capture_failed', 'error_type': type(exc).__name__, 'scenarios': [],
                        'applied_to_live_predictions': False, 'delay_probability': None,
                        'race_start_utc': context['race_start_utc'], 'retrieved_at_utc': utc_now().isoformat()}, {}
    weather['feature_data_cutoff_utc'] = context['data_cutoff_utc']
    dump_new(folder/'race_weather.json', weather)
    dump_new(folder/'race_weather_raw.json', raw)
    freeze_snapshot(folder, context)
    print('Pre-race snapshot frozen. Nothing has been uploaded.', flush=True)


def score_frames(predictions, actual):
    if predictions.Driver.duplicated().any() or actual.Driver.duplicated().any():
        raise ValueError('Duplicate drivers in forecast or actual results.')
    # A non-starter has no classified position and a late substitute was never
    # forecast. Score the rest of a full field and record who was left out.
    common = set(predictions.Driver) & set(actual.Driver)
    unforecast, unclassified = set(actual.Driver) - common, set(predictions.Driver) - common
    excluded = sorted(unforecast | unclassified)
    if excluded and (max(len(unforecast), len(unclassified)) > MAX_UNSCORED_DRIVERS
                     or len(common) < MIN_SCORED_DRIVERS):
        raise ValueError('Driver coverage differs; refusing to score a partial result.')
    predictions, actual = predictions[predictions.Driver.isin(common)], actual[actual.Driver.isin(common)]
    if actual.actual_position.isna().any() or actual.actual_position.duplicated().any():
        raise ValueError('Actual classification is incomplete or invalid.')
    data = predictions.merge(actual, on='Driver', validate='one_to_one', suffixes=('','_actual'))
    metrics = {'drivers':len(data), 'finish_mae':float((data.avg_finish-data.actual_position).abs().mean())}
    if excluded:
        metrics['unscored_drivers'] = excluded
    for column, limit in [('win_chance',1),('podium_chance',3),('points_chance',10)]:
        if column in data:
            if not data[column].between(0,1).all():
                raise ValueError('Invalid predicted probabilities.')
            metrics[column+'_brier'] = float(((data[column]-(data.actual_position<=limit).astype(float))**2).mean())
    data['finish_error'] = data.avg_finish-data.actual_position
    return metrics, data


def run_scoring(folder, forecast_folder):
    from src.backtest import _load_race_session, _extract_actual_results_from_race_session
    manifest = verified_snapshot(forecast_folder)
    context = manifest['context']
    # Avoid scoring a live/provisional race. Delay is conservative, not a claim
    # that all classifications become final after exactly eight hours.
    if pd.Timestamp(utc_now()) < pd.Timestamp(context['race_start_utc']) + pd.Timedelta(hours=8):
        raise ResultsNotReady('Scoring opens eight hours after the scheduled race start. Try again later.')
    print(f"Loading actual race classification for {context['event']}…", flush=True)
    session = _load_race_session(context['year'], context['event'])
    status = getattr(session, 'session_status', pd.DataFrame())
    if 'Status' not in status or not status.Status.eq('Finished').any():
        raise ResultsNotReady('The race session is not confirmed finished; scoring is unavailable.')
    actual = _extract_actual_results_from_race_session(session)
    if not actual.actual_result_source.eq('fastf1_results').all():
        raise ResultsNotReady('Official session results are unavailable; lap-derived fallbacks are not scored.')
    predictions = pd.read_csv(Path(forecast_folder)/'frozen/simulation_summary.csv')
    metrics, comparison = score_frames(predictions, actual)
    metrics.update(category=manifest['category'], evaluated_at_utc=utc_now().isoformat(),
                   snapshot_sha256=digest(Path(forecast_folder)/'frozen/manifest.json'))
    actual.to_csv(folder/'actual_results.csv', index=False)
    comparison.to_csv(folder/'score_comparison.csv', index=False)
    dump_new(folder/'score.json', metrics)
    print(json.dumps(metrics, indent=2), flush=True)


def sharing_export(folder):
    """Explicit local export only: no endpoint, identity, local paths or raw logs."""
    manifest = verified_snapshot(folder)
    frame = pd.read_csv(Path(folder)/'frozen/simulation_summary.csv')
    fields = ['Driver','avg_finish','win_chance','podium_chance','points_chance','dnf_chance']
    payload = {'schema_version':1, 'app_version':APP_VERSION, 'context':manifest['context'],
        'category':manifest['category'], 'timestamp_authority':manifest['timestamp_authority'],
        'created_at_utc':manifest['created_at_utc'], 'input_hashes':manifest['files'],
        'model_source_hashes':manifest['model_source_hashes'],
        'predictions':json.loads(frame[[c for c in fields if c in frame]].to_json(orient='records'))}
    job = json.loads((Path(folder)/'job.json').read_text(encoding='utf-8'))
    payload['settings'] = {k:job[k] for k in ('n_sims','seed','overtaking_difficulty')}
    return payload
