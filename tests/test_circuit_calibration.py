import json

import pandas as pd
import pytest

from src.circuit_calibration import (benchmark, calibration_venue, clean_order_changes,
    posterior, race_events, read_tables, sha256)


def laps():
    return pd.DataFrame([{'Driver': driver, 'LapNumber': n,
        'LapStartTimeSeconds': n*100+offset-90, 'LapTimeSeconds': 90,
        'IsAccurate': True, 'Deleted': False, 'PitIn': False, 'PitOut': False,
        'TrackStatus': '1'} for n in (1, 2, 3, 4) for driver, offset in
        [('A', 0 if n < 3 else 3), ('B', 2 if n < 3 else 0)]])


def feed(times, codes):
    return pd.DataFrame({'Time': pd.to_timedelta(times, unit='s'), 'Status': codes})


def test_event_window_includes_initial_state_but_not_ended_prestart_red():
    events, reason = race_events(laps(), feed([0, 5, 150, 200, 450], [5, 4, 6, 1, 5]))
    assert reason is None
    assert events['safety_car'] == 1
    assert events['virtual_safety_car'] == 1
    assert events['red_flag'] == 0


def test_vsc_does_not_count_as_safety_car_and_missing_is_unknown():
    events, _ = race_events(laps(), feed([0, 180], [1, 6]))
    assert events['safety_car'] == 0
    assert events['virtual_safety_car'] == 1
    assert race_events(laps(), pd.DataFrame())[0] is None
    assert race_events(laps(), feed([100], [1]))[0] is None
    assert race_events(laps(), feed([0, 200], [1, 99]))[0] is None


def test_proxy_counts_clean_nearby_reversal_but_rejects_pit_or_yellow():
    assert clean_order_changes(laps()) == {'changes': 1, 'exposure': 2, 'reason': None}
    for column, value in [('PitIn', True), ('TrackStatus', '12'), ('IsAccurate', None), ('Deleted', None)]:
        d = laps()
        d[column] = d[column].astype(object)
        d.loc[(d.Driver == 'A') & (d.LapNumber == 3), column] = value
        assert clean_order_changes(d)['changes'] is None
    duplicated = pd.concat([laps(), laps().iloc[:1]], ignore_index=True)
    assert clean_order_changes(duplicated)['changes'] is None


def row(year=2021, round=1, layout='one', sc=1, red=0):
    return {'year': year, 'round': round, 'event': 'Race', 'circuit_id': layout,
            'layout_id': layout, 'events': {'safety_car': sc, 'red_flag': red}}


def test_layout_observations_not_transferred_and_zero_events_not_zero_probability():
    history = [row(layout='old', sc=0)]*5
    fresh = posterior(history, 'new', 'safety_car')
    old = posterior(history, 'old', 'safety_car')
    assert fresh['races'] == 0
    assert old['races'] == 5
    assert 0 < old['low90'] < old['mean'] < old['high90'] < 1


def test_chronological_predictions_do_not_use_current_or_future_outcomes():
    first = [row(), row(2022, 1), row(2022, 2)]
    changed = [row(), row(2022, 1, sc=0, red=1), row(2022, 2, sc=0, red=1)]
    a, _ = benchmark(first, {})
    b, _ = benchmark(changed, {})
    assert [r['prediction'] for r in a if r['round'] == 1] == [r['prediction'] for r in b if r['round'] == 1]
    assert [r['prediction'] for r in a if r['round'] == 2] != [r['prediction'] for r in b if r['round'] == 2]


def test_explicit_alias_does_not_modify_saved_manifest_and_conflict_stays_unknown():
    m = {'year': 2025, 'event': 'Abu Dhabi Grand Prix', 'venue': {
        'venue_status': 'unresolved', 'feed_location': 'Yas Island'}}
    before = json.dumps(m)
    v, source = calibration_venue(m)
    assert v['circuit_id'] == 'yas_marina'
    assert source == 'explicit_yas_island_alias'
    assert json.dumps(m) == before
    m['venue']['venue_status'] = 'conflict'
    assert not calibration_venue(m)[0].get('circuit_id')
    melbourne = {'year': 2022, 'event': 'Australian Grand Prix', 'venue': {
        'venue_status': 'resolved', 'circuit_id': 'albert_park', 'layout_id': 'albert_park_gp'}}
    assert calibration_venue(melbourne)[0]['layout_id'] == 'albert_park_since_2022'


def test_consumed_tables_are_hash_checked_and_cannot_escape_partition(tmp_path):
    file = tmp_path/'laps.csv'
    file.write_text('Driver,LapNumber\nA,1\n')
    info = {'table': 'laps', 'bytes': file.stat().st_size, 'sha256': sha256(file)}
    manifest = {'files': {'laps.csv': info}}
    assert len(read_tables(tmp_path/'session.json', manifest)[0]['laps']) == 1
    file.write_text('Driver,LapNumber\nB,1\n')
    with pytest.raises(ValueError, match='Changed'):
        read_tables(tmp_path/'session.json', manifest)
    with pytest.raises(ValueError, match='Invalid'):
        read_tables(tmp_path/'session.json', {'files': {'../outside.csv': info}})
