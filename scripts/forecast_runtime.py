"""Seal, verify and run a versioned local forecast source snapshot.

The snapshot has private code/config and shares only data and outputs with the
development workspace. Verification happens before importing the automation.
This detects accidental drift; it is not an adversarial security boundary.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import runpy
import sys


MANIFEST = 'forecast-runtime.json'
SOURCE_FOLDERS = ('src', 'scripts', 'portable_app', 'config', 'assets', 'matlab')
ROOT_FILES = ('main.py', 'requirements.txt', 'requirements-dev.txt', 'LICENSE')


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    files = {root/name for name in ROOT_FILES if (root/name).is_file()}
    for name in SOURCE_FOLDERS:
        files.update(p for p in (root/name).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts
                     and p.suffix not in {'.pyc', '.pyo', '.log', '.tmp'})
    return {p.relative_to(root).as_posix(): fingerprint(p) for p in sorted(files)}


def installed_dependencies(root):
    names = set()
    for line in (root/'requirements.txt').read_text(encoding='utf-8').splitlines():
        match = re.match(r'^([A-Za-z0-9_.-]+)==', line.strip())
        if match:
            names.add(match[1])
    return {name: version(name) for name in sorted(names)}


def seal(root, workspace):
    """Write once, after suite registration and validation in the snapshot."""
    root, workspace = Path(root).resolve(), Path(workspace).resolve()
    if root == workspace:
        raise ValueError('Seal a separate snapshot, not the development checkout.')
    from src.app_services.prediction_trials import read_suite
    suite = read_suite(root)
    if suite is None:
        raise ValueError('An enabled, verified shadow suite is required.')
    targets = {name: str((workspace/name).resolve()) for name in ('data', 'outputs')}
    for name, target in targets.items():
        if (root/name).resolve() != Path(target):
            raise ValueError(f'{name} must share the original workspace.')
    from datetime import datetime, timezone
    manifest = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'workspace': str(workspace), 'shared_targets': targets,
                'python': str(Path(sys.executable).resolve()),
                'dependencies': installed_dependencies(root),
                'suite_sha256': suite[2], 'files': inventory(root)}
    with (root/MANIFEST).open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
    return manifest


def verify(root):
    """Read-only verification. Never repair or silently reseal a runtime."""
    root = Path(root).resolve()
    manifest = json.loads((root/MANIFEST).read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1:
        raise ValueError('Unsupported forecast runtime manifest.')
    actual, expected = inventory(root), manifest['files']
    changed = sorted(name for name in actual.keys() | expected.keys()
                     if actual.get(name) != expected.get(name))
    if changed:
        raise ValueError('Forecast runtime files changed: ' + ', '.join(changed))
    if Path(sys.executable).resolve() != Path(manifest['python']).resolve():
        raise ValueError('Forecast runtime Python executable changed.')
    for name, expected_version in manifest['dependencies'].items():
        if version(name) != expected_version:
            raise ValueError(f'Forecast runtime dependency changed: {name}.')
    for name, target in manifest['shared_targets'].items():
        if name not in ('data', 'outputs') or (root/name).resolve() != Path(target).resolve():
            raise ValueError('Forecast runtime shared workspace changed.')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seal', 'verify', 'run'))
    parser.add_argument('--workspace', type=Path, help='Original data/output workspace, for seal only.')
    args, forwarded = parser.parse_known_args()
    if forwarded and args.mode != 'run':
        parser.error('Automation arguments are accepted only by run.')
    root = Path(__file__).resolve().parents[1]
    try:
        if args.mode == 'seal':
            if args.workspace is None:
                parser.error('seal requires --workspace')
            manifest = seal(root, args.workspace)
        else:
            manifest = verify(root)
            from src.app_services.prediction_trials import read_suite
            suite = read_suite(root)
            if suite is None or suite[2] != manifest['suite_sha256']:
                raise ValueError('Forecast runtime shadow suite changed.')
        if args.mode != 'run':
            print(json.dumps({'status': 'verified', 'files': len(manifest['files']),
                              'suite_sha256': manifest['suite_sha256']}))
            return 0
    except (OSError, ValueError, KeyError, PackageNotFoundError) as exc:
        print(json.dumps({'status': 'runtime_verification_failed', 'error': str(exc)}))
        return 1
    sys.argv = ['scripts.auto_forecast', *forwarded]
    runpy.run_module('scripts.auto_forecast', run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
