import json
from unittest.mock import Mock

import fastf1
import pytest

from src.data_sources.fastf1_cache import enable_cache


def test_cache_recovery_preserves_original_and_processed_files(tmp_path, monkeypatch):
    original = tmp_path/'fastf1_http_cache.sqlite'; original.write_bytes(b'preserve damaged original')
    processed = tmp_path/'session.ff1pkl'; processed.write_bytes(b'preserve processed data')
    (tmp_path/'http_backend.json').write_text(json.dumps({'cache_name':'fastf1_http_cache_recovery_test'}))
    configure = Mock(); monkeypatch.setattr(fastf1.Cache, 'configure', configure)
    enable_cache(tmp_path)
    assert configure.call_args.kwargs['cache_dir'] == str(tmp_path)
    assert 'recovery_test' in str(configure.call_args.kwargs['_backend'].db_path)
    assert original.read_bytes() == b'preserve damaged original'
    assert processed.read_bytes() == b'preserve processed data'


def test_cache_override_cannot_escape_workspace(tmp_path):
    (tmp_path/'http_backend.json').write_text(json.dumps({'cache_name':'../outside'}))
    with pytest.raises(ValueError, match='replacement'):
        enable_cache(tmp_path)
