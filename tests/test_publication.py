import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from scripts import publication_rehearsal as rehearsal
from src.app_services.publication import (LocalPublicationStore, build_publication, payload_checksum,
                                          validate_publication)

EXAMPLES = Path(__file__).resolve().parents[1]/'docs/schemas/examples/forecast-publication-v1'
EVENT = {'year': 2024, 'round': 12}


@pytest.fixture
def q_payload(tmp_path):
    return build_publication(rehearsal.fixture_snapshot(tmp_path/'q', 'Q', '2024-07-06T16:30:00Z'), 'established')


def resign(payload):
    payload['checksum']['value'] = payload_checksum(payload)
    return payload


def test_built_payload_is_valid_and_carries_no_local_config(q_payload):
    assert validate_publication(q_payload) == []
    text = json.dumps(q_payload)
    assert 'never-published' not in text and 'source_dir' not in text
    assert q_payload['model']['settings'] == {'n_sims': 10000, 'seed': 42, 'overtaking_difficulty': 0.55}
    assert q_payload['stage'] == 'Q' and q_payload['input_cutoff_utc'] == '2024-07-06T16:30:00Z'


def test_retries_of_one_snapshot_build_identical_payloads(tmp_path):
    folder = rehearsal.fixture_snapshot(tmp_path/'fp2', 'FP2', '2024-07-05T18:30:00Z')
    assert build_publication(folder, 'established') == build_publication(folder, 'established')


def test_frozen_snapshot_edits_block_publication(tmp_path):
    folder = rehearsal.fixture_snapshot(tmp_path/'q', 'Q', '2024-07-06T16:30:00Z')
    (folder/'frozen/simulation_summary.csv').write_text('changed')
    with pytest.raises(ValueError, match='changed'):
        build_publication(folder, 'established')


@pytest.mark.parametrize('change,message', [
    (lambda p: p.update(kind='personal'), 'personal scenarios'),
    (lambda p: p.update(stage='FP3', available_sessions=['FP1', 'FP2']), 'publication_id'),
    (lambda p: p.update(available_sessions=['FP1']), 'stage is not consistent'),
    (lambda p: p.update(generated_at_utc='2024-07-07T14:00:00+00:00'), 'after the race started'),
    (lambda p: p.update(generated_at_utc='2024-07-06T16:00:00+00:00'), 'before its input cutoff'),
    (lambda p: p.update(input_cutoff_utc='2024-07-06T16:30:00'), 'timezone'),
    (lambda p: p['predictions'][1].update(Driver='VER'), 'one row per named driver'),
    (lambda p: p['predictions'][0].update(dnf_chance=1.5), 'dnf_chance outside'),
    (lambda p: p['predictions'][0].update(win_chance=0.5), 'sum to one'),
    (lambda p: p['model'].update(api_key='x'), 'producer-only'),
    (lambda p: p['limitations'].append('see C:\\Users\\kyle\\run.log'), 'local path'),
])
def test_validation_rejects_unpublishable_payloads(q_payload, change, message):
    payload = copy.deepcopy(q_payload)
    change(payload)
    errors = validate_publication(resign(payload))
    assert any(message in error for error in errors), errors


def test_checksum_detects_unsigned_edits(q_payload):
    q_payload['predictions'][0]['avg_finish'] = 1.2
    assert validate_publication(q_payload) == ['checksum does not match payload']


def test_example_payloads_match_their_names():
    names = sorted(path.name for path in EXAMPLES.glob('*.json'))
    assert 'accepted-q.json' in names and len(names) >= 6
    for path in EXAMPLES.glob('*.json'):
        errors = validate_publication(json.loads(path.read_text(encoding='utf-8')))
        assert (errors == []) == path.name.startswith('accepted'), (path.name, errors)


def test_publish_is_write_once_and_retry_safe(tmp_path, q_payload):
    store = LocalPublicationStore(tmp_path/'store')
    assert store.publish(q_payload, now='2024-07-06T16:40:00Z')['status'] == 'published'
    snapshot = next((tmp_path/'store/snapshots').rglob('*.json'))
    original = snapshot.read_bytes()
    assert store.publish(copy.deepcopy(q_payload), now='2024-07-06T16:45:00Z')['status'] == 'duplicate'
    conflict = copy.deepcopy(q_payload)
    first, second = conflict['predictions'][:2]
    first['win_chance'], second['win_chance'] = second['win_chance'], first['win_chance']
    receipt = store.publish(resign(conflict), now='2024-07-06T16:50:00Z')
    assert receipt['status'] == 'rejected' and 'different content' in receipt['errors'][0]
    assert snapshot.read_bytes() == original
    assert store.read_latest(EVENT, '2024-07-06T16:55:00Z')['state'] == 'current'


def test_failed_validation_keeps_previous_forecast_and_labels_it(tmp_path, q_payload):
    store = LocalPublicationStore(tmp_path/'store')
    fp2 = build_publication(rehearsal.fixture_snapshot(tmp_path/'fp2', 'FP2', '2024-07-05T18:30:00Z'), 'established')
    store.publish(fp2, now='2024-07-05T19:00:00Z')
    q_payload['predictions'] = q_payload['predictions'][:5]
    assert store.publish(resign(q_payload), now='2024-07-06T16:40:00Z')['status'] == 'rejected'
    view = store.read_latest(EVENT, '2024-07-06T16:41:00Z')
    assert view['publication']['stage'] == 'FP2' and view['state'] == 'stale'
    assert any('Q update failed' in reason for reason in view['reasons'])
    assert (tmp_path/'store/rejections.jsonl').read_text().count('\n') == 1


def test_fewer_inputs_never_replace_latest(tmp_path, q_payload):
    store = LocalPublicationStore(tmp_path/'store')
    store.publish(q_payload, now='2024-07-06T16:40:00Z')
    # A later manual run on PRE inputs is stored but is not what clients see.
    pre = build_publication(rehearsal.fixture_snapshot(tmp_path/'pre', 'PRE', '2024-07-06T18:00:00Z',
                                                       cutoff='2024-07-03T00:00:00Z'), 'established')
    receipt = store.publish(pre, now='2024-07-06T18:05:00Z')
    assert receipt == {'status': 'published', 'publication_id': pre['publication_id'], 'latest': False}
    assert store.read_latest(EVENT, '2024-07-06T18:10:00Z')['publication']['stage'] == 'Q'


def test_offline_producer_old_forecast_and_race_start_are_explicit(tmp_path, q_payload):
    store = LocalPublicationStore(tmp_path/'store')
    assert store.read_latest(EVENT, '2024-07-06T16:00:00Z')['state'] == 'unavailable'
    store.publish(q_payload, now='2024-07-06T16:40:00Z')
    assert store.read_latest(EVENT, '2024-07-06T17:00:00Z')['state'] == 'current'
    offline = store.read_latest(EVENT, '2024-07-06T23:00:00Z')
    assert offline['state'] == 'stale' and offline['reasons'] == ['forecast producer is offline; updates are paused']
    store.heartbeat('2024-07-07T13:00:00Z')
    aged = LocalPublicationStore(tmp_path/'store', stale_after=timedelta(hours=12)).read_latest(EVENT, '2024-07-07T13:30:00Z')
    assert aged['reasons'] == ['forecast is 21h old']
    assert store.read_latest(EVENT, '2024-07-07T14:00:00Z')['state'] == 'closed'


def test_corrupted_store_is_not_served(tmp_path, q_payload):
    store = LocalPublicationStore(tmp_path/'store')
    store.publish(q_payload, now='2024-07-06T16:40:00Z')
    snapshot = next((tmp_path/'store/snapshots').rglob('*.json'))
    record = json.loads(snapshot.read_text())
    record['publication']['predictions'][0]['win_chance'] = 0.5
    snapshot.write_text(json.dumps(record))
    view = store.read_latest(EVENT, '2024-07-06T17:00:00Z')
    assert view['state'] == 'unavailable' and view['publication'] is None


def test_rehearsal_passes_every_step(tmp_path):
    log = rehearsal.rehearse(tmp_path)
    assert [row['step'] for row in log if not row['passed']] == []
    assert len(log) == 9

