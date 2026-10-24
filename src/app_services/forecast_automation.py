"""Session-aware, local-only automation for prospective race forecasts."""
from __future__ import annotations

import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from portable_app.instance_lock import workspace_lock
from src.app_services.beta import next_race, run_forecast, verified_snapshot
from src.app_services.simulation_jobs import write_json
from src.discord_post import post_files_to_discord, validate_message
from src.app_services.discord_reports import forecast_message
from src.app_services.discord_cards import render_forecast_cards


def context_key(context: dict) -> tuple[int, str, str]:
    """Return the fields that identify a newly eligible forecast input set."""
    return int(context["year"]), str(context["event"]), str(context["session"])


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def find_frozen_forecast(root: Path, context: dict) -> Path | None:
    """Find a valid completed snapshot for this race and eligible session."""
    target = context_key(context)
    run_root = Path(root) / "outputs" / "app_runs"
    candidates = []
    for job_path in run_root.glob("*/job.json"):
        job = _read_json(job_path)
        if not job or job.get("kind") != "forecast" or job.get("status") != "completed":
            continue
        folder = job_path.parent
        saved_context = _read_json(folder / "forecast_context.json")
        if not saved_context or context_key(saved_context) != target:
            continue
        try:
            manifest = verified_snapshot(folder)
            created = datetime.fromisoformat(manifest['created_at_utc'])
            requested = datetime.fromisoformat(job.get('created_at', manifest['created_at_utc']))
            if created.tzinfo is None or requested.tzinfo is None:
                continue
        except (KeyError, OSError, ValueError):
            continue
        candidates.append((created, requested, folder.name, folder))
    return max(candidates)[-1] if candidates else None


def _interrupt_orphaned_jobs(run_root: Path) -> None:
    """A lock-owning process cannot coexist with a genuinely active app job."""
    for job_path in run_root.glob("*/job.json"):
        job = _read_json(job_path)
        if not job or job.get("status") not in {"running", "cancelling"}:
            continue
        job.update(
            status="interrupted",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error="The previous process ended before it recorded completion.",
        )
        write_json(job_path, job)


def _discord_files(folder: Path) -> list[Path]:
    """Return the stable forecast table plus a bounded visual bundle."""
    files = [folder / "frozen" / "simulation_summary.csv"]
    report_dir = folder / "source" / "report"
    files.extend(sorted(report_dir.glob("*.png")))
    for name in ("probabilities.png", "fantasy_expected_points.png", "fantasy_value.png", "detailed_report.png"):
        files.append(folder / "source" / name)
    files.extend(
        [
            folder / "source" / "strategy" / "predicted_tyre_strategy.png",
            folder / "source" / "season" / "latest_season_projection.png",
        ]
    )
    unique: list[Path] = []
    for path in files:
        if path.is_file() and path not in unique:
            unique.append(path)
    return unique


def _forecast_delivery_plan(folder: Path) -> dict:
    """Pin the message and attachment order before the first delivery attempt."""
    destination = folder / 'discord_report'
    path = destination / 'delivery_plan.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    legacy = (folder / 'discord_post_result.json').exists() or any(folder.glob('discord_batch_*_result.json'))
    detail = os.getenv('DISCORD_REPORT_DETAIL', 'compact').strip().lower()
    if detail not in {'compact', 'full'}:
        raise ValueError('DISCORD_REPORT_DETAIL must be compact or full.')
    payload = forecast_message(folder)
    destination.mkdir(exist_ok=True)
    if legacy:
        # A partially delivered legacy bundle must keep its original batch order.
        files = _discord_files(folder)
    else:
        charts = render_forecast_cards(folder, destination)
        files = [*charts, folder / 'frozen/simulation_summary.csv']
        from src.app_services.driver_explanations import render_driver_explanations
        evidence = render_driver_explanations(folder, destination)
        files.extend(file for file in evidence if detail == 'full' or file.suffix != '.png')
        if detail == 'full':
            files.extend(file for file in _discord_files(folder) if file not in files)
    plan = {'format_version': 3, 'detail': 'legacy' if legacy else detail,
            'payload': payload, 'files': [str(file.relative_to(folder)) for file in files]}
    write_json(path, plan)
    return plan


def post_frozen_forecast(folder: Path, webhook_url: str | None = None) -> dict:
    """Deliver all available outputs in batches, without resending successful ones."""
    folder = Path(folder)
    receipt = _read_json(folder / 'discord_post_result.json')
    if receipt and (receipt.get('ok') or receipt.get('delivery_state') in {'sending', 'uncertain'}):
        return {**receipt, 'skipped': True,
                'requires_review': not bool(receipt.get('ok'))}
    plan = _forecast_delivery_plan(folder)
    files = [folder / name for name in plan['files']]
    if len(files) <= 10:
        return _post_forecast_batch(folder, webhook_url, files, message=plan['payload'])
    results = []
    for index in range(0, len(files), 10):
        message = plan['payload'] if index == 0 else {
            'content': (f"{plan['payload']['embeds'][0]['title']} — supporting attachments "
                        f"({index // 10 + 1}/{(len(files) + 9) // 10})."), 'embeds': []}
        result = _post_forecast_batch(folder, webhook_url, files[index:index + 10],
                                      f'discord_batch_{index // 10 + 1}_result.json', message=message)
        results.append(result)
        if not result.get('ok'):
            return result
    result = {'ok': True, 'delivery_state': 'sent', 'status': results[-1]['status'],
              'posted_files': [str(path) for path in files], 'batches': len(results),
              'attempted_at': datetime.now(timezone.utc).isoformat()}
    write_json(folder / 'discord_post_result.json', result)
    return result


def _post_forecast_batch(folder: Path, webhook_url: str | None, files: list[Path],
                         receipt_name: str = 'discord_post_result.json', *, message: dict | None = None) -> dict:
    """Post a frozen forecast once; failed attempts remain retryable."""
    folder = Path(folder)
    receipt_path = folder / receipt_name
    existing = _read_json(receipt_path)
    if existing and existing.get("ok"):
        return {**existing, "skipped": True}
    if existing and existing.get('delivery_state') in {'sending', 'uncertain'}:
        return {**existing, 'skipped': True, 'requires_review': True}
    if existing and existing.get('next_attempt_at'):
        if datetime.now(timezone.utc) < datetime.fromisoformat(existing['next_attempt_at']):
            return {**existing, 'skipped': True}

    manifest = verified_snapshot(folder)
    context = manifest["context"]
    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        raise ValueError(
            "DISCORD_WEBHOOK_URL is missing. Add it to the project .env file before enabling Discord."
        )

    message = message or forecast_message(folder)
    validate_message(**message)
    if not files or not all(path.is_file() for path in files):
        raise ValueError('Forecast attachments are missing; nothing was posted.')
    attempts = int((existing or {}).get('attempts', 0)) + 1
    # Reserve delivery before making the network request. A crash after Discord
    # accepts it leaves an uncertain delivery for review instead of reposting.
    write_json(receipt_path, {'ok': False, 'delivery_state': 'sending',
        'attempts': attempts, 'attempted_at': datetime.now(timezone.utc).isoformat()})
    try:
        result = post_files_to_discord(
            webhook_url=webhook_url,
            **message,
            file_paths=files,
            username="F1 Sim",
        )
    except Exception:
        result = {'ok': False, 'status': 'network_exception'}
    # Transport errors cannot prove whether Discord accepted the message.
    uncertain = result.get('status') in {'url_error', 'network_exception'}
    result['delivery_state'] = 'sent' if result.get('ok') else ('uncertain' if uncertain else 'pending')
    result['attempts'] = attempts
    if not result.get('ok') and not uncertain:
        delay = min(360, 15 * 2 ** min(attempts - 1, 5))
        result['next_attempt_at'] = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()
    if "posted_files" in result:
        result["posted_files"] = [str(path) for path in result["posted_files"]]
    if result.get("ok"):
        # The full Discord response contains transient CDN URLs and identifiers;
        # the durable receipt only needs the success status and local file list.
        result.pop("response", None)
    result.update(
        attempted_at=datetime.now(timezone.utc).isoformat(),
        context_key=list(context_key(context)),
    )
    write_json(receipt_path, result)
    if not result.get("ok"):
        raise RuntimeError(f"Discord post failed with status {result.get('status')}.")
    return result


def _deliver(folder: Path, discord_enabled: bool):
    """Post first, but hold a failure until this run's captures are saved."""
    if not discord_enabled:
        return None, None
    try:
        return post_frozen_forecast(folder), None
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        return None, exc


def drain_discord_queue(root: Path) -> list[dict]:
    """Retry eligible deliveries across all completed automated forecasts."""
    deliveries = []
    for path in sorted((root / 'outputs' / 'app_runs').glob('*/job.json')):
        job = _read_json(path) or {}
        if job.get('kind') != 'forecast' or job.get('status') != 'completed' or not job.get('discord_enabled'):
            continue
        try:
            result = post_frozen_forecast(path.parent)
            deliveries.append({'id': job['id'], **result})
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            deliveries.append({'id': job.get('id'), 'ok': False, 'error': str(exc)})
    return deliveries


# The frozen-forecast protocol shared by PC automation and the Centre's
# "Forecast next race" button, so both produce comparable snapshots.
FORECAST_DEFAULTS = {'n_sims': 10_000, 'seed': 42, 'overtaking_difficulty': 0.55}


def run_automated_forecast(
    root: Path,
    *,
    n_sims: int = FORECAST_DEFAULTS['n_sims'],
    seed: int = FORECAST_DEFAULTS['seed'],
    overtaking_difficulty: float = FORECAST_DEFAULTS['overtaking_difficulty'],
    discord_enabled: bool = False,
    post_race_enabled: bool = False,
) -> dict:
    """Run for a new session or changed verified FIA grid; retain every snapshot."""
    root = Path(root).resolve()
    if not 100 <= int(n_sims) <= 100_000:
        raise ValueError("Use 100-100,000 simulations.")
    if not 0 <= int(seed) <= 2**32 - 1:
        raise ValueError("Seed must be between 0 and 4,294,967,295.")
    if not 0 <= float(overtaking_difficulty) <= 1:
        raise ValueError("Overtaking difficulty must be between 0 and 1.")

    with workspace_lock(root):
        run_root = root / "outputs" / "app_runs"
        run_root.mkdir(parents=True, exist_ok=True)
        _interrupt_orphaned_jobs(run_root)
        deliveries = drain_discord_queue(root) if discord_enabled else []
        post_race = []
        if post_race_enabled:
            from src.app_services.post_race_automation import run_post_race_queue
            post_race = run_post_race_queue(root, discord_enabled=discord_enabled)
        context = next_race(root)
        existing = find_frozen_forecast(root, context)
        grid_update = None
        if existing is not None:
            from src.app_services.grid_updates import forecast_grid_status
            grid_update = forecast_grid_status(root, existing, context, cutoff=context['data_cutoff_utc'])
            if grid_update['status'] == 'grid_update_available' and grid_update['refresh_allowed']:
                context = {**context, 'revision_reason':'fia_grid_update',
                           'supersedes_forecast':existing.name, 'grid_revision':grid_update}
                existing = None
        if existing is not None:
            from src.app_services.ensemble_shadow import try_capture_shadow
            ensemble_shadow = try_capture_shadow(root, existing)
            from src.app_services.prediction_trials import try_capture_trial, try_collect_current_practice
            current_practice = try_collect_current_practice(root, context)
            discord_result, discord_error = _deliver(existing, discord_enabled)
            prediction_trial = try_capture_trial(root, existing)
            from src.app_services.classification_checks import try_capture_checks
            classification_checks = try_capture_checks(root, existing)
            from src.app_services.race_weather_updates import capture_weather_update
            try:
                weather_update = capture_weather_update(root, context)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                weather_update = {'status': 'capture_failed', 'error_type': type(exc).__name__}
            if discord_error:
                raise discord_error
            return {
                "status": "skipped",
                "reason": "already_completed",
                "context": context,
                "folder": str(existing),
                "discord": discord_result,
                "deliveries": deliveries,
                "post_race": post_race,
                "weather_update": weather_update,
                "ensemble_shadow": ensemble_shadow,
                "prediction_trial": prediction_trial,
                "classification_checks": classification_checks,
                "current_practice": current_practice,
                "grid_update": grid_update,
            }

        job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
        folder = run_root / job_id
        folder.mkdir()
        job = {
            "id": job_id,
            "label": "Next race forecast",
            "kind": "forecast",
            "scenario": "all",
            "input_source": "saved",
            "historical": None,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_dir": str(folder / "source"),
            "n_sims": int(n_sims),
            "seed": int(seed),
            "overtaking_difficulty": float(overtaking_difficulty),
            "matlab": None,
            "forecast_folder": None,
            "note": (
                "Automated local forecast; Discord upload enabled after freeze."
                if discord_enabled
                else "Automated local forecast; no upload or Discord publishing."
            ),
            "discord_enabled": bool(discord_enabled),
            "revision_reason": context.get('revision_reason'),
            "supersedes_forecast": context.get('supersedes_forecast'),
        }
        write_json(folder / "job.json", job)

        try:
            with (folder / "run.log").open("w", encoding="utf-8", buffering=1) as log:
                with redirect_stdout(log), redirect_stderr(log):
                    run_forecast(folder, job, context=context)
                    if context.get('grid_revision'):
                        from src.app_services.grid_updates import validate_grid_revision
                        validate_grid_revision(folder, context['grid_revision'])
        except Exception as exc:
            with (folder / "run.log").open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            job.update(
                status="failed",
                exit_code=1,
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            write_json(folder / "job.json", job)
            raise

        saved_context = _read_json(folder / "forecast_context.json") or context
        job.update(
            status="completed",
            exit_code=0,
            label=(
                f"Next race - {saved_context['year']} {saved_context['event']} - "
                f"{saved_context['session']}"
            ),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json(folder / "job.json", job)
        from src.app_services.ensemble_shadow import try_capture_shadow
        ensemble_shadow = try_capture_shadow(root, folder)
        from src.app_services.prediction_trials import try_capture_trial, try_collect_current_practice
        current_practice = try_collect_current_practice(root, saved_context)
        discord_result, discord_error = _deliver(folder, discord_enabled)
        prediction_trial = try_capture_trial(root, folder)
        from src.app_services.classification_checks import try_capture_checks
        classification_checks = try_capture_checks(root, folder)
        if discord_error:
            raise discord_error
        return {
            "status": "completed",
            "context": saved_context,
            "folder": str(folder),
            "discord": discord_result,
            "deliveries": deliveries,
            "post_race": post_race,
            "ensemble_shadow": ensemble_shadow,
            "prediction_trial": prediction_trial,
            "classification_checks": classification_checks,
            "current_practice": current_practice,
        }
