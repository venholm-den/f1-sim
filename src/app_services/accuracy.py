"""How past frozen forecasts scored against official results, read from saved score jobs.

Only official forecasts count. Personal simulations, including forecasts run with
changed settings, are listed separately with the reason and never enter the record.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.app_services.run_class import classify

# Brier scores the score job saves, and how many drivers each one rewards.
THRESHOLDS = {'win_chance_brier': 1, 'podium_chance_brier': 3, 'points_chance_brier': 10}


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def even_guess_brier(drivers: int, places: int) -> float:
    """Brier score of giving every driver the same chance, places/drivers.

    It is the reference a forecast has to beat: a skill of zero means no better
    than an even guess, and one would be a perfect forecast.
    """
    p = min(1.0, places / drivers)
    return p * (1 - p)


def skill(brier, drivers, places):
    if brier is None or not drivers:
        return None
    reference = even_guess_brier(drivers, places)
    if reference <= 0:
        return None
    return 1 - float(brier) / reference


def _retired(frame: pd.DataFrame) -> pd.Series:
    """True retired, False finished, NA unknown; older scores may lack the column."""
    if 'actual_dnf' not in frame:
        return pd.Series(pd.NA, index=frame.index, dtype='boolean')
    text = frame['actual_dnf'].astype(str).str.strip().str.lower()
    return text.map({'true': True, '1': True, '1.0': True, 'false': False, '0': False, '0.0': False}).astype('boolean')


def finishers_only(frame: pd.DataFrame) -> dict:
    """Finish error with retired drivers removed and both orders re-ranked.

    It answers how good the forecast was at ordering the cars that finished, so
    a retirement no forecast could know about does not count as a miss.
    """
    retired = _retired(frame)
    if retired.isna().all():
        return {'retirements': None, 'finishers_finish_mae': None}
    finished = frame[retired.eq(False).fillna(False)].dropna(subset=['avg_finish', 'actual_position'])
    mae = None
    if len(finished) >= 2:
        predicted = finished.avg_finish.rank(method='first')
        actual = finished.actual_position.rank(method='first')
        mae = float((predicted - actual).abs().mean())
    return {'retirements': int(retired.eq(True).sum()), 'finishers_finish_mae': mae}


def retirement_record(scored: list[dict]) -> list[dict]:
    """Each driver's forecast retirement chances summed against real retirements."""
    rows = [row for race in scored for row in race['comparison']
            if row.get('actual_dnf') is not None and row.get('dnf_chance') is not None]
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    frame['actual_dnf'] = frame.actual_dnf.astype(bool)
    grouped = frame.groupby('Driver').agg(races=('Driver', 'size'), expected=('dnf_chance', 'sum'),
                                          retirements=('actual_dnf', 'sum'), average_chance=('dnf_chance', 'mean'))
    grouped = grouped.reset_index().sort_values(['retirements', 'expected'], ascending=False)
    return [{'driver': r.Driver, 'races': int(r.races), 'expected': float(r.expected),
             'retirements': int(r.retirements), 'average_chance': float(r.average_chance)}
            for r in grouped.itertuples()]


def _context(job: dict) -> dict:
    manifest = _read(Path(job.get('forecast_folder', '')) / 'frozen/manifest.json')
    context = manifest.get('context') or {}
    if not context and isinstance(job.get('race_key'), list) and len(job['race_key']) == 2:
        context = {'year': job['race_key'][0], 'event': job['race_key'][1]}
    return {'year': context.get('year'), 'event': context.get('event'), 'session': context.get('session'),
            'category': manifest.get('category')}


def _forecast_key(job: dict):
    """The forecast a score job scored; app score jobs record only its folder."""
    if job.get('forecast_id'):
        return job['forecast_id']
    return Path(job['forecast_folder']).name if job.get('forecast_folder') else None


def _race(context: dict) -> tuple:
    return (context.get('year'), str(context.get('event') or '').casefold())


def _jobs(roots) -> list[tuple[Path, dict, bool]]:
    """(run folder, job, in the first workspace) for every saved job, once each."""
    seen, jobs = set(), []
    for index, root in enumerate(dict.fromkeys(Path(root).resolve() for root in roots)):
        for path in (root / 'outputs/app_runs').glob('*/job.json'):
            job = _read(path)
            if job.get('id') and job['id'] not in seen:
                seen.add(job['id'])
                jobs.append((path.parent, job, index == 0))
    return jobs


def accuracy_state(root, extra_roots=()) -> dict:
    """Scored races, newest first, and frozen forecasts that have no score yet.

    extra_roots adds other workspaces, such as the scheduled PC forecasts, so
    their scored races appear too; only the first root's forecasts can be
    scored from the app. Each race is listed once: a forecast scored twice shows
    its latest score, and a race with several scored forecasts shows the latest
    forecast's. Unscored forecasts of a scored race, and all but the latest
    unscored forecast of a race, are counted as superseded, not listed.
    """
    jobs = _jobs([root, *extra_roots])
    latest, scored_keys, excluded = {}, set(), []
    for folder, job, _ in jobs:
        score = _read(folder / 'score.json')
        if job.get('kind') != 'score' or job.get('status') != 'completed' or not score:
            continue
        scored_keys.add(_forecast_key(job))
        source = classify(Path(job['forecast_folder'])) if job.get('forecast_folder') else None
        if source and source['run_class'] != 'official':
            excluded.append({'id': job['id'], 'forecast_id': _forecast_key(job), **_context(job),
                             'reasons': source['reasons']})
            continue
        drivers = int(score.get('drivers') or 0)
        comparison, finishers = [], {'retirements': None, 'finishers_finish_mae': None}
        if (folder / 'score_comparison.csv').is_file():
            frame = pd.read_csv(folder / 'score_comparison.csv')
            frame['actual_dnf'] = _retired(frame)
            keep = [c for c in ('Driver', 'avg_finish', 'actual_position', 'win_chance', 'podium_chance',
                                'dnf_chance', 'actual_dnf') if c in frame]
            if 'actual_position' in frame:
                finishers = finishers_only(frame)
                frame = frame[keep].sort_values('actual_position')
                # Blank cells become null so the payload stays valid JSON.
                comparison = frame.astype(object).where(frame.notna(), None).to_dict('records')
        row = {'id': job['id'], 'forecast_id': _forecast_key(job), **_context(job),
               'evaluated_at': score.get('evaluated_at_utc') or job.get('finished_at'),
               'drivers': drivers, 'finish_mae': score.get('finish_mae'), **finishers,
               'expected_retirements': (sum(r['dnf_chance'] for r in comparison if r.get('dnf_chance') is not None)
                                        if any(r.get('dnf_chance') is not None for r in comparison) else None),
               **{key: score.get(key) for key in THRESHOLDS},
               **{key.replace('_brier', '_skill'): skill(score.get(key), drivers, places)
                  for key, places in THRESHOLDS.items()},
               'comparison': comparison}
        # One row per race: the latest forecast's score, and its latest evaluation.
        forecast_job = _read(Path(job['forecast_folder']) / 'job.json') if job.get('forecast_folder') else {}
        rank = (str(forecast_job.get('created_at') or ''), str(row['evaluated_at'] or ''), row['id'])
        race = _race(row)
        if race not in latest or rank > latest[race][0]:
            latest[race] = (rank, row)
    scored = sorted((row for _, row in latest.values()),
                    key=lambda row: (str(row['evaluated_at'] or ''), row['id']), reverse=True)
    scored_races = set(latest)

    waiting = {}
    superseded = 0
    for folder, job, own in jobs:
        manifest = _read(folder / 'frozen/manifest.json')
        if job.get('kind') != 'forecast' or not manifest or job['id'] in scored_keys:
            continue
        context = manifest.get('context') or {}
        source = classify(folder, job)
        if source['run_class'] != 'official':
            excluded.append({'id': job['id'], 'year': context.get('year'), 'event': context.get('event'),
                             'session': context.get('session'), 'category': manifest.get('category'),
                             'reasons': source['reasons']})
            continue
        row = {'id': job['id'], 'year': context.get('year'), 'event': context.get('event'),
               'session': context.get('session'), 'race_start_utc': context.get('race_start_utc'),
               'category': manifest.get('category'), 'created_at': job.get('created_at'), 'scorable': own}
        race = _race(context)
        if race in scored_races:
            superseded += 1
            continue
        if race in waiting:
            superseded += 1
            if str(row['created_at'] or '') <= str(waiting[race]['created_at'] or ''):
                continue
        waiting[race] = row
    pending = sorted(waiting.values(), key=lambda row: str(row['created_at'] or ''), reverse=True)
    excluded.sort(key=lambda row: str(row['id']), reverse=True)
    return {'scored': scored, 'pending': pending, 'superseded': superseded, 'excluded': excluded,
            'retirement_record': retirement_record(scored)}
