"""Append-only weather updates between session forecasts; never resend Discord."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.beta import digest, dump_new
from src.race_weather import collect_race_weather, utc
from src.track import load_track_profile
from src.venues import venue_for_context


def capture_weather_update(root: Path, context: dict, *, now=None) -> dict:
    context = {**context, 'venue': venue_for_context(context)}
    stamp = utc(now or datetime.now(timezone.utc))
    start = utc(context['race_start_utc'])
    reference = root / 'data/track_profiles.csv'
    if not reference.is_file():
        return {'status': 'reference_unavailable'}
    if start <= stamp or start - stamp > pd.Timedelta(days=14):
        return {'status': 'outside_upcoming_capture_window'}
    interval = pd.Timedelta(hours=1 if start - stamp <= pd.Timedelta(hours=48) else 6)
    archive = root / 'outputs/race_weather_updates' / f"{int(context['year'])}_{int(context['round'])}"
    for path in sorted(archive.glob('*/manifest.json'), reverse=True):
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
            age = stamp - utc(previous['captured_at_utc'])
            if (previous['race_start_utc'] != start.isoformat() or age < pd.Timedelta(0)
                    or previous['context'].get('venue') != context['venue']):
                continue
            if age >= interval:
                break
            if (set(previous['files']) == {'race_weather.json', 'race_weather_raw.json'}
                    and all(digest(path.parent / name) == checksum for name, checksum in previous['files'].items())):
                return {'status': 'cached', 'folder': str(path.parent), 'captured_at_utc': previous['captured_at_utc']}
        except (ValueError, OSError, KeyError, TypeError):
            continue
    profile = load_track_profile(context['event'], str(reference), metadata=context)
    report, raw = collect_race_weather(start, profile['latitude'], profile['longitude'], now=stamp)
    folder = archive / stamp.strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    dump_new(folder / 'race_weather.json', report)
    dump_new(folder / 'race_weather_raw.json', raw)
    dump_new(folder / 'manifest.json', {'schema_version': 1, 'category': 'weather_update_informational',
        'context': context, 'race_start_utc': start.isoformat(), 'captured_at_utc': stamp.isoformat(),
        'applied_to_live_predictions': False,
        'files': {name: digest(folder / name) for name in ('race_weather.json', 'race_weather_raw.json')}})
    return {'status': report['status'], 'folder': str(folder), 'captured_at_utc': stamp.isoformat()}
