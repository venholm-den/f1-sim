"""Archive replay: forecasts rebuilt for past races from the local historical library.

Each race is forecast from its qualifying session and the races before it, with
the established model settings, then scored the way an official forecast is.
It is retrospective: the model and its settings were chosen after these races
happened, so the results sit apart from the official record and never enter it.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.app_services import historical_library as library
from src.app_services.accuracy import THRESHOLDS, finishers_only, skill
from src.app_services.simulation_jobs import write_json

TABLES = ('laps', 'results', 'weather_samples')
PROBABILITIES = {'win_chance_brier': 'win_chance', 'podium_chance_brier': 'podium_chance',
                 'points_chance_brier': 'points_chance'}


def downloaded_years(root) -> list[int]:
    return sorted({row['year'] for row in library.inventory(root)['seasons']
                   if row['mode'] == 'detailed' and row['sessions']}, reverse=True)


def options(root, payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('Choose seasons to replay.')
    years = sorted({int(year) for year in payload.get('years', [])})
    available = downloaded_years(root)
    if not years:
        raise ValueError('Choose at least one season to replay.')
    missing = [year for year in years if year not in available]
    if missing:
        raise ValueError(f"Download detailed sessions for {', '.join(map(str, missing))} in Historical data first.")
    n_sims = int(payload.get('n_sims', 2000))
    if not 100 <= n_sims <= 10000:
        raise ValueError('Use 100 to 10,000 simulated races per race.')
    return {'years': years, 'n_sims': n_sims, 'seed': 42}


def _session(folder: Path, manifest: dict):
    if manifest.get('status') != 'complete' or not manifest.get('files'):
        raise ValueError('files missing or damaged')
    # Manifests written on Windows use backslashes; both separators work there.
    manifest = {**manifest, 'files': {name.replace('\\', '/'): info for name, info in manifest['files'].items()}}
    try:
        files = list(library.partition_files(folder, manifest))
    except (ValueError, KeyError, TypeError):
        raise ValueError('files missing or damaged') from None
    tables = {info['table']: pd.read_csv(file) for file, info in files
              if info['table'] in TABLES}
    laps, results = tables.get('laps', pd.DataFrame()), tables.get('results', pd.DataFrame())
    if laps.empty or results.empty:
        raise ValueError('laps or classification missing')
    if 'TrackStatus' in laps:
        laps['TrackStatus'] = laps.TrackStatus.astype(str).str.removesuffix('.0')
    laps['LapTime'] = pd.to_timedelta(laps.LapTimeSeconds, unit='s')
    if manifest['session'] == 'Q':
        ranks = pd.to_numeric(results.Position, errors='coerce')
        if sorted(ranks.dropna()) != list(range(1, len(results) + 1)):
            raise ValueError('classification is incomplete')
    event = pd.Series({'RoundNumber': manifest['round'], 'EventName': manifest['event'],
                       'Location': manifest.get('venue', {}).get('feed_location')})
    return SimpleNamespace(laps=laps, results=results, event=event, session_info={},
                           weather_data=tables.get('weather_samples', pd.DataFrame()))


def load(root, years) -> tuple[list, list]:
    """Races with a saved race session, oldest first. The season before the
    first chosen one is read too, when saved, so early rounds have history."""
    from src.accuracy_benchmark import ReplayRace
    wanted = set(years) | {min(years) - 1}
    found, skipped = {}, []
    for pointer in sorted(library.library_root(root).glob('*/detailed/*/session.json')):
        saved = library.read_json(pointer)
        if saved.get('year') not in wanted or saved.get('session') not in ('Q', 'R'):
            continue
        key = int(saved['year']), int(saved['round'])
        entry = found.setdefault(key, {'event': saved.get('event', pointer.parent.name), 'sessions': {}})
        try:
            if saved['session'] == 'R' and saved.get('venue', {}).get('race_quality', {}).get('training_eligible') is False:
                raise ValueError('aborted, kept for audit only')
            entry['sessions'][saved['session']] = _session(pointer.parent, saved)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            if key[0] in years:
                skipped.append({'year': key[0], 'round': key[1], 'event': entry['event'],
                                'reason': f"{'Qualifying' if saved['session'] == 'Q' else 'Race'} session {exc}"})
    races = [ReplayRace(year, round_number, value['event'], value['sessions'])
             for (year, round_number), value in sorted(found.items()) if 'R' in value['sessions']]
    return races, skipped


def actual_outcome(race_session) -> pd.DataFrame:
    """Finishing position and whether each car retired.

    Archived status text is unreliable for retirements (some say "Lapped"), so a
    car also counts as retired when classified 'R' or more than three laps short.
    """
    from src.result_status import classify_result_status
    results = race_session.results.copy()
    results['actual_position'] = pd.to_numeric(results.Position, errors='coerce')
    laps = race_session.laps.groupby('Driver').LapNumber.max().reindex(results.Abbreviation).fillna(0).to_numpy()
    retired = (results.Status.map(classify_result_status).ne('finished')
               | results.get('ClassifiedPosition', pd.Series('', index=results.index)).astype(str).eq('R')
               | pd.Series(laps < laps.max() - 3, index=results.index))
    return pd.DataFrame({'Driver': results.Abbreviation, 'actual_position': results.actual_position,
                         'actual_dnf': retired.astype(bool)})


def score(comparison: pd.DataFrame) -> dict:
    """The official score job's measures, plus finishers-only error and a grid baseline."""
    drivers = len(comparison)
    row = {'drivers': drivers,
           'finish_mae': float((comparison.avg_finish - comparison.actual_position).abs().mean()),
           'grid_finish_mae': float((comparison.grid_position - comparison.actual_position).abs().mean()),
           'spearman': float(comparison.avg_finish.corr(comparison.actual_position, method='spearman')),
           'expected_retirements': float(comparison.dnf_chance.sum()),
           **finishers_only(comparison)}
    for key, column in PROBABILITIES.items():
        brier = float(((comparison[column] - comparison.actual_position.le(THRESHOLDS[key]).astype(float)) ** 2).mean())
        row[key] = brier
        row[key.replace('_brier', '_skill')] = skill(brier, drivers, THRESHOLDS[key])
    return row


def replay_race(race, previous, n_sims, seed) -> dict:
    from src.accuracy_benchmark import build_replay_inputs
    from src.simulate import simulate_races
    meta = {'year': race.year, 'round': race.round, 'event': race.event, 'session': 'Q'}
    features, track, weather = build_replay_inputs(race.sessions['Q'], previous, metadata=meta)
    actual = actual_outcome(race.sessions['R'])
    if set(actual.Driver) != set(features.Driver) or actual.actual_position.isna().any():
        raise ValueError('Race entry list differs from qualifying')
    summary, _, _ = simulate_races(features, n_sims=n_sims, seed=seed,
                                   overtaking_difficulty=track['overtaking_difficulty'], weather_modifiers=weather)
    comparison = (summary[['Driver', 'avg_finish', 'win_chance', 'podium_chance', 'points_chance', 'dnf_chance']]
                  .merge(features[['Driver', 'grid_position']], on='Driver').merge(actual, on='Driver'))
    return {**meta, **score(comparison)}


def summarise(races: pd.DataFrame) -> list[dict]:
    """Season averages, newest season first."""
    rows = []
    for year, group in races.groupby('year'):
        known = group.dropna(subset=['retirements'])
        rows.append({'year': int(year), 'races': len(group),
                     **{key: float(group[key].mean()) for key in
                        ('finish_mae', 'finishers_finish_mae', 'grid_finish_mae', 'spearman',
                         'win_chance_skill', 'podium_chance_skill', 'points_chance_skill')},
                     'retirements': int(known.retirements.sum()),
                     'expected_retirements': float(known.expected_retirements.sum())})
    return sorted(rows, key=lambda row: row['year'], reverse=True)


def run(root, folder: Path, plan: dict) -> dict:
    progress = folder / 'replay_progress.json'
    write_json(progress, {'stage': 'Reading the historical library', 'processed': 0, 'total': 0})
    races, skipped = load(root, plan['years'])
    targets = [index for index, race in enumerate(races) if race.year in plan['years']]
    rows = []
    for done, index in enumerate(targets):
        race = races[index]
        write_json(progress, {'stage': f'{race.year} {race.event}', 'processed': done, 'total': len(targets)})
        reason = None
        if any((row['year'], row['round']) == race.key for row in skipped):
            continue  # already listed with the reason it could not be read
        if 'Q' not in race.sessions:
            reason = 'No saved qualifying session'
        elif index < 2:
            reason = 'Needs two earlier races in the library'
        else:
            try:
                rows.append(replay_race(race, races[:index], plan['n_sims'], plan['seed']))
                print(f"{race.year} {race.event}: finish error {rows[-1]['finish_mae']:.2f} "
                      f"({done + 1}/{len(targets)})", flush=True)
            except (ValueError, KeyError) as exc:
                reason = str(exc)
        if reason:
            skipped.append({'year': race.year, 'round': race.round, 'event': race.event, 'reason': reason})
    if not rows:
        raise ValueError('No race in these seasons could be replayed. Download detailed Q and R sessions first.')
    frame = pd.DataFrame(rows)
    frame.to_csv(folder / 'replay_races.csv', index=False)
    result = {'years': plan['years'], 'n_sims': plan['n_sims'], 'seed': plan['seed'],
              'seasons': summarise(frame), 'skipped': skipped}
    write_json(folder / 'replay_summary.json', result)
    write_json(progress, {'stage': 'Finished', 'processed': len(targets), 'total': len(targets)})
    print(f'Archive replay finished: {len(rows)} races scored, {len(skipped)} skipped.', flush=True)
    return result


def result(folder: Path) -> dict | None:
    summary = library.read_json(folder / 'replay_summary.json')
    races = folder / 'replay_races.csv'
    if not summary or not races.is_file():
        return None
    frame = pd.read_csv(races).sort_values(['year', 'round'], ascending=[False, True])
    summary['races'] = frame.astype(object).where(frame.notna(), None).to_dict('records')
    return summary


def latest(root) -> dict:
    """Newest finished replay, and the seasons that could be replayed now."""
    from src.app_services.accuracy import _read
    run_root = Path(root) / 'outputs/app_runs'
    jobs = sorted((job for job in (_read(path) for path in run_root.glob('*/job.json'))
                   if job.get('kind') == 'archive_replay' and job.get('status') == 'completed'),
                  key=lambda job: str(job.get('finished_at') or job.get('created_at')), reverse=True)
    for job in jobs:
        replay = result(run_root / job['id'])
        if replay:
            return {'available_years': downloaded_years(root), 'latest': {**replay, 'id': job['id'],
                    'finished_at': job.get('finished_at')}}
    return {'available_years': downloaded_years(root), 'latest': None}
