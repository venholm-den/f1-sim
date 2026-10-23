"""Run the session-aware forecast check used by Windows Task Scheduler."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.app_services.forecast_automation import (
    find_frozen_forecast,
    run_automated_forecast,
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one forecast when a new F1 session is eligible.")
    parser.add_argument("--n-sims", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument('--post-race', action='store_true',
                        help='Evaluate completed races and post analysis when --discord is enabled.')
    parser.add_argument('--post-race-only', action='store_true',
                        help='Evaluate completed races without preparing a new forecast.')
    parser.add_argument('--weekend-briefing', action='store_true',
                        help='Post one weekend schedule/track card at 09:00 UK time on the day before FP1 (requires --discord).')
    parser.add_argument('--env-file', type=Path, default=None,
                        help='Explicit project-relative or absolute dotenv file; defaults to .env.')
    parser.add_argument("--overtaking-difficulty", type=float, default=0.55)
    parser.add_argument(
        "--discord",
        action="store_true",
        help="Upload each successfully frozen forecast to the configured Discord webhook.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Show the eligible session without starting a forecast.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    env_file = args.env_file or root / '.env'
    if not env_file.is_absolute():
        env_file = root / env_file
    if args.env_file is not None and not env_file.is_file():
        raise ValueError('The explicitly selected environment file does not exist.')
    load_dotenv(env_file)
    weekend = None
    try:
        if args.weekend_briefing and not args.post_race_only:
            from portable_app.instance_lock import workspace_lock
            from src.app_services.weekend_briefing import run_weekend_briefing
            try:
                if args.check_only:
                    weekend = run_weekend_briefing(root, check_only=True)
                else:
                    with workspace_lock(root):
                        weekend = run_weekend_briefing(root, discord_enabled=args.discord)
            except RuntimeError as exc:
                if 'already open' in str(exc).lower():
                    raise
                weekend = {'status': 'failed', 'error_type': type(exc).__name__}
            except Exception as exc:
                weekend = {'status': 'failed', 'error_type': type(exc).__name__}
        fia = None
        if not args.check_only:
            from portable_app.instance_lock import workspace_lock
            from src.data_sources.fia_sync import refresh
            with workspace_lock(root):
                try:
                    fia = refresh(root)
                except Exception as exc:
                    fia = {'status': 'error', 'error': type(exc).__name__}
        fantasy = None
        if not args.check_only:
            from src.fantasy_market import collect
            try:
                fantasy = collect(root)
            except Exception as exc:
                fantasy = {'status': 'error', 'error': type(exc).__name__}
        if args.check_only:
            from src.app_services.beta import next_race

            context = next_race(root)
            existing = find_frozen_forecast(root, context)
            from src.app_services.grid_updates import forecast_grid_status
            grid_update = forecast_grid_status(root, existing, context, cutoff=context['data_cutoff_utc']) if existing else None
            result = {
                "status": "grid_update_ready" if grid_update and grid_update['status']=='grid_update_available' and grid_update['refresh_allowed'] else "already_completed" if existing else "ready",
                "context": context,
                "folder": str(existing) if existing else None,
                "grid_update": grid_update,
            }
        elif args.post_race_only:
            from portable_app.instance_lock import workspace_lock
            from src.app_services.post_race_automation import run_post_race_queue
            with workspace_lock(root):
                result = {'post_race': run_post_race_queue(root, discord_enabled=args.discord)}
        else:
            result = run_automated_forecast(
                root,
                n_sims=args.n_sims,
                seed=args.seed,
                overtaking_difficulty=args.overtaking_difficulty,
                discord_enabled=args.discord,
                post_race_enabled=args.post_race,
            )
        if fantasy is not None:
            result['fantasy_collection'] = fantasy
        if weekend is not None:
            result['weekend_briefing'] = weekend
        if fia is not None:
            result['fia_collection'] = fia
        if not args.check_only:
            from src.app_services.ensemble_shadow import score_shadow_queue
            result['ensemble_shadow_scoring'] = score_shadow_queue(root)
            from src.app_services.prediction_trials import score_trials, comparison_report
            try:
                with workspace_lock(root):
                    result['prediction_trial_scoring'] = score_trials(root)
                    if (root/'config/prediction_trials.json').is_file():
                        result['prediction_trial_report'] = comparison_report(root)
            except Exception as exc:
                result['prediction_trial_scoring'] = {'status':'failed','error_type':type(exc).__name__}
        if not args.check_only:
            from src.app_services.automation_health import record
            result['health'] = record(root, result)
        print(json.dumps(result, indent=2))
        return result.get('health', {}).get('exit_code', 0)
    except RuntimeError as exc:
        if "already open" in str(exc).lower():
            print(json.dumps({"status": "skipped", "reason": "simulation_centre_open"}, indent=2))
            return 0
        if args.check_only:
            raise
        from src.app_services.automation_health import record
        result = {'status': 'failed', 'error_type': type(exc).__name__, 'weekend_briefing': weekend}
        result['health'] = record(root, result)
        print(json.dumps(result, indent=2))
        return 1
    except Exception as exc:
        if args.check_only:
            raise
        from src.app_services.automation_health import record
        result = {'status': 'failed', 'error_type': type(exc).__name__, 'weekend_briefing': weekend}
        result['health'] = record(root, result)
        print(json.dumps(result, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
