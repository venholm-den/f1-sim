import json

import pandas as pd
import pytest

from src.app_services.accuracy import accuracy_state, even_guess_brier, skill
from src.app_services.driver_intel import season_summary


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def test_even_guess_reference_and_skill():
    assert even_guess_brier(20, 1) == pytest.approx(0.05 * 0.95)
    assert even_guess_brier(20, 10) == pytest.approx(0.25)
    assert skill(0.0, 20, 1) == pytest.approx(1.0)
    assert skill(even_guess_brier(20, 3), 20, 3) == pytest.approx(0.0)
    assert skill(None, 20, 1) is None and skill(0.1, 0, 1) is None


def test_accuracy_lists_scored_races_and_unscored_forecasts(tmp_path):
    runs = tmp_path / 'outputs/app_runs'
    context = {'year': 2026, 'event': 'Monaco Grand Prix', 'session': 'Q', 'race_start_utc': '2026-06-07T13:00:00Z'}
    for forecast in ('f1', 'f2'):
        write(runs / forecast / 'job.json', {'id': forecast, 'kind': 'forecast', 'status': 'completed', 'created_at': forecast})
        write(runs / forecast / 'frozen/manifest.json', {'context': context, 'category': 'prospective'})
    write(runs / 's1/job.json', {'id': 's1', 'kind': 'score', 'status': 'completed', 'created_at': 'x',
                                 'forecast_id': 'f1', 'forecast_folder': str(runs / 'f1')})
    write(runs / 's1/score.json', {'drivers': 20, 'finish_mae': 3.1, 'win_chance_brier': 0.0425,
                                   'podium_chance_brier': 0.1, 'points_chance_brier': 0.2, 'evaluated_at_utc': '2026-06-08'})
    pd.DataFrame({'Driver': ['B', 'A'], 'avg_finish': [2.0, None], 'actual_position': [2, 1]}).to_csv(
        runs / 's1/score_comparison.csv', index=False)
    write(runs / 's2/job.json', {'id': 's2', 'kind': 'score', 'status': 'failed', 'created_at': 'y', 'forecast_id': 'f2'})

    state = accuracy_state(tmp_path)
    [race] = state['scored']
    assert (race['event'], race['category'], race['finish_mae']) == ('Monaco Grand Prix', 'prospective', 3.1)
    assert race['win_chance_skill'] == pytest.approx(1 - 0.0425 / 0.0475)
    assert race['points_chance_skill'] == pytest.approx(0.2)
    assert [row['Driver'] for row in race['comparison']] == ['A', 'B']
    assert race['comparison'][0]['avg_finish'] is None
    json.dumps(state, allow_nan=False)
    assert [row['id'] for row in state['pending']] == ['f2']


def test_accuracy_scores_finishers_apart_from_retirements_and_tallies_them(tmp_path):
    runs = tmp_path / 'outputs/app_runs'
    context = {'year': 2026, 'event': 'Singapore Grand Prix', 'session': 'Q'}
    write(runs / 'f1/job.json', {'id': 'f1', 'kind': 'forecast', 'status': 'completed', 'created_at': 'f1'})
    write(runs / 'f1/frozen/manifest.json', {'context': context, 'category': 'prospective'})
    write(runs / 's1/job.json', {'id': 's1', 'kind': 'score', 'status': 'completed', 'created_at': 'x',
                                 'forecast_id': 'f1', 'forecast_folder': str(runs / 'f1')})
    write(runs / 's1/score.json', {'drivers': 4, 'finish_mae': 1.5})
    # STR was forecast 2nd but retired; the rest finished in forecast order.
    pd.DataFrame({'Driver': ['VER', 'STR', 'NOR', 'ALO'], 'avg_finish': [1.0, 2.0, 3.0, 4.0],
                  'actual_position': [1, 4, 2, 3], 'dnf_chance': [.05, .5, .05, .3],
                  'actual_dnf': [False, True, False, None]}).to_csv(runs / 's1/score_comparison.csv', index=False)
    state = accuracy_state(tmp_path)
    [race] = state['scored']
    assert race['retirements'] == 1
    assert race['finishers_finish_mae'] == pytest.approx(0.0)
    assert race['expected_retirements'] == pytest.approx(0.9)
    assert [row['actual_dnf'] for row in race['comparison']] == [False, False, None, True]
    record = {row['driver']: row for row in state['retirement_record']}
    assert set(record) == {'VER', 'STR', 'NOR'}
    assert (record['STR']['retirements'], record['STR']['expected']) == (1, pytest.approx(.5))
    assert state['retirement_record'][0]['driver'] == 'STR'
    json.dumps(state, allow_nan=False)


def test_scores_without_retirement_labels_leave_finishers_blank(tmp_path):
    runs = tmp_path / 'outputs/app_runs'
    write(runs / 'f1/job.json', {'id': 'f1', 'kind': 'forecast', 'status': 'completed', 'created_at': 'f1'})
    write(runs / 'f1/frozen/manifest.json', {'context': {'year': 2026, 'event': 'GP'}, 'category': 'prospective'})
    write(runs / 's1/job.json', {'id': 's1', 'kind': 'score', 'status': 'completed', 'created_at': 'x',
                                 'forecast_id': 'f1', 'forecast_folder': str(runs / 'f1')})
    write(runs / 's1/score.json', {'drivers': 2, 'finish_mae': 1.0})
    pd.DataFrame({'Driver': ['A', 'B'], 'avg_finish': [1.0, 2.0], 'actual_position': [2, 1]}).to_csv(
        runs / 's1/score_comparison.csv', index=False)
    [race] = accuracy_state(tmp_path)['scored']
    assert (race['retirements'], race['finishers_finish_mae'], race['expected_retirements']) == (None, None, None)


def test_season_summary_counts_head_to_heads_only_when_both_finish():
    results = pd.DataFrame([
        {'round': 1, 'session': 'R', 'Driver': 'NOR', 'Team': 'McLaren', 'position': 1, 'points': 25, 'classified': True},
        {'round': 1, 'session': 'R', 'Driver': 'PIA', 'Team': 'McLaren', 'position': 2, 'points': 18, 'classified': True},
        {'round': 2, 'session': 'S', 'Driver': 'PIA', 'Team': 'McLaren', 'position': 1, 'points': 8, 'classified': True},
        {'round': 2, 'session': 'R', 'Driver': 'NOR', 'Team': 'McLaren', 'position': None, 'points': 0, 'classified': False},
        {'round': 2, 'session': 'R', 'Driver': 'PIA', 'Team': 'McLaren', 'position': 1, 'points': 25, 'classified': True},
        {'round': 3, 'session': 'R', 'Driver': 'NOR', 'Team': 'McLaren', 'position': 3, 'points': 15, 'classified': True},
        {'round': 3, 'session': 'R', 'Driver': 'PIA', 'Team': 'McLaren', 'position': 5, 'points': 10, 'classified': True},
    ])
    summary = season_summary(results)
    assert summary['rounds'] == 3
    assert [(d['driver'], d['points'], d['wins'], d['retirements']) for d in summary['drivers']] == [
        ('PIA', 61.0, 1, 0), ('NOR', 40.0, 1, 1)]
    assert summary['drivers'][1]['avg_finish'] == 2.0
    assert summary['pairs'] == [{'team': 'McLaren', 'a': 'NOR', 'b': 'PIA', 'a_ahead': 2, 'b_ahead': 0, 'races': 3}]
    assert season_summary(pd.DataFrame())['drivers'] == []
