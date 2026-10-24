"""Evaluate the latest automated frozen forecast once per completed race."""
from __future__ import annotations

import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.app_services.beta import ResultsNotReady, digest, run_scoring, verified_snapshot
from src.app_services.simulation_jobs import write_json
from src.discord_post import delivery_state, post_files_to_discord, validate_message, validate_webhook_url
from src.app_services.discord_reports import analysis_summary, message_text, post_race_message


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def eligible_forecasts(root: Path, now: datetime | None = None) -> list[tuple[Path, dict]]:
    """Choose the latest prospective automated snapshot per race after eight hours."""
    now = now or datetime.now(timezone.utc)
    latest = {}
    for path in (Path(root) / 'outputs/app_runs').glob('*/job.json'):
        job = _read(path)
        if (job.get('kind') != 'forecast' or job.get('status') != 'completed'
                or not job.get('discord_enabled')):
            continue
        try:
            manifest = verified_snapshot(path.parent)
            context = manifest['context']
            if manifest['category'] != 'prospective':
                continue
            if now < datetime.fromisoformat(context['race_start_utc']) + timedelta(hours=8):
                continue
            key = (int(context['year']), str(context['event']))
            created = datetime.fromisoformat(manifest['created_at_utc'])
            if key not in latest or created > latest[key][0]:
                latest[key] = (created, path.parent, manifest)
        except (KeyError, OSError, ValueError, TypeError):
            continue
    return [(folder, manifest) for _, folder, manifest in sorted(latest.values(), key=lambda item: item[0])]


def render_analysis(folder: Path, context: dict, *, history_root: Path | None = None) -> None:
    """Create a compact measured comparison and an attachment for every driver."""
    comparison = pd.read_csv(folder / 'score_comparison.csv').sort_values('actual_position')
    payload = post_race_message(folder, context, history_root=history_root)
    write_json(folder / 'post_race_embed.json', payload)
    summary = analysis_summary(comparison)
    write_json(folder / 'analysis_summary.json', summary)
    (folder / 'post_race_analysis.txt').write_text(message_text(payload), encoding='utf-8')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(7.5, max(8, len(comparison) * .4)))
    figure.subplots_adjust(left=.14, right=.97, top=.83, bottom=.09)
    axes.scatter(comparison.avg_finish, comparison.Driver, label='Forecast average', color='#168a88', s=45)
    axes.scatter(comparison.actual_position, comparison.Driver, label='Actual position', color='#c66b15', s=45)
    for row in comparison.itertuples():
        axes.plot([row.avg_finish, row.actual_position], [row.Driver, row.Driver], color='#aaa', alpha=.5)
    axes.invert_yaxis()
    axes.set_xlabel('Finishing position', fontsize=12)
    axes.tick_params(labelsize=12)
    axes.set_xticks(range(1, len(comparison) + 1, 2))
    axes.grid(axis='x', alpha=.2)
    axes.legend(loc='lower left', bbox_to_anchor=(0, 1.015), ncol=2, fontsize=11, frameon=False)
    axes.spines[['top', 'right']].set_visible(False)
    figure.suptitle(f"{context['year']} {context['event']}\nForecast vs actual", fontsize=17, y=.975)
    label = f"Model error {summary['finish_mae']:.2f} places"
    if summary['grid_baseline_mae'] is not None:
        label += f" | Frozen grid baseline {summary['grid_baseline_mae']:.2f}"
    figure.text(.5, .895, label, ha='center', fontsize=11)
    figure.text(.5, .025, 'All classified drivers, including retirements • lower error is better', ha='center', fontsize=10)
    figure.savefig(folder / 'forecast_vs_actual.png', dpi=170)
    plt.close(figure)
    from src.app_services.discord_cards import render_post_race_card
    card = render_post_race_card(folder, context, folder)
    write_json(folder / 'post_race_delivery_plan.json', {
        'format_version': 3, 'payload': payload,
        'files': [card.name, 'score_comparison.csv', 'actual_results.csv'],
    })


def post_analysis(folder: Path, webhook_url: str | None = None) -> dict:
    """Persist delivery before sending; never blindly repeat an uncertain upload."""
    receipt_path = folder / 'discord_post_result.json'
    existing = _read(receipt_path)
    if existing.get('ok') or existing.get('delivery_state') in {'sending', 'uncertain', 'failed'}:
        return {**existing, 'skipped': True, 'requires_review': not bool(existing.get('ok'))}
    now = datetime.now(timezone.utc)
    if existing.get('next_attempt_at') and now < datetime.fromisoformat(existing['next_attempt_at']):
        return {**existing, 'skipped': True}
    webhook_url = webhook_url or os.getenv('DISCORD_WEBHOOK_URL', '')
    if not webhook_url:
        raise ValueError('DISCORD_WEBHOOK_URL is missing; post-race analysis remains local.')
    validate_webhook_url(webhook_url)
    payload = _read(folder / 'post_race_embed.json')
    plan = _read(folder / 'post_race_delivery_plan.json')
    names = ('post_race_analysis.txt', 'forecast_vs_actual.png', 'score_comparison.csv', 'actual_results.csv', 'score.json')
    if payload and not existing:
        names = ('forecast_vs_actual.png', 'score_comparison.csv', 'actual_results.csv')
    if plan:
        names = tuple(plan['files'])
        payload = plan['payload']
    # Persist the attachment selection in the first receipt so retries are stable.
    files = ([Path(name) for name in existing['posted_files']] if existing.get('posted_files')
             else [folder / name for name in names])
    if not all(path.is_file() for path in files):
        raise ValueError('The post-race report is incomplete; nothing was posted.')
    message = payload or {'content': (folder / 'post_race_analysis.txt').read_text(encoding='utf-8'), 'embeds': []}
    validate_message(**message)
    attempts = int(existing.get('attempts', 0)) + 1
    write_json(receipt_path, {'ok': False, 'delivery_state': 'sending', 'attempts': attempts,
                              'attempted_at': now.isoformat(), 'posted_files': [str(path) for path in files]})
    try:
        response = post_files_to_discord(webhook_url=webhook_url, **message,
                                        file_paths=files, username='F1 Sim')
    except Exception:
        response = {'ok': False, 'status': 'network_exception'}
    state = delivery_state(response)
    result = {'ok': bool(response.get('ok')), 'status': response.get('status'),
              'delivery_state': state,
              'attempts': attempts, 'attempted_at': datetime.now(timezone.utc).isoformat(),
              'posted_files': [str(path) for path in files]}
    if state == 'pending':
        delay = min(360, 15 * 2 ** min(attempts - 1, 5))
        result['next_attempt_at'] = (now + timedelta(minutes=delay)).isoformat()
    write_json(receipt_path, result)
    return result


def run_post_race_queue(root: Path, *, discord_enabled: bool = False) -> list[dict]:
    """Caller holds the workspace lock. Failures remain visible and retryable."""
    root = Path(root)
    run_root = root / 'outputs/app_runs'
    results = []
    for forecast_folder, manifest in eligible_forecasts(root):
        context = manifest['context']
        race_key = [int(context['year']), str(context['event'])]
        report_folder = None
        # Reuse one completed analysis per race, including when the next race is eligible.
        for path in sorted(run_root.glob('*/job.json')):
            saved = _read(path)
            if (saved.get('kind') == 'score' and saved.get('automated_post_race')
                    and saved.get('status') == 'completed' and saved.get('race_key') == race_key):
                report_folder = path.parent
                break
        if report_folder is None:
            job_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid4().hex[:8]
            report_folder = run_root / job_id
            report_folder.mkdir()
            job = {'id': job_id, 'kind': 'score', 'status': 'running',
                   'label': f"Post-race - {context['year']} {context['event']} - {context['session']}",
                   'created_at': datetime.now(timezone.utc).isoformat(), 'automated_post_race': True,
                   'race_key': race_key, 'forecast_folder': str(forecast_folder),
                   'forecast_id': forecast_folder.name, 'discord_enabled': bool(discord_enabled)}
            write_json(report_folder / 'job.json', job)
            try:
                with (report_folder / 'run.log').open('w', encoding='utf-8') as log:
                    with redirect_stdout(log), redirect_stderr(log):
                        run_scoring(report_folder, forecast_folder)
                        render_analysis(report_folder, context)
            except ResultsNotReady:
                job.update(status='waiting_for_results', finished_at=datetime.now(timezone.utc).isoformat())
                write_json(report_folder / 'job.json', job)
                results.append({'race_key': race_key, 'status': 'waiting_for_results', 'folder': str(report_folder)})
                continue
            except Exception as exc:
                with (report_folder / 'run.log').open('a', encoding='utf-8') as log:
                    traceback.print_exc(file=log)
                job.update(status='failed', error=str(exc), finished_at=datetime.now(timezone.utc).isoformat())
                write_json(report_folder / 'job.json', job)
                results.append({'race_key': race_key, 'status': 'failed', 'folder': str(report_folder),
                                'error': str(exc)})
                continue
            job.update(status='completed', finished_at=datetime.now(timezone.utc).isoformat())
            write_json(report_folder / 'job.json', job)
        try:
            # Check the original source again before using a persisted report.
            source = Path(_read(report_folder / 'job.json')['forecast_folder'])
            verified_snapshot(source)
            if _read(report_folder / 'score.json').get('snapshot_sha256') != digest(source / 'frozen/manifest.json'):
                raise ValueError('The analysis does not match its original frozen forecast.')
            delivery = post_analysis(report_folder) if discord_enabled else None
            from src.app_services.classification_checks import try_capture_checks
            classification_checks = try_capture_checks(root, source, official_folder=report_folder)
            results.append({'race_key': race_key, 'status': 'completed', 'folder': str(report_folder),
                            'discord': delivery, 'classification_checks': classification_checks})
        except (KeyError, OSError, ValueError) as exc:
            results.append({'race_key': race_key, 'status': 'failed', 'folder': str(report_folder),
                            'error': str(exc)})
    return results
