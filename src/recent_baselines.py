"""Versioned, same-season race baseline data with explicit coverage and cutoffs."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.actual_strategy import extract_actual_strategy_from_session
from src.collect import _load_fastf1_session, completed_race_quality, enable_fastf1_cache
from src.features import build_driver_features
from src.historical_data import _extract_results, _extract_race_control, _with_metadata
from src.lap_details import extract_lap_details
from src.model import _prepare_baseline_features
from src.weather import summarize_weather
from src.venues import venue_for_context

WINDOWS = (2, 5, 8)


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None or pd.isna(stamp):
        raise ValueError('Use a timezone-aware cutoff.')
    return stamp.tz_convert('UTC')


def plan_races(schedule: pd.DataFrame, year: int, target_round: int, cutoff, count: int) -> list[dict]:
    cutoff = _utc(cutoff)
    if not 1 <= count <= 24 or target_round < 1:
        raise ValueError('Use 1-24 baseline races and a positive target round.')
    rows = []
    for _, event in schedule.iterrows():
        round_number = int(event['RoundNumber'])
        if not 0 < round_number < target_round:
            continue
        start = next((pd.to_datetime(event.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
                      for i in range(1, 6) if event.get(f'Session{i}') == 'Race'), None)
        # A scheduled start is insufficient. Allow time for completion/results,
        # then independently require terminal status and complete classification.
        if start is None or pd.isna(start) or start + pd.Timedelta(hours=8) > cutoff:
            continue
        rows.append({'year': year, 'round': round_number, 'event': str(event['EventName']),
                     'session': 'R', 'race_start_utc': start.isoformat()})
    return sorted(rows, key=lambda row: row['round'], reverse=True)[:count]


def driver_coverage(results: pd.DataFrame, features: pd.DataFrame, year: int, round_number: int,
                    laps: pd.DataFrame | None = None) -> pd.DataFrame:
    expected = results[['Abbreviation', 'TeamName']].rename(columns={'Abbreviation': 'Driver', 'TeamName': 'Team'})
    if expected.Driver.isna().any() or expected.Driver.duplicated().any() or features.Driver.duplicated().any():
        raise ValueError('Duplicate or missing baseline driver identifiers.')
    if not set(features.Driver).issubset(set(expected.Driver)):
        raise ValueError('Pace features include a driver absent from the classification.')
    columns = ['Driver', 'relative_pace', 'race_pace', 'clean_laps', 'raw_laps']
    detail = expected.merge(features.reindex(columns=columns), on='Driver', how='left', validate='one_to_one')
    detail['pace_available'] = np.isfinite(pd.to_numeric(detail.relative_pace, errors='coerce'))
    detail['clean_laps'] = detail.clean_laps.fillna(0)
    detail['raw_laps'] = detail.raw_laps.fillna(0)
    if laps is not None:
        detail['raw_laps'] = detail.Driver.map(laps.Driver.value_counts()).fillna(0)
    detail['thin_pace_sample'] = detail.pace_available & detail.clean_laps.lt(5)
    detail['source_year'] = year
    detail['source_round'] = round_number
    return detail


def baseline_windows(features: pd.DataFrame, coverage: pd.DataFrame, roster: list[str]) -> tuple[dict, pd.DataFrame]:
    rounds = sorted(coverage.source_round.unique(), reverse=True)
    summaries, counts = {}, []
    for window in WINDOWS:
        selected = rounds[:window]
        subset = features[features.source_round.isin(selected)].copy()
        subset['baseline_age'] = subset.source_round.map({round_number: age for age, round_number in enumerate(selected)})
        summary = _prepare_baseline_features(subset)
        # A recent substitute must not inflate the assumed next-race roster.
        summaries[window] = pd.DataFrame({'Driver': roster}).merge(summary, on='Driver', how='left', validate='one_to_one')
        for driver in roster:
            observed = coverage[coverage.source_round.isin(selected) & coverage.Driver.eq(driver)]
            counts.append({'Driver': driver, 'window_requested': window, 'races_in_window': len(selected),
                           'classified_races': len(observed), 'usable_pace_races': int(observed.pace_available.sum()),
                           'missing_pace_races': len(selected) - int(observed.pace_available.sum()),
                           'clean_laps': int(observed.clean_laps.sum()), 'raw_laps': int(observed.raw_laps.sum()),
                           'thin_pace_races': int(observed.thin_pace_sample.sum()),
                           'latest_pace_round': int(observed.loc[observed.pace_available, 'source_round'].max()) if observed.pace_available.any() else None,
                           'coverage_complete': len(observed) == len(selected) and observed.pace_available.all()})
    return summaries, pd.DataFrame(counts)


def build_recent_baselines(year: int, target_round: int, destination: Path, *, count: int = 16,
                           cutoff=None, schedule=None, load=None) -> dict:
    import fastf1
    captured = datetime.now(timezone.utc).isoformat()
    cutoff = _utc(cutoff or captured)
    if cutoff > _utc(captured):
        raise ValueError('A baseline cutoff cannot be in the future.')
    enable_fastf1_cache()
    schedule = schedule if schedule is not None else fastf1.get_event_schedule(year)
    target = schedule[schedule.RoundNumber.eq(target_round)]
    if len(target) != 1:
        raise ValueError('Select a published target round.')
    target_row = target.iloc[0]
    target_start = next((pd.to_datetime(target_row.get(f'Session{i}DateUtc'), utc=True, errors='coerce')
                         for i in range(1, 6) if target_row.get(f'Session{i}') == 'Race'), None)
    if target_start is None or pd.isna(target_start):
        raise ValueError('Target race UTC start is unavailable.')
    cutoff = min(cutoff, target_start)
    candidates = plan_races(schedule, year, target_round, cutoff, count)
    if not candidates:
        raise ValueError('No eligible same-season races precede the cutoff.')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    tables = {name: [] for name in ('baseline_race_features', 'driver_race_coverage', 'fastf1_laps',
              'fastf1_race_results', 'fastf1_actual_strategy', 'fastf1_weather_summary', 'fastf1_race_control_summary')}
    manifest, latest_roster = [], []
    for candidate in candidates:
        row = {**candidate, 'status': 'error', 'error': '', 'captured_at_utc': captured}
        print(f"Loading baseline {year} round {candidate['round']}: {candidate['event']}", flush=True)
        try:
            session = (load or _load_fastf1_session)(year, candidate['round'], 'R')
            identity = venue_for_context(candidate, session=session)
            row.update({key: identity[key] for key in ('circuit_id', 'circuit_name', 'layout_id', 'venue_status')})
            quality = completed_race_quality(session)
            features = build_driver_features(session.laps)
            if features.empty:
                raise ValueError('No usable race pace features.')
            for column, value in [('source_year', year), ('source_round', candidate['round']),
                                  ('source_event', candidate['event']), ('source_race_start_utc', candidate['race_start_utc'])]:
                features[column] = value
            coverage = driver_coverage(session.results, features, year, candidate['round'], session.laps)
            weather = _with_metadata(pd.DataFrame([summarize_weather(session, use_forecast=False)]), candidate)
            weather['WeatherRows'] = len(getattr(session, 'weather_data', []))
            extracted = {'baseline_race_features': features, 'driver_race_coverage': coverage,
                         'fastf1_laps': extract_lap_details(session, candidate),
                         'fastf1_race_results': _extract_results(session, candidate),
                         'fastf1_actual_strategy': extract_actual_strategy_from_session(session, candidate),
                         'fastf1_weather_summary': weather, 'fastf1_race_control_summary': _extract_race_control(session, candidate)}
            race_folder = destination / 'races' / f"{year}_{candidate['round']:02d}"
            for frame in extracted.values():
                for key in ('circuit_id', 'layout_id', 'venue_status'):
                    frame['source_' + key] = identity[key]
            race_folder.mkdir(parents=True, exist_ok=False)
            for name, frame in extracted.items():
                frame.to_csv(race_folder / f'{name}.csv', index=False)
            for name, frame in extracted.items():
                tables[name].append(frame)
            if not latest_roster:
                latest_roster = session.results.Abbreviation.astype(str).tolist()
            row.update(quality, status='ok', feature_drivers=len(features),
                       missing_pace_drivers=';'.join(coverage.loc[~coverage.pace_available, 'Driver']),
                       thin_pace_drivers=';'.join(coverage.loc[coverage.thin_pace_sample, 'Driver']),
                       clean_laps=int(features.clean_laps.sum()), weather_rows=int(weather.WeatherRows.iloc[0]))
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
            print(f"  unavailable: {row['error']}", flush=True)
        manifest.append(row)
        # Persist attempted coverage as the acquisition progresses.
        pd.DataFrame(manifest).to_csv(destination / 'manifest.csv', index=False)
        if 'ratelimit' in row['error'].lower() or 'rate limit' in row['error'].lower():
            break
    frames = {name: pd.concat(parts, ignore_index=True) if parts else pd.DataFrame() for name, parts in tables.items()}
    if frames['baseline_race_features'].empty:
        raise ValueError(f'No valid baseline races; see {destination / "manifest.csv"}.')
    for name, frame in frames.items():
        frame.to_csv(destination / f'{name}.csv', index=False)
    summaries, coverage = baseline_windows(frames['baseline_race_features'], frames['driver_race_coverage'], latest_roster)
    for window, summary in summaries.items():
        summary.to_csv(destination / f'baseline_summary_{window}_races.csv', index=False)
    coverage.to_csv(destination / 'driver_window_coverage.csv', index=False)
    report = {'schema_version': 1, 'category': 'recent_baseline_dataset', 'captured_at_utc': captured,
              'cutoff_utc': cutoff.isoformat(), 'target': {'year': year, 'round': target_round, 'event': str(target_row.EventName),
                  'venue': venue_for_context({'year': year, 'event': str(target_row.EventName)}, event_data=target_row)},
              'requested_races': count, 'eligible_races': len(candidates),
              'completed_races': sum(row['status'] == 'ok' for row in manifest), 'failed_races': [row for row in manifest if row['status'] != 'ok'],
              'race_rounds': sorted(frames['driver_race_coverage'].source_round.unique().tolist()),
              'lap_rows': len(frames['fastf1_laps']), 'feature_rows': len(frames['baseline_race_features']),
              'unique_drivers': frames['driver_race_coverage'].Driver.nunique(),
              'latest_baseline_roster': latest_roster, 'roster_source': 'latest_completed_baseline_assumption',
              'window_coverage': {str(window): {'races': int(coverage[coverage.window_requested.eq(window)].races_in_window.max()),
                  'drivers': len(latest_roster), 'full_pace_coverage_drivers': int(coverage[coverage.window_requested.eq(window)].coverage_complete.sum())} for window in WINDOWS},
              'applied_live_baseline_count_change': False,
              'limitations': ['Same-season races only; no fallback across regulation years.',
                  'Current cached feeds may contain later corrections; publication times are not attested.',
                  'Latest completed race roster is a next-race assumption, not a confirmed target entry list.',
                  'Legacy pace and inferred tyre degradation/DNF features remain heuristic.',
                  'Observed past race weather is historical context, not a forecast of the target race.',
                  'Coverage expansion is not evidence of improved prediction accuracy.'],
              'source_hashes': {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                  for name in ('recent_baselines.py', 'collect.py', 'features.py', 'model.py', 'venues.py')},
              'files': {str(path.relative_to(destination)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in destination.rglob('*.csv')}}
    (destination / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    lines = [f"# Recent baseline for {year} {target_row.EventName}", '',
             f"Built {report['completed_races']} completed races; {report['lap_rows']:,} lap rows; {report['feature_rows']} driver-race feature rows.",
             f"Cutoff: {cutoff.isoformat()}. Latest baseline roster: {len(latest_roster)} drivers (assumed).", '',
             '| Window | Races available | Drivers with pace in every race |', '| --- | ---: | ---: |']
    lines += [f"| {window} races | {values['races']} | {values['full_pace_coverage_drivers']}/{values['drivers']} |" for window, values in report['window_coverage'].items()]
    lines += ['', '## Race coverage', '', '| Round | Race | Classification drivers | Pace drivers | Missing pace |', '| --- | --- | ---: | ---: | --- |']
    lines += [f"| {row['round']} | {row['event']} | {row.get('result_drivers', 0)} | {row.get('feature_drivers', 0)} | {row.get('missing_pace_drivers') or row.get('error') or 'None'} |" for row in manifest]
    lines += ['', '## Limits', '', *['- ' + limit for limit in report['limitations']], '',
              'The automated two-race setting and experimental model switches are unchanged. No forecasts were reposted.']
    (destination / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report
