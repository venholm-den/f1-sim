from types import SimpleNamespace

import pandas as pd
import pytest

from src.app_services.shadow_candidates import prepare_candidate, read_history, write_history


def test_history_roundtrip_filters_target_and_rejects_late_packet(tmp_path):
    path = tmp_path/'history.json.gz'
    session = SimpleNamespace(laps=pd.DataFrame({'Driver':['AAA'], 'LapTime':[pd.Timedelta(seconds=90)],
        'LapStartDate':[pd.Timestamp('2026-01-01')]}), results=pd.DataFrame({'Status':['Finished']}),
        weather_data=pd.DataFrame({'Rainfall':[False]}))
    rows = [(dict(year=2026, round=r, event='GP'), {'Q':session,'R':session}) for r in (1,2,3)]
    write_history(path, rows, captured_at='2026-01-03T00:00:00Z')
    context = dict(year=2026, round=3, data_cutoff_utc='2026-01-04T00:00:00Z')
    loaded = read_history(path, context)
    assert [m['round'] for m,_ in loaded] == [1,2]
    pd.testing.assert_frame_equal(loaded[0][1]['R'].laps, session.laps)
    assert not loaded[0][1]['R'].weather_data.Rainfall.iloc[0]
    with pytest.raises(ValueError, match='cutoff'):
        read_history(path, {**context, 'data_cutoff_utc':'2026-01-02T00:00:00Z'})
    with pytest.raises(FileExistsError):
        write_history(path, rows, captured_at='2026-01-03T00:00:00Z')


@pytest.mark.parametrize('name',['pit_scenarios_v1','agent_laps_v1'])
def test_dry_candidates_fail_closed_on_rain(name):
    with pytest.raises(ValueError, match='Dry-only'):
        prepare_candidate(name, pd.DataFrame(), {'weather_modifiers':{'rainfall_flag':True}}, {'year':2026})


def test_q_candidate_does_not_substitute_a_pre_qualifying_grid():
    with pytest.raises(ValueError, match='Q stage'):
        prepare_candidate('qualifying_partial_pooling_v1', pd.DataFrame(), {}, {'session':'FP2'})


def test_agent_protocol_explicitly_resolves_settings_and_pit_plans():
    frame = pd.DataFrame({'Driver':['AAA','BBB'],'estimated_race_laps':[10,10]})
    changed, options, evidence = prepare_candidate('agent_laps_v1', frame,
        {'overtaking_difficulty':.8}, {'year':2026})
    assert options['agent_settings']['step_seconds'] == 1.
    assert options['agent_settings']['passability'] == pytest.approx(.2)
    assert options['agent_settings']['season_year'] == 2026
    assert options['agent_settings']['overtaking_aid'] == 'none'
    assert len(options['pit_plans']) == 4
    pd.testing.assert_frame_equal(frame, changed)


def test_explicit_trial_history_cutoff_keeps_older_source_feature_cutoff(tmp_path):
    path = tmp_path/'history.json.gz'
    session = SimpleNamespace(laps=pd.DataFrame(), results=pd.DataFrame(), weather_data=pd.DataFrame())
    write_history(path, [(dict(year=2026, round=1, event='GP'), {'R':session})], captured_at='2026-01-03T00:00:00Z')
    context = dict(year=2026, round=2, data_cutoff_utc='2026-01-02T00:00:00Z', history_cutoff_utc='2026-01-04T00:00:00Z')
    assert len(read_history(path, context)) == 1
    with pytest.raises(ValueError, match='cutoff'):
        read_history(path, {**context, 'history_cutoff_utc':'2026-01-02T00:00:00Z'})


def test_neutralisation_arm_uses_portable_track_labels_and_incremental_baseline(tmp_path):
    from tests.test_neutralisation import labelled_session
    from src.app_services.shadow_candidates import BASELINES
    path = tmp_path/'history.json.gz'
    session = labelled_session(); session.results = pd.DataFrame()
    write_history(path, [(dict(year=2025, round=1), {'R': session})], captured_at='2026-01-01T00:00:00Z')
    frame = pd.DataFrame({'Driver': ['AAA'], 'estimated_race_laps': [20]})
    _, options, evidence = prepare_candidate('agent_neutralisation_v1', frame, {},
        dict(year=2026, round=1, data_cutoff_utc='2026-01-02T00:00:00Z'), path)
    assert options['agent_settings']['neutralisation_model']['schedules'][0]['events'][0]['kind'] == 'SC'
    assert BASELINES['agent_neutralisation_v1'] == 'agent_laps_v1'
    assert evidence['neutralisation_model']['target'] == [2026, 1]
