from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

import webview

from src.app_services.app_paths import resource_path, select_workspace
from portable_app.web_backend import PortableWebApi, project_root, WORKSPACE_ENV
from portable_app.instance_lock import workspace_lock


def web_asset(path: str) -> Path:
    return resource_path(Path("portable_app") / "web" / path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Race Workbench portable web app")
    parser.add_argument("--debug", action="store_true", help="Open developer tools where supported")
    parser.add_argument('--race-setup', action='store_true', help='Open Race Setup (the default)')
    parser.add_argument('--simulation-centre', action='store_true', help='Open forecasts, scoring and Simulink tools')
    parser.add_argument('--workspace', type=Path, help='Use a separate local data and results workspace')
    parser.add_argument('--repo-workspace', action='store_true',
                        help="From source, use this checkout's data folder instead of the saved app data folder")
    parser.add_argument('--browser', action='store_true', help='Run in a local web browser instead of a desktop window')
    parser.add_argument('--no-open', action='store_true', help='Start the browser server without opening a tab')
    parser.add_argument('--job-worker', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.job_worker:
        # Windowed runtimes may supply None OR a dummy stdout stream. Always
        # own the worker log explicitly, regardless of inherited handles.
        from contextlib import redirect_stdout, redirect_stderr
        from portable_app.job_worker import run
        with open(Path(args.job_worker)/'run.log', 'a', encoding='utf-8', buffering=1) as log:
            with redirect_stdout(log), redirect_stderr(log):
                try:
                    run(Path(args.job_worker))
                except Exception:
                    # Fail in the log, not a blocking PyInstaller error dialog.
                    import traceback
                    traceback.print_exc()
                    raise SystemExit(1)
        return

    root = select_workspace(args.workspace, project_root(), frozen=getattr(sys, 'frozen', False),
                            use_repo=args.repo_workspace)
    print(f'Using workspace: {root}', flush=True)
    os.chdir(root)
    os.environ[WORKSPACE_ENV] = str(root)
    with workspace_lock(root):
        run_app(args)


def run_app(args):
    api = PortableWebApi()
    if args.browser:
        from portable_app.centre_server import serve
        serve(api, open_browser=not args.no_open, start_page='centre.html' if args.simulation_centre else '')
        return
    index_path = web_asset('centre.html' if args.simulation_centre else 'index.html')
    window = webview.create_window(
        "Race Workbench",
        url=index_path.as_uri(),
        js_api=api,
        width=1664,
        height=960,
        min_size=(1180, 760),
    )
    api.set_window(window)
    window.events.closed += api.lab_cancel
    webview.start(debug=args.debug, icon=str(resource_path(Path("assets") / "race_workbench.ico")))


if __name__ == "__main__":
    main()
