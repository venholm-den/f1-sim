"""Championship odds from archived classifications and the season calendar."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.app_services.historical_library import library_root, partition_files, read_json
from src.championship_odds import OddsSettings, normalise_results, simulate_championship

SESSION_NAMES = {'Race': 'R', 'Sprint': 'S'}


def archived_results(root, year) -> pd.DataFrame:
    """Race and sprint classifications from the local historical library.

    Detailed (FastF1) sessions take priority over results-only (Jolpica) rounds.
    """
    frames, seen = [], set()
    for mode in ('detailed', 'results'):
        for pointer in sorted((library_root(root)/str(year)/mode).glob('*/session.json')):
            saved = read_json(pointer)
            key = (saved.get('round'), saved.get('session'))
            if saved.get('status') != 'complete' or saved.get('session') not in ('R', 'S') or key in seen:
                continue
            try:
                files = [file for file, info in partition_files(pointer.parent, saved) if info.get('table') == 'results']
            except (ValueError, KeyError, TypeError, OSError):
                continue
            if files:
                frame = normalise_results(pd.read_csv(files[0]))
                if not frame.empty:
                    frames.append(frame.assign(source=f'archive_{mode}'))
                    seen.add(key)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def season_schedule(root, year) -> pd.DataFrame:
    import fastf1
    from src.data_sources.fastf1_cache import enable_cache
    enable_cache(str(Path(root)/'data/cache'))
    return fastf1.get_event_schedule(year, include_testing=False)


def scheduled_sessions(schedule: pd.DataFrame) -> list[dict]:
    """One row per championship race or sprint: round, event, session code and UTC start."""
    rows = []
    for _, event in schedule.iterrows():
        round_number = int(pd.to_numeric(event.get('RoundNumber'), errors='coerce') or 0)
        if round_number <= 0:
            continue
        for index in range(1, 6):
            code = SESSION_NAMES.get(str(event.get(f'Session{index}', '')))
            if not code:
                continue
            start = pd.to_datetime(event.get(f'Session{index}DateUtc', event.get(f'Session{index}Date')),
                                   utc=True, errors='coerce')
            rows.append({'round': round_number, 'event': str(event.get('EventName', f'Round {round_number}')),
                         'session': code, 'start': start})
    return rows


def fastf1_results(year, round_number, session) -> pd.DataFrame:
    import fastf1
    loaded = fastf1.get_session(year, round_number, session)
    loaded.load(laps=False, telemetry=False, weather=False, messages=False)
    frame = loaded.results.copy()
    return frame.assign(Round=round_number, Session=session, Event=loaded.event['EventName'])


def season_inputs(root, year, now=None, schedule=None, fetch=fastf1_results):
    """Completed results, outstanding sessions and warnings for one season."""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    results = archived_results(root, year)
    sessions = scheduled_sessions(season_schedule(root, year) if schedule is None else schedule)
    have = set() if results.empty else set(zip(results['round'], results['session']))
    warnings, fetched = [], []
    for item in sessions:
        key = (item['round'], item['session'])
        if key in have or pd.isna(item['start']) or item['start'] > now:
            continue
        # A finished session that is not archived yet; try FastF1 before counting it as missing.
        try:
            frame = normalise_results(fetch(year, item['round'], item['session']))
        except Exception:
            frame = pd.DataFrame()
        if frame.empty:
            if item['start'] > now - pd.Timedelta(days=2):
                # Still running or only just finished: treat it as outstanding rather than missing.
                continue
            name = 'sprint' if item['session'] == 'S' else 'race'
            warnings.append(f"R{item['round']} {item['event']} {name} results are not downloaded; "
                            'its points are missing from the standings.')
            have.add(key)
            continue
        fetched.append(frame.assign(source='fastf1'))
        have.add(key)
    if fetched:
        results = pd.concat([results, *fetched], ignore_index=True)
    remaining = {}
    for item in sessions:
        if (item['round'], item['session']) in have:
            continue
        entry = remaining.setdefault(item['round'], {'round': item['round'], 'event': item['event'],
                                                     'race': False, 'sprint': False, 'date': None})
        entry['race' if item['session'] == 'R' else 'sprint'] = True
        if item['session'] == 'R' and pd.notna(item['start']):
            entry['date'] = item['start'].date().isoformat()
    return results, [remaining[key] for key in sorted(remaining)], warnings


def championship_odds(root, year, n_sims=20000, now=None, schedule=None, fetch=fastf1_results):
    results, remaining, warnings = season_inputs(root, year, now=now, schedule=schedule, fetch=fetch)
    if results.empty:
        raise ValueError(f'No {year} race results are available. Download the season in Historical data first.')
    payload = simulate_championship(results, remaining, OddsSettings(n_sims=int(n_sims)))
    sources = sorted(set(results.get('source', pd.Series(dtype=str)).dropna()))
    payload.update(year=int(year), warnings=warnings, sources=sources,
                   computed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    return payload
