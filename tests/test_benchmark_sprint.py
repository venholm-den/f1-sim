import pandas as pd

from scripts.benchmark_sprint import _grid_order, race_pace


def test_race_pace_uses_clean_accurate_laps():
    laps = pd.DataFrame({'Driver': ['AAA'] * 6 + ['BBB'] * 6,
                         'LapTimeSeconds': [90.0] * 5 + [120.0] + [91.0] * 6,
                         'PitIn': [None] * 5 + [1.0] + [None] * 6,
                         'PitOut': [None] * 12,
                         'IsAccurate': [True] * 12})
    pace = race_pace(laps, 0).set_index('Driver')
    assert pace.loc['AAA', 'relative_pace'] == 0
    assert pace.loc['BBB', 'relative_pace'] == 1.0


def test_race_pace_drops_drivers_with_few_laps():
    laps = pd.DataFrame({'Driver': ['AAA'] * 5 + ['BBB'] * 2, 'LapTimeSeconds': [90.0] * 7,
                         'PitIn': [None] * 7, 'PitOut': [None] * 7, 'IsAccurate': [True] * 7})
    assert race_pace(laps, 0).Driver.tolist() == ['AAA']


def test_grid_order_awards_points_by_grid_slot():
    features = pd.DataFrame({'Driver': ['A', 'B', 'C'], 'grid_position': [1, 2, 9]})
    order = _grid_order(features).set_index('Driver')
    assert order.avg_points.tolist() == [8, 7, 0]
    assert order.win_chance.tolist() == [1.0, 0.0, 0.0]
    assert order.points_chance.tolist() == [1.0, 1.0, 0.0]
