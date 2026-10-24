from __future__ import annotations

import hashlib
import json
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


def user_workspace_dir() -> Path:
    """The saved app data folder the packaged app uses (%LOCALAPPDATA%\\RaceWorkbench)."""
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'RaceWorkbench'


def select_workspace(explicit: Path | None, repo_root: Path, *, frozen: bool, use_repo: bool = False) -> Path:
    """Choose the data and results folder for this launch.

    Source runs share the packaged app's saved data folder when it exists, so
    both see the same downloads and results. --repo-workspace keeps the
    checkout's own folders; --workspace always wins.
    """
    if explicit:
        return initialize_user_workspace(explicit)
    if frozen or (not use_repo and user_workspace_dir().is_dir()):
        return initialize_user_workspace()
    return repo_root


SEEDED_FILES = ['config/default_run_config.json', 'data/fantasy_prices.csv', 'data/track_profiles.csv',
                'data/team_power_units.csv', 'data/fia_documents/fia_document_index.csv']
SEED_RECORD = 'config/.bundled_seed.json'


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize_user_workspace(root: Path | None = None) -> Path:
    """Packaged releases never write caches or user settings into the install.

    Bundled config and reference data are copied in once. A later release
    replaces a copy only while it still matches what was copied, so files the
    user (or the FIA sync) changed are always kept.
    """
    target = root or user_workspace_dir()
    target.mkdir(parents=True, exist_ok=True)
    record_path = target/SEED_RECORD
    try:
        record = json.loads(record_path.read_text(encoding='utf-8'))
        record = record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        record = {}
    updated = dict(record)
    for relative in SEEDED_FILES:
        source = bundled_root()/relative
        destination = target/relative
        if not source.is_file():
            continue
        bundled = _sha256(source)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            updated[relative] = bundled
            continue
        current = _sha256(destination)
        if current == bundled:
            updated[relative] = bundled
        elif record.get(relative) == current:
            # Unedited copy of an older release: take the new bundled data.
            temporary = destination.with_name(destination.name + '.seed.tmp')
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
            updated[relative] = bundled
    if updated != record:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(updated, indent=2, sort_keys=True), encoding='utf-8')
    return target.resolve()
