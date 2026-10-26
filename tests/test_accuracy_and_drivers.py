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
    for forecast, event in (('f1', 'Monaco Grand Prix'), ('f2', 'Spanish Grand Prix')):
        write(runs / forecast / 'job.json', {'id': forecast, 'kind': 'forecast', 'status': 'completed', 'created_at': forecast})
        write(runs / forecast / 'frozen/manifest.json', {'context': {**context, 'event': event}, 'category': 'prospective'})
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


def _forecast(runs, forecast_id, event, session, created):
    write(runs / forecast_id / 'job.json', {'id': forecast_id, 'kind': 'forecast', 'status': 'completed',
                                            'created_at': created})
    write(runs / forecast_id / 'frozen/manifest.json', {'context': {'year': 2026, 'event': event, 'session': session},
                                                        'category': 'prospective'})


def _score(runs, score_id, forecast_id, evaluated, mae, record_id=True):
    job = {'id': score_id, 'kind': 'score', 'status': 'completed', 'created_at': evaluated,
           'forecast_folder': str(runs / forecast_id)}
    if record_id:
        job['forecast_id'] = forecast_id
    write(runs / score_id / 'job.json', job)
    write(runs / score_id / 'score.json', {'drivers': 20, 'finish_mae': mae, 'evaluated_at_utc': evaluated})


def test_accuracy_lists_each_forecast_once_and_drops_superseded_forecasts(tmp_path):
    runs = tmp_path / 'outputs/app_runs'
    _forecast(runs, 'bah_fp3', 'Bahrain Grand Prix', 'FP3', '2026-10-03')
    _forecast(runs, 'bah_q', 'Bahrain Grand Prix', 'Q', '2026-10-04')
    _forecast(runs, 'mex_pre', 'Mexico City Grand Prix', 'PRE', '2026-10-25')
    _forecast(runs, 'mex_fp1', 'Mexico City Grand Prix', 'FP1', '2026-10-30')
    # The app's score jobs record the forecast folder but not its id; one was scored twice.
    _score(runs, 's1', 'bah_q', '2026-10-05', 3.0, record_id=False)
    _score(runs, 's2', 'bah_q', '2026-10-06', 2.5, record_id=False)
    # Both Singapore forecasts were scored; the later Q forecast represents the race.
    _forecast(runs, 'sin_pre', 'Singapore Grand Prix', 'PRE', '2026-10-09')
    _forecast(runs, 'sin_q', 'Singapore Grand Prix', 'Q', '2026-10-10')
    _score(runs, 's3', 'sin_q', '2026-10-12', 3.2)
    _score(runs, 's4', 'sin_pre', '2026-10-13', 3.6)
    state = accuracy_state(tmp_path)
    assert [(row['id'], row['forecast_id'], row['finish_mae']) for row in state['scored']] == [
        ('s3', 'sin_q', 3.2), ('s2', 'bah_q', 2.5)]
    # Bahrain FP3 was superseded by the scored Q forecast, and Mexico PRE by its FP1 forecast.
    assert [row['id'] for row in state['pending']] == ['mex_fp1']
    assert state['superseded'] == 2


def test_accuracy_reads_scores_from_the_pc_forecast_workspace(tmp_path):
    app, pc = tmp_path / 'app', tmp_path / 'pc'
    _forecast(pc / 'outputs/app_runs', 'usa_q', 'United States Grand Prix', 'Q', '2026-10-24')
    _score(pc / 'outputs/app_runs', 's_usa', 'usa_q', '2026-10-26', 3.2)
    _forecast(app / 'outputs/app_runs', 'mex_pre', 'Mexico City Grand Prix', 'PRE', '2026-10-25')
    _forecast(pc / 'outputs/app_runs', 'mex_fp1', 'Mexico City Grand Prix', 'FP1', '2026-10-30')
    state = accuracy_state(app, [pc, app])
    assert [row['event'] for row in state['scored']] == ['United States Grand Prix']
    # Only the app's own forecasts can be scored from the app.
    assert [(row['id'], row['scorable']) for row in state['pending']] == [('mex_fp1', False)]
    assert accuracy_state(app)['pending'][0]['scorable'] is True


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
