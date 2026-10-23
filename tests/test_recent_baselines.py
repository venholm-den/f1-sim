from types import SimpleNamespace

import pandas as pd
import pytest

from src import collect, recent_baselines as baselines


def schedule():
    return pd.DataFrame({'RoundNumber': [0, 1, 2, 3, 4],
        'EventName': ['Testing', 'A GP', 'B GP', 'Target GP', 'Future GP'],
        'Session5': ['Race'] * 5,
        'Session5DateUtc': ['2026-02-10T12:00Z', '2026-03-01T12:00Z', '2026-03-08T12:00Z',
                            '2026-03-15T12:00Z', '2026-03-22T12:00Z']})


def session(states=None, positions=None):
    return SimpleNamespace(event={}, session_status=pd.DataFrame({'Status': states or ['Started', 'Finished', 'Ends']}),
        results=pd.DataFrame({'Abbreviation': ['A', 'B'], 'TeamName': ['T', 'T'],
                              'Position': positions or [1, 2], 'Status': ['Finished', 'Retired']}),
        laps=pd.DataFrame({'Driver': ['A', 'B'], 'LapTime': [pd.Timedelta(seconds=90)] * 2}))


def features():
    return pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T'], 'relative_pace': [0., 1.],
        'race_pace': [90., 91.], 'best_lap': [89., 90.], 'lap_std': [1., 1.], 'deg_per_lap': [0., .1],
        'clean_laps': [10, 3], 'raw_laps': [15, 10], 'dnf_prob': [.05, .05]})


def test_plan_uses_prior_same_season_rounds_and_allows_completion_time():
    result = baselines.plan_races(schedule(), 2026, 3, '2026-03-14T00:00Z', 8)
    assert [row['round'] for row in result] == [2, 1]
    assert {row['year'] for row in result} == {2026}
    early = baselines.plan_races(schedule(), 2026, 3, '2026-03-08T18:00Z', 8)
    assert [row['round'] for row in early] == [1]
    assert baselines.plan_races(schedule(), 2026, 1, '2026-03-14T00:00Z', 8) == []


@pytest.mark.parametrize('count', [0, 25])
def test_plan_rejects_invalid_count(count):
    with pytest.raises(ValueError, match='1-24'):
        baselines.plan_races(schedule(), 2026, 3, '2026-03-14T00:00Z', count)


@pytest.mark.parametrize('states', [['Started'], ['Started', 'Aborted'], ['Finished', 'Started']])
def test_completion_gate_rejects_live_or_resumed_race(states):
    with pytest.raises(ValueError, match='finished'):
        collect.completed_race_quality(session(states=states))


@pytest.mark.parametrize('positions', [[1, None], [1, 1], [0, 2], [1.5, 2]])
def test_completion_gate_rejects_partial_classification(positions):
    with pytest.raises(ValueError, match='incomplete'):
        collect.completed_race_quality(session(positions=positions))


def test_archive_accepts_unranked_nonparticipant_but_never_a_missing_starter():
    sample = session(positions=[1, None])
    sample.results.loc[1, 'Status'] = 'Withdrew'
    sample.laps = sample.laps.iloc[:1]
    assert collect.completed_race_quality(sample, archive=True)['unranked_nonparticipants'] == 1
    with pytest.raises(ValueError, match='incomplete'):
        collect.completed_race_quality(sample)
    sample.results.loc[1, 'Status'] = 'Engine'
    with pytest.raises(ValueError, match='incomplete'):
        collect.completed_race_quality(sample, archive=True)


def test_archive_keeps_aborted_classification_explicitly_out_of_training():
    sample = session(states=['Started', 'Aborted', 'Finalised', 'Ends'])
    quality = collect.completed_race_quality(sample, archive=True)
    assert quality['aborted_classified'] and not quality['training_eligible']
    with pytest.raises(ValueError, match='finished'):
        collect.completed_race_quality(sample)


def test_missing_pace_is_reported_without_dropping_driver_or_inventing_sample():
    result = baselines.driver_coverage(session().results, features().head(1), 2026, 2, session().laps)
    missing = result[result.Driver.eq('B')].iloc[0]
    assert not missing.pace_available
    assert pd.isna(missing.relative_pace) and missing.clean_laps == 0 and missing.raw_laps == 1
    assert len(result) == 2


def test_window_recency_weights_coverage_and_current_roster():
    f = pd.concat([features().assign(source_year=2026, source_round=r) for r in (1, 2, 3)])
    f.loc[f.source_round.eq(3) & f.Driver.eq('A'), 'relative_pace'] = 2
    coverage = pd.concat([baselines.driver_coverage(session().results, features(), 2026, r) for r in (1, 2, 3)])
    summaries, counts = baselines.baseline_windows(f, coverage, ['A'])
    assert summaries[2].Driver.tolist() == ['A']  # Exclude historical substitute B.
    assert summaries[2].baseline_relative_pace.iloc[0] == pytest.approx(2 / (1 + 1 / 1.45))
    assert summaries[2].baseline_rounds.iloc[0] == 2
    assert counts[counts.window_requested.eq(8)].races_in_window.iloc[0] == 3


def test_live_loader_skips_unfinished_prior_race_and_falls_back_chronologically(monkeypatch):
    monkeypatch.setattr(collect, 'enable_fastf1_cache', lambda: None)
    monkeypatch.setattr(collect, '_normalise_schedule', lambda year: schedule() if year == 2026 else schedule().iloc[:0])
    monkeypatch.setattr(collect, '_load_fastf1_session', lambda year, round_number, code:
                        session(states=['Started']) if round_number == 2 else session())
    loaded = collect.load_recent_race_sessions(2026, 3, count=1)
    assert len(loaded) == 1 and loaded[0][1]['round'] == 1


def test_builder_rejects_future_cutoff_and_does_not_create_output(tmp_path):
    with pytest.raises(ValueError, match='future'):
        baselines.build_recent_baselines(2026, 3, tmp_path / 'data', cutoff='2099-01-01T00:00Z', schedule=schedule())
    assert not (tmp_path / 'data').exists()


def test_builder_writes_hashes_and_protects_existing_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(baselines, 'enable_fastf1_cache', lambda: None)
    monkeypatch.setattr(baselines, 'build_driver_features', lambda laps: features())
    monkeypatch.setattr(baselines, 'summarize_weather', lambda *a, **k: {'weather_source': 'neutral_default'})
    monkeypatch.setattr(baselines, 'extract_lap_details', lambda s, m: s.laps.assign(Year=m['year'], Round=m['round']))
    monkeypatch.setattr(baselines, '_extract_race_control', lambda *a: pd.DataFrame())
    target = tmp_path / 'build'
    report = baselines.build_recent_baselines(2026, 3, target, cutoff='2026-03-14T00:00Z',
                                             schedule=schedule(), load=lambda *a: session())
    assert report['completed_races'] == 2 and report['race_rounds'] == [1, 2]
    assert report['applied_live_baseline_count_change'] is False
    assert 'driver_window_coverage.csv' in report['files']
    original = (target / 'report.json').read_bytes()
    with pytest.raises(FileExistsError):
        baselines.build_recent_baselines(2026, 3, target, cutoff='2026-03-14T00:00Z', schedule=schedule())
    assert (target / 'report.json').read_bytes() == original
