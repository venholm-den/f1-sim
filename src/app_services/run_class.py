"""Official forecasts versus My simulations.

An official forecast is a frozen prospective snapshot from a forecast job run
with the fixed protocol. Everything else (Race setup runs, what-ifs, replays,
forecasts with changed settings) is a personal simulation: it stays local and
never enters the accuracy record or a publication.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# New forecasts use v2. Unversioned 10k snapshots retain their original status.
OFFICIAL_PROTOCOL_VERSION = '100k_v2'
OFFICIAL_PROTOCOL = {'n_sims': 100_000, 'seed': 42, 'overtaking_difficulty': 0.55}
LEGACY_PROTOCOL = {**OFFICIAL_PROTOCOL, 'n_sims': 10_000}
SETTING_LABELS = {'n_sims': 'Simulations', 'seed': 'Seed', 'overtaking_difficulty': 'Overtaking difficulty'}


def protocol_changes(job: dict, *, protocol: dict | None = None) -> list[dict]:
    """Settings that differ from the official protocol. A missing setting is not a change."""
    changes = []
    for key, official in (OFFICIAL_PROTOCOL if protocol is None else protocol).items():
        if job.get(key) is None:
            continue
        try:
            used = float(job[key])
        except (TypeError, ValueError):
            used = math.nan
        if not math.isclose(used, official, rel_tol=0, abs_tol=1e-9):
            changes.append({'setting': key, 'label': SETTING_LABELS[key], 'official': official, 'used': job[key]})
    return changes


def describe(changes: list[dict]) -> list[str]:
    return [f"{c['label']} {c['official']} → {c['used']}" for c in changes]


def _read(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def classify(folder, job: dict | None = None) -> dict:
    """official or personal for one run folder, with the reasons a run is personal."""
    folder = Path(folder)
    job = _read(folder/'job.json') if job is None else job
    manifest = _read(folder/'frozen/manifest.json')
    reasons = []
    if job.get('kind') != 'forecast':
        reasons.append('Not a forecast run (Race setup, what-if or replay)')
    if not manifest:
        reasons.append('No frozen pre-race snapshot')
    elif manifest.get('category') != 'prospective':
        reasons.append(f"Snapshot category is {manifest.get('category')!r}, not prospective")
    protocol = (LEGACY_PROTOCOL if not job.get('protocol_version') and job.get('n_sims') == 10_000
                else OFFICIAL_PROTOCOL)
    if job.get('protocol_version') not in (None, OFFICIAL_PROTOCOL_VERSION):
        reasons.append('Unknown official protocol version')
    changes = protocol_changes(job, protocol=protocol)
    if changes:
        reasons.append('Changed from the official protocol: ' + '; '.join(describe(changes)))
    return {'run_class': 'personal' if reasons else 'official', 'reasons': reasons, 'changes': changes}


def require_official(folder, job: dict | None = None) -> dict:
    result = classify(folder, job)
    if result['run_class'] != 'official':
        raise ValueError('This is a personal simulation, not an official forecast: ' + '; '.join(result['reasons']) + '.')
    return result
