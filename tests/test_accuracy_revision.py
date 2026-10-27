from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.qualifying_features import build_qualifying_features, attach_current_qualifying
from src.retirement_progress import (PROGRESS_COLUMNS, attach_retirement_progress,
                                     sample_completed_laps, distance_order)
from src.simulate import simulate_races
from src.performance import add_performance_profile
from src.run_config import ModelSettings, config_to_dict, load_app_config
from src.accuracy_benchmark import build_replay_inputs
from tests.test_accuracy_benchmark import races
from tests.test_simulate import _minimal_features
from tests.test_historical_model import _write_fixture
from src.historical_model import build_historical_feature_table


def test_official_q_order_survives_faster_eliminated_lap_and_invalid_timing(tmp_path):
    _write_fixture(tmp_path)
    results = pd.read_csv(tmp_path/'fastf1_race_results.csv')
    laps = pd.read_csv(tmp_path/'fastf1_laps.csv')
    # AAA set the fastest overall lap, but BBB won the final qualifying segment.
    results.loc[results.Session.eq('Q') & results.Abbreviation.eq('AAA'), 'Position'] = 2
    results.loc[results.Session.eq('Q') & results.Abbreviation.eq('BBB'), 'Position'] = 1
    results.to_csv(tmp_path/'fastf1_race_results.csv', index=False)
    laps.loc[laps.Driver.eq('CCC'), 'LapTimeSeconds'] = np.nan
    laps.to_csv(tmp_path/'fastf1_laps.csv', index=False)
    table = build_historical_feature_table(tmp_path)
    assert table.loc[table.DriverCode.eq('AAA'), 'q_rank'].eq(2).all()
    assert table.loc[table.DriverCode.eq('BBB'), 'q_rank'].eq(1).all()
    assert table.loc[table.DriverCode.eq('CCC'), 'q_rank'].eq(3).all()
    assert table.loc[table.DriverCode.eq('CCC'), 'q_best_lap'].isna().all()
    event = results.loc[results.Year.eq(2024) & results.Round.eq(1)]
    event_laps = laps.loc[laps.Year.eq(2024) & laps.Round.eq(1)]
    session = SimpleNamespace(results=event.loc[event.Session.eq('Q')], laps=event_laps)
    live = attach_current_qualifying(pd.DataFrame({'Driver': ['AAA','BBB','CCC','DDD']}), session,
        {'year': 2024, 'round': 1, 'event': 'Event 1', 'session': 'Q'})
    archived = build_qualifying_features(event_laps, event)
    pd.testing.assert_series_equal(live.q_rank, archived.q_rank, check_names=False)
    assert live.q_best_lap.equals(archived.q_best_lap)
    no_q = results.loc[results.Session.eq('R')]
    no_q.to_csv(tmp_path/'fastf1_race_results.csv', index=False)
    assert 'q_rank' not in build_historical_feature_table(tmp_path)


def test_timing_uses_only_valid_laps_and_missing_classification_never_gets_invented():
    common = {'Year': 2025, 'Round': 1, 'Event': 'GP', 'Session': 'Q'}
    results = pd.DataFrame({**common, 'Abbreviation': ['A','B'], 'Position': [1,2]})
    laps = pd.DataFrame({**common, 'Driver': ['A'] * 4 + ['B'], 'LapTimeSeconds': [60,61,62,80,81],
        'Deleted': [True,False,False,False,False], 'IsAccurate': [True,False,True,True,True],
        'TrackStatus': ['1','1','2','1','1']})
    assert build_qualifying_features(laps, results).q_best_lap.tolist() == [80,81]
    assert build_qualifying_features(laps, results.assign(Position=[1,1])).empty
    with pytest.raises(ValueError, match='Duplicate'):
        build_qualifying_features(laps, pd.concat([results,results]))


def test_live_timedeltas_and_archive_seconds_share_identical_q_predictors():
    from src.lap_details import extract_lap_details
    raw = pd.DataFrame({'Driver': ['A','A','B'], 'LapTime': pd.to_timedelta([60,80,81],unit='s'),
        'Sector1Time': pd.to_timedelta([20,26,27],unit='s'), 'IsAccurate': True,
        'Deleted': False, 'TrackStatus': '1', 'PitInTime': pd.to_timedelta([10,None,None],unit='s'),
        'PitOutTime': pd.NaT})
    results = pd.DataFrame({'Abbreviation': ['A','B'], 'Position': [2,1]})
    session = SimpleNamespace(laps=raw, results=results)
    metadata = {'year': 2025, 'round': 1, 'event': 'GP', 'session': 'Q'}
    live = attach_current_qualifying(pd.DataFrame({'Driver': ['A','B']}), session, metadata)
    archived = build_qualifying_features(extract_lap_details(session, metadata),
        results.assign(Year=2025, Round=1, Event='GP', Session='Q'))
    for column in ['q_rank', 'q_best_lap', 'q_best_s1', 'q_gap_to_best']:
        pd.testing.assert_series_equal(live[column], archived[column])


def test_configured_single_pass_matches_benchmark_and_is_independent_of_model_blend():
    data = races()
    meta = dict(year=2024, round=4, event=data[3].event, session='Q')
    features, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=meta)
    current = pd.DataFrame({'Driver': features.Driver})
    first = add_performance_profile(features, current, current_session_type='Q', metadata=meta,
                                     pace_blend='single_pace_blend_v1')
    distorted = features.assign(model_pace=[99., 0.], relative_pace=[99., 0.])
    second = add_performance_profile(distorted, current, current_session_type='Q', metadata=meta,
                                      pace_blend='single_pace_blend_v1')
    pd.testing.assert_series_equal(first.race_pace_score, second.race_pace_score)
    benchmark, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=meta,
                                          feature_variant='single_pace_blend_v1')
    assert first.race_pace_score.tolist() == pytest.approx(benchmark.race_pace_score.tolist())
    assert first.reliability_score.equals(second.reliability_score)
    longer, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=meta, n_baseline_races=3)
    assert longer.baseline_rounds.eq(3).all()


def test_retirement_distance_prior_respects_cutoff_and_excludes_unknown_status():
    session = SimpleNamespace(results=pd.DataFrame({'Abbreviation': ['A','B','C','D'],
        'Status': ['Finished','Engine','Mystery','Did not start'], 'Laps': [50,5,1,0]}))
    features = _minimal_features()
    history = [(session, {'year': 2025, 'round': 1})]
    meta = {'year': 2025, 'round': 2}
    output = attach_retirement_progress(features, history, meta)
    assert output.retirement_progress_observations.eq(1).all()
    assert output[PROGRESS_COLUMNS].sum(axis=1).tolist() == pytest.approx([1.] * len(features))
    assert output.retirement_progress_bin_1.gt(output.retirement_progress_bin_0).all()
    with pytest.raises(ValueError, match='cutoff'):
        attach_retirement_progress(features, history, {'year': 2025, 'round': 1})
    fallback = attach_retirement_progress(features, [], meta)
    assert fallback[PROGRESS_COLUMNS].eq(.1).all().all()


def test_retirement_classification_orders_distance_and_preserves_occurrence_draws():
    features = attach_retirement_progress(_minimal_features(), [], {'year': 2025, 'round': 1})
    features['reliability_score'] = .25
    legacy = simulate_races(features, n_sims=2000, seed=123)
    explicit = simulate_races(features, n_sims=2000, seed=123, retirement_classification='legacy')
    for before, after in zip(legacy, explicit):
        pd.testing.assert_frame_equal(before, after)
    revised = simulate_races(features, n_sims=2000, seed=123, retirement_classification='completed_laps_v1')
    old, raw = legacy[2], revised[2]
    assert old.dnf.equals(raw.dnf)
    assert old.projected_race_time_seconds.equals(raw.projected_race_time_seconds)
    assert raw.loc[~raw.dnf, 'completed_laps'].eq(66).all()
    assert raw.loc[raw.dnf, 'completed_laps'].lt(66).all()
    assert raw.loc[~raw.classified, 'points'].eq(0).all()
    assert raw.loc[raw.dnf & raw.classified, 'points'].gt(0).any()
    assert raw.dnf.mean() == pytest.approx(.25, abs=.02)
    for _, group in raw.groupby('sim_id'):
        order = group.sort_values('finish_position')
        assert order.completed_laps.is_monotonic_decreasing
        assert sorted(order.finish_position) == [1,2,3,4]
    # Later retirement beats earlier retirement despite a much slower car.
    assert distance_order(np.array([[5000.,100.,6000.]]), np.array([[60,3,66]])).tolist() == [[2,0,1]]
    with pytest.raises(ValueError, match='requires prior'):
        sample_completed_laps(_minimal_features(), np.ones((1,4), dtype=bool), 66, np.random.default_rng(1))


def test_model_options_defaults_and_round_trip(tmp_path):
    import json
    path = tmp_path/'config.json'
    path.write_text(json.dumps({'model': {'pace_blend': 'single_pace_blend_v1',
        'retirement_model': 'retirement_progress_v1', 'retirement_history_races': 20}}))
    config = load_app_config(path)
    saved = config_to_dict(config)
    assert saved['model']['pace_blend'] == 'single_pace_blend_v1'
    assert saved['model']['retirement_history_races'] == 20
    with pytest.raises(ValueError, match='separately'):
        replace(config.model, use_stint_pace=True)
    with pytest.raises(ValueError, match='retirement_model'):
        replace(config.model, retirement_model='unknown')
    path.write_text('{}')
    default = load_app_config(path)
    assert default.model.pace_blend == 'legacy'
    # Promoted 27 October 2026 (docs/season-grid-retirements.md); still allowed to post.
    assert default.model.retirement_model == 'season_grid_dnf_v1'
    assert default.run.n_baseline_races == 10
    replace(default, outputs=replace(default.outputs, post_to_discord=True))
