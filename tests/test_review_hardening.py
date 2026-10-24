"""Low-severity review findings: download limits, Discord delivery and read caching."""
from unittest.mock import Mock

import pytest

from src.app_services import output_index
from src.data_sources.fia_documents import _cache_file_for_url, download_fia_pdf, fetch_fia_pdf
from src.discord_post import delivery_state, post_files_to_discord, validate_webhook_url


def response(status=200, body=b'%PDF-1.7', headers=None):
    item = Mock()
    item.status_code = status
    item.headers = headers or {}
    item.iter_content.return_value = [body[i:i+4] for i in range(0, len(body), 4)]
    item.raise_for_status.return_value = None
    return item


def test_fia_pdf_redirects_are_rechecked_against_the_allowlist():
    hops = {'https://fia.com/a.pdf': response(302, headers={'Location': 'https://www.fia.com/a.pdf'}),
            'https://www.fia.com/a.pdf': response()}
    get = Mock(side_effect=lambda url, **kwargs: hops[url])
    assert fetch_fia_pdf('https://fia.com/a.pdf', get=get) == b'%PDF-1.7'
    assert all(call.kwargs['allow_redirects'] is False and call.kwargs['stream'] for call in get.call_args_list)
    away = Mock(return_value=response(302, headers={'Location': 'https://evil.example/a.pdf'}))
    with pytest.raises(ValueError, match='official'):
        fetch_fia_pdf('https://www.fia.com/a.pdf', get=away)
    assert away.call_count == 1


def test_fia_pdf_size_cap_applies_while_streaming():
    with pytest.raises(ValueError, match='20 MB'):
        fetch_fia_pdf('https://www.fia.com/a.pdf', get=lambda *a, **k: response(body=b'%PDF' + b'x' * 20), max_bytes=16)
    with pytest.raises(ValueError, match='20 MB'):
        fetch_fia_pdf('https://www.fia.com/a.pdf', get=lambda *a, **k: response(headers={'Content-Length': '99'}), max_bytes=16)
    with pytest.raises(ValueError, match='20 MB'):
        fetch_fia_pdf('https://www.fia.com/a.pdf', get=lambda *a, **k: response(body=b'<html>'))


def test_legacy_pdf_cache_keys_by_full_url(tmp_path):
    first = _cache_file_for_url(tmp_path, 'https://www.fia.com/2025/bahrain/decision.pdf')
    second = _cache_file_for_url(tmp_path, 'https://www.fia.com/2025/jeddah/decision.pdf')
    assert first != second
    with pytest.raises(ValueError, match='official'):
        download_fia_pdf('http://www.fia.com/a.pdf', cache_dir=tmp_path)


def test_webhook_url_must_be_discord_https():
    validate_webhook_url('https://discord.com/api/webhooks/1/token')
    for url in ['http://discord.com/api/webhooks/1/token', 'https://discord.com.evil.example/api/webhooks/1/t',
                'https://discord.com/other', '']:
        with pytest.raises(ValueError):
            validate_webhook_url(url)
    assert post_files_to_discord('https://evil.example/hook', 'x', [], embeds=[{'title': 'x'}])['status'] == 'invalid_webhook_url'


def test_oversized_attachments_are_not_retried():
    assert delivery_state({'ok': True, 'status': 200}) == 'sent'
    assert delivery_state({'ok': False, 'status': 'url_error'}) == 'uncertain'
    assert delivery_state({'ok': False, 'status': 413}) == 'failed'
    assert delivery_state({'ok': False, 'status': 429}) == 'pending'


def test_post_race_413_is_terminal(tmp_path, monkeypatch):
    from src.app_services import post_race_automation
    (tmp_path/'post_race_analysis.txt').write_text('Result')
    for name in ('forecast_vs_actual.png', 'score_comparison.csv', 'actual_results.csv', 'score.json'):
        (tmp_path/name).write_text('x')
    sent = Mock(return_value={'ok': False, 'status': 413})
    monkeypatch.setattr(post_race_automation, 'post_files_to_discord', sent)
    first = post_race_automation.post_analysis(tmp_path, 'https://discord.com/api/webhooks/1/t')
    assert first['delivery_state'] == 'failed' and 'next_attempt_at' not in first
    again = post_race_automation.post_analysis(tmp_path, 'https://discord.com/api/webhooks/1/t')
    assert again['skipped'] and again['requires_review'] and sent.call_count == 1


def test_output_table_reads_are_cached_until_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path/'laps.csv'
    path.write_text('Driver,Lap\nVER,1\n')
    reads = Mock(wraps=output_index.pd.read_csv)
    monkeypatch.setattr(output_index.pd, 'read_csv', reads)
    first = output_index.read_output_table(tmp_path, 'laps.csv')
    first.loc[0, 'Driver'] = 'changed'
    assert output_index.read_output_table(tmp_path, 'laps.csv').Driver.tolist() == ['VER']
    assert reads.call_count == 1
    path.write_text('Driver,Lap\nNOR,1\nVER,2\n')
    assert output_index.read_output_table(tmp_path, 'laps.csv').Driver.tolist() == ['NOR', 'VER']
    assert output_index.read_output_table(tmp_path, 'missing.csv').empty
