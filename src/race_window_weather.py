"""Select race-target forecast weather with an explicit availability cutoff."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from src.race_weather import collect_race_weather, payload_hash, utc, analyse_windows
from src.weather import DEFAULT_WEATHER_SUMMARY, _calculate_modifiers


def scheduled_race_start(session):
    event = getattr(session, 'event', {})
    for index in range(1, 6):
        if str(event.get(f'Session{index}', '')).strip().casefold() == 'race':
            value = event.get(f'Session{index}DateUtc')
            if value is not None:
                # FastF1 explicitly labels this field UTC but may store it naive.
                import pandas as pd
                stamp = pd.Timestamp(value)
                if pd.isna(stamp):
                    break
                return (stamp.tz_localize('UTC') if stamp.tzinfo is None else utc(stamp)).isoformat()
    raise ValueError('Scheduled race UTC start is unavailable; session date is not a substitute.')


def select_race_window(report, *, race_start, cutoff, latitude, longitude):
    """Use scheduled best-match guidance, never Q observations or a nearest day.

    A capture at a later time is a new forecast, not a replay of an earlier
    cutoff. Regional rain guidance does not identify wet track or tyre choice.
    """
    start, asof = utc(race_start), utc(cutoff)
    if utc(report['race_start_utc']) != start:
        raise ValueError('Weather report targets a different scheduled race start.')
    coordinates = report.get('requested_coordinates', {})
    if latitude is None or longitude is None or coordinates != {'latitude': latitude, 'longitude': longitude}:
        raise ValueError('Weather report coordinates differ from the physical venue.')
    if not utc(report['retrieved_at_utc']) <= asof < start:
        raise ValueError('Weather capture must be available by the pre-race forecast cutoff.')
    result = {**DEFAULT_WEATHER_SUMMARY, 'weather_source': 'race_window_unavailable',
              'forecast_time': start.isoformat(), 'forecast_available_at_utc': report['retrieved_at_utc'],
              'forecast_cutoff_utc': asof.isoformat(), 'race_weather_status': report.get('status'),
              'notes': 'Race forecast unavailable; neutral modifiers and unknown rainfall retained.'}
    windows = [s for s in report.get('scenarios', []) if s.get('delay_minutes') == 0]
    if len(windows) != 1:
        return result
    scenario = windows[0]
    if utc(scenario['start_utc']) != start or utc(scenario['end_utc']) <= start:
        raise ValueError('Scheduled weather window is invalid.')
    member = scenario.get('best_match') or {}
    if not member.get('simulation_usable') or not member.get('complete'):
        return result
    import numpy as np
    required = ['air_temp_avg', 'humidity_avg', 'wind_speed_avg']
    if any(member.get(key) is None for key in required) or not np.isfinite([member[key] for key in required]).all():
        raise ValueError('Race forecast contains invalid weather values.')
    if not isinstance(member.get('wet_hour'), (bool, np.bool_)):
        raise ValueError('Race forecast rainfall is unknown.')
    result.update(_calculate_modifiers(member['air_temp_avg'], None, member['humidity_avg'],
                                       member['wind_speed_avg'], member['wet_hour']))
    result.update({key: member[key] for key in required})
    result.update(weather_source='race_window_best_match_v1_experimental',
                  forecast_provider='Open-Meteo', rainfall_flag=member['wet_hour'],
                  race_window_end_utc=scenario['end_utc'],
                  rain_probability=None, ensemble_wet_hour_frequency=scenario.get('wet_hour_frequency'),
                  notes='Scheduled race-window regional guidance; wet track and tyre transitions are not inferred.')
    return result


def candidate_weather(session, profile, output_dir, *, report_path=None, cutoff=None):
    """Capture prospectively, or consume a saved raw/report packet for replay."""
    start = scheduled_race_start(session)
    if report_path:
        path = Path(report_path)
        report = json.loads(path.read_text(encoding='utf-8'))
        raw = json.loads(path.with_name('race_weather_raw.json').read_text(encoding='utf-8'))
        if payload_hash(raw) != report.get('raw_sha256'):
            raise ValueError('Race weather raw payload checksum mismatch.')
        if raw and max(utc(value['retrieved_at_utc']) for value in raw.values()) != utc(report['retrieved_at_utc']):
            raise ValueError('Race weather report and raw availability times differ.')
        report['scenarios'] = analyse_windows(raw, start, report['duration_minutes'])
    else:
        report, raw = collect_race_weather(start, profile.get('latitude'), profile.get('longitude'))
    asof = cutoff or datetime.now(timezone.utc).isoformat()
    folder = Path(output_dir)
    # Runs already own unique output directories; never overwrite an old packet.
    for filename, value in [('race_weather_raw.json', raw), ('race_weather.json', report)]:
        with (folder / filename).open('x', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
    return select_race_window(report, race_start=start, cutoff=asof,
                             latitude=profile.get('latitude'), longitude=profile.get('longitude'))
