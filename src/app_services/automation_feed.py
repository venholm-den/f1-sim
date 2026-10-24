"""Read completed PC forecasts without changing their files or delivery state."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.app_services.beta import verified_snapshot


DEFAULT_PC_WORKSPACE = Path('C:/code_project/f1-sim')

# The PC-runs panel polls every 15 s. Rehash a snapshot only when its frozen
# files change; scoring, sharing and Discord still verify from scratch.
_verified: dict[str, tuple[tuple, dict]] = {}


def _file_stamps(frozen: Path) -> tuple:
    return tuple(sorted((path.name, stat.st_size, stat.st_mtime_ns)
                        for path in frozen.iterdir() if path.is_file() for stat in [path.stat()]))


def cached_snapshot(folder: Path) -> dict:
    stamps = _file_stamps(Path(folder)/'frozen')
    cached = _verified.get(str(folder))
    if cached and cached[0] == stamps:
        return cached[1]
    manifest = verified_snapshot(folder)
    _verified[str(folder)] = (stamps, manifest)
    return manifest


def delivery_status(folder, *, label, kind):
    """Expose receipt facts without webhook URLs, response bodies or payloads."""
    receipt = folder/'discord_post_result.json'
    try:
        data = json.loads(receipt.read_text(encoding='utf-8'))
        state = data.get('delivery_state')
        if state not in {'sent', 'pending', 'failed', 'uncertain', 'sending'}:
            state = 'sent' if data.get('ok') is True else 'failed'
        return {'label': label, 'kind': kind, 'status': state,
                'attempted_at': data.get('attempted_at'), 'http_status': data.get('status')}
    except FileNotFoundError:
        return {'label': label, 'kind': kind, 'status': 'not_recorded', 'attempted_at': None}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'label': label, 'kind': kind, 'status': 'unreadable', 'attempted_at': None}


def forecast_feed(workspace: Path, pc_workspace: str = '') -> dict:
    pc = Path(pc_workspace).expanduser().resolve() if pc_workspace else DEFAULT_PC_WORKSPACE
    roots = list(dict.fromkeys([Path(workspace).resolve(), pc.resolve()]))
    runs, rejected = [], 0
    for root in roots:
        for path in (root / 'outputs/app_runs').glob('*/job.json'):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job.get('kind') != 'forecast' or job.get('status') != 'completed':
                    continue
                folder = path.parent.resolve()
                if not folder.is_relative_to((root / 'outputs/app_runs').resolve()):
                    continue
                manifest = cached_snapshot(folder)
                context = manifest['context']
                year, event, session = int(context['year']), str(context['event']), str(context['session'])
                if not event.strip() or session not in {'PRE', 'FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R'}:
                    raise ValueError('Invalid forecast context')
                stamp = datetime.fromisoformat(manifest['created_at_utc'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('Forecast timestamp must include a timezone')
                # The full folder identifies a run even when two workspaces have the same job ID.
                runs.append({'id': str(folder), 'job_id': job['id'],
                    'context': {'year': year, 'event': event, 'session': session},
                    'created_at': stamp.isoformat(), 'timestamp': stamp.timestamp(),
                    'workspace': str(root), 'output_dir': str(folder / 'source'),
                    'frozen_dir': str(folder / 'frozen'), 'category': manifest.get('category', 'unknown'),
                    'label': f'{year} {event} · {session}'})
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                rejected += 1
    runs.sort(key=lambda run: (run['timestamp'], run['id']), reverse=True)
    deliveries = [delivery_status(Path(run['id']), label=run['label'], kind='forecast') for run in runs[:10]]
    for root in roots:
        for path in (root/'outputs/weekend_briefings').glob('*/briefing.json'):
            try:
                briefing = json.loads(path.read_text(encoding='utf-8'))
                deliveries.append(delivery_status(path.parent,
                    label=f"{int(briefing['year'])} {str(briefing['event'])} · Weekend briefing", kind='weekend_briefing'))
            except (OSError, ValueError, TypeError, KeyError):
                continue
        for path in (root/'outputs/app_runs').glob('*/job.json'):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job.get('kind') == 'score' and job.get('status') == 'completed':
                    deliveries.append(delivery_status(path.parent, label=str(job.get('label', 'Post-race analysis')), kind='post_race'))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
    deliveries.sort(key=lambda row: str(row.get('attempted_at') or ''), reverse=True)
    try:
        health_data = json.loads((pc/'outputs/automation/last_health.json').read_text(encoding='utf-8'))
        health = {key: health_data.get(key) for key in ('status', 'checked_at_utc', 'failures', 'warnings', 'waiting')}
    except (OSError, ValueError, TypeError, AttributeError):
        health = {'status': 'unknown', 'checked_at_utc': None}
    return {'latest': runs[0] if runs else None, 'runs': runs, 'deliveries': deliveries[:20], 'health': health,
            'pc_workspace': str(pc), 'pc_available': pc.is_dir(), 'rejected': rejected}


def selected_forecast(workspace: Path, pc_workspace: str, identifier: str) -> dict:
    for run in forecast_feed(workspace, pc_workspace)['runs']:
        if run['id'] == identifier:
            return run
    raise ValueError('This completed forecast is unavailable or failed verification.')
