from __future__ import annotations

import argparse
from pathlib import Path

import webview

from src.app_services.app_paths import resource_path
from portable_app.web_backend import PortableWebApi


def web_asset(path: str) -> Path:
    return resource_path(Path("portable_app") / "web" / path)


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Race Simulator portable web app")
    parser.add_argument("--debug", action="store_true", help="Open developer tools where supported")
    args = parser.parse_args()

    api = PortableWebApi()
    index_path = web_asset("index.html")
    window = webview.create_window(
        "F1 Race Simulator",
        url=index_path.as_uri(),
        js_api=api,
        width=1440,
        height=920,
        min_size=(1180, 760),
    )
    api.set_window(window)
    webview.start(debug=args.debug)


if __name__ == "__main__":
    main()
