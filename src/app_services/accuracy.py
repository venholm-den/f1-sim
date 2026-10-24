"""How past frozen forecasts scored against official results, read from saved score jobs."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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


def _context(job: dict) -> dict:
    manifest = _read(Path(job.get('forecast_folder', '')) / 'frozen/manifest.json')
    context = manifest.get('context') or {}
    if not context and isinstance(job.get('race_key'), list) and len(job['race_key']) == 2:
        context = {'year': job['race_key'][0], 'event': job['race_key'][1]}
    return {'year': context.get('year'), 'event': context.get('event'), 'session': context.get('session'),
            'category': manifest.get('category')}


def accuracy_state(root) -> dict:
    """Scored races, newest first, and frozen forecasts that have no score yet."""
    run_root = Path(root) / 'outputs/app_runs'
    jobs = [job for job in (_read(path) for path in run_root.glob('*/job.json')) if job.get('id')]
    scored, scored_forecasts = [], set()
    for job in jobs:
        folder = run_root / job['id']
        score = _read(folder / 'score.json')
        if job.get('kind') != 'score' or job.get('status') != 'completed' or not score:
            continue
        scored_forecasts.add(job.get('forecast_id'))
        drivers = int(score.get('drivers') or 0)
        comparison = []
        if (folder / 'score_comparison.csv').is_file():
            frame = pd.read_csv(folder / 'score_comparison.csv')
            keep = [c for c in ('Driver', 'avg_finish', 'actual_position', 'win_chance', 'podium_chance') if c in frame]
            if 'actual_position' in frame:
                frame = frame[keep].sort_values('actual_position')
                # Blank cells become null so the payload stays valid JSON.
                comparison = frame.astype(object).where(frame.notna(), None).to_dict('records')
        scored.append({'id': job['id'], 'forecast_id': job.get('forecast_id'), **_context(job),
                       'evaluated_at': score.get('evaluated_at_utc') or job.get('finished_at'),
                       'drivers': drivers, 'finish_mae': score.get('finish_mae'),
                       **{key: score.get(key) for key in THRESHOLDS},
                       **{key.replace('_brier', '_skill'): skill(score.get(key), drivers, places)
                          for key, places in THRESHOLDS.items()},
                       'comparison': comparison})
    scored.sort(key=lambda row: (str(row['evaluated_at'] or ''), row['id']), reverse=True)

    pending = []
    for job in jobs:
        folder = run_root / job['id']
        manifest = _read(folder / 'frozen/manifest.json')
        if job.get('kind') != 'forecast' or not manifest or job['id'] in scored_forecasts:
            continue
        context = manifest.get('context') or {}
        pending.append({'id': job['id'], 'year': context.get('year'), 'event': context.get('event'),
                        'session': context.get('session'), 'race_start_utc': context.get('race_start_utc'),
                        'category': manifest.get('category'), 'created_at': job.get('created_at')})
    pending.sort(key=lambda row: str(row['created_at'] or ''), reverse=True)
    return {'scored': scored, 'pending': pending}
