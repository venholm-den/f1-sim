import json
from pathlib import Path

import pandas as pd
import pytest

from src.app_services.beta import freeze_snapshot
from src.app_services.classification_checks import capture_checks, compare_classification, compare_stint_ages, resolve_race_session, try_capture_checks
from src.data_sources.openf1 import OpenF1Client
from src.stage_ensemble_benchmark import digest
from src.venues import resolve_venue


def context():
    return dict(year=2026, round=8, event='British Grand Prix', session='Q',
        data_cutoff_utc='2026-06-08T13:00:00Z', race_start_utc='2026-06-09T12:00:00Z',
        venue=resolve_venue(2026, 'British Grand Prix'))


def race():
    return dict(year=2026, meeting_key=1, session_key=10, session_name='Race',
        date_start='2026-06-09T12:00:00Z', circuit_short_name='Silverstone')


def roster(key=10):
    return [dict(session_key=key, driver_number=n, name_acronym=d) for n, d in [(1, 'AAA'), (2, 'BBB')]]


def rows(key=10):
    return [dict(session_key=key, driver_number=n, position=p, dnf=False, dns=False, dsq=False)
            for n, p in [(1, 1), (2, 2)]]


def test_result_and_grid_client_use_explicit_session_keys(monkeypatch):
    client = OpenF1Client()
    calls = []
    monkeypatch.setattr(client, 'get_dataframe', lambda name, params: calls.append((name, params)))
    client.session_result(10); client.starting_grid(10)
    assert calls == [('session_result', {'session_key': 10}), ('starting_grid', {'session_key': 10})]


def test_session_resolver_rejects_wrong_circuit_date_year_and_duplicates():
    assert resolve_race_session([race()], context())['session_key'] == 10
    for invalid in ({**race(), 'circuit_short_name': 'Barcelona'}, {**race(), 'date_start': '2026-06-09T14:00:00Z'},
                    {**race(), 'year': 2025}, {**race(), 'circuit_short_name': None}):
        with pytest.raises(ValueError, match='unique'):
            resolve_race_session([invalid], context())
    with pytest.raises(ValueError, match='unique'):
        resolve_race_session([race(), race()], context())


def test_rank_disagreements_preserve_primary_and_unknown_flags_are_not_false():
    primary = pd.DataFrame({'Driver': ['AAA', 'BBB'], 'actual_position': [2, 1],
                            'actual_status': ['Engine', 'Finished']})
    before = primary.copy(deep=True)
    remote = rows(); remote[0]['dnf'] = None
    check = compare_classification(primary, remote, roster(), 10, position_column='actual_position', source='fastf1_results')
    assert check['status'] == 'disagreement' and not check['automatic_override']
    assert len(check['changes']) == 2  # Only positions: unknown is not a healthy finish.
    assert check['unknown_status_drivers'] == ['AAA']
    pd.testing.assert_frame_equal(before, primary)
    remote[0]['dnf'] = True
    primary.actual_position = [1, 2]
    assert compare_classification(primary, remote, roster(), 10, position_column='actual_position', source='fastf1_results')['status'] == 'match'


@pytest.mark.parametrize('status,flag', [('Did not start', 'dns'), ('Disqualified', 'dsq')])
def test_dns_dsq_do_not_become_pace_or_retirement_errors(status, flag):
    primary = pd.DataFrame({'Driver': ['AAA', 'BBB'], 'actual_position': [1, 2], 'actual_status': [status, 'Finished']})
    remote = rows(); remote[0][flag] = True
    assert compare_classification(primary, remote, roster(), 10, position_column='actual_position', source='fastf1_results')['status'] == 'match'


def test_partial_duplicate_or_wrong_session_rows_fail_closed():
    primary = pd.DataFrame({'Driver': ['AAA', 'BBB'], 'q_rank': [1, 2]})
    for remote in (rows()[:1], rows()+rows()[:1], rows(11), [{**r, 'position': None} for r in rows()]):
        with pytest.raises(ValueError):
            compare_classification(primary, remote, roster(), 10, position_column='q_rank', source='fastf1')


class FakeClient:
    def __init__(self, missing=False):
        self.calls = []; self.missing = missing

    def get_json(self, endpoint, params):
        self.calls.append((endpoint, params))
        if endpoint == 'sessions':
            if params.get('session_name') == 'Race':
                return [race()]
            return [{**race(), 'session_name': 'Qualifying', 'session_key': 9, 'date_start': '2026-06-08T12:00:00Z'}]
        if endpoint == 'drivers':
            return roster(params['session_key'])
        return [] if self.missing else rows(params['session_key'])


def forecast(tmp_path, *, stage='Q', grid_source='fia_official_grid'):
    folder = tmp_path/'outputs/app_runs/forecast'; folder.mkdir(parents=True)
    pd.DataFrame({'Driver': ['AAA', 'BBB'], 'avg_finish': [1., 2.]}).to_csv(folder/'simulation_summary.csv', index=False)
    pd.DataFrame({'Driver': ['AAA', 'BBB'], 'q_rank': [1, 2], 'grid_position': [1, 2],
                  'grid_source': grid_source}).to_csv(folder/'features.csv', index=False)
    freeze_snapshot(folder, {**context(), 'session': stage}, now='2026-06-08T13:01:00Z')
    return folder


def test_pre_without_verified_classification_makes_no_openf1_requests(tmp_path):
    folder = forecast(tmp_path, stage='PRE', grid_source='saved_model_grid')
    client = FakeClient()
    result = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:00:00Z')
    assert result['status'] == 'not_applicable' and not client.calls


def test_access_failure_is_explicit_cached_and_session_request_is_narrow(tmp_path):
    import requests
    from src.data_sources.openf1 import OpenF1AccessUnavailable
    folder = forecast(tmp_path)
    class Unavailable(FakeClient):
        def get_json(self, endpoint, params):
            self.calls.append((endpoint, params))
            response = requests.Response(); response.status_code = 401
            raise OpenF1AccessUnavailable('Independent access unavailable', response=response)
    client = Unavailable()
    result = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:00:00Z')
    assert result['status'] == 'access_unavailable' and len(client.calls) == 1
    assert 'date_start>' in client.calls[0][1] and 'date_start<' in client.calls[0][1]
    cached = capture_checks(tmp_path, folder, client=client, now='2026-06-08T15:01:00Z')
    assert cached['status'] == 'access_unavailable' and len(client.calls) == 1


def test_old_whole_season_failure_does_not_block_corrected_request(tmp_path):
    folder = forecast(tmp_path); client = FakeClient()
    first = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:00:00Z')
    report = Path(first['folder'])/'report.json'
    old = json.loads(report.read_text()); old.pop('request_policy')
    old['status'] = 'capture_failed'; old['errors'] = [{'error_type':'HTTPError'}]
    report.write_text(json.dumps(old))
    second = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:01:00Z')
    assert second['status'] == 'completed' and second['folder'] != first['folder']
    assert json.loads(report.read_text())['status'] == 'capture_failed'


def test_capture_uses_q_result_and_race_grid_only_timestamps_raw_and_caches(tmp_path):
    folder = forecast(tmp_path); client = FakeClient()
    frozen_before = (folder/'frozen/features.csv').read_bytes()
    result = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:00:00Z')
    assert result['status'] == 'completed'
    assert all(c['status'] == 'match' for c in result['checks'].values())
    assert ('session_result', {'session_key': 10}) not in client.calls
    assert ('session_result', {'session_key': 9}) in client.calls
    report = json.loads((Path(result['folder'])/'report.json').read_text())
    assert report['source_feature_cutoff_utc'] == context()['data_cutoff_utc']
    assert all(r['publication_time_utc'] is None and r['response_received_at_utc'] == '2026-06-08T14:00:00+00:00' for r in report['requests'])
    count = len(client.calls)
    assert capture_checks(tmp_path, folder, client=client, now='2026-06-08T15:00:00Z')['status'] == 'cached'
    assert len(client.calls) == count
    assert (folder/'frozen/features.csv').read_bytes() == frozen_before


def test_unpublished_checks_retry_later_without_overwriting_or_blocking(tmp_path):
    folder = forecast(tmp_path); client = FakeClient(missing=True)
    first = capture_checks(tmp_path, folder, client=client, now='2026-06-08T14:00:00Z')
    client.missing = False
    second = capture_checks(tmp_path, folder, client=client, now='2026-06-08T15:01:00Z')
    assert first['folder'] != second['folder']
    assert all(c['status'] == 'unavailable' for c in first['checks'].values())
    assert all(c['status'] == 'match' for c in second['checks'].values())
    assert try_capture_checks(tmp_path, folder)['status'] == 'disabled'


def test_post_race_requires_matching_completed_official_score(tmp_path):
    folder = forecast(tmp_path); client = FakeClient()
    assert capture_checks(tmp_path, folder, client=client, now='2026-06-10T14:00:00Z')['status'] == 'ineligible'
    assert not client.calls
    score = tmp_path/'official'; score.mkdir()
    (score/'score.json').write_text(json.dumps({'snapshot_sha256': digest(folder/'frozen/manifest.json'),
                                              'evaluated_at_utc': '2026-06-10T12:00:00Z'}))
    pd.DataFrame({'Driver': ['AAA', 'BBB'], 'actual_position': [1, 2], 'actual_status': 'Finished',
                  'actual_result_source': 'fastf1_results'}).to_csv(score/'actual_results.csv', index=False)
    result = capture_checks(tmp_path, folder, client=client, official_folder=score, now='2026-06-10T14:00:00Z')
    assert result['checks']['race_result']['status'] == 'match'
    assert ('session_result', {'session_key': 10}) in client.calls
    assert not any(e == 'starting_grid' for e, _ in client.calls)


def test_start_age_crosscheck_accounts_for_unobserved_early_laps():
    ledger = pd.DataFrame({'Driver': ['AAA'], 'Session': ['Q'], 'Stint': [1], 'Compound': ['SOFT'],
                           'first_lap_number': [3], 'start_tyre_life': [5]})
    remote = [dict(driver_number=1, session_key=9, stint_number=1, compound='SOFT', lap_start=1, tyre_age_at_start=2)]
    result = compare_stint_ages(ledger, remote, roster(9), 9, 'Q')
    assert result['status'] == 'match' and result['compared_stints'] == 1
    remote[0]['tyre_age_at_start'] = 0
    result = compare_stint_ages(ledger, remote, roster(9), 9, 'Q')
    assert result['status'] == 'disagreement' and result['changes'][0]['openf1'] == 3
    assert not result['automatic_override'] and not result['official_inventory']
    with pytest.raises(ValueError, match='identities'):
        compare_stint_ages(ledger, remote*2, roster(9), 9, 'Q')
