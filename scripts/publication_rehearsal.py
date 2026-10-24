"""Rehearse forecast publication failure modes against fixtures.

Builds synthetic frozen snapshots, publishes them into a throwaway local store
and checks what a client would see after each step: normal publication,
duplicate and conflicting retries, failed validation, an interrupted pointer
update, a failed producer run, a late retry of an older forecast and a
producer outage. Nothing is uploaded and no real forecast folder is touched.

    .\\.venv\\Scripts\\python.exe -m scripts.publication_rehearsal --output outputs\\publication_rehearsal
    .\\.venv\\Scripts\\python.exe -m scripts.publication_rehearsal --write-examples docs\\schemas\\examples
"""
from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

import pandas as pd

from src.app_services import beta
from src.app_services.publication import LocalPublicationStore, build_publication, payload_checksum

RACE_START = '2024-07-07T14:00:00+00:00'
DRIVERS = ['VER', 'NOR', 'LEC', 'PIA', 'SAI', 'HAM', 'RUS', 'PER', 'ALO', 'STR',
           'GAS', 'OCO', 'ALB', 'TSU', 'RIC', 'HUL', 'MAG', 'BOT', 'ZHO', 'SAR']
SESSIONS = {'PRE': [], 'FP2': ['FP1', 'FP2'], 'Q': ['FP1', 'FP2', 'FP3', 'Q']}


def fixture_snapshot(folder, stage, generated_at, cutoff=None):
    """A frozen prospective snapshot with a plausible 20-driver summary."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    weights = pd.Series(range(len(DRIVERS), 0, -1), dtype=float) ** 2
    win = weights / weights.sum()
    pd.DataFrame({'Driver': DRIVERS, 'avg_finish': [1.6 + 0.9 * i for i in range(len(DRIVERS))],
                  'win_chance': win.round(6), 'podium_chance': (win * 3).clip(upper=1).round(6),
                  'points_chance': (win * 10).clip(upper=1).round(6),
                  'dnf_chance': [0.06] * len(DRIVERS)}).to_csv(folder/'simulation_summary.csv', index=False)
    (folder/'job.json').write_text(json.dumps({'kind': 'forecast', 'n_sims': 10000, 'seed': 42, 'overtaking_difficulty': 0.55,
                                              'source_dir': 'C:\\private\\never-published'}))
    context = {'year': 2024, 'event': 'Example Grand Prix', 'round': 12, 'session': stage,
               'available_sessions': SESSIONS[stage], 'race_start_utc': RACE_START,
               'data_cutoff_utc': cutoff or generated_at, 'session_evidence': {}}
    beta.freeze_snapshot(folder, context, now=generated_at)
    return folder


def _step(log, name, receipt, view, expect):
    passed = all(view.get(key) == value if key != 'latest_stage'
                 else (view['publication'] or {}).get('stage') == value for key, value in expect.items())
    log.append({'step': name, 'receipt': receipt, 'client_state': view['state'], 'client_reasons': view['reasons'],
                'client_stage': (view['publication'] or {}).get('stage'), 'expected': expect, 'passed': passed})


def rehearse(workdir):
    workdir = Path(workdir)
    store = LocalPublicationStore(workdir/'store')
    event = {'year': 2024, 'round': 12}
    log = []

    def view(now):
        return store.read_latest(event, now)

    store.heartbeat('2024-07-05T19:00:00Z')
    fp2 = build_publication(fixture_snapshot(workdir/'fp2', 'FP2', '2024-07-05T18:30:00Z'), 'established')
    receipt = store.publish(fp2, now='2024-07-05T19:00:00Z')
    _step(log, 'FP2 forecast published', receipt, view('2024-07-05T19:05:00Z'),
          {'state': 'current', 'latest_stage': 'FP2'})

    receipt = store.publish(copy.deepcopy(fp2), now='2024-07-05T19:10:00Z')
    _step(log, 'Network retry of the same FP2 payload', receipt, view('2024-07-05T19:15:00Z'),
          {'state': 'current', 'latest_stage': 'FP2'})

    altered = copy.deepcopy(fp2)
    first, second = altered['predictions'][:2]
    first['win_chance'], second['win_chance'] = second['win_chance'], first['win_chance']
    altered['checksum']['value'] = payload_checksum(altered)
    receipt = store.publish(altered, now='2024-07-05T19:20:00Z')
    _step(log, 'Same publication id with altered content', receipt, view('2024-07-05T19:25:00Z'),
          {'state': 'current', 'latest_stage': 'FP2'})

    store.heartbeat('2024-07-06T16:00:00Z')
    q = build_publication(fixture_snapshot(workdir/'q', 'Q', '2024-07-06T16:30:00Z'), 'established')
    broken = copy.deepcopy(q)
    broken['predictions'] = broken['predictions'][:10]
    receipt = store.publish(broken, now='2024-07-06T16:40:00Z')
    _step(log, 'Q payload fails validation (partial field)', receipt, view('2024-07-06T16:45:00Z'),
          {'state': 'stale', 'latest_stage': 'FP2'})

    # Simulate a crash after the snapshot write but before the pointer moved.
    pointer = store._latest('2024-r12')
    saved = pointer.read_bytes()
    store.publish(q, now='2024-07-06T16:50:00Z')
    pointer.write_bytes(saved)
    receipt = store.publish(copy.deepcopy(q), now='2024-07-06T16:55:00Z')
    _step(log, 'Retry repairs an interrupted pointer update', receipt, view('2024-07-06T17:00:00Z'),
          {'state': 'current', 'latest_stage': 'Q'})

    late = build_publication(fixture_snapshot(workdir/'fp2-late', 'FP2', '2024-07-05T18:45:00Z'), 'established')
    receipt = store.publish(late, now='2024-07-06T17:05:00Z')
    _step(log, 'Late retry of an older FP2 forecast', receipt, view('2024-07-06T17:10:00Z'),
          {'state': 'current', 'latest_stage': 'Q'})

    store.record_failure(event, 'Q', 'pipeline_error', now='2024-07-06T18:00:00Z')
    _step(log, 'Producer run fails after the Q forecast', None, view('2024-07-06T18:05:00Z'),
          {'state': 'stale', 'latest_stage': 'Q'})

    _step(log, 'Producer PC offline overnight', None, view('2024-07-07T08:00:00Z'),
          {'state': 'stale', 'latest_stage': 'Q'})

    _step(log, 'Race has started', None, view('2024-07-07T14:30:00Z'),
          {'state': 'closed', 'latest_stage': 'Q'})
    return log


def write_examples(directory):
    """Accepted and rejected example payloads for the v1 contract."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        accepted = build_publication(fixture_snapshot(Path(temp)/'q', 'Q', '2024-07-06T16:30:00Z'), 'established')

    def variant(change):
        payload = copy.deepcopy(accepted)
        change(payload)
        payload['checksum']['value'] = payload_checksum(payload)
        return payload

    tampered = copy.deepcopy(accepted)
    tampered['predictions'][0]['avg_finish'] = 1.2
    rejected = {
        'rejected-tampered-checksum': tampered,
        'rejected-personal-scenario': variant(lambda p: p.update(kind='personal')),
        'rejected-after-race-start': variant(lambda p: p.update(generated_at_utc='2024-07-07T14:05:00+00:00')),
        'rejected-stage-not-available': variant(lambda p: p.update(available_sessions=['FP1', 'FP2'])),
        'rejected-producer-secret': variant(lambda p: p['model'].update(webhook_url='https://example.invalid')),
        'rejected-partial-field': variant(lambda p: p.update(predictions=p['predictions'][:10])),
    }
    files = {'accepted-q.json': accepted, **{f'{name}.json': payload for name, payload in rejected.items()}}
    for name, payload in files.items():
        (directory/name).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return sorted(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output', type=Path, help='Folder for the rehearsal report.')
    parser.add_argument('--write-examples', type=Path, help='Write v1 example payloads here instead.')
    args = parser.parse_args(argv)
    if args.write_examples:
        for name in write_examples(args.write_examples):
            print(name)
        return 0
    with tempfile.TemporaryDirectory() as temp:
        log = rehearse(temp)
    for row in log:
        mark = 'PASS' if row['passed'] else 'FAIL'
        status = (row['receipt'] or {}).get('status', '-')
        print(f"{mark}  {row['step']}: publish={status}, client={row['client_state']} "
              f"showing {row['client_stage']}; {'; '.join(row['client_reasons']) or 'no warnings'}")
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'rehearsal.json').write_text(json.dumps(log, indent=2) + '\n', encoding='utf-8')
    return 0 if all(row['passed'] for row in log) else 1


if __name__ == '__main__':
    raise SystemExit(main())
