"""Select an opt-in replacement HTTP cache while retaining processed datasets."""
import json
from pathlib import Path
import re

import fastf1


def enable_cache(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    override = directory/'http_backend.json'
    if not override.exists():
        fastf1.Cache.enable_cache(str(directory))
        return
    name = json.loads(override.read_text(encoding='utf-8'))['cache_name']
    if not isinstance(name, str) or not re.fullmatch(r'fastf1_http_cache_recovery_[a-zA-Z0-9_-]+', name):
        raise ValueError('Invalid replacement HTTP cache name.')
    from requests_cache.backends import SQLiteCache
    fastf1.Cache.configure(cache_dir=str(directory), _backend=SQLiteCache(str(directory/name)))
