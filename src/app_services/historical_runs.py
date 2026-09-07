"""Historical session discovery and isolated replay configuration."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.config_service import load_json_config

SESSION_CODES = {'Practice 1':'FP1', 'Practice 2':'FP2', 'Practice 3':'FP3',
                 'Qualifying':'Q', 'Sprint':'S', 'Sprint Qualifying':'SQ',
                 'Sprint Shootout':'SQ', 'Race':'R'}


def validate_selection(selection):
    year = int(selection.get('year', 0))
    event = str(selection.get('event', '')).strip()
    session = str(selection.get('session', 'Q'))
    if not 2018 <= year <= datetime.now(timezone.utc).year:
        raise ValueError('Choose a historical year from 2018 to the current year.')
    if not event or event.lower() == 'latest' or len(event) > 120:
        raise ValueError('Select a named historical Grand Prix, not latest.')
    if session not in SESSION_CODES.values():
        raise ValueError('Select a supported historical session.')
    return {'year':year, 'event':event, 'session':session}


def events_from_schedule(schedule, now=None):
    # Only prior-day sessions are offered; a scheduled start does not prove a
    # same-day session has finished or its timing data is available.
    cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True).normalize()
    events = []
    for _, row in schedule.iterrows():
        if row.get('RoundNumber', 0) <= 0:
            continue
        sessions = []
        for index in range(1, 6):
            code = SESSION_CODES.get(row.get(f'Session{index}'))
            date = pd.to_datetime(row.get(f'Session{index}DateUtc', row.get(f'Session{index}Date')), utc=True, errors='coerce')
            if code and pd.notna(date) and date < cutoff:
                sessions.append(code)
        if sessions:
            events.append({'event':str(row.EventName), 'sessions':sessions})
    return events


def historical_events(year, root):
    import fastf1
    year = int(year)
    validate_selection({'year':year, 'event':'Schedule', 'session':'Q'})
    cache = Path(root)/'data/cache'
    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    events = events_from_schedule(fastf1.get_event_schedule(year))
    if not events:
        raise ValueError('No completed sessions found. Check the year and your connection.')
    return events


def replay_config(selection, output_dir, n_sims, seed, difficulty):
    config = load_json_config()
    config['run'].update(**selection, n_sims=n_sims, random_seed=seed,
                         n_baseline_races=2, historical_strategy_lookback_years=1,
                         default_overtaking_difficulty=difficulty)
    config['outputs'].update(output_dir=str(output_dir), post_to_discord=False,
                             save_prediction_snapshot=True, save_raw_results=False,
                             save_report_images=False)
    config['model'].update(use_weather_forecast=False, use_historical_model_calibration=False)
    return config
