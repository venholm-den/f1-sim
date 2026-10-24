from itertools import combinations
import threading
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.fantasy_team import market_assets, pick_teams, team_distribution, team_key


def asset(code, price, points, team=''):
    return {'code': code, 'team': team or code, 'price': price, 'points': points}


def brute_force(drivers, constructors, budget, size=(3, 2), multiplier=2.0):
    best = -np.inf
    for ds in combinations(drivers, size[0]):
        for cs in combinations(constructors, size[1]):
            if sum(a['price'] for a in ds + cs) > budget:
                continue
            points = [a['points'] for a in ds]
            best = max(best, sum(points) + (multiplier - 1) * max(points) + sum(a['points'] for a in cs))
    return best


def test_best_team_matches_a_brute_force_search():
    rng = np.random.default_rng(3)
    drivers = [asset(f'D{i}', float(rng.uniform(4, 30)), float(rng.uniform(-5, 40))) for i in range(9)]
    constructors = [asset(f'C{i}', float(rng.uniform(5, 30)), float(rng.uniform(0, 50))) for i in range(5)]
    rules = {'drivers': 3, 'constructors': 2}

    teams = pick_teams(drivers, constructors, budget=70, rules=rules)

    assert teams[0]['expected_points'] == pytest.approx(brute_force(drivers, constructors, 70), abs=0.01)
    assert all(t['cost'] <= 70 for t in teams)
    assert [t['expected_points'] for t in teams] == sorted((t['expected_points'] for t in teams), reverse=True)


def test_boost_goes_on_the_best_driver_and_can_be_turned_off():
    drivers = [asset('A', 10, 30), asset('B', 10, 20), asset('C', 10, 10)]
    constructors = [asset('X', 10, 5), asset('Y', 10, 4)]
    rules = {'drivers': 2, 'constructors': 2}

    boosted = pick_teams(drivers, constructors, budget=100, rules=rules)[0]
    plain = pick_teams(drivers, constructors, budget=100, rules=rules, boost=False)[0]

    assert boosted['boost'] == 'A' and boosted['expected_points'] == 30 * 2 + 20 + 9
    assert plain['boost'] is None and plain['expected_points'] == 30 + 20 + 9


def test_locked_and_left_out_assets_are_respected():
    drivers = [asset('A', 10, 30), asset('B', 10, 20), asset('C', 10, 1)]
    constructors = [asset('X', 10, 5), asset('Y', 10, 4), asset('Z', 10, 3)]
    rules = {'drivers': 2, 'constructors': 2}

    team = pick_teams(drivers, constructors, budget=100, rules=rules, include=['C'], exclude=['X'])[0]

    assert {a['code'] for a in team['drivers']} == {'A', 'C'}
    assert {a['code'] for a in team['constructors']} == {'Y', 'Z'}
    with pytest.raises(ValueError, match='both'):
        pick_teams(drivers, constructors, rules=rules, include=['A'], exclude=['A'])


def test_transfers_past_the_free_ones_cost_ten_points_each():
    drivers = [asset('A', 10, 10), asset('B', 10, 10), asset('C', 10, 15), asset('D', 10, 30)]
    constructors = [asset('X', 10, 5), asset('Y', 10, 5), asset('Z', 10, 5)]
    rules = {'drivers': 2, 'constructors': 2}
    plan = dict(rules=rules, boost=False, current=['A', 'B', 'X', 'Y'], bank=0.0)

    one_free = pick_teams(drivers, constructors, free_transfers=1, **plan)
    none_free = pick_teams(drivers, constructors, free_transfers=0, **plan)

    # D gains 20 over A or B; C gains only 5, which a 10-point hit does not pay for.
    assert one_free[0]['transfers_in'] == ['D'] and one_free[0]['transfer_penalty'] == 0
    assert one_free[0]['expected_points'] == 30 + 10 + 10  # constructors add 10
    assert none_free[0]['transfers_in'] == ['D'] and none_free[0]['expected_points'] == 40
    keep = next(t for t in none_free if not t['transfers_in'])
    assert keep['expected_points'] == 30
    swap_both = pick_teams(drivers, constructors, free_transfers=1, top=20, **plan)
    both = next(t for t in swap_both if t['transfers_in'] == ['C', 'D'])
    assert both['transfer_penalty'] == -10 and both['expected_points'] == 30 + 15 + 10 - 10


def test_current_team_budget_is_its_value_plus_the_bank():
    drivers = [asset('A', 10, 10), asset('B', 10, 10), asset('D', 15, 30)]
    constructors = [asset('X', 10, 5), asset('Y', 10, 5)]
    rules = {'drivers': 2, 'constructors': 2}
    plan = dict(rules=rules, boost=False, current=['A', 'B', 'X', 'Y'], free_transfers=2)

    assert pick_teams(drivers, constructors, bank=4.0, **plan)[0]['transfers_in'] == []
    assert pick_teams(drivers, constructors, bank=5.0, **plan)[0]['transfers_in'] == ['D']
    with pytest.raises(ValueError, match='needs 2 drivers'):
        pick_teams(drivers, constructors, rules=rules, current=['A', 'X', 'Y'])


def test_no_team_within_budget_is_reported():
    drivers = [asset('A', 40, 30), asset('B', 40, 20)]
    constructors = [asset('X', 30, 5), asset('Y', 30, 4)]
    with pytest.raises(ValueError, match='budget'):
        pick_teams(drivers, constructors, budget=100, rules={'drivers': 2, 'constructors': 2})


def test_market_prices_join_simulated_drivers_and_teams_by_name():
    market = [{'asset_type': 'driver', 'code': 'OCO', 'price': '9.9'},
              {'asset_type': 'constructor', 'code': 'HAA', 'name': 'Haas', 'price': '12.0'},
              {'asset_type': 'constructor', 'code': 'RBR', 'name': 'Red Bull Racing', 'price': '32.7'}]
    drivers = pd.DataFrame({'Driver': ['OCO', 'NEW'], 'Team': ['Haas F1 Team', 'Haas F1 Team'],
                            'avg_fantasy_points': [12.0, 3.0]})
    teams = pd.DataFrame({'Team': ['Haas F1 Team', 'Red Bull Racing', 'Cadillac'],
                          'avg_constructor_points': [20.0, 40.0, 1.0]})

    priced_drivers, priced_teams, missing = market_assets(market, drivers, teams)

    assert team_key('Haas F1 Team') == team_key('haas')
    assert [d['code'] for d in priced_drivers] == ['OCO']
    assert {t['code']: t['price'] for t in priced_teams} == {'HAA': 12.0, 'RBR': 32.7}
    assert missing == ['NEW', 'Cadillac']


def test_team_distribution_doubles_the_boosted_driver():
    team = {'drivers': [{'code': 'A', 'boosted': True}, {'code': 'B', 'boosted': False}],
            'constructors': [{'team': 'T'}]}
    drivers = pd.DataFrame({'sim_id': [0, 0, 1, 1], 'Driver': ['A', 'B', 'A', 'B'],
                            'fantasy_points': [10.0, 1.0, 20.0, 2.0]})
    teams = pd.DataFrame({'sim_id': [0, 1], 'Team': ['T', 'T'], 'constructor_fantasy_points': [5.0, 5.0]})

    result = team_distribution(team, drivers, teams)

    assert result['sims'] == 2
    assert result['p10'] == pytest.approx(26 + 0.1 * 21)
    assert result['p90'] == pytest.approx(26 + 0.9 * 21)


def test_desktop_picks_a_team_from_the_run_and_latest_official_prices(tmp_path, monkeypatch):
    import portable_app.web_backend as backend
    from src import fantasy_market
    run = tmp_path / 'run'
    run.mkdir()
    codes = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6']
    pd.DataFrame({'Driver': codes, 'Team': ['T1', 'T1', 'T2', 'T2', 'T3', 'T3'],
                  'avg_fantasy_points': [30, 25, 20, 15, 10, 5], 'avg_overtake_points': 4.0}
                 ).to_csv(run / 'simulation_summary.csv', index=False)
    pd.DataFrame({'Team': ['T1', 'T2', 'T3'], 'avg_constructor_points': [50, 30, 10]}
                 ).to_csv(run / 'fantasy_constructor_summary.csv', index=False)
    row = {'source': 'official', 'season': '2026', 'round': '18', 'event': 'United States Grand Prix',
           'captured_at': '2026-10-24T13:02:37+00:00', 'is_active': 'True'}
    old = {**row, 'round': '17', 'captured_at': '2026-10-17T13:02:37+00:00'}
    rows = ([{**row, 'asset_type': 'driver', 'code': c, 'price': str(10 + i)} for i, c in enumerate(codes)]
            + [{**row, 'asset_type': 'constructor', 'code': t, 'name': t, 'price': '20'} for t in ('T1', 'T2', 'T3')]
            + [{**old, 'asset_type': 'driver', 'code': 'D1', 'price': '1'}])
    monkeypatch.setattr(fantasy_market, 'history', lambda workspace: (rows, {}, []))
    monkeypatch.setattr(backend, 'settings_from_payload',
                        lambda payload, defaults: SimpleNamespace(output_dir=payload['output_dir']))
    api = backend.PortableWebApi.__new__(backend.PortableWebApi)
    api.ui_preferences = {'pc_workspace': str(tmp_path)}
    api._jobs = SimpleNamespace(root=tmp_path)
    api.default_settings = None

    result = api.fantasy_team({'output_dir': str(run)}, budget=120)

    best = result['teams'][0]
    assert result['market']['round'] == 18 and result['notes'] == []
    assert {a['code'] for a in best['constructors']} == {'T1', 'T2'}
    assert best['boost'] == 'D1' and best['cost'] <= 120
    assert {a['price'] for a in result['drivers'] if a['code'] == 'D1'} == {10.0}

    planned = api.fantasy_team({'output_dir': str(run)}, current=['D3', 'D4', 'D5', 'D6', 'D2', 'T3', 'T2'],
                               bank=5, free_transfers=2)
    assert planned['current']['transfers_in'] == [] and planned['current']['budget_left'] == 5
    assert len(planned['teams'][0]['transfers_in']) >= 1
    assert planned['budget'] == pytest.approx(sum([11, 12, 13, 14, 15, 20, 20]) + 5)
