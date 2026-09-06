from __future__ import annotations

import argparse
import sys
from pathlib import Path

import webview

from src.app_services.app_paths import resource_path
from portable_app.web_backend import PortableWebApi, project_root
from portable_app.instance_lock import workspace_lock


def web_asset(path: str) -> Path:
    return resource_path(Path("portable_app") / "web" / path)


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Race Simulator portable web app")
    parser.add_argument("--debug", action="store_true", help="Open developer tools where supported")
    parser.add_argument('--race-setup', action='store_true', help='Open the original race dashboard')
    parser.add_argument('--browser', action='store_true', help='Run in a local web browser instead of a desktop window')
    parser.add_argument('--no-open', action='store_true', help='Start the browser server without opening a tab')
    parser.add_argument('--job-worker', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.job_worker:
        from portable_app.job_worker import run
        run(Path(args.job_worker))
        return

    root = Path.cwd() if getattr(sys, 'frozen', False) else project_root()
    with workspace_lock(root):
        run_app(args)


def run_app(args):
    api = PortableWebApi()
    if args.browser:
        from portable_app.centre_server import serve
        serve(api, open_browser=not args.no_open)
        return
    index_path = web_asset('index.html' if args.race_setup else 'centre.html')
    window = webview.create_window(
        "F1 Race Simulator",
        url=index_path.as_uri(),
        js_api=api,
        width=1440,
        height=920,
        min_size=(1180, 760),
    )
    api.set_window(window)
    window.events.closed += api.lab_cancel
    webview.start(debug=args.debug)


if __name__ == "__main__":
    main()
