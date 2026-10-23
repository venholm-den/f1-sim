from __future__ import annotations

import sys
import os
import shutil
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


def initialize_user_workspace(root: Path | None = None) -> Path:
    """Packaged releases never write caches or user settings into the install."""
    target = root or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'RaceWorkbench'
    target.mkdir(parents=True, exist_ok=True)
    for relative in ['config/default_run_config.json','data/fantasy_prices.csv',
                     'data/track_profiles.csv','data/team_power_units.csv','data/fia_documents/fia_document_index.csv']:
        source = bundled_root()/relative
        destination = target/relative
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return target.resolve()
