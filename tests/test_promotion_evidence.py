import numpy as np
import pandas as pd
import pytest

from src.app_services.model_candidates import candidate_options
from src.promotion_evidence import (accuracy_decision, betting_e_value, correctness_decision, lane_for,
                                    minimum_detectable_effect, paired_races, power_table, races_needed)


def rows(candidate_shift, races=8, seeds=(1, 2, 3), noise=0.001):
    rng = np.random.default_rng(0)
    out = []
    for round_ in range(1, races + 1):
        base = {'finish_mae': 3 + rng.normal(0, .3), 'win_brier': .03, 'podium_brier': .07,
                'top10_brier': .18, 'rps': .13}
        for seed in seeds:
            out.append({'round': round_, 'seed': seed, 'arm': 'live',
                        **{k: v + rng.normal(0, noise) for k, v in base.items()}})
            out.append({'round': round_, 'seed': seed, 'arm': 'cand',
                        **{k: v + candidate_shift.get(k, 0) + rng.normal(0, noise) for k, v in base.items()}})
    return pd.DataFrame(out)


def test_lanes():
    assert lane_for('grid_penalty_model', 'announced_v1') == 'correctness'
    assert lane_for('sprint_model', 'sprint_v1') == 'correctness'
    assert lane_for('safety_car_model', 'multi_sc_v1') == 'accuracy'
    lanes = {(item['key'], option['value']): option['lane']
             for item in candidate_options() for option in item['options']}
    assert lanes[('grid_penalty_model', 'off')] is None
    assert lanes[('grid_penalty_model', 'announced_v1')] == 'correctness'
    assert lanes[('race_engine', 'agent_laps_v1')] == 'accuracy'


def test_seeds_average_within_a_race():
    pair = paired_races(rows({'rps': -.01}), 'cand', 'live')
    assert len(pair) == 8 and pair.rps_delta.mean() == pytest.approx(-.01, abs=.002)
    assert 'loss_delta' in pair


def test_correctness_gate_passes_a_harmless_fix_and_blocks_a_regression():
    assert correctness_decision(rows({}), 'cand', 'live')['passed']
    worse = correctness_decision(rows({'top10_brier': .01}), 'cand', 'live')
    assert not worse['passed'] and not worse['checks']['top10_brier']['passed']
    assert worse['activated'] is False
    assert not correctness_decision(rows({}, races=3), 'cand', 'live')['passed']


def test_accuracy_gate_uses_five_percent_rps_with_no_mae_regression():
    better = accuracy_decision(rows({'rps': -.01}, noise=0), 'cand', 'live')
    assert better['passed'] and better['primary_metric'] == 'rps' and better['primary_improvement'] > .05
    # A large finish-MAE gain alone no longer passes: the probabilities must improve.
    mae_only = accuracy_decision(rows({'finish_mae': -.3}, noise=0), 'cand', 'live')
    assert not mae_only['passed'] and mae_only['loss_improvement'] > .05
    assert any('rps improvement' in reason for reason in mae_only['reasons'])
    worse_mae = accuracy_decision(rows({'rps': -.01, 'finish_mae': .05}, noise=0), 'cand', 'live')
    assert not worse_mae['passed'] and 'finish_mae regressed.' in worse_mae['reasons']
    small = accuracy_decision(rows({'rps': -.002}), 'cand', 'live')
    assert not small['passed'] and set(small['sequential']) >= {'loss', 'rps'}


def test_accuracy_gate_falls_back_to_threshold_rps():
    threshold = rows({}, noise=0).drop(columns='rps')
    threshold['threshold_rps'] = threshold[['win_brier', 'podium_brier', 'top10_brier']].mean(axis=1)
    threshold.loc[threshold.arm.eq('cand'), ['win_brier', 'podium_brier', 'top10_brier', 'threshold_rps']] -= .01
    decision = accuracy_decision(threshold, 'cand', 'live')
    assert decision['primary_metric'] == 'threshold_rps' and decision['passed']
    assert not accuracy_decision(rows({}).drop(columns='rps'), 'cand', 'live')['passed']


def test_power_arithmetic():
    assert minimum_detectable_effect(1.0, 6) == pytest.approx(2.486 / np.sqrt(6), rel=1e-3)
    assert races_needed(1.0, minimum_detectable_effect(1.0, 24)) == 24
    table = power_table(paired_races(rows({'rps': -.01}), 'cand', 'live'))
    rps = table.set_index('metric').loc['rps']
    assert rps.improvement_in_sds > 0 and rps.races_to_detect_observed_gain >= 2


def test_e_value_grows_with_consistent_gains_and_not_under_the_null():
    assert betting_e_value([-1.0] * 12, bound=1.0)['candidate_better']
    null = betting_e_value(np.random.default_rng(3).normal(0, .3, 200), bound=1.0)
    assert null['e_value'] < 20
    assert betting_e_value([0.5] * 10, bound=1.0)['e_value'] < 1
    with pytest.raises(ValueError):
        betting_e_value([0.1], bound=0)
