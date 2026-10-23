import pandas as pd
import pytest

from src.prediction_data import practice_features, prior_reliability, strategy_records, delay_records, outcome_records
from src.data_sources.fia_extraction import parse_document, published_utc, asof_grid
from src.data_sources.weather_archive import collect_run, pair_samples
from src.historical_model import build_historical_feature_table, train_historical_models
from tests.test_long_run_pace import practice_laps


def practice_inputs():
    laps = practice_laps()
    laps['CleanPushLap'] = True
    for key, value in [('Year', 2021), ('Round', 1), ('Event', 'GP'), ('Session', 'FP2')]:
        laps[key] = value
    messages = pd.DataFrame([{'Year': 2021, 'Round': 1, 'Event': 'GP', 'Session': s, 'Time': t} for s, t in
                             [('FP2', '2021-03-26T16:00:00Z'), ('Q', '2021-03-27T16:00:00Z')]])
    return laps, messages


def test_practice_rejects_post_q_sprint_and_missing_time_evidence():
    laps, messages = practice_inputs()
    features = practice_features(laps, messages).set_index('DriverCode')
    assert features.loc['A', 'fp2_long_run_relative_pace'] > features.loc['B', 'fp2_long_run_relative_pace']
    messages.loc[messages.Session.eq('FP2'), 'Time'] = '2021-03-28T16:00:00Z'
    assert practice_features(laps, messages).empty
    assert practice_features(laps).empty


def test_practice_rejects_yellow_and_short_runs():
    laps, messages = practice_inputs()
    laps.loc[laps.Stint.eq(2), 'TrackStatus'] = '12'
    assert practice_features(laps, messages).empty


def results():
    return pd.DataFrame([{'Year': 2025, 'Round': n, 'Event': f'GP{n}', 'Session': 'R', 'Abbreviation': 'AAA',
                          'TeamName': 'A', 'Status': status} for n, status in [(1, 'Retired'), (2, 'Finished'), (3, 'Engine')]])


def test_prior_history_cannot_see_target_or_future_outcomes():
    inputs = pd.DataFrame([{'Year': 2025, 'Round': n, 'DriverCode': 'AAA', 'Team': 'A'} for n in [1, 2, 3]])
    source = results()
    a = prior_reliability(inputs, source)
    assert list(a.prior_driver_starts) == [0, 1, 2]
    source.loc[source.Round.eq(3), 'Status'] = 'Finished'
    pd.testing.assert_frame_equal(a, prior_reliability(inputs, source))
    assert outcome_records(source).loc[0, 'mechanical'] != outcome_records(source).loc[0, 'mechanical']


def test_confirmed_cause_needs_source_and_cannot_relabel_finisher():
    causes = pd.DataFrame([{'Year': 2025, 'Round': 1, 'Event': 'GP1', 'DriverCode': 'AAA',
                           'OutcomeClass': 'mechanical_dnf', 'PublishedAtUtc': '2025-01-01T12:00:00Z',
                           'SourceURL': 'https://example.org/confirmed', 'Verified': True}])
    records = outcome_records(results(), causes)
    assert records.loc[0, 'mechanical'] == 1 and records.loc[0, 'independently_verified_cause']
    causes.loc[0, ['Round', 'Event']] = [2, 'GP2']
    with pytest.raises(ValueError, match='known retirement'):
        outcome_records(results(), causes)


def test_confirmed_cause_cannot_arrive_after_target_forecast():
    inputs = pd.DataFrame([{'Year': 2025, 'Round': 2, 'DriverCode': 'AAA', 'Team': 'A'}])
    causes = pd.DataFrame([{'Year': 2025, 'Round': 1, 'Event': 'GP1', 'DriverCode': 'AAA',
                           'OutcomeClass': 'mechanical_dnf', 'PublishedAtUtc': '2025-01-10T12:00:00Z',
                           'SourceURL': 'https://example.org/confirmed', 'Verified': True}])
    before = prior_reliability(inputs, results(), causes, {(2025, 2): pd.Timestamp('2025-01-09T12:00:00Z')})
    after = prior_reliability(inputs, results(), causes, {(2025, 2): pd.Timestamp('2025-01-11T12:00:00Z')})
    assert before.iloc[0].prior_team_mechanical_rate == .1
    assert after.iloc[0].prior_team_mechanical_rate == pytest.approx(2/11)
    inputs['Round'] = 1
    warmup = prior_reliability(inputs, results(), causes, {(2025, 1): pd.Timestamp('2025-01-11T12:00:00Z')})
    assert warmup.iloc[0].prior_team_starts == 0


def test_utc_origin_uses_session_time_not_segment_time(tmp_path):
    from src.app_services import historical_library as library
    from scripts.build_prediction_data import archived_origin
    folder = tmp_path/'saved'
    trace = pd.DataFrame({'Date': pd.date_range('2025-01-01T12:00:00Z', periods=12, freq='s'),
                          'SessionTime': pd.to_timedelta(range(100, 112), unit='s'),
                          'Time': pd.to_timedelta(range(12), unit='s')})
    library.save_partition(folder, {'year': 2025, 'round': 1, 'event': 'GP', 'session': 'R'},
                           {'mode': 'detailed', 'telemetry': True}, {'car_1': trace}, {}, [])
    saved = library.read_json(folder/'session.json')
    origin, source = archived_origin(folder/'session.json', saved)
    assert origin == pd.Timestamp('2025-01-01T11:58:20Z') and source['sha256']


def test_pit_traversal_separates_neutralisation_and_missing_crossings():
    laps = pd.DataFrame({'Year': [2025]*3, 'Round': [1]*3, 'Event': ['GP']*3, 'Session': ['R']*3,
                         'Driver': ['AAA']*3, 'Stint': [1, 1, 2], 'Compound': ['SOFT', 'SOFT', 'HARD'],
                         'LapNumber': [1, 2, 3], 'TyreLife': [1, 2, 1], 'TrackStatus': ['1', '4', '4'],
                         'PitInTimeSeconds': [None, 200, None], 'PitOutTimeSeconds': [None, None, 225]})
    stints, pits = strategy_records(laps)
    assert len(stints) == 2 and pits.iloc[0].pit_lane_seconds == 25 and pits.iloc[0].phase == 'safety_car'
    assert strategy_records(laps.drop(columns=['PitInTimeSeconds']))[1].empty


def test_delay_labels_require_verified_times_and_normal_controls_are_explicit():
    rows = pd.DataFrame([{'Year': 2025, 'Round': 1, 'Event': 'GP', 'ScheduledStartUtc': '2025-01-01T12:00:00Z',
                          'ActualStartUtc': '2025-01-01T12:30:00Z', 'StartDefinition': 'formation_lap', 'Reason': 'weather',
                          'SourceURL': 'https://example.org/start', 'Verified': True}])
    assert delay_records(rows).iloc[0].delay_minutes == 30
    rows.loc[0, 'Verified'] = False
    with pytest.raises(ValueError, match='verified'):
        delay_records(rows)
    rows.loc[0, 'Verified'] = True
    rows.loc[0, 'ActualStartUtc'] = '2025-01-01 12:30:00'
    with pytest.raises(ValueError, match='timezone'):
        delay_records(rows)


def roster():
    return pd.DataFrame({'Round': [1, 1], 'Abbreviation': ['VER', 'NOR'], 'DriverNumber': [1, 4],
                         'BroadcastName': ['M VERSTAPPEN', 'L NORRIS'], 'TeamName': ['Red Bull', 'McLaren']})


def test_fia_grid_requires_complete_identity_and_cutoff_excludes_later_revision():
    row = {'year': 2025, 'event': 'GP', 'session': 'R', 'document_title': 'Final Starting Grid',
           'published_at': '01.03.25 12:00 CET', 'document_url': 'https://www.fia.com/grid.pdf'}
    doc = {'pages': [{'text': '', 'columns': ['1 1 Max VERSTAPPEN * 1:20.123', '2 4 Lando NORRIS 1:20.234']}]}
    kind, rows = parse_document(doc, row, roster())
    assert kind == 'grids' and len(rows) == 2
    frame = pd.DataFrame(rows)
    assert asof_grid(frame, 2025, 'GP', '2025-03-01T10:59:00Z').empty
    assert len(asof_grid(frame, 2025, 'GP', '2025-03-01T11:00:00Z')) == 2
    doc['pages'][0]['columns'][1] = ''
    with pytest.raises(ValueError, match='Incomplete'):
        parse_document(doc, row, roster())
    assert published_utc('undated') is pd.NaT
    row['session'] = 'S'
    with pytest.raises(ValueError, match='Sprint'):
        parse_document(doc, row, roster())


def test_fia_entry_list_excludes_reserve_drivers():
    row = {'year': 2025, 'event': 'GP', 'document_title': 'Entry List', 'published_at': '',
           'document_url': 'https://www.fia.com/list.pdf'}
    doc = {'pages': [{'text': '1 Max Verstappen NED Red Bull\n4 Lando Norris GBR McLaren\nIn addition to the list\n50 New Driver GBR McLaren', 'columns': []}]}
    kind, rows = parse_document(doc, row, roster())
    assert kind == 'entries' and len(rows) == 2
    assert rows[0]['PublishedAtUtc'] == ''


def test_asof_grid_rejects_a_truncated_publication():
    row = {'year': 2025, 'event': 'GP', 'session': 'R', 'document_title': 'Final Starting Grid',
           'published_at': '01.03.25 12:00 CET', 'document_url': 'https://www.fia.com/grid.pdf'}
    doc = {'pages': [{'text': '', 'columns': ['1 1 Max VERSTAPPEN 1:20.123', '2 4 Lando NORRIS 1:20.234']}]}
    _, rows = parse_document(doc, row, roster())
    with pytest.raises(ValueError, match='incomplete'):
        asof_grid(pd.DataFrame(rows).iloc[:1], 2025, 'GP', '2025-03-01T12:00:00Z')


def test_weather_rejects_event_name_with_wrong_physical_circuit():
    from src.data_sources.weather_archive import validate_identity
    venues = pd.DataFrame([{'year': 2026, 'round': 16, 'event': 'Bahrain Grand Prix', 'circuit_id': 'sepang',
                            'layout_id': 'sepang_gp', 'latitude': 2.76083, 'longitude': 101.73833}])
    request = {'Year': 2026, 'Round': 16, 'Event': 'Bahrain Grand Prix', 'CircuitId': 'bahrain',
               'LayoutId': 'bahrain_gp', 'Latitude': 26.0325, 'Longitude': 50.5106}
    with pytest.raises(ValueError, match='physical circuit'):
        validate_identity(request, venues)


def test_weather_initialisation_is_not_proof_of_public_availability(tmp_path):
    from tests.test_race_weather import payload
    from unittest.mock import Mock
    response = Mock()
    response.json.return_value = payload()
    request = {'Year': 2026, 'Round': 1, 'Event': 'GP', 'CircuitId': 'sepang', 'LayoutId': 'sepang_gp',
               'Latitude': 2.76, 'Longitude': 101.74, 'RunUtc': '2026-10-10T18:00:00Z',
               'CutoffUtc': '2026-10-11T06:00:00Z', 'ScheduledStartUtc': '2026-10-11T12:00:00Z'}
    report = collect_run(request, tmp_path/'capture', get=Mock(return_value=response))
    assert not report['eligible_for_training'] and report['delay_probability'] is None
    samples = pd.DataFrame({'Time': ['0 days 00:10:00'], 'AirTemp': [30]})
    assert pair_samples({'forecast': {'payload': payload()}}, samples, request['ScheduledStartUtc']).empty


def test_enriched_training_is_inactive_and_future_practice_does_not_leak(tmp_path):
    from tests.test_historical_model import _write_fixture
    _write_fixture(tmp_path)
    baseline = build_historical_feature_table(tmp_path)
    enriched = build_historical_feature_table(tmp_path, enriched=True)
    assert len(enriched) == len(baseline) and 'prior_team_dnf_rate' in enriched
    artifacts = train_historical_models(tmp_path, tmp_path/'candidate', enriched=True)
    import json
    metrics = json.loads(open(artifacts.metrics).read())
    assert not metrics['activated'] and metrics['feature_set'] == 'practice_reliability_v1'
    assert metrics['feature_coverage']['prior_team_dnf_rate']['train'] == metrics['train_rows']
