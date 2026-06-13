from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import requests


DISCORD_MESSAGE_LIMIT = 2000
SAFE_MESSAGE_LIMIT = 1850
MAX_FILES_PER_MESSAGE = 10


def _get_webhook_url(webhook_url: str | None = None) -> str:
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    url = url.strip()

    if not url:
        raise ValueError(
            "No Discord webhook URL found. Add DISCORD_WEBHOOK_URL to your .env file."
        )

    return url


def _chunk_message(message: str) -> list[str]:
    text = str(message or "").strip()

    if not text:
        return []

    chunks: list[str] = []
    current = ""

    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line

        if len(candidate) <= SAFE_MESSAGE_LIMIT:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(line) <= SAFE_MESSAGE_LIMIT:
            current = line
        else:
            for i in range(0, len(line), SAFE_MESSAGE_LIMIT):
                chunks.append(line[i : i + SAFE_MESSAGE_LIMIT])
            current = ""

    if current:
        chunks.append(current)

    return chunks


def _existing_files(files: list[str] | tuple[str, ...] | None) -> list[str]:
    if not files:
        return []

    valid_files: list[str] = []

    for file_path in files:
        path = Path(file_path)

        if path.exists() and path.is_file():
            valid_files.append(str(path))
        else:
            print(f"Discord attachment skipped, file not found: {file_path}")

    return valid_files


def _raise_for_discord_error(response: requests.Response) -> None:
    if response.status_code in {200, 204}:
        return

    try:
        detail: Any = response.json()
    except Exception:
        detail = response.text

    raise RuntimeError(
        "Discord webhook failed "
        f"with status {response.status_code}: {detail}"
    )


def _post_text(
    webhook_url: str,
    content: str,
) -> None:
    if not content.strip():
        return

    response = requests.post(
        webhook_url,
        json={"content": content[:DISCORD_MESSAGE_LIMIT]},
        timeout=30,
    )

    _raise_for_discord_error(response)


def _post_file_batch(
    webhook_url: str,
    files: list[str],
    content: str | None = None,
) -> None:
    if not files:
        return

    payload = {}

    if content and content.strip():
        payload["content"] = content[:DISCORD_MESSAGE_LIMIT]

    with ExitStack() as stack:
        multipart_files = {}

        for index, file_path in enumerate(files):
            path = Path(file_path)
            handle = stack.enter_context(path.open("rb"))

            multipart_files[f"files[{index}]"] = (
                path.name,
                handle,
                "application/octet-stream",
            )

        response = requests.post(
            webhook_url,
            data={"payload_json": json.dumps(payload)},
            files=multipart_files,
            timeout=120,
        )

    _raise_for_discord_error(response)


def post_to_discord(
    content: str | None = None,
    files: list[str] | tuple[str, ...] | None = None,
    webhook_url: str | None = None,
    message: str | None = None,
) -> None:
    """
    Posts a message and optional files to a Discord webhook.

    Supports both:
    - post_to_discord(content="...", files=[...])
    - post_to_discord(message="...", files=[...])
    """

    url = _get_webhook_url(webhook_url)

    final_message = content if content is not None else message
    message_chunks = _chunk_message(final_message or "")
    valid_files = _existing_files(files)

    if not message_chunks and not valid_files:
        print("Discord post skipped: no message or files supplied.")
        return

    if not valid_files:
        for chunk in message_chunks:
            _post_text(url, chunk)
        return

    file_batches = [
        valid_files[i : i + MAX_FILES_PER_MESSAGE]
        for i in range(0, len(valid_files), MAX_FILES_PER_MESSAGE)
    ]

    if len(message_chunks) <= 1:
        first_content = message_chunks[0] if message_chunks else None

        _post_file_batch(
            webhook_url=url,
            files=file_batches[0],
            content=first_content,
        )

        for batch in file_batches[1:]:
            _post_file_batch(
                webhook_url=url,
                files=batch,
                content=None,
            )

        return

    for chunk in message_chunks:
        _post_text(url, chunk)

    for index, batch in enumerate(file_batches, start=1):
        batch_message = (
            f"Report images batch {index}/{len(file_batches)}"
            if len(file_batches) > 1
            else "Report images"
        )

        _post_file_batch(
            webhook_url=url,
            files=batch,
            content=batch_message,
        )