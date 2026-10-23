from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.app_services import historical_library as library, session_replay as replay
from src.venues import resolve_venue


def lap_frame(event, session, drivers):
    rows = []
    for code, number, team, pace in drivers:
        for lap in range(1, 4):
            rows.append({'Year': 2021, 'Event': event, 'Round': 18, 'Session': session, 'Driver': code,
                         'DriverNumber': number, 'Team': team, 'LapNumber': lap, 'Compound': 'MEDIUM',
                         'LapStartTimeSeconds': 100+(lap-1)*pace, 'LapTimeSeconds': pace,
                         'Sector1Seconds': pace/3, 'Sector2Seconds': pace/3, 'Sector3Seconds': pace/3,
                         'PitIn': False, 'PitOut': lap == 1, 'Deleted': False})
    return pd.DataFrame(rows)


def circuit(start, pace):
    times = np.arange(start, start+3*pace, 0.25)
    theta = (times-start)/pace*2*np.pi
    return times, pd.DataFrame({'SessionTime': pd.to_timedelta(times, unit='s'), 'X': 1000+500*np.cos(theta),
                                'Y': 1000+500*np.sin(theta), 'Status': 'OnTrack'})


def save(root, *, session='R', telemetry=True, event='Mexico City Grand Prix'):
    drivers = [('AAA', 44, 'Alpha', 60.0), ('BBB', 33, 'Beta', 62.0)]
    tables = {'laps': lap_frame(event, session, drivers),
              'results': pd.DataFrame({'DriverNumber': [33, 44], 'Abbreviation': ['BBB', 'AAA'],
                                       'TeamName': ['Beta Racing', 'Alpha Racing'], 'Position': [1, 2]}),
              'track_status': pd.DataFrame({'Time': pd.to_timedelta([90, 150], unit='s'),
                                            'Status': [1, 4], 'Message': ['AllClear', 'SCDeployed']})}
    if telemetry:
        for _, number, _, pace in drivers:
            times, position = circuit(100, pace)
            if number == 33:
                # Pit box: no samples for 20 seconds mid-session.
                position = position[(times < 140) | (times > 160)]
            tables[f'position_{number}'] = position
            tables[f'car_{number}'] = pd.DataFrame({'SessionTime': pd.to_timedelta(times, unit='s'),
                                                    'Speed': 300.0, 'Throttle': 100, 'Brake': times % 10 < 1,
                                                    'nGear': 8, 'RPM': 11000, 'DRS': 0})
    task = {'year': 2021, 'round': 18, 'event': event, 'session': session}
    folder = library.library_root(root)/'2021'/'detailed'/f'18_{session}'
    library.save_partition(folder, task, library.options({'years': [2021], 'telemetry': telemetry}),
                           tables, resolve_venue(2021, event), [] if telemetry else ['telemetry'])
    return folder


def test_lists_saved_sessions_with_telemetry_flag(tmp_path):
    save(tmp_path, session='Q', telemetry=False)
    save(tmp_path, session='R')
    found = replay.sessions(tmp_path)['sessions']
    assert [(row['session'], row['telemetry']) for row in found] == [('Q', False), ('R', True)]
    assert found[1]['id'] == '2021/detailed/18_R'


def test_replay_resamples_positions_and_hides_gaps(tmp_path, monkeypatch):
    import fastf1
    monkeypatch.setattr(fastf1, 'get_session', Mock(side_effect=AssertionError('Replay must not download.')))
    save(tmp_path)
    data = replay.replay(tmp_path, '2021/detailed/18_R')
    assert data['race'] and data['telemetry'] and data['start'] == 100 and data['end'] == 286
    # Classification order and team names win over lap rows.
    assert [driver['code'] for driver in data['drivers']] == ['BBB', 'AAA']
    assert data['drivers'][0]['team'] == 'Beta Racing'
    assert len(data['laps']['44']) == 3 and data['laps']['44'][2]['end'] == 280
    frames = data['positions']['33']
    assert len(frames) == len(data['positions']['44']) == 187
    assert frames[0] == [1500, 1000]
    assert frames[50] is None and frames[30] is not None
    # Lap 1 ended 40 seconds after the last sample for car 44: hidden, not frozen.
    assert data['positions']['44'][-1] is None
    assert len(data['outline']) > 20
    assert [row['status'] for row in data['trackStatus']] == ['1', '4']


def test_replay_without_telemetry_keeps_timing_and_explains(tmp_path):
    save(tmp_path, telemetry=False)
    data = replay.replay(tmp_path, '2021/detailed/18_R')
    assert data['positions'] == {} and not data['telemetry']
    assert 'Car positions were not downloaded' in data['positionsMessage']
    assert data['laps']['33'][0]['time'] == 62


def test_lap_telemetry_traces_against_distance(tmp_path):
    save(tmp_path)
    lap = replay.lap_telemetry(tmp_path, '2021/detailed/18_R', 44, 2)
    trace = lap['trace']
    assert lap['lap']['lap'] == 2 and trace['time'][0] == 0
    assert trace['distance'][0] == 0 and trace['distance'][-1] == pytest.approx(300/3.6*60, rel=.01)
    assert set(trace['brake']) == {0, 100} and trace['gear'][0] == 8
    assert trace['lapDistance'] == pytest.approx(300/3.6*60, rel=.01)
    assert len(trace['xy']) == len(trace['distance'])


def test_lap_telemetry_missing_is_a_clear_error(tmp_path):
    save(tmp_path, telemetry=False)
    with pytest.raises(ValueError, match='Car telemetry was not downloaded'):
        replay.lap_telemetry(tmp_path, '2021/detailed/18_R', 44, 2)


@pytest.mark.parametrize('session_id', ['../../outside', '2021/results/18_R', '2021/detailed', ''])
def test_rejects_paths_outside_saved_detailed_sessions(tmp_path, session_id):
    save(tmp_path)
    with pytest.raises(ValueError):
        replay.replay(tmp_path, session_id)


def test_changed_archive_file_is_refused(tmp_path):
    folder = save(tmp_path)
    file = next(folder.glob('versions/*/position_44.csv.gz'))
    data = file.read_bytes()
    file.write_bytes(data[:-1]+bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError, match='checksum'):
        replay.replay(tmp_path, '2021/detailed/18_R')
