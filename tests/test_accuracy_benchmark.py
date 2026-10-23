from types import SimpleNamespace

import pandas as pd
import pytest

from src.accuracy_benchmark import (ReplayRace, benchmark, build_replay_forecast,
    chronological_partitions, evaluate_forecast)
from tests.test_long_run_pace import practice_laps


def races():
    output = []
    for round_number in range(1, 7):
        sessions = {}
        for code in ['FP2', 'Q', 'R']:
            results = pd.DataFrame({'Abbreviation': ['A', 'B'], 'TeamName': ['A', 'B'],
                'Position': [1, 2], 'Status': ['Finished', 'Finished']})
            sessions[code] = SimpleNamespace(laps=practice_laps(), results=results,
                weather_data=pd.DataFrame(), track_status=pd.DataFrame())
        output.append(ReplayRace(2024, round_number, 'Example GP', sessions))
    return output


def test_partitions_are_whole_races_chronological_and_disjoint():
    development, holdout = chronological_partitions([(2024, i) for i in range(1, 8)])
    assert not development & holdout
    assert max(development) < min(holdout)
    with pytest.raises(ValueError, match='At least four'):
        chronological_partitions([(2024, 1)])


def test_target_race_data_cannot_affect_prediction_and_future_baseline_rejected():
    events = races()
    target = events[2]
    metadata = {'year': 2024, 'round': 3, 'event': 'Example GP', 'session': 'FP2'}
    first, _ = build_replay_forecast(target.sessions['FP2'], events[:2], metadata=metadata,
                                    candidate=True, n_sims=100)
    target.sessions['R'].laps['LapTimeSeconds'] += 100
    target.sessions['R'].results['Position'] = [2, 1]
    second, _ = build_replay_forecast(target.sessions['FP2'], events[:2], metadata=metadata,
                                     candidate=True, n_sims=100)
    pd.testing.assert_frame_equal(first, second)
    with pytest.raises(ValueError, match='cutoff'):
        build_replay_forecast(target.sessions['FP2'], [target], metadata=metadata, n_sims=100)


def test_benchmark_writes_separate_heldout_metrics_and_baselines(tmp_path):
    output = tmp_path / 'benchmark'
    report = benchmark(races(), output, n_sims=100, sessions=('FP2', 'Q'))
    assert report['development_races'][-1] < report['holdout_races'][0]
    summary = pd.read_csv(output / 'summary.csv')
    assert set(summary.variant) == {'legacy', 'matched_stints_v2', 'grid_order', 'recent_form'}
    assert set(summary['split']) == {'development', 'holdout'}
    assert not report['promotion_gate_passed']
    assert report['source_sha256']['src/accuracy_benchmark.py']
    assert report['input_sha256']['2024/1/R/laps']
    assert report['stage_coverage']


def test_partial_driver_coverage_is_not_scored():
    with pytest.raises(ValueError, match='coverage'):
        evaluate_forecast(pd.DataFrame({'Driver': ['A']}),
                          pd.DataFrame({'Abbreviation': ['A', 'B'], 'Position': [1, 2]}))
