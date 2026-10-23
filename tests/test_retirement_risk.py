from types import SimpleNamespace
import pandas as pd
import pytest

from src.retirement_risk import apply_retirement_risk
from src.accuracy_candidates import single_pace_blend, candidate_grid_multiplier
from src.accuracy_benchmark import build_replay_inputs
from tests.test_accuracy_benchmark import races


def test_retirement_risk_uses_prior_outcomes_not_lap_quality_and_keeps_unknown_causes():
    session = SimpleNamespace(results=pd.DataFrame({'Abbreviation': ['A', 'B', 'C', 'D'],
        'TeamName': ['T'] * 4, 'Status': ['Lapped', 'Retired', 'Did not start', 'Mystery']}))
    recent = [(session, {'year': 2024, 'round': 1, 'event': 'GP'})]
    features = pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T'], 'lap_std': [1, 99]})
    meta = {'year': 2024, 'round': 2, 'event': 'GP'}
    output = apply_retirement_risk(features, recent, meta)
    assert output.retirement_known_observations.eq(2).all()
    assert output.retirement_unknown_observations.eq(2).all()
    assert output.loc[1, 'dnf_prob'] > output.loc[0, 'dnf_prob']
    features.lap_std = [999, 0]
    pd.testing.assert_series_equal(output.dnf_prob, apply_retirement_risk(features, recent, meta).dnf_prob)
    columns = ['retirement_mechanical_dnf_prob', 'retirement_non_mechanical_dnf_prob', 'retirement_unspecified_dnf_prob']
    assert (output[columns].sum(axis=1) - output.dnf_prob).abs().max() < 1e-12
    with pytest.raises(ValueError, match='cutoff'):
        apply_retirement_risk(features, recent, {'year': 2024, 'round': 1})
    with pytest.raises(ValueError, match='unique'):
        apply_retirement_risk(features, recent + recent, meta)


def test_single_blend_applies_quality_once_and_leaves_other_signals_alone():
    features = pd.DataFrame({'current_relative_pace_capped': [0., 2.], 'baseline_relative_pace': [1., 0.],
        'current_signal_quality': [.5, 1.], 'race_pace_score': [1., 0.], 'long_run_pace_score': [1.2, .5],
        'projected_lap_time': [81., 80.], 'dnf_prob': [.04, .05]})
    result = single_pace_blend(features, 'Q')
    assert result.race_weight_used.tolist() == [.1, .2]
    assert result.race_pace_score.tolist() == pytest.approx([.5, 0.])
    assert result.dnf_prob.equals(features.dnf_prob)
    assert candidate_grid_multiplier('q_grid_3_3_v1', 'Q') == 3.3
    assert candidate_grid_multiplier('q_grid_3_3_v1', 'PRE') is None


def test_new_candidates_never_read_target_race_results_or_laps():
    data = races()
    target = data[2]
    meta = dict(year=2024, round=3, event=target.event, session='Q')
    before = {variant: build_replay_inputs(target.sessions['Q'], data[:2], metadata=meta,
        feature_variant=variant)[0] for variant in ['all_cause_dnf_v2', 'single_pace_blend_v1']}
    target.sessions['R'].results['Status'] = 'Engine'
    target.sessions['R'].laps['LapTimeSeconds'] = 999
    for variant, expected in before.items():
        actual = build_replay_inputs(target.sessions['Q'], data[:2], metadata=meta, feature_variant=variant)[0]
        pd.testing.assert_frame_equal(expected, actual)
