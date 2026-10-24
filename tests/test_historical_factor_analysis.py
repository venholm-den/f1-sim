from copy import deepcopy
import hashlib
import json

import pandas as pd
import pytest

from scripts.analyse_historical_factors import build_features, clean_laps, load_archive, evaluate
from scripts.analyse_factor_followups import stable_order, stage_checks


def fixture_sessions():
    sessions = {}
    for round_ in (1, 2, 3):
        for code in ('Q', 'R'):
            meta = dict(year=2023, round=round_, event='Example Grand Prix',
                        session=code, venue={'layout_id': 'example'})
            rows = []
            for i, driver in enumerate(('A', 'B', 'C', 'D')):
                for lap in range(1, 7):
                    rows.append(dict(Year=2023, Round=round_, Event=meta['event'], Session=code,
                        Driver=driver, LapNumber=lap, LapTimeSeconds=90+i+.01*lap,
                        Sector1Seconds=30+i*.3, Sector2Seconds=30+i*.3,
                        Sector3Seconds=30+i*.4+.01*lap, SpeedST=300+i,
                        LapStartUtc=f'2023-01-{round_:02}T12:{lap:02}:00Z',
                        LapStartTimeSeconds=lap*100., Stint=1, Compound='MEDIUM', TyreLife=lap,
                        IsAccurate=True, CleanPushLap=True, Deleted=False, PitIn=False,
                        PitOut=False, TrackStatus='1'))
            results = pd.DataFrame(dict(Year=2023, Round=round_, Event=meta['event'], Session=code,
                Abbreviation=list('ABCD'), TeamName=['T1', 'T1', 'T2', 'T2'],
                DriverNumber=['1', '2', '3', '4'], Position=[1, 2, 3, 4],
                GridPosition=[1, 2, 3, 4], Status='Finished'))
            sessions[2023, round_, code] = dict(meta=meta, results=results, laps=pd.DataFrame(rows),
                track_status=pd.DataFrame({'Status': ['1']}))
    return sessions


def empty_telemetry():
    return pd.DataFrame(columns=['Year', 'Round', 'Session', 'DriverNumber'])


def test_target_and_future_outcomes_cannot_change_earlier_predictors():
    original = fixture_sessions()
    first, _, _ = build_features(original, empty_telemetry())
    changed = deepcopy(original)
    for round_ in (2, 3):
        changed[2023, round_, 'R']['results']['Position'] = [4, 3, 2, 1]
    second, _, _ = build_features(changed, empty_telemetry())
    columns = ['prior_driver_form', 'prior_driver_grid_residual', 'prior_race_pace',
               'prior_team_form', 'prior_driver_dnf', 'prior_layout_grid_error']
    pd.testing.assert_frame_equal(first.loc[first.Round.le(2), columns],
                                  second.loc[second.Round.le(2), columns])
    assert first.loc[first.Round.eq(1), 'prior_driver_form'].isna().all()
    assert first.loc[first.Round.eq(2), 'prior_driver_form'].notna().all()


def test_post_qualifying_practice_is_not_available_to_q_predictor():
    sessions = fixture_sessions()
    practice = deepcopy(sessions[2023, 2, 'Q'])
    practice['laps']['LapStartUtc'] = '2023-01-02T14:00:00Z'
    sessions[2023, 2, 'FP2'] = practice
    frame, _, _ = build_features(sessions, empty_telemetry())
    assert 'fp2_pace' not in frame
    sessions[2023, 2, 'FP2']['laps']['LapStartUtc'] = '2023-01-02T09:00:00Z'
    frame, _, _ = build_features(sessions, empty_telemetry())
    assert frame.loc[frame.Round.eq(2), 'fp2_pace'].notna().all()


def test_clean_laps_reject_mixed_flags_deleted_and_pit_laps():
    frame = pd.DataFrame(dict(IsAccurate=True, TrackStatus=['1', '14', '1', '1'],
        Deleted=[False, False, True, False], PitIn=[False, False, False, True], LapTimeSeconds=90.))
    assert list(clean_laps(frame).index) == [0]


def test_missing_q_utc_times_do_not_fabricate_practice_availability():
    sessions = fixture_sessions()
    sessions[2023, 2, 'FP2'] = deepcopy(sessions[2023, 2, 'Q'])
    sessions[2023, 2, 'Q']['laps'] = sessions[2023, 2, 'Q']['laps'].drop(columns='LapStartUtc')
    frame, _, _ = build_features(sessions, empty_telemetry())
    assert frame.Round.eq(2).sum() == 4
    assert 'fp2_pace' not in frame


def test_control_message_utc_can_establish_old_archive_practice_order():
    sessions=fixture_sessions()
    sessions[2023,2,'FP2']=deepcopy(sessions[2023,2,'Q'])
    for code in ('Q','FP2'):
        sessions[2023,2,code]['laps']=sessions[2023,2,code]['laps'].drop(columns='LapStartUtc')
    sessions[2023,2,'Q']['race_control_messages']=pd.DataFrame({'Time':['2023-01-02T12:00:00Z']})
    sessions[2023,2,'FP2']['race_control_messages']=pd.DataFrame({'Time':['2023-01-02T09:00:00Z','2023-01-02T09:30:00Z']})
    frame,_,_=build_features(sessions,empty_telemetry())
    assert frame.loc[frame.Round.eq(2),'fp2_pace'].notna().all()
    assert frame.loc[frame.Round.eq(2),'timing_q_source'].eq('control_message_utc').all()
    sessions[2023,2,'FP2']['race_control_messages']=pd.DataFrame({'Time':['2023-01-02T14:00:00Z']})
    frame,_,_=build_features(sessions,empty_telemetry())
    assert 'fp2_pace' not in frame


def test_telemetry_summary_reuse_rejects_tampering(tmp_path):
    cache = tmp_path/'cache'; cache.mkdir()
    (cache/'telemetry_summary.csv').write_text('changed')
    (cache/'telemetry_cache.json').write_text(json.dumps({'parser_version':1,
        'files':{'telemetry_summary.csv':'not_the_original_checksum'}}))
    with pytest.raises(ValueError, match='checksum'):
        load_archive(tmp_path, tmp_path/'out', cache)


def test_summary_cache_never_bypasses_raw_file_integrity(tmp_path):
    root = tmp_path/'data/historical_library/2023/detailed/example'
    root.mkdir(parents=True)
    raw = root/'laps.csv'; raw.write_text('original')
    meta = dict(year=2023, round=1, event='Example', session='Q', status='complete',
                files={'laps.csv':{'table':'laps','bytes':raw.stat().st_size,
                                  'sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}})
    pointer=root/'session.json';pointer.write_text(json.dumps(meta))
    cache=tmp_path/'cache';cache.mkdir()
    pd.DataFrame([dict(manifest=str(pointer),manifest_sha256=hashlib.sha256(pointer.read_bytes()).hexdigest(),
                       verified=True)]).to_csv(cache/'session_inventory.csv',index=False)
    pd.DataFrame(columns=['Year','Round','Session','DriverNumber']).to_csv(cache/'telemetry_summary.csv',index=False)
    manifest={'parser_version':1,'files':{name:hashlib.sha256((cache/name).read_bytes()).hexdigest()
        for name in ['session_inventory.csv','telemetry_summary.csv']}}
    (cache/'telemetry_cache.json').write_text(json.dumps(manifest))
    raw.write_text('tampered')
    out=tmp_path/'out';out.mkdir()
    sessions,_,_,failures,_,_=load_archive(tmp_path,out,cache)
    assert not sessions and len(failures)==1
    assert 'integrity failure' in failures[0]['reason']


def test_rank_ties_use_driver_identity_instead_of_result_row_order():
    assert list(stable_order([.5,.5,.5],['C','A','B'])) == [3,1,2]


def test_earlier_stage_predictions_do_not_use_later_qualifying_rank():
    source,_,_=build_features(fixture_sessions(),empty_telemetry())
    frame=pd.concat([source,source.assign(Year=2024)],ignore_index=True)
    first=stage_checks(frame)
    changed=frame.copy()
    changed.loc[changed.Year.eq(2024),'q_rank']=1000
    changed.loc[changed.Year.eq(2024),'q_percentile']=1000
    pd.testing.assert_frame_equal(first,stage_checks(changed))


def test_scoring_refuses_outcome_columns_as_factors(tmp_path):
    frame,_,_=build_features(fixture_sessions(),empty_telemetry())
    with pytest.raises(ValueError,match='cannot be predictors'):
        evaluate(frame,tmp_path,groups={'leaked':['actual_finish']})
