from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.pit_scenarios import assumed_plans, plan_lap_costs, elapsed_pit_costs
from src.qualifying_pace import fit_qualifying_pace, apply_qualifying_pace, sample_pace
from src.qualifying_features import attach_current_qualifying
from src.race_window_weather import scheduled_race_start, select_race_window, candidate_weather
from src.retirement_survival import attach_survival_risk, CAUSES
from src.retirement_progress import PROGRESS_COLUMNS
from src.run_config import load_app_config, config_to_dict
from src.simulate import simulate_races
from src.accuracy_benchmark import build_replay_inputs
from tests.test_accuracy_benchmark import races
from tests.test_simulate import _minimal_features
from tests.test_race_weather import responses, START, NOW
from src.race_weather import collect_race_weather


def test_race_window_ignores_q_observations_and_rejects_wrong_time_or_venue():
    get, _ = responses()
    report, raw = collect_race_weather(START, 1.29, 103.86, now=NOW, get=get)
    # This test exercises window selection with a historical mock capture.
    # Keep its completion after the mock request and before the fixture race,
    # independent of the wall clock on the machine running the suite.
    report['retrieved_at_utc'] = (pd.Timestamp(NOW)+pd.Timedelta(seconds=1)).isoformat()
    kwargs = dict(race_start=START, cutoff=report['retrieved_at_utc'], latitude=1.29, longitude=103.86)
    # Existing fixture has rain before the race, but a dry actual race window.
    summary = select_race_window(report, **kwargs)
    assert summary['rainfall_flag'] is False
    assert summary['weather_source'] == 'race_window_best_match_v1_experimental'
    assert summary['track_temp_avg'] is None and summary['rain_probability'] is None
    with pytest.raises(ValueError, match='available'):
        select_race_window(report, **{**kwargs, 'cutoff': NOW})
    with pytest.raises(ValueError, match='different'):
        select_race_window(report, **{**kwargs, 'race_start': '2026-10-12T12:00:00Z'})
    with pytest.raises(ValueError, match='coordinates'):
        select_race_window(report, **{**kwargs, 'longitude': 104.})
    report['scenarios'][0]['best_match']['simulation_usable'] = False
    unknown = select_race_window(report, **kwargs)
    assert unknown['rainfall_flag'] is None and unknown['dnf_factor'] == 1


def test_race_schedule_uses_labelled_utc_race_field_not_session_date():
    session = SimpleNamespace(event={'Session4': 'Qualifying', 'Session4DateUtc': '2026-10-10T12:00',
                                     'Session5': 'Race', 'Session5DateUtc': '2026-10-11T12:00'})
    assert scheduled_race_start(session) == '2026-10-11T12:00:00+00:00'
    with pytest.raises(ValueError, match='unavailable'):
        scheduled_race_start(SimpleNamespace(event={}))


def test_partial_pooling_pace_is_chronological_and_keeps_joint_uncertainty():
    data = races()
    metadata = dict(year=2024, round=4, event=data[3].event, session='Q')
    history = [(r.sessions['Q'], r.sessions['R'], dict(year=r.year, round=r.round, event=r.event)) for r in data[:3]]
    artifact = fit_qualifying_pace(history, metadata)
    assert artifact['training_races'] == [[2024, 1], [2024, 2], [2024, 3]]
    with pytest.raises(ValueError, match='cutoff'):
        fit_qualifying_pace(history + [(data[3].sessions['Q'], data[3].sessions['R'], metadata)], metadata)
    features, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=metadata)
    features = attach_current_qualifying(features, data[3].sessions['Q'], metadata)
    result = apply_qualifying_pace(features, artifact, metadata)
    samples = sample_pace(result, 1000, 42)
    assert np.isfinite(samples).all() and (samples >= 0).all()
    assert result.pace_posterior_sd_seconds.gt(0).all()
    assert np.std(samples[:, 1] - samples[:, 0]) > 0
    # Target outcomes are absent from the API and cannot influence a forecast.
    data[3].sessions['R'].results['Position'] = [2, 1]
    data[3].sessions['R'].laps['LapTimeSeconds'] += 50
    repeated = fit_qualifying_pace(history, metadata)
    assert artifact == repeated
    with pytest.raises(ValueError, match='target'):
        apply_qualifying_pace(features, artifact, {**metadata, 'round': 5})
    first, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=metadata,
                                      feature_variant='qualifying_partial_pooling_v1')
    assert first.race_pace_blend_version.eq('qualifying_partial_pooling_v1_experimental').all()


def test_pit_scenarios_change_race_time_and_avoid_double_degradation_penalty():
    features = _minimal_features()
    plans = [p for p in assumed_plans(features, 66) if len(p['pit_laps']) == 1]
    for plan in plans:
        plan['weight'] = 1.
    expensive = deepcopy(plans)
    for plan in expensive:
        plan['pit_loss_seconds'] += 20
    _, _, first = simulate_races(features, n_sims=100, seed=42, pit_plans=plans)
    _, _, second = simulate_races(features, n_sims=100, seed=42, pit_plans=expensive)
    no_flag = ~first.red_flag
    assert (second.projected_race_time_seconds - first.projected_race_time_seconds)[no_flag].to_numpy() == pytest.approx(20)
    changed = features.assign(tyre_deg_score=.15, long_run_pace_score=50., strategy_score=1.5)
    _, _, third = simulate_races(changed, n_sims=100, seed=42, pit_plans=plans)
    pd.testing.assert_series_equal(first.projected_race_time_seconds, third.projected_race_time_seconds)
    assert first.planned_pit_stops.eq(1).all()
    assert first.dnf.equals(second.dnf)
    costs = plan_lap_costs(plans[0], 66)
    assert np.isfinite(costs).all()
    labels = np.full((1, 4), plans[0]['name'], dtype=object)
    completed = np.array([[0, 10, 40, 66]])
    partial, stops = elapsed_pit_costs(features, plans, labels, completed, 66)
    assert partial[0, 0] == 0 and stops.tolist() == [[0, 0, 1, 1]]
    assert partial[0, 3] == pytest.approx(costs.sum())
    with pytest.raises(ValueError, match='weights'):
        simulate_races(features, n_sims=10, pit_plans=[{**p, 'weight': .5} for p in plans])


def test_survival_uses_censoring_and_preserves_unspecified_cause():
    features = _minimal_features()
    results = pd.DataFrame({'Abbreviation': ['RUS', 'HAM', 'ANT', 'LEC', 'UNK', 'DNS'],
        'TeamName': ['Mercedes', 'Ferrari', 'Mercedes', 'Ferrari', 'Other', 'Other'],
        'Status': ['Finished', 'Engine', 'Retired', '+1 Lap', 'Mystery', 'Did not start'],
        'Laps': [60, 5, 45, 59, 3, 0]})
    history = [(SimpleNamespace(results=results), dict(year=2025, round=1))]
    metadata = dict(year=2025, round=2)
    result = attach_survival_risk(features, history, metadata)
    assert result.retirement_known_observations.eq(4).all()
    assert result.retirement_progress_observations.eq(2).all()
    assert result[PROGRESS_COLUMNS].sum(axis=1).to_numpy() == pytest.approx(1)
    assert result[[f'retirement_{c}_prob' for c in CAUSES]].sum(axis=1).to_numpy() == pytest.approx(result.dnf_prob)
    _, _, samples = simulate_races(result, n_sims=3000, seed=42, retirement_classification='completed_laps_v1')
    rates = samples.groupby('Driver').dnf.mean().reindex(result.Driver).to_numpy()
    assert rates == pytest.approx(result.dnf_prob.to_numpy(), abs=.025)
    assert samples.loc[samples.dnf, 'completed_laps'].lt(66).all()
    with pytest.raises(ValueError, match='cutoff'):
        attach_survival_risk(features, history, dict(year=2025, round=1))


def test_candidates_are_opt_in_and_config_round_trips():
    config = load_app_config()
    # Earlier integration tests can load dotenv; candidate tests must explicitly
    # select local output rather than inherit a user's delivery preference.
    config = replace(config, outputs=replace(config.outputs, post_to_discord=False))
    assert config.model.race_engine == 'aggregate_legacy'
    assert config.model.weather_model == 'session_legacy'
    with pytest.raises(ValueError, match='artifact'):
        replace(config.model, pace_blend='qualifying_partial_pooling_v1')
    candidate = replace(config.model, pace_blend='qualifying_partial_pooling_v1',
        qualifying_pace_model_path='candidate.json', race_engine='pit_scenarios_v1',
        weather_model='race_window_v1', retirement_model='survival_dnf_v1')
    saved = config_to_dict(replace(config, model=candidate))
    assert saved['model']['qualifying_pace_model_path'] == 'candidate.json'
    with pytest.raises(ValueError, match='local output'):
        replace(config, model=candidate, outputs=replace(config.outputs, post_to_discord=True))
    with pytest.raises(ValueError, match='race_engine'):
        replace(config.model, race_engine='bad')


def test_explicit_archive_fills_whole_classification_without_mutating_cache(tmp_path):
    from src.qualifying_archive import read_qualifying_archive, with_qualifying_classification
    metadata = dict(year=2024, round=1, event='Example GP', session='Q')
    session = races()[0].sessions['Q']
    saved = session.results.assign(Year=2024, Round=1, Event='Example GP', Session='Q')
    path = tmp_path/'q.csv'; saved.to_csv(path, index=False)
    session.results['Position'] = np.nan
    archive = read_qualifying_archive(path)
    repaired = with_qualifying_classification(session, metadata, archive)
    assert repaired.results.Position.tolist() == [1, 2]
    assert session.results.Position.isna().all()
    assert repaired.results.ClassificationArchiveSHA256.str.len().eq(64).all()
    assert with_qualifying_classification(session, metadata, archive.iloc[:1]) is session
    pd.concat([saved,saved]).to_csv(path,index=False)
    with pytest.raises(ValueError, match='duplicate'):
        read_qualifying_archive(path)


def test_rank_only_pace_retains_unknown_timing_and_uses_explicit_reference():
    data = races(); metadata = dict(year=2024, round=4, event='Example GP', session='Q')
    history = [(r.sessions['Q'], r.sessions['R'], dict(year=r.year, round=r.round, event=r.event)) for r in data[:3]]
    model = fit_qualifying_pace(history, metadata)
    data[3].sessions['Q'].laps['Deleted'] = np.nan
    features, _, _ = build_replay_inputs(data[3].sessions['Q'], data[:3], metadata=metadata)
    features = attach_current_qualifying(features, data[3].sessions['Q'], metadata)
    assert features.q_best_lap.isna().all()
    output = apply_qualifying_pace(features, model, metadata)
    assert output.q_best_lap.isna().all()
    assert output.pace_reference_source.eq('existing_model_base_lap_estimate_missing_Q_timing').all()
    assert np.isfinite(sample_pace(output,100,42)).all()


def test_pace_artifact_rejects_stale_source(tmp_path):
    import hashlib, json
    from pathlib import Path
    from src.qualifying_pace import load_qualifying_pace
    artifact = {'source_sha256': {'src/qualifying_pace.py': hashlib.sha256(
        Path('src/qualifying_pace.py').read_bytes()).hexdigest()}}
    path = tmp_path/'model.json';path.write_text(json.dumps(artifact))
    assert load_qualifying_pace(path) == artifact
    artifact['source_sha256']['src/qualifying_pace.py'] = 'stale'
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match='stale'):
        load_qualifying_pace(path)


def test_replay_weather_never_lazy_loads_missing_session_data():
    from src.weather import summarize_weather
    class Missing:
        @property
        def weather_data(self):
            raise RuntimeError('not loaded')
        def load(self, **kwargs):
            pytest.fail('Replay must not load optional weather')
    summary = summarize_weather(Missing(), use_forecast=False, allow_load=False)
    assert summary['rainfall_flag'] is None
