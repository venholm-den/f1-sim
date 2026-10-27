import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.app_services.championship import championship_odds, season_inputs
from src.championship_odds import (RACE_POINTS, SPRINT_POINTS, OddsSettings, normalise_results,
                                   simulate_championship, standings)

TEAMS = {'AAA': 'Alpha', 'BBB': 'Alpha', 'CCC': 'Bravo', 'DDD': 'Bravo', 'EEE': 'Charlie', 'FFF': 'Charlie'}


def classification(round_number, order, session='R', retired=(), event=None):
    table = RACE_POINTS if session == 'R' else SPRINT_POINTS
    rows = []
    for index, driver in enumerate(order, 1):
        out = driver in retired
        rows.append({'Round': round_number, 'Session': session, 'Event': event or f'Round {round_number}',
                     'Abbreviation': driver, 'TeamName': TEAMS[driver], 'Position': float(index),
                     # Archived FastF1 rows can carry a numeric classified position for a retirement.
                     'ClassifiedPosition': str(index), 'Status': 'Retired' if out else 'Finished',
                     'Points': 0.0 if out or index > len(table) else float(table[index - 1])})
    return pd.DataFrame(rows)


def season(rounds, order=('AAA', 'CCC', 'BBB', 'DDD', 'EEE', 'FFF')):
    return pd.concat([classification(r, list(order)) for r in range(1, rounds + 1)], ignore_index=True)


def test_normalise_uses_status_before_numeric_classified_position():
    frame = normalise_results(classification(1, list(TEAMS), retired={'BBB'}))
    retired = frame.set_index('Driver').loc['BBB']
    assert not retired['classified'] and pd.isna(retired['position'])
    assert frame['classified'].sum() == 5


def test_normalise_reads_jolpica_columns():
    jolpica = pd.DataFrame({'Round': [3, 3], 'Session': ['R', 'R'], 'driverCode': ['aaa', 'BBB'],
                            'constructorName': ['Alpha', 'Alpha'], 'position': [1, 2],
                            'positionText': ['1', 'R'], 'points': [25, 0], 'status': ['Finished', 'Engine']})
    frame = normalise_results(jolpica)
    assert frame['Driver'].tolist() == ['AAA', 'BBB']
    assert frame['classified'].tolist() == [True, False]


def test_standings_sum_points_and_wins_by_driver_and_team():
    results = normalise_results(pd.concat([season(2), classification(2, ['CCC', 'AAA', 'BBB', 'DDD', 'EEE', 'FFF'], 'S')]))
    drivers, teams = standings(results)
    assert drivers.set_index('Driver').loc['AAA', 'points'] == 50 + 7
    assert drivers.set_index('Driver').loc['AAA', 'wins'] == 2
    assert teams.set_index('Team').loc['Alpha', 'points'] == 50 + 30 + 7 + 6


def test_unreachable_leader_has_clinched_and_rivals_are_eliminated():
    payload = simulate_championship(normalise_results(season(10)), [{'round': 11, 'race': True}],
                                    OddsSettings(n_sims=500))
    leader = payload['drivers'][0]
    assert leader['name'] == 'AAA' and leader['clinched'] and leader['title_chance'] == 1.0
    assert all(row['eliminated'] and row['title_chance'] == 0 for row in payload['drivers'][1:])
    assert payload['max_points_available'] == 25


def test_close_fight_is_uncertain_and_constructors_add_team_mates():
    # AAA and CCC trade wins; the title is open with three races and a sprint left.
    rounds = [classification(r, ['AAA', 'CCC', 'BBB', 'DDD', 'EEE', 'FFF'] if r % 2 else
                             ['CCC', 'AAA', 'DDD', 'BBB', 'EEE', 'FFF']) for r in range(1, 9)]
    remaining = [{'round': 9, 'race': True, 'sprint': True}, {'round': 10, 'race': True}, {'round': 11, 'race': True}]
    payload = simulate_championship(normalise_results(pd.concat(rounds)), remaining, OddsSettings(n_sims=4000))
    drivers = {row['name']: row for row in payload['drivers']}
    assert 0.2 < drivers['AAA']['title_chance'] < 0.8
    assert drivers['AAA']['title_chance'] + drivers['CCC']['title_chance'] > 0.95
    assert sum(row['title_chance'] for row in payload['drivers']) == pytest.approx(1.0)
    assert payload['max_points_available'] == 3 * 25 + 8
    teams = {row['name']: row for row in payload['constructors']}
    gained = sum(drivers[d]['expected_points'] - drivers[d]['current_points'] for d in ('AAA', 'BBB'))
    assert teams['Alpha']['expected_points'] - teams['Alpha']['current_points'] == pytest.approx(gained)
    assert sum(row['title_chance'] for row in payload['constructors']) == pytest.approx(1.0)
    json.dumps(payload, allow_nan=False)


def test_simulation_is_reproducible_for_a_seed():
    results, remaining = normalise_results(season(4)), [{'round': 5, 'race': True}, {'round': 6, 'race': True}]
    first = simulate_championship(results, remaining, OddsSettings(n_sims=300, seed=7))
    second = simulate_championship(results, remaining, OddsSettings(n_sims=300, seed=7))
    assert first['drivers'] == second['drivers']


def test_new_driver_borrows_team_mate_form():
    # GGG replaces BBB at Alpha for the latest round only.
    TEAMS['GGG'] = 'Alpha'
    try:
        latest = classification(5, ['AAA', 'GGG', 'CCC', 'DDD', 'EEE', 'FFF'])
        payload = simulate_championship(normalise_results(pd.concat([season(4), latest])),
                                        [{'round': 6, 'race': True}], OddsSettings(n_sims=2000))
    finally:
        del TEAMS['GGG']
    drivers = {row['name']: row for row in payload['drivers']}
    assert not drivers['BBB']['active'] and drivers['GGG']['active']
    assert drivers['GGG']['expected_points'] - drivers['GGG']['current_points'] > 5


def write_session(root, year, round_number, session, frame, mode='detailed'):
    folder = Path(root)/'data/historical_library'/str(year)/mode/f'{round_number:02d}_round_{session}'
    (folder/'versions/v1').mkdir(parents=True)
    path = folder/'versions/v1/results.csv'
    frame.to_csv(path, index=False)
    data = path.read_bytes()
    (folder/'session.json').write_text(json.dumps({
        'year': year, 'round': round_number, 'session': session, 'status': 'complete',
        'files': {'versions/v1/results.csv': {'table': 'results', 'rows': len(frame), 'bytes': len(data),
                                              'sha256': hashlib.sha256(data).hexdigest()}}}))


def schedule(rounds, sprint_rounds=()):
    rows = []
    for r in range(1, rounds + 1):
        race = pd.Timestamp('2026-03-01') + pd.Timedelta(weeks=2 * r)
        row = {'RoundNumber': r, 'EventName': f'Round {r}', 'Session5': 'Race', 'Session5DateUtc': race}
        if r in sprint_rounds:
            row.update(Session3='Sprint', Session3DateUtc=race - pd.Timedelta(days=1))
        rows.append(row)
    return pd.DataFrame(rows)


def offline(*_):
    raise RuntimeError('offline')


def test_season_inputs_reads_archive_and_lists_remaining_sessions(tmp_path):
    for r in (1, 2, 3):
        write_session(tmp_path, 2026, r, 'R', classification(r, list(TEAMS)))
    write_session(tmp_path, 2026, 2, 'S', classification(2, list(TEAMS), 'S'))
    now = pd.Timestamp('2026-03-01') + pd.Timedelta(weeks=7)  # after round 3, before round 4
    results, remaining, warnings = season_inputs(tmp_path, 2026, now=now, schedule=schedule(5, {2, 5}), fetch=offline)
    assert set(zip(results['round'], results['session'])) == {(1, 'R'), (2, 'R'), (2, 'S'), (3, 'R')}
    assert [(r['round'], r['race'], r['sprint']) for r in remaining] == [(4, True, False), (5, True, True)]
    assert warnings == []


def test_unarchived_finished_race_is_fetched_or_reported(tmp_path):
    write_session(tmp_path, 2026, 1, 'R', classification(1, list(TEAMS)))
    now = pd.Timestamp('2026-03-01') + pd.Timedelta(weeks=9)  # rounds 1-4 finished
    fetched = []

    def fetch(year, round_number, session):
        fetched.append(round_number)
        if round_number == 2:
            return classification(2, list(TEAMS))
        raise RuntimeError('not published')

    results, remaining, warnings = season_inputs(tmp_path, 2026, now=now, schedule=schedule(6), fetch=fetch)
    assert fetched == [2, 3, 4]
    assert sorted(results['round'].unique()) == [1, 2]
    assert [r['round'] for r in remaining] == [5, 6]
    assert len(warnings) == 2 and re.match(r'R3 Round 3 race results are not downloaded', warnings[0])


def test_race_finished_moments_ago_stays_outstanding(tmp_path):
    write_session(tmp_path, 2026, 1, 'R', classification(1, list(TEAMS)))
    now = pd.Timestamp('2026-03-01') + pd.Timedelta(weeks=4, hours=3)  # round 2 started three hours ago
    _, remaining, warnings = season_inputs(tmp_path, 2026, now=now, schedule=schedule(3), fetch=offline)
    assert [r['round'] for r in remaining] == [2, 3] and warnings == []


def test_championship_odds_needs_results(tmp_path):
    with pytest.raises(ValueError, match='No 2026 race results'):
        championship_odds(tmp_path, 2026, schedule=schedule(3), fetch=offline)


def test_championship_odds_payload(tmp_path):
    for r in (1, 2):
        write_session(tmp_path, 2026, r, 'R', classification(r, list(TEAMS)))
    now = pd.Timestamp('2026-03-01') + pd.Timedelta(weeks=5)
    payload = championship_odds(tmp_path, 2026, n_sims=200, now=now, schedule=schedule(4), fetch=offline)
    assert payload['year'] == 2026 and payload['remaining_races'] == 2 and payload['completed_rounds'] == 2
    assert payload['sources'] == ['archive_detailed']
    json.dumps(payload, allow_nan=False)


def test_dominant_driver_is_not_pulled_back_by_noise():
    # AAA has won every race. Added place noise costs a P1 driver points it can never win
    # back; drawing from their own results (plus a little team-mate prior) keeps more of them.
    results, remaining = normalise_results(season(10)), [{'round': r, 'race': True} for r in (11, 12, 13)]
    pool = {row['name']: row for row in simulate_championship(results, remaining, OddsSettings(n_sims=2000))['drivers']}
    places = {row['name']: row for row in simulate_championship(
        results, remaining, OddsSettings(n_sims=2000, pace_mode='places'))['drivers']}
    gain = {name: rows['AAA']['expected_points'] - rows['AAA']['current_points'] for name, rows in
            (('pool', pool), ('places', places))}
    assert gain['pool'] > 0.85 * 3 * 25 > 0.8 * 3 * 25 > gain['places']


def test_form_tilt_moves_draws_within_a_drivers_own_results():
    from src.championship_odds import _tilted_draws
    rng = np.random.default_rng(1)
    pools = [(np.array([1.0, 5.0, np.inf]), np.array([0.25, 0.5, 0.25]))]
    neutral = _tilted_draws(pools, np.zeros((20000, 1)), rng)[:, 0]
    assert np.mean(neutral == 1) == pytest.approx(0.25, abs=0.02)
    assert np.mean(np.isinf(neutral)) == pytest.approx(0.25, abs=0.02)
    better = _tilted_draws(pools, np.full((20000, 1), 2.0), rng)[:, 0]
    worse = _tilted_draws(pools, np.full((20000, 1), -2.0), rng)[:, 0]
    assert np.mean(better == 1) > 0.6 and np.mean(np.isinf(worse)) > 0.6
    assert set(np.unique(np.concatenate([better, worse]))) <= {1.0, 5.0, np.inf}


def test_backtest_scores_a_season_cut():
    from scripts.benchmark_championship_odds import season_rows, summarise
    rows = season_rows(normalise_results(season(8)), 2026, OddsSettings(n_sims=300), cuts=[6])
    assert set(rows['cut']) == {6} and rows['champion'].sum() == 1
    assert rows.loc[rows['driver'].eq('AAA'), 'actual_gain'].item() == 50
    summary = summarise(rows)
    assert summary['cuts'] == 1 and summary['combined'] == pytest.approx(summary['title_brier'] + summary['top3_brier'])
