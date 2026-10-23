import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from src import discord_post
from src.app_services import discord_reports as reports, forecast_automation, post_race_automation
from src.app_services.beta import digest, freeze_snapshot


def snapshot(root, name, session, created, chances, finishes, drivers=('A', 'B'), **context_extra):
    folder = root / name
    folder.mkdir()
    context = {'year': 2026, 'event': 'Example GP', 'session': session,
               'race_start_utc': '2026-10-04T07:00:00+00:00', 'data_cutoff_utc': created}
    context.update(context_extra)
    pd.DataFrame({'Driver': drivers, 'avg_finish': finishes, 'win_chance': chances,
                  'dnf_chance': [.05] * len(drivers)}).to_csv(folder / 'simulation_summary.csv', index=False)
    freeze_snapshot(folder, context, now=created)
    (folder / 'job.json').write_text(json.dumps({'kind': 'forecast', 'status': 'completed'}))
    return folder


def fields(message):
    return {field['name']: field['value'] for field in message['embeds'][0]['fields']}


def test_changes_compare_latest_prior_session_same_race_and_ignore_future(tmp_path):
    snapshot(tmp_path, 'FP2', 'FP2', '2026-10-03T08:00:00+00:00', [.4, .6], [1.9, 1.1])
    snapshot(tmp_path, 'FP3', 'FP3', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    current = snapshot(tmp_path, 'Q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8])
    snapshot(tmp_path, 'future', 'FP1', '2026-10-03T11:00:00+00:00', [.9, .1], [1, 2])
    message = reports.forecast_message(current)
    changes = fields(message)['Changes since previous forecast']
    assert '**FP3**' in changes and '+10.0 pp' in changes and '-10.0 pp' in changes
    assert '0.30 places better' in changes and '0.30 places worse' in changes
    assert '29.9' not in changes
    assert 'race rain forecast unavailable' in fields(message)['Data and assumptions']


def test_first_forecast_and_roster_changes_are_explicit(tmp_path):
    first = snapshot(tmp_path, 'first', 'FP3', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    assert 'First available' in fields(reports.forecast_message(first))['Changes since previous forecast']
    current = snapshot(tmp_path, 'Q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8], drivers=['A', 'C'])
    assert 'roster differs' in fields(reports.forecast_message(current))['Changes since previous forecast']


def test_missing_probabilities_do_not_become_zero_win_chances(tmp_path):
    folder = tmp_path / 'forecast'
    folder.mkdir()
    context = {'year': 2026, 'event': 'Example GP', 'session': 'PRE', 'race_start_utc': '2026-10-04T07:00:00+00:00'}
    pd.DataFrame({'Driver': ['A'], 'avg_finish': [1.]}).to_csv(folder / 'simulation_summary.csv', index=False)
    freeze_snapshot(folder, context, now='2026-10-03T08:00:00+00:00')
    values = fields(reports.forecast_message(folder))
    assert 'Best expected finishes' in values and 'Highest win chances' not in values
    assert '0.0%' not in values['Best expected finishes']
    assert 'previous baseline driver roster' in values['Data and assumptions']


def test_corrupt_prior_snapshot_is_not_used(tmp_path):
    prior = snapshot(tmp_path, 'FP3', 'FP3', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    (prior / 'frozen/simulation_summary.csv').write_text('changed')
    current = snapshot(tmp_path, 'Q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8])
    assert 'First available' in fields(reports.forecast_message(current))['Changes since previous forecast']


def test_grid_update_compares_superseded_qualifying_forecast_not_sprint(tmp_path):
    snapshot(tmp_path, 'sprint', 'S', '2026-10-03T08:00:00+00:00', [.2, .8], [1.9, 1.1])
    prior = snapshot(tmp_path, 'original_q', 'Q', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    current = snapshot(tmp_path, 'updated_q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8],
                       supersedes_forecast=prior.name, revision_reason='fia_grid_update')
    message = reports.forecast_message(current)
    assert 'FIA grid update' in message['embeds'][0]['title']
    changes = fields(message)['Changes since previous forecast']
    assert 'Q (previous revision)' in changes and '+10.0 pp' in changes and '+40.0 pp' not in changes
    (prior / 'frozen/simulation_summary.csv').write_text('changed')
    # A corrupt explicit predecessor must not silently fall back to the sprint.
    assert 'First available' in fields(reports.forecast_message(current))['Changes since previous forecast']


def test_new_cards_render_available_data_and_preserve_frozen_inputs(tmp_path):
    from PIL import Image
    from src.app_services.discord_cards import render_forecast_cards
    prior = snapshot(tmp_path, 'prior', 'Q', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    current = snapshot(tmp_path, 'current', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8],
                       supersedes_forecast=prior.name)
    before = {p.name: p.read_bytes() for p in (current / 'frozen').iterdir()}
    paths = render_forecast_cards(current, current / 'preview')
    assert {p.name for p in paths} == {'race_outlook.png', 'forecast_update.png'}
    for path in paths:
        with Image.open(path) as image:
            assert image.size == (1600, 1280)
    assert before == {p.name: p.read_bytes() for p in (current / 'frozen').iterdir()}


def test_saved_old_delivery_plan_is_not_upgraded_or_rerendered(tmp_path, monkeypatch):
    folder = tmp_path / 'forecast'
    (folder / 'discord_report').mkdir(parents=True)
    path = folder / 'discord_report/delivery_plan.json'
    path.write_text(json.dumps({'format_version': 2, 'files': ['old.png'], 'payload': {'content': 'Original'}}))
    before = path.read_bytes()
    monkeypatch.setattr(forecast_automation, 'render_forecast_cards', lambda *a: pytest.fail('Rerendered pinned report'))
    assert forecast_automation._forecast_delivery_plan(folder)['format_version'] == 2
    assert path.read_bytes() == before


def test_baseline_has_identical_coverage_and_retirement_is_observed_context(tmp_path):
    comparison = pd.DataFrame({'Driver': ['A', 'B', 'C'], 'avg_finish': [1.1, 1.9, 3.],
        'grid_position': [1, 2, 3], 'actual_position': [3, 1, 2], 'actual_dnf': [True, False, False],
        'actual_status': ['Retired', 'Finished', 'Finished'], 'dnf_chance': [.04, .04, .04]})
    comparison.to_csv(tmp_path / 'score_comparison.csv', index=False)
    (tmp_path / 'score.json').write_text('{}')
    context = {'year': 2026, 'event': 'Example GP', 'session': 'Q'}
    summary = reports.analysis_summary(comparison)
    assert summary['grid_baseline_mae'] == pytest.approx(4 / 3)
    assert summary['non_retirement_finish_mae'] == pytest.approx(.95)
    message = reports.post_race_message(tmp_path, context)
    values = fields(message)
    assert 'worse' not in values['Performance against a simple baseline']
    assert 'Frozen grid baseline: **1.33' in values['Performance against a simple baseline']
    assert 'Retired' in values['Largest misses and observed outcomes'] and '4.0%' in values['Retirement context']
    assert 'diagnostic subset' in values['Retirement context']


@pytest.mark.parametrize('grid', [[1, None, 3], [1, 1, 3], [0, 2, 3], [1.5, 2, 3]])
def test_invalid_grid_withholds_baseline_instead_of_scoring_partial_rows(grid):
    comparison = pd.DataFrame({'grid_position': grid, 'actual_position': [1, 2, 3]})
    assert reports.grid_baseline(comparison) is None


def test_compact_bundle_and_retry_are_pinned_even_if_detail_setting_changes(tmp_path, monkeypatch):
    folder = snapshot(tmp_path, 'Q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8])
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'compact')
    sent = []
    monkeypatch.setattr(forecast_automation, 'post_files_to_discord',
                        lambda **kwargs: sent.append(kwargs) or {'ok': False, 'status': 503})
    with pytest.raises(RuntimeError):
        forecast_automation.post_frozen_forecast(folder, 'https://discord.invalid/test')
    receipt = folder / 'discord_post_result.json'
    saved = json.loads(receipt.read_text())
    saved['next_attempt_at'] = '2000-01-01T00:00:00+00:00'
    receipt.write_text(json.dumps(saved))
    monkeypatch.setenv('DISCORD_REPORT_DETAIL', 'full')
    monkeypatch.setattr(forecast_automation, 'post_files_to_discord',
                        lambda **kwargs: sent.append(kwargs) or {'ok': True, 'status': 200})
    forecast_automation.post_frozen_forecast(folder, 'https://discord.invalid/test')
    assert [p.name for p in sent[0]['file_paths']] == ['race_outlook.png', 'simulation_summary.csv']
    assert sent[0]['file_paths'] == sent[1]['file_paths']
    assert sent[0]['embeds'] == sent[1]['embeds']
    assert len(sent[0]['embeds']) == 1


def test_legacy_partial_batch_keeps_original_attachment_order(tmp_path, monkeypatch):
    folder = snapshot(tmp_path, 'Q', 'Q', '2026-10-03T10:00:00+00:00', [.6, .4], [1.2, 1.8])
    report = folder / 'source/report'
    report.mkdir(parents=True)
    for index in range(10):
        (report / f'{index}.png').write_bytes(b'png')
    first_receipt = folder / 'discord_batch_1_result.json'
    first_receipt.write_text(json.dumps({'ok': True, 'status': 200}))
    original = first_receipt.read_bytes()
    calls = []
    monkeypatch.setattr(forecast_automation, 'post_files_to_discord',
                        lambda **kwargs: calls.append(kwargs) or {'ok': True, 'status': 200})
    result = forecast_automation.post_frozen_forecast(folder, 'https://discord.invalid/test')
    assert result['ok'] and len(calls) == 1
    assert calls[0]['file_paths'] == [report / '9.png']
    assert first_receipt.read_bytes() == original
    assert calls[0]['embeds'] == []


def test_multipart_has_json_embed_no_mentions_and_server_confirmation(tmp_path, monkeypatch):
    file = tmp_path / 'chart.png'
    file.write_bytes(b'chart')
    response = Mock()
    response.status = 200
    response.read.return_value = b'{}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    requests = []
    monkeypatch.setattr(discord_post, 'urlopen', lambda request, **kwargs: requests.append(request) or response)
    embed = {'title': 'Example', 'fields': [{'name': 'Score', 'value': '4.00'}]}
    result = discord_post.post_files_to_discord('https://discord.invalid/test?wait=false&thread_id=123', '', [file], embeds=[embed])
    assert result['ok']
    request = requests[0]
    assert 'wait=true' in request.full_url and 'thread_id=123' in request.full_url
    body = request.data.decode()
    payload_text = body.split('name="payload_json"\r\n\r\n', 1)[1].split('\r\n--', 1)[0]
    payload = json.loads(payload_text)
    assert payload['embeds'] == [embed] and payload['allowed_mentions'] == {'parse': []}
    assert 'filename="chart.png"' in body


def test_invalid_embed_fails_before_http_request(tmp_path, monkeypatch):
    file = tmp_path / 'chart.png'
    file.write_bytes(b'chart')
    monkeypatch.setattr(discord_post, 'urlopen', lambda *args, **kwargs: pytest.fail('Unexpected request'))
    with pytest.raises(ValueError, match='field value'):
        discord_post.post_files_to_discord('https://discord.invalid/test', '', [file],
            embeds=[{'title': 'Example', 'fields': [{'name': 'Score', 'value': 'a' * 1025}]}])


def test_new_post_race_embed_uses_three_attachments_and_reuses_saved_payload(tmp_path, monkeypatch):
    pd.DataFrame({'Driver': ['A'], 'avg_finish': [1.], 'actual_position': [1],
                  'grid_position': [1], 'actual_dnf': [False]}).to_csv(tmp_path / 'score_comparison.csv', index=False)
    pd.DataFrame({'Driver': ['A'], 'actual_position': [1]}).to_csv(tmp_path / 'actual_results.csv', index=False)
    (tmp_path / 'score.json').write_text('{}')
    post_race_automation.render_analysis(tmp_path, {'year': 2026, 'event': 'Example GP', 'session': 'Q'})
    calls = []
    monkeypatch.setattr(post_race_automation, 'post_files_to_discord',
                        lambda **kwargs: calls.append(kwargs) or {'ok': False, 'status': 503})
    post_race_automation.post_analysis(tmp_path, 'https://discord.invalid/test')
    path = tmp_path / 'discord_post_result.json'
    receipt = json.loads(path.read_text())
    receipt['next_attempt_at'] = '2000-01-01T00:00:00+00:00'
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(post_race_automation, 'post_files_to_discord',
                        lambda **kwargs: calls.append(kwargs) or {'ok': True, 'status': 200})
    post_race_automation.post_analysis(tmp_path, 'https://discord.invalid/test')
    assert len(calls[0]['file_paths']) == 3 and calls[0]['embeds']
    assert calls[0]['embeds'] == calls[1]['embeds'] and calls[0]['file_paths'] == calls[1]['file_paths']


def test_recent_baselines_deduplicate_races_and_ignore_later_races(tmp_path):
    source = snapshot(tmp_path, 'prior', 'Q', '2026-10-03T09:00:00+00:00', [.5, .5], [1.5, 1.5])
    frame = pd.DataFrame({'Driver': ['A', 'B'], 'avg_finish': [1.5, 1.5],
                          'grid_position': [1, 2], 'actual_position': [1, 2]})
    for identifier in ['20261004T000000Z_11111111', '20261004T010000Z_22222222']:
        folder = tmp_path / identifier
        folder.mkdir()
        frame.to_csv(folder / 'score_comparison.csv', index=False)
        (folder / 'job.json').write_text(json.dumps({'kind': 'score', 'status': 'completed', 'forecast_folder': str(source)}))
        (folder / 'score.json').write_text(json.dumps({'snapshot_sha256': digest(source / 'frozen/manifest.json')}))
    current = reports.analysis_summary(frame)
    context = {'year': 2026, 'event': 'Next GP', 'race_start_utc': '2026-10-11T07:00:00+00:00'}
    trend = reports._recent_scores(tmp_path / 'current', context, current)
    assert 'Last 2 evaluated races' in trend and '0/2 races' in trend
    context['race_start_utc'] = '2026-10-01T07:00:00+00:00'
    assert '1 evaluated race' in reports._recent_scores(tmp_path / 'current', context, current)
