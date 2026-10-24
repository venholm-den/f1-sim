"""One frozen, combined challenger for a whole season (shadow only).

Testing candidates one at a time spends fresh races on each comparison and
never tests them together. A challenger is a single combination of candidate
choices, frozen with the hash of every source file before the season's first
session, and compared with the live model at every race of that season.

A frozen challenger file is write-once. Verification recomputes the source
hashes: any change means it is no longer the same challenger, and a new one
must be frozen for a later season. Freezing never changes live settings,
config files or Discord delivery, and challenger configs reject Discord posting.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = 'challenger_v1'
HASHED = ('main.py', 'src', 'data/track_profiles.csv', 'data/track_calibration', 'data/team_power_units.csv')
HASHED_SUFFIXES = {'.py', '.json', '.csv'}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Times must include a timezone.')
    return parsed.astimezone(timezone.utc)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root: str | Path) -> dict[str, str]:
    """sha256 of every tracked source, config and track file a forecast can read."""
    root = Path(root)
    hashes = {}
    for name in HASHED:
        path = root / name
        files = [path] if path.is_file() else sorted(path.rglob('*')) if path.is_dir() else []
        for file in files:
            if (file.is_file() and file.suffix in HASHED_SUFFIXES and '__pycache__' not in file.parts
                    and not file.name.startswith('.env')):
                hashes[file.relative_to(root).as_posix()] = _digest(file)
    return hashes


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Check names, season, deadline and candidate choices; return a clean copy."""
    from src.app_services.model_candidates import active_candidates
    from src.model_config import SIMULATION_PARAMETERS
    from src.promotion_evidence import lane_for
    name = str(spec.get('name', '')).strip()
    if not name or not name.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Challenger name must be letters, digits, - or _.')
    season = int(spec['season'])
    deadline = _instant(spec['freeze_before_utc'])
    if deadline.year != season:
        raise ValueError('Freeze deadline must fall in the challenger season.')
    candidates = active_candidates(spec.get('candidates'))
    if not candidates:
        raise ValueError('Choose at least one candidate; the live model is the baseline.')
    overrides = {str(k): float(v) for k, v in (spec.get('parameter_overrides') or {}).items()}
    unknown = set(overrides) - set(SIMULATION_PARAMETERS)
    if unknown:
        raise ValueError(f'Unknown simulation parameters: {sorted(unknown)}.')
    return {'name': name, 'season': season, 'freeze_before_utc': deadline.isoformat(),
            'candidates': candidates,
            'lanes': {key: lane_for(key, value) for key, value in candidates.items()},
            'parameter_overrides': overrides,
            'hypothesis': str(spec.get('hypothesis', '')).strip(),
            'primary_metric': str(spec.get('primary_metric', 'rps')),
            'evidence': [str(item) for item in spec.get('evidence', [])]}


def freeze(spec: dict[str, Any], root: str | Path, output_dir: str | Path, *, now: datetime | None = None) -> Path:
    """Write the frozen challenger once. Refuses after the deadline or over an existing file."""
    from src.promotion_evidence import SEQUENTIAL_BOUNDS
    clean = validate_spec(spec)
    current = now or _now()
    if current >= _instant(clean['freeze_before_utc']):
        raise ValueError('The freeze deadline has passed; freeze a challenger for a later season.')
    if clean['primary_metric'] not in SEQUENTIAL_BOUNDS:
        raise ValueError(f'Primary metric must be one of {sorted(SEQUENTIAL_BOUNDS)}.')
    hashes = source_hashes(root)
    record = {'schema': SCHEMA, **clean, 'frozen_at_utc': current.isoformat(),
              'sequential_bounds': dict(SEQUENTIAL_BOUNDS), 'source_hashes': hashes,
              'source_fingerprint': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
              'activated': False, 'promotion_approved': False}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{clean['name']}_{clean['season']}.json"
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
    return path


def load(path: str | Path) -> dict[str, Any]:
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    if record.get('schema') != SCHEMA:
        raise ValueError('Not a frozen challenger file.')
    return record


def verify(path: str | Path, root: str | Path) -> dict[str, Any]:
    """Compare today's sources with the frozen hashes."""
    record = load(path)
    frozen, current = record['source_hashes'], source_hashes(root)
    changed = sorted(n for n in frozen.keys() & current.keys() if frozen[n] != current[n])
    missing = sorted(frozen.keys() - current.keys())
    added = sorted(current.keys() - frozen.keys())
    return {'name': record['name'], 'season': record['season'], 'unchanged': not (changed or missing or added),
            'changed': changed, 'missing': missing, 'added': added}


def run_config(path: str | Path, base_config: dict[str, Any]) -> dict[str, Any]:
    """A validated local run config with the challenger's candidates applied."""
    from src.app_services.model_candidates import apply_candidates
    record = load(path)
    base = json.loads(json.dumps(base_config))
    base.setdefault('outputs', {})['post_to_discord'] = False
    config, _ = apply_candidates(base, record['candidates'])
    config['challenger'] = {'name': record['name'], 'season': record['season'],
                            'source_fingerprint': record['source_fingerprint'],
                            'parameter_overrides': record['parameter_overrides']}
    return config


def season_evidence(path: str | Path, seed_rows, baseline: str = 'live') -> dict[str, Any]:
    """Sequential and gate evidence for the challenger against live, race by race.

    seed_rows: long-format metric rows with year, round, seed and arm columns,
    where the challenger's arm is its frozen name and live is `baseline`.
    Only races in the challenger season count; the freeze deadline precedes them.
    """
    from src.promotion_evidence import accuracy_decision, betting_e_value, paired_races
    record = load(path)
    rows = seed_rows[seed_rows['year'].eq(record['season'])]
    pair = paired_races(rows, record['name'], baseline, race_keys=('year', 'round')).sort_values('round')
    metric = record['primary_metric']
    decision = accuracy_decision(rows, record['name'], baseline, race_keys=('year', 'round'),
                                 bounds=record['sequential_bounds'])
    primary = betting_e_value(pair[metric + '_delta'], record['sequential_bounds'][metric])
    return {'name': record['name'], 'season': record['season'], 'primary_metric': metric,
            'primary': primary, 'gate': decision, 'activated': False, 'promotion_approved': False}
