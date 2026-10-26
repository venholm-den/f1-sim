import json
from pathlib import Path
import sys

import pytest

from scripts.forecast_runtime import MANIFEST, inventory, verify


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path/'runtime'
    (root/'src').mkdir(parents=True)
    (root/'src/simulate.py').write_text('original')
    (root/'config').mkdir()
    (root/'config/prediction_trials.json').write_text('{"enabled": true}')
    for name in ('data', 'outputs'):
        (root/name).mkdir()
    manifest = {'schema_version': 1, 'files': inventory(root),
                'python': str(Path(sys.executable).resolve()), 'dependencies': {},
                'shared_targets': {name: str(root/name) for name in ('data', 'outputs')}}
    (root/MANIFEST).write_text(json.dumps(manifest))
    return root


def test_runtime_rejects_edited_code_and_control_config(runtime):
    verify(runtime)
    source = runtime/'src/simulate.py'
    source.write_text('changed')
    with pytest.raises(ValueError, match='src/simulate.py'):
        verify(runtime)
    source.write_text('original')
    (runtime/'config/prediction_trials.json').write_text('{"enabled": false}')
    with pytest.raises(ValueError, match='config/prediction_trials.json'):
        verify(runtime)


def test_runtime_detects_new_code_but_allows_new_outputs(runtime):
    (runtime/'outputs/result.json').write_text('{}')
    verify(runtime)
    (runtime/'src/new_module.py').write_text('unexpected')
    with pytest.raises(ValueError, match='src/new_module.py'):
        verify(runtime)


def test_runtime_rejects_dependency_or_workspace_drift(runtime, monkeypatch):
    path = runtime/MANIFEST
    manifest = json.loads(path.read_text())
    manifest['dependencies'] = {'fastf1': 'pinned'}
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr('scripts.forecast_runtime.version', lambda name: 'different')
    with pytest.raises(ValueError, match='dependency changed: fastf1'):
        verify(runtime)
    manifest['dependencies'] = {}
    manifest['shared_targets']['outputs'] = str(runtime/'different-output-workspace')
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='shared workspace changed'):
        verify(runtime)


def test_guard_refuses_to_start_automation_after_source_drift(runtime, monkeypatch):
    import scripts.forecast_runtime as module
    (runtime/'src/simulate.py').write_text('changed')
    monkeypatch.setattr(module, '__file__', str(runtime/'scripts/forecast_runtime.py'))
    monkeypatch.setattr(sys, 'argv', ['forecast_runtime', 'run', '--discord'])
    called = []
    monkeypatch.setattr(module.runpy, 'run_module', lambda *args, **kwargs: called.append(args))
    assert module.main() == 1
    assert called == []
