"""Summarize automation outcomes without copying exception text or credentials."""
from datetime import datetime, timezone
from src.app_services.simulation_jobs import write_json

OPTIONAL = {'fantasy_collection', 'fia_collection', 'ensemble_shadow',
            'ensemble_shadow_scoring', 'prediction_trial', 'prediction_trial_scoring',
            'prediction_trial_report', 'current_practice', 'weather_update', 'form_shadow'}


def summarize(result):
    failures, warnings, waiting = [], [], []
    def visit(value, path):
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, [*path, str(index)])
        elif isinstance(value, dict):
            status = str(value.get('status', ''))
            state = value.get('delivery_state')
            if status == 'waiting_for_results' or (value.get('skipped') and state == 'pending'):
                waiting.append('.'.join(path) or 'run')
            elif (status in {'error', 'failed', 'capture_failed', 'score_failed', 'unreadable', 'access_unavailable'}
                    or value.get('requires_review') or state in {'sending', 'uncertain'}
                    or (value.get('ok') is False and not value.get('skipped'))):
                target = warnings if path and (path[0] in OPTIONAL or 'classification_checks' in path) else failures
                target.append('.'.join(path) or 'run')
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    visit(item, [*path, key])
    visit(result, [])
    return {'status': 'failed' if failures else 'warning' if warnings else 'waiting' if waiting else 'ok',
            'failures': failures, 'warnings': warnings, 'waiting': waiting,
            'exit_code': 1 if failures else 0,
            'checked_at_utc': datetime.now(timezone.utc).isoformat()}


def record(root, result):
    health = summarize(result)
    folder = root/'outputs/automation'
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder/'last_health.json', health)
    return health
