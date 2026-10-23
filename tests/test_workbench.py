import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from portable_app import web_backend
from src.app_services.dashboard_health import output_context
from src.app_services.workbench import compare_summaries, data_preview, export_results, saved_details, validate_settings


@pytest.fixture
def api(tmp_path, monkeypatch):
    from src.app_services import automation_feed
    monkeypatch.setattr(automation_feed, 'DEFAULT_PC_WORKSPACE', tmp_path)
    monkeypatch.chdir(tmp_path)
    instance = web_backend.PortableWebApi()
    return instance


def test_invalid_data_directory_does_not_change_settings(api):
    previous = api.default_settings
    with pytest.raises(ValueError, match='directory must exist'):
        api.workbench_save({'n_sims': 17}, 'missing-data')
    assert api.default_settings == previous
    assert not api._settings_path.exists()


def test_saved_preferences_restore_outputs_and_never_enable_discord(api):
    api.workbench_save({'n_sims': 123, 'post_to_discord': True, 'save_raw_results': False}, auto_reload=True)
    reloaded = web_backend.PortableWebApi()
    assert reloaded.default_settings.n_sims == 123
    assert not reloaded.default_settings.save_raw_results
    assert not reloaded.default_settings.post_to_discord
    assert reloaded.ui_preferences['auto_reload']


def test_malformed_settings_fall_back_to_project_defaults(api):
    api._settings_path.parent.mkdir(parents=True, exist_ok=True)
    api._settings_path.write_text('[]')
    reloaded = web_backend.PortableWebApi()
    assert 'settings_error' in reloaded.ui_preferences


@pytest.mark.parametrize('changes', [{'n_sims': 0}, {'n_baseline_races': 0}, {'random_seed': -1}, {'session': 'UNKNOWN'},
                                    {'default_overtaking_difficulty': 1.1}])
def test_invalid_parameters_rejected_before_run(api, changes):
    with pytest.raises(ValueError):
        validate_settings(replace(api.default_settings, **changes))


def test_manual_run_uses_fresh_folder_and_honours_output_switches(api, monkeypatch):
    from unittest.mock import Mock
    from src.app_services import simulation_jobs
    process = Mock(pid=123)
    process.poll.return_value = None
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    result = api.start_run({'n_sims': 20, 'save_raw_results': False, 'save_report_images': False,
                            'save_prediction_snapshot': False})
    config = json.loads(Path(result['configPath']).read_text())
    assert config['ignore_environment_overrides']
    assert not any(config['outputs'][key] for key in ('post_to_discord', 'save_raw_results',
                                                    'save_report_images', 'save_prediction_snapshot'))
    assert Path(result['outputDir']).parent.name == 'workbench_runs'
    assert not Path(result['outputDir']).is_relative_to(api._jobs.run_root)
    assert api._jobs.process is process
    from portable_app import job_worker
    monkeypatch.setattr('src.app_services.run_service.run_pipeline_with_config', lambda *_: 0)
    job_worker.run(Path(result['configPath']).parent)
    saved = json.loads((Path(result['outputDir'])/'ui_run.json').read_text())
    assert saved['settings']['n_sims'] == 20
    assert saved['elapsed_seconds'] >= 0
    process.poll.return_value = 0
    process.wait.return_value = 0
    api._jobs._wait(api._manual_job, process)
    assert api.run_status()['status'] == 'completed'
    assert api.last_output == result['outputDir']
    second = api.start_run({'n_sims': 20})
    assert result['outputDir'] != second['outputDir']


@pytest.mark.parametrize('changes', [{'post_to_discord': True}, {'output_dir': 'outputs/app_runs'},
                                    {'output_dir': 'outputs/frozen'}])
def test_manual_run_cannot_post_or_overwrite_archive(api, changes):
    with pytest.raises(ValueError):
        api.start_run(changes)


def test_saved_context_independent_of_form_when_snapshot_disabled(tmp_path):
    (tmp_path/'weather_context.json').write_text(json.dumps({'year': 2026, 'event': 'Saved GP', 'session': 'FP2'}))
    context = output_context(tmp_path, 2025, 'Selected GP', 'Q')
    assert (context['year'], context['event'], context['session']) == (2026, 'Saved GP', 'FP2')
    assert context['source'] == 'saved_weather_context'


def test_preview_whitelists_sources_and_bounds_pages(tmp_path):
    path = tmp_path/'prices.csv'
    pd.DataFrame({'Driver': [f'D{i}' for i in range(23)], 'Price': [10]*23}).to_csv(path, index=False)
    config = {'data': {'fantasy_prices_path': str(path)}}
    last = data_preview(config, 'fantasy_prices', 99)
    assert last['page'] == last['pages'] == 3
    assert len(last['rows']) == 3
    with pytest.raises(ValueError, match='configured'):
        data_preview(config, '../secrets')


def test_exports_preserve_source_and_explain_missing_snapshot(tmp_path):
    source = tmp_path/'simulation_summary.csv'
    source.write_text('Driver,win_chance\nAAA,1\n')
    original = source.read_bytes()
    result = export_results(tmp_path, 'csv')
    assert not result['uploaded']
    assert (Path(result['folder'])/source.name).read_bytes() == original == source.read_bytes()
    with pytest.raises(ValueError, match='No prediction snapshot'):
        export_results(tmp_path, 'snapshot')
    frozen = tmp_path/'frozen'
    frozen.mkdir()
    (frozen/source.name).write_bytes(original)
    with pytest.raises(ValueError, match='read-only'):
        export_results(frozen, 'csv')
    assert not (frozen/'exports').exists()


def test_comparison_requires_matching_rosters_and_correct_percentage_points():
    first = pd.DataFrame({'Driver': ['AAA', 'BBB'], 'win_chance': [.1, .9], 'avg_finish': [2, 1]})
    second = pd.DataFrame({'Driver': ['AAA', 'BBB'], 'win_chance': [.4, .6], 'avg_finish': [1, 2]})
    result = compare_summaries(first, second)
    assert result['rows'][0]['win_chance_delta_pp'] == pytest.approx(30)
    assert result['rows'][0]['avg_finish_delta'] == -1
    with pytest.raises(ValueError, match='coverage differs'):
        compare_summaries(first, second.iloc[:1])
    with pytest.raises(ValueError, match='unique'):
        compare_summaries(first, pd.concat([second, second]))


def test_manual_history_is_comparable_without_arbitrary_path_access(api):
    for index in (1, 2):
        folder = Path(api.default_settings.output_dir)/'workbench_runs'/str(index)
        folder.mkdir(parents=True)
        (folder/'ui_run.json').write_text(json.dumps({'completed_at_utc': f'2026-10-05T01:00:0{index}Z'}))
        (folder/'weather_context.json').write_text(json.dumps({'year': 2026, 'event': 'GP', 'session': 'Q'}))
        pd.DataFrame({'Driver': ['AAA'], 'avg_finish': [index]}).to_csv(folder/'simulation_summary.csv', index=False)
    history = api.workbench_history()['history']
    assert len(history) == 2
    assert api.workbench_compare(history[1]['id'], history[0]['id'])['rows'][0]['avg_finish_delta'] == 1
    with pytest.raises(ValueError, match='Unknown run'):
        api.workbench_compare('../private', history[0]['id'])


def test_unknown_risks_and_all_saved_modifiers_are_explicit(tmp_path):
    (tmp_path/'weather_context.json').write_text(json.dumps({'weather_source': 'unknown', 'strategy_factor': 1.1}))
    assert web_backend.weather_summary(tmp_path)['modifiers']['strategy_factor'] == 1.1
    details = saved_details(tmp_path)
    assert details['confidence'] is None
    assert details['risk'] == {}


def test_closing_app_cancels_manual_worker_and_preserves_partial_folder(api, monkeypatch):
    from unittest.mock import Mock
    from src.app_services import simulation_jobs
    process = Mock(pid=123)
    process.poll.return_value = None
    process.wait.return_value = 1
    monkeypatch.setattr(simulation_jobs.subprocess, 'Popen', Mock(return_value=process))
    monkeypatch.setattr(simulation_jobs.threading, 'Thread', Mock())
    monkeypatch.setattr(simulation_jobs.subprocess, 'run', Mock())
    result = api.start_run({'n_sims':20})
    identifier = api._manual_job
    assert api.lab_cancel()
    api._jobs._wait(identifier, process)
    assert api.run_status()['status'] == 'cancelled'
    assert Path(result['outputDir']).is_dir()
    assert not (Path(result['outputDir'])/'ui_run.json').exists()
