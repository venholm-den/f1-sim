"""Reproduction metadata for new forecasts; existing manifests remain immutable."""
import hashlib
import importlib.metadata
import platform
import sys
from src.app_services.app_paths import bundled_root


def runtime_provenance():
    root = bundled_root()
    paths = [root/'main.py', root/'requirements.txt']
    for directory in ('src', 'portable_app', 'scripts'):
        paths.extend(sorted((root/directory).rglob('*.py')))
    source = {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in paths if path.is_file()}
    packages = {}
    for name in ('fastf1', 'numpy', 'pandas', 'scikit-learn', 'scipy', 'pywebview', 'requests'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'packaged': bool(getattr(sys, 'frozen', False)),
            'packages': packages, 'source_sha256': source,
            'limitations': ['Hashes identify available source; they are not a trusted timestamp.']}
