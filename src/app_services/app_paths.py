from __future__ import annotations

import sys
from pathlib import Path


def bundled_root() -> Path:
    """Return the root used for bundled read-only resources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]

    return Path(__file__).resolve().parents[2]


def resource_path(path: str | Path) -> Path:
    file_path = Path(path)

    if file_path.is_absolute():
        return file_path

    local_path = Path.cwd() / file_path

    if local_path.exists():
        return local_path

    return bundled_root() / file_path
