from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _guess_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _multipart_body(
    fields: dict[str, str],
    file_paths: list[str | Path],
) -> tuple[bytes, str]:
    boundary = f"----f1-sim-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    for index, file_path in enumerate(file_paths):
        path = Path(file_path)
        filename = path.name
        content_type = _guess_content_type(path)

        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="files[{index}]"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def post_files_to_discord(
    webhook_url: str,
    content: str,
    file_paths: list[str | Path],
    username: str | None = None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Post one message with file attachments to a Discord webhook."""

    if not webhook_url:
        return {"ok": False, "status": "missing_webhook_url"}

    existing_files = [str(Path(path)) for path in file_paths if path and Path(path).exists()]

    if not existing_files:
        return {"ok": False, "status": "no_files_to_post"}

    fields = {"content": content}

    if username:
        fields["username"] = username

    body, boundary = _multipart_body(fields, existing_files)

    request = Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "f1-sim-backtest/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "response": response_body,
                "posted_files": existing_files,
            }
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "response": response_body,
            "posted_files": existing_files,
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": "url_error",
            "response": str(exc),
            "posted_files": existing_files,
        }


def _metric_value(metrics_path: str | Path | None, key: str) -> str | None:
    if not metrics_path or not Path(metrics_path).exists():
        return None

    try:
        import pandas as pd

        df = pd.read_csv(metrics_path)
    except Exception:
        return None

    if df.empty or key not in df.columns:
        return None

    value = df.iloc[0][key]

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if key.endswith("accuracy") or key.endswith("score") or key.endswith("overlap"):
        return f"{number:.0%}"

    return f"{number:.2f}"


def post_backtest_to_discord(
    paths: dict[str, str],
    webhook_url: str | None = None,
    event_title: str | None = None,
) -> dict[str, Any]:
    webhook_url = webhook_url or os.getenv("BACKTEST_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")

    pngs = [
        paths.get("strategy_comparison_png"),
        paths.get("backtest_metrics_png"),
        paths.get("finish_comparison_png"),
    ]
    pngs = [path for path in pngs if path and Path(path).exists()]

    strategy_accuracy = _metric_value(paths.get("strategy_metrics"), "stop_count_accuracy")
    exact_accuracy = _metric_value(paths.get("strategy_metrics"), "exact_strategy_accuracy")
    finish_mae = _metric_value(paths.get("metrics"), "finish_mae")

    lines = [f"Backtest complete{f' for {event_title}' if event_title else ''}."]

    if finish_mae:
        lines.append(f"Finish MAE: {finish_mae}")
    if strategy_accuracy:
        lines.append(f"Strategy stop accuracy: {strategy_accuracy}")
    if exact_accuracy:
        lines.append(f"Exact strategy accuracy: {exact_accuracy}")

    lines.append("See attached PNG summaries.")

    return post_files_to_discord(
        webhook_url=webhook_url or "",
        content="\n".join(lines),
        file_paths=pngs,
        username="F1 Sim Backtest",
    )


def write_discord_post_result(result: dict[str, Any], output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return str(path)
