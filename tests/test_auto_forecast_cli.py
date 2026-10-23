import sys
from pathlib import Path

import pytest

from scripts import auto_forecast


def test_explicit_env_file_is_selected_without_loading_default(monkeypatch, tmp_path):
    selected = tmp_path / '.env.automation'
    selected.write_text('TEST_CONFIGURATION=one\n')
    calls = []
    monkeypatch.setattr(sys, 'argv', ['auto_forecast', '--check-only', '--env-file', '.env.automation'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda path: calls.append(Path(path)))
    from src.app_services import beta
    monkeypatch.setattr(beta, 'next_race', lambda root: {'year': 2026, 'event': 'Example', 'session': 'Q'})
    monkeypatch.setattr(auto_forecast, 'find_frozen_forecast', lambda *args: None)
    assert auto_forecast.main() == 0
    assert calls == [selected]


def test_missing_explicit_env_never_falls_back_to_a_different_webhook(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['auto_forecast', '--check-only', '--env-file', '.env.automation'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda path: pytest.fail('Unexpected dotenv fallback'))
    with pytest.raises(ValueError, match='explicitly selected'):
        auto_forecast.main()


def test_weekend_briefing_runs_before_forecast_and_failure_does_not_block_it(monkeypatch, tmp_path, capsys):
    from src.app_services import weekend_briefing
    from src import fantasy_market
    from src.data_sources import fia_sync
    calls = []
    monkeypatch.setattr(sys, 'argv', ['auto_forecast', '--weekend-briefing', '--discord'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda p: None)
    def unavailable(*a, **k):
        calls.append('briefing')
        assert k['discord_enabled']
        raise ValueError('Calendar unavailable')
    monkeypatch.setattr(weekend_briefing, 'run_weekend_briefing', unavailable)
    monkeypatch.setattr(fantasy_market, 'collect', lambda root: {'status': 'disabled'})
    monkeypatch.setattr(fia_sync, 'refresh', lambda root: {'status': 'disabled'})
    monkeypatch.setattr(auto_forecast, 'run_automated_forecast', lambda *a, **k: calls.append('forecast') or {'status': 'skipped'})
    assert auto_forecast.main() == 1  # Failure remains visible in scheduler health.
    assert calls == ['briefing', 'forecast']
    assert 'weekend_briefing' in capsys.readouterr().out


def test_check_only_weekend_briefing_does_not_enable_discord(monkeypatch, tmp_path):
    from src.app_services import weekend_briefing, beta
    calls = []
    monkeypatch.setattr(sys, 'argv', ['auto_forecast', '--check-only', '--weekend-briefing', '--discord'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda p: None)
    monkeypatch.setattr(weekend_briefing, 'run_weekend_briefing', lambda *a, **k: calls.append(k) or {'status': 'not_due'})
    monkeypatch.setattr(beta, 'next_race', lambda root: {'year': 2026, 'event': 'Example', 'session': 'Q'})
    monkeypatch.setattr(auto_forecast, 'find_frozen_forecast', lambda *a: None)
    assert auto_forecast.main() == 0 and calls == [{'check_only': True}]


def test_fantasy_refresh_runs_even_when_forecast_already_completed(monkeypatch, tmp_path, capsys):
    from src import fantasy_market
    calls = []
    monkeypatch.setattr(sys, 'argv', ['auto_forecast'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda p: None)
    monkeypatch.setattr(fantasy_market, 'collect', lambda root: calls.append(root) or {'status': 'updated'})
    monkeypatch.setattr(auto_forecast, 'run_automated_forecast', lambda *a, **k: {'status': 'already_completed'})
    assert auto_forecast.main() == 0
    assert calls == [tmp_path]
    assert 'fantasy_collection' in capsys.readouterr().out


def test_fantasy_failure_does_not_prevent_forecast(monkeypatch, tmp_path, capsys):
    from src import fantasy_market
    monkeypatch.setattr(sys, 'argv', ['auto_forecast'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda p: None)
    def fail(root):
        raise RuntimeError('Collector unavailable')
    monkeypatch.setattr(fantasy_market, 'collect', fail)
    monkeypatch.setattr(auto_forecast, 'run_automated_forecast', lambda *a, **k: {'status': 'ready'})
    assert auto_forecast.main() == 0
    assert '"fantasy_collection"' in capsys.readouterr().out


def test_check_only_does_not_collect_fantasy(monkeypatch, tmp_path):
    from src import fantasy_market
    from src.app_services import beta
    monkeypatch.setattr(sys, 'argv', ['auto_forecast', '--check-only'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda p: None)
    monkeypatch.setattr(fantasy_market, 'collect', lambda root: pytest.fail('Check-only wrote Fantasy data'))
    monkeypatch.setattr(beta, 'next_race', lambda root: {'year': 2026, 'event': 'Example', 'session': 'Q'})
    monkeypatch.setattr(auto_forecast, 'find_frozen_forecast', lambda *a: None)
    assert auto_forecast.main() == 0


def test_fia_refresh_runs_before_completed_forecast_and_check_only_never_refreshes(monkeypatch,tmp_path):
    from src.data_sources import fia_sync
    from src import fantasy_market
    calls=[]
    monkeypatch.setattr(sys,'argv',['auto_forecast'])
    monkeypatch.setattr(auto_forecast,'project_root',lambda:tmp_path)
    monkeypatch.setattr(auto_forecast,'load_dotenv',lambda p:None)
    monkeypatch.setattr(fia_sync,'refresh',lambda root:calls.append('fia') or {'status':'completed'})
    monkeypatch.setattr(fantasy_market,'collect',lambda root:{'status':'disabled'})
    monkeypatch.setattr(auto_forecast,'run_automated_forecast',lambda *a,**k:calls.append('forecast') or {'status':'already_completed'})
    assert auto_forecast.main()==0 and calls==['fia','forecast']
    calls.clear()
    monkeypatch.setattr(sys,'argv',['auto_forecast','--check-only'])
    from src.app_services import beta
    monkeypatch.setattr(beta,'next_race',lambda root:{'year':2026,'event':'GP','session':'Q'})
    monkeypatch.setattr(auto_forecast,'find_frozen_forecast',lambda *a:None)
    assert auto_forecast.main()==0 and calls==[]


def test_fia_failure_does_not_prevent_forecast(monkeypatch,tmp_path,capsys):
    from src.data_sources import fia_sync
    from src import fantasy_market
    monkeypatch.setattr(sys,'argv',['auto_forecast'])
    monkeypatch.setattr(auto_forecast,'project_root',lambda:tmp_path)
    monkeypatch.setattr(auto_forecast,'load_dotenv',lambda p:None)
    def fail(root):
        raise RuntimeError('FIA unavailable')
    monkeypatch.setattr(fia_sync,'refresh',fail)
    monkeypatch.setattr(fantasy_market,'collect',lambda root:{'status':'disabled'})
    monkeypatch.setattr(auto_forecast,'run_automated_forecast',lambda *a,**k:{'status':'ready'})
    assert auto_forecast.main()==0
    assert '"fia_collection"' in capsys.readouterr().out


@pytest.mark.parametrize('result, expected', [
    ({'post_race':[{'status':'failed'}]}, 1),
    ({'deliveries':[{'ok':False,'delivery_state':'uncertain'}]}, 1),
    ({'post_race':[{'status':'waiting_for_results'}]}, 0),
])
def test_core_outcome_controls_scheduler_exit_and_health(monkeypatch, tmp_path, result, expected):
    import json
    from src import fantasy_market
    from src.data_sources import fia_sync
    monkeypatch.setattr(sys, 'argv', ['auto_forecast'])
    monkeypatch.setattr(auto_forecast, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(auto_forecast, 'load_dotenv', lambda path: None)
    monkeypatch.setattr(fantasy_market, 'collect', lambda root: {'status':'disabled'})
    monkeypatch.setattr(fia_sync, 'refresh', lambda root: {'status':'disabled'})
    monkeypatch.setattr(auto_forecast, 'run_automated_forecast', lambda *a, **k: result)
    assert auto_forecast.main() == expected
    assert json.loads((tmp_path/'outputs/automation/last_health.json').read_text())['exit_code'] == expected
