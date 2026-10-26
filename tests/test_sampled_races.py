import pandas as pd

from src.app_services.workbench import sampled_futures
from src.simulate import sample_races


def test_sample_races_keeps_first_simulations_in_finishing_order():
    results = pd.DataFrame({
        'sim_id': [0, 0, 1, 1, 2, 2],
        'Driver': ['VER', 'NOR', 'VER', 'NOR', 'VER', 'NOR'],
        'Team': ['Red Bull Racing', 'McLaren'] * 3,
        'finish_position': [2, 1, 1, 2, 1, 2],
        'dnf': [False, False, False, False, True, False],
        'points': [18, 25, 25, 18, 25, 18],
    })
    sample = sample_races(results, count=2)
    assert sample.columns.tolist() == ['sim_id', 'Driver', 'Team', 'finish_position', 'dnf']
    assert sample['Driver'].tolist() == ['NOR', 'VER', 'VER', 'NOR']


def test_sampled_futures_groups_orders_and_retirements():
    frame = pd.DataFrame({
        'sim_id': [0, 0, 1, 1], 'Driver': ['VER', 'NOR', 'NOR', 'VER'], 'Team': ['Red Bull Racing', 'McLaren', 'McLaren', 'Red Bull Racing'],
        'finish_position': [2, 1, 1, 2], 'dnf': [False, False, False, True],
    })
    futures = sampled_futures(frame)
    assert futures['races'] == [{'order': ['NOR', 'VER'], 'retired': []}, {'order': ['NOR', 'VER'], 'retired': ['VER']}]
    assert futures['teams'] == {'VER': 'Red Bull Racing', 'NOR': 'McLaren'}
    assert sampled_futures(pd.DataFrame()) is None
