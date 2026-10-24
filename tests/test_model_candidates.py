import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from portable_app import web_backend
from src.app_services.model_candidates import (CANDIDATES, active_candidates, apply_candidates,
                                                candidate_labels, candidate_options)


@pytest.fixture
def api(tmp_path, monkeypatch):
    from src.app_services import automation_feed, simulation_jobs
    monkeypatch.setattr(automation_feed, 'DEFAULT_PC_WORKSPACE', tmp_path)
    monkeypatch.chdir(tmp_path)
    process = Mock(pid=123)
    process.poll.return_value = None
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    return web_backend.PortableWebApi()


def test_every_candidate_defaults_to_the_established_model():
    base = {'model': {'model_version': 'test', 'use_fastf1_weather': True, 'use_race_control_context': True,
                      'use_track_red_flag_base_chance': True}}
    config, active = apply_candidates(base, {item['key']: item['default'] for item in candidate_options()})
    assert active == {} and config == base


def test_unknown_candidates_and_values_are_rejected():
    with pytest.raises(ValueError, match='Unknown model candidate'):
        active_candidates({'pace_blend': 'qualifying_partial_pooling_v1'})
    with pytest.raises(ValueError, match='Unknown value'):
        active_candidates({'safety_car_model': 'always'})


def test_run_config_rules_reject_impossible_combinations(api):
    with pytest.raises(ValueError, match='own SC/VSC'):
        api.start_run({'n_sims': 20, 'candidates': {'race_engine': 'agent_laps_v1',
                                                    'safety_car_model': 'track_sc_v1'}})
    with pytest.raises(ValueError, match='agent race engine'):
        api.start_run({'n_sims': 20, 'candidates': {'pair_pass_model': 'pair_overtaking_v1'}})
    assert not (Path(api.default_settings.output_dir)/'workbench_runs').exists() or \
        not any((Path(api.default_settings.output_dir)/'workbench_runs').iterdir())


def test_candidate_run_is_local_labelled_and_badged(api, monkeypatch):
    result = api.start_run({'n_sims': 20, 'candidates': {'race_engine': 'agent_laps_v1',
                                                         'pair_pass_model': 'pair_overtaking_v1'}})
    config = json.loads(Path(result['configPath']).read_text())
    assert config['model']['race_engine'] == 'agent_laps_v1'
    assert config['model']['agent_settings']['pair_pass_model'] == 'pair_overtaking_v1'
    assert config['outputs']['post_to_discord'] is False
    from portable_app import job_worker
    monkeypatch.setattr('src.app_services.run_service.run_pipeline_with_config', lambda *_: 0)
    job_worker.run(Path(result['configPath']).parent)
    saved = json.loads((Path(result['outputDir'])/'ui_run.json').read_text())
    assert saved['candidates'] == {'race_engine': 'agent_laps_v1', 'pair_pass_model': 'pair_overtaking_v1'}
    history = api.workbench_history()['history']
    entry = next(item for item in history if item['kind'] == 'monte_carlo')
    assert entry['label'].endswith('· candidate')
    assert entry['candidates'] == candidate_labels(saved['candidates'])


def test_initial_state_offers_candidates_switched_off(api):
    options = api.initial_state()['modelCandidates']
    assert {item['key'] for item in options} == set(CANDIDATES)
    assert all(item['default'] == item['options'][0]['value'] for item in options)
