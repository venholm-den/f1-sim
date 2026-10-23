from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.app_services import archive_telemetry as telemetry, historical_library as library
from src.venues import resolve_venue
from portable_app import web_backend


def save(root, *, year=2021, event='Mexico City Grand Prix', session='Q', venue=None, short=False):
    times = np.linspace(100, 160, 121)
    theta = np.linspace(0, 2*np.pi, 121)
    positions = pd.DataFrame({'SessionTime': pd.to_timedelta(times, unit='s'),
                             'X': 1000+500*np.cos(theta), 'Y': 1000+500*np.sin(theta), 'Status': 'OnTrack'})
    if short:
        positions = positions.iloc[50:80]
    laps = pd.DataFrame({'Year': [year], 'Event': [event], 'Round': [18], 'Session': [session],
                         'Driver': ['AAA'], 'DriverNumber': [44], 'LapNumber': [2],
                         'LapStartTimeSeconds': [100], 'LapTimeSeconds': [60],
                         'Sector1Seconds': [20], 'Sector2Seconds': [20], 'Sector3Seconds': [20]})
    task = {'year':year,'round':18,'event':event,'session':session}
    folder = library.library_root(root)/str(year)/'detailed'/f'18_{event}_{session}'
    library.save_partition(folder,task,library.options({'years':[year],'telemetry':True}),
                            {'laps':laps,'position_44':positions},venue or resolve_venue(year,event),[])
    return folder


def test_track_uses_downloaded_complete_lap_and_real_sector_boundaries(tmp_path, monkeypatch):
    import fastf1
    network = Mock(side_effect=AssertionError('Archive geometry must not download session telemetry.'))
    monkeypatch.setattr(fastf1,'get_session',network)
    save(tmp_path)
    found = telemetry.layout(tmp_path,2021,'Mexico City Grand Prix','Q')
    assert found['status']=='available' and found['source']=='historical_library'
    assert len(found['points'])==121
    assert {point['sector'] for point in found['points']} == {'S1','S2','S3'}
    assert found['points'][0]['progress']==0 and found['points'][-1]['progress']==1
    assert found['fastestLap']['driver']=='AAA' and found['sectors']['S1']['seconds']==20
    assert not network.called


def test_pre_geometry_is_labelled_with_actual_source_session(tmp_path):
    save(tmp_path)
    found = telemetry.layout(tmp_path,2021,'Mexico City Grand Prix','PRE')
    assert found['requested_session']=='PRE' and found['session']=='Q'
    assert found['status']=='available' and 'Geometry only' in found['message']


def test_requested_session_preferred_then_another_session_of_same_event(tmp_path):
    save(tmp_path,session='Q')
    save(tmp_path,session='R')
    assert telemetry.layout(tmp_path,2021,'Mexico City Grand Prix','R')['session']=='R'
    assert telemetry.layout(tmp_path,2021,'Mexico City Grand Prix','FP1')['session']=='Q'


def test_no_other_year_event_workspace_or_relocated_circuit_is_substituted(tmp_path):
    save(tmp_path)
    assert not telemetry.layout(tmp_path,2022,'Mexico City Grand Prix')['points']
    assert not telemetry.layout(tmp_path,2021,'Canadian Grand Prix')['points']
    assert not telemetry.layout(tmp_path/'other',2021,'Mexico City Grand Prix')['points']
    wrong = resolve_venue(2021,'Bahrain Grand Prix')
    assert not telemetry.layout(tmp_path,2021,'Mexico City Grand Prix',venue=wrong)['points']


def test_short_arc_or_zero_coordinates_are_not_a_track_outline(tmp_path):
    save(tmp_path,short=True)
    assert telemetry.layout(tmp_path,2021,'Mexico City Grand Prix')['status']=='data_missing'
    positions = pd.DataFrame({'SessionTime':pd.to_timedelta(np.linspace(100,160,121),unit='s'), 'X':0,'Y':0})
    lap = pd.Series({'LapStartTimeSeconds':100,'LapTimeSeconds':60})
    assert not telemetry._lap_points(telemetry._position_samples(positions),lap)


def test_future_outline_uses_latest_matching_layout_without_historical_times(tmp_path):
    save(tmp_path, year=2021)
    save(tmp_path, year=2025)
    found = telemetry.layout(tmp_path, 2026, 'Mexico City Grand Prix', 'PRE',
                             resolve_venue(2026, 'Mexico City Grand Prix'), allow_reference=True)
    assert found['status'] == 'available' and found['year'] == 2026
    assert found['geometry_year'] == 2025 and found['geometry_session'] == 'Q'
    assert found['reference_geometry'] and '2025' in found['message']
    assert not found['sectors'] and not found['fastestLap']
    assert all('sector' not in point for point in found['points'])


def test_outline_reference_requires_explicit_matching_layout_and_no_future_data(tmp_path):
    save(tmp_path, year=2025)
    venue = resolve_venue(2026, 'Mexico City Grand Prix')
    for target in ({**venue, 'layout_id': 'changed'}, {**venue, 'layout_id': None},
                   {**venue, 'venue_status': 'conflict'}):
        assert not telemetry.layout(tmp_path, 2026, 'Mexico City Grand Prix', 'PRE', target, allow_reference=True)['points']
    assert not telemetry.layout(tmp_path, 2024, 'Mexico City Grand Prix', 'PRE', venue, allow_reference=True)['points']


def test_same_weekend_geometry_precedes_reference_and_renamed_events_match_identity(tmp_path):
    save(tmp_path, year=2025)
    save(tmp_path, year=2026, session='FP1')
    venue = resolve_venue(2026, 'Mexico City Grand Prix')
    found = telemetry.layout(tmp_path, 2026, 'Mexico City Grand Prix', 'PRE', venue, allow_reference=True)
    assert found['session'] == 'FP1' and not found.get('reference_geometry')
    found = telemetry.layout(tmp_path, 2027, 'Renamed Mexico GP', 'PRE', venue, allow_reference=True)
    assert found['geometry_year'] == 2026 and found['geometry_event'] == 'Mexico City Grand Prix'


def test_damaged_archive_can_be_repaired_without_negative_cache(tmp_path):
    folder = save(tmp_path)
    manifest = library.read_json(folder/'session.json')
    name = next(name for name,info in manifest['files'].items() if info['table']=='position_44')
    file = folder/name
    original = file.read_bytes()
    damaged = bytearray(original)
    damaged[-1] ^= 1
    file.write_bytes(damaged)
    found = telemetry.layout(tmp_path,2021,'Mexico City Grand Prix')
    assert found['status']=='archive_error' and 'checksum' in found['message']
    file.write_bytes(original)
    assert telemetry.layout(tmp_path,2021,'Mexico City Grand Prix')['status']=='available'


def test_setup_api_reads_its_workspace_and_resolves_latest_event(tmp_path,monkeypatch):
    save(tmp_path)
    monkeypatch.chdir(tmp_path)
    api = web_backend.PortableWebApi()
    profile = resolve_venue(2021,'Mexico City Grand Prix') | {'event':'Mexico City Grand Prix'}
    monkeypatch.setattr(api,'setup_options',lambda *_:{'trackProfile':profile})
    found = api.setup_track(2021,'latest','PRE')
    assert found['event']=='Mexico City Grand Prix' and found['source']=='historical_library'
    with pytest.raises(ValueError,match='supported session'):
        api.setup_track(2021,'latest','INVALID')
