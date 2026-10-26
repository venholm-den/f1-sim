import json
from unittest.mock import Mock

import pandas as pd
import pytest

from src.app_services import archive_replay as replay, historical_library as library, simulation_jobs
from src.app_services.accuracy import accuracy_state

DRIVERS = ['AAA', 'BBB', 'CCC', 'DDD']


def archive(root, year=2025, rounds=4, q_rounds=None):
    config = library.options({'years': [year], 'sessions': ['Q', 'R']})
    for number in range(1, rounds + 1):
        for session in ('Q', 'R'):
            if session == 'Q' and q_rounds is not None and number not in q_rounds:
                continue
            task = {'year': year, 'round': number, 'event': f'GP {number}', 'session': session}
            laps = pd.DataFrame({'Driver': DRIVERS * 2, 'LapNumber': [1] * 4 + [2, 2, 2, 2 if session == 'Q' else 1],
                                 'LapTimeSeconds': [80, 81, 82, 83] * 2, 'TrackStatus': [1.0] * 8})
            if session == 'Q':
                results = pd.DataFrame({'Abbreviation': DRIVERS, 'Position': [1, 2, 3, 4]})
            else:
                results = pd.DataFrame({'Abbreviation': DRIVERS, 'Position': [2, 1, 3, 4],
                                        'ClassifiedPosition': ['2', '1', '3', '4'],
                                        'Status': ['Finished', 'Finished', 'Lapped', 'Finished']})
            library.save_partition(library.library_root(root) / str(year) / 'detailed' / f'{number}_{session}',
                                   task, config, {'laps': laps, 'results': results}, {}, [])


def test_options_need_downloaded_seasons(tmp_path):
    archive(tmp_path)
    assert replay.options(tmp_path, {'years': [2025]}) == {'years': [2025], 'n_sims': 2000, 'seed': 42}
    with pytest.raises(ValueError, match='Download detailed sessions for 2024'):
        replay.options(tmp_path, {'years': [2024]})
    with pytest.raises(ValueError, match='10,000'):
        replay.options(tmp_path, {'years': [2025], 'n_sims': 50000})


def test_load_reads_previous_season_for_history_and_lists_unreadable_sessions(tmp_path):
    archive(tmp_path, 2024, rounds=2)
    archive(tmp_path, 2025, rounds=3)
    pointer = library.library_root(tmp_path) / '2025/detailed/3_Q/session.json'
    saved = json.loads(pointer.read_text())
    saved['files'] = {name.replace('/', '\\'): info for name, info in saved['files'].items()}
    pointer.write_text(json.dumps(saved))
    damaged = library.library_root(tmp_path) / '2025/detailed/2_Q'
    (damaged / next(iter(library.read_json(damaged / 'session.json')['files']))).write_text('x')
    races, skipped = replay.load(tmp_path, [2025])
    assert [race.key for race in races] == [(2024, 1), (2024, 2), (2025, 1), (2025, 2), (2025, 3)]
    # Windows-style manifest paths still read; a damaged file is listed, not raised.
    assert 'Q' in races[-1].sessions and 'Q' not in races[-2].sessions
    assert skipped == [{'year': 2025, 'round': 2, 'event': 'GP 2', 'reason': 'Qualifying session files missing or damaged'}]
    assert races[0].sessions['R'].laps.TrackStatus.iloc[0] == '1'


def test_actual_outcome_counts_lapped_cars_that_stopped_early_as_retired(tmp_path):
    archive(tmp_path, rounds=1)
    races, _ = replay.load(tmp_path, [2025])
    outcome = replay.actual_outcome(races[0].sessions['R']).set_index('Driver')
    assert outcome.actual_dnf.tolist() == [False, False, False, False]
    session = races[0].sessions['R']
    session.laps = pd.concat([session.laps, pd.DataFrame({'Driver': ['AAA'] * 5, 'LapNumber': [3, 4, 5, 6, 7]})])
    assert replay.actual_outcome(session).set_index('Driver').actual_dnf.tolist() == [False, True, True, True]


def test_score_matches_the_official_measures():
    comparison = pd.DataFrame({'Driver': DRIVERS, 'avg_finish': [1.5, 2, 3, 4], 'actual_position': [1, 2, 3, 4],
                               'grid_position': [2, 1, 3, 4], 'win_chance': [.5, .5, 0, 0],
                               'podium_chance': [1, 1, 1, 0], 'points_chance': [1] * 4, 'dnf_chance': [.1] * 4,
                               'actual_dnf': [False, False, False, True]})
    row = replay.score(comparison)
    assert row['finish_mae'] == pytest.approx(.125) and row['grid_finish_mae'] == .5
    assert row['finishers_finish_mae'] == 0 and row['retirements'] == 1
    assert row['expected_retirements'] == pytest.approx(.4)
    assert row['win_chance_brier'] == pytest.approx(.125)
    assert row['podium_chance_skill'] == 1


def test_run_scores_races_with_history_and_explains_the_rest(tmp_path, monkeypatch):
    archive(tmp_path, rounds=4, q_rounds={1, 2, 4})
    calls = []

    def fake(race, previous, n_sims, seed):
        calls.append((race.key, [r.key for r in previous], n_sims, seed))
        return {'year': race.year, 'round': race.round, 'event': race.event, 'session': 'Q', 'drivers': 4,
                'finish_mae': 2.0, 'finishers_finish_mae': 1.0, 'grid_finish_mae': 1.5, 'spearman': .5,
                'retirements': 1, 'expected_retirements': .2, 'win_chance_skill': .1,
                'podium_chance_skill': .2, 'points_chance_skill': .3}
    monkeypatch.setattr(replay, 'replay_race', fake)
    folder = tmp_path / 'job'
    folder.mkdir()
    result = replay.run(tmp_path, folder, {'years': [2025], 'n_sims': 300, 'seed': 42})
    assert calls == [((2025, 4), [(2025, 1), (2025, 2), (2025, 3)], 300, 42)]
    assert [(r['round'], r['reason']) for r in result['skipped']] == [
        (1, 'Needs two earlier races in the library'), (2, 'Needs two earlier races in the library'),
        (3, 'No saved qualifying session')]
    assert result['seasons'] == [{'year': 2025, 'races': 1, 'finish_mae': 2.0, 'finishers_finish_mae': 1.0,
                                  'grid_finish_mae': 1.5, 'spearman': .5, 'win_chance_skill': .1,
                                  'podium_chance_skill': .2, 'points_chance_skill': .3,
                                  'retirements': 1, 'expected_retirements': .2}]
    assert json.loads((folder / 'replay_progress.json').read_text())['processed'] == 4


def test_replay_job_stays_out_of_the_official_record(tmp_path, monkeypatch):
    archive(tmp_path)
    jobs = simulation_jobs.SimulationJobs(tmp_path)
    monkeypatch.setattr(jobs, '_launch', Mock())
    job_id = jobs.start({'kind': 'archive_replay', 'replay': {'years': [2025], 'n_sims': 500}})['id']
    folder = tmp_path / 'outputs/app_runs' / job_id
    job = json.loads((folder / 'job.json').read_text())
    assert job['replay'] == {'years': [2025], 'n_sims': 500, 'seed': 42} and 'Retrospective' in job['note']
    assert 'run_class' not in jobs.history()[0]
    pd.DataFrame([{'year': 2025, 'round': 3, 'event': 'GP 3', 'finish_mae': 2.0}]).to_csv(folder / 'replay_races.csv', index=False)
    simulation_jobs.write_json(folder / 'replay_summary.json', {'years': [2025], 'n_sims': 500, 'seed': 42,
                                                                'seasons': [], 'skipped': []})
    job.update(status='completed', finished_at='2025-01-01T00:00:00+00:00')
    simulation_jobs.write_json(folder / 'job.json', job)
    state = accuracy_state(tmp_path)
    assert state['scored'] == [] and state['pending'] == [] and state['excluded'] == []
    latest = replay.latest(tmp_path)
    assert latest['available_years'] == [2025]
    assert latest['latest']['id'] == job_id and latest['latest']['races'][0]['event'] == 'GP 3'
