import pandas as pd
import pytest

from src.accuracy_benchmark import build_replay_inputs
from src.accuracy_candidates import decouple_feature_dnf, normalise_historical_pace
from tests.test_accuracy_benchmark import races


def test_dnf_correction_changes_only_failure_prior_not_pace_or_uncertainty():
    features = pd.DataFrame({'Driver': ['A', 'B'], 'dnf_prob': [.04, .08],
        'relative_pace': [0., 1.], 'clean_laps': [20, 2], 'lap_std': [.2, 3.],
        'model_uncertainty': [1., 2.]})
    original = features.copy()
    corrected = decouple_feature_dnf(features)
    assert corrected.dnf_prob.eq(.045).all()
    pd.testing.assert_frame_equal(corrected.drop(columns='dnf_prob'), features.drop(columns='dnf_prob'))
    pd.testing.assert_frame_equal(features, original)


def test_equal_percentage_gaps_are_equal_at_target_circuit():
    def frame(seconds):
        return pd.DataFrame({'Driver': ['A', 'B'], 'true_pace': [seconds, seconds * 1.01],
            'relative_pace': [0, seconds * .01], 'model_pace': [0, seconds * .01],
            'dnf_prob': [.05, .06], 'deg_per_lap': [.02, .03]})
    short = normalise_historical_pace(frame(60), 90)
    long = normalise_historical_pace(frame(120), 90)
    assert short.relative_pace.tolist() == pytest.approx([0., .9])
    pd.testing.assert_series_equal(short.relative_pace, long.relative_pace)
    pd.testing.assert_series_equal(short.dnf_prob, frame(60).dnf_prob)
    pd.testing.assert_series_equal(short.deg_per_lap, frame(60).deg_per_lap)
    with pytest.raises(ValueError, match='finite'):
        normalise_historical_pace(frame(60), float('nan'))


def test_replay_isolates_dnf_and_never_reads_target_race_for_reference():
    events = races()
    target = events[2]
    metadata = dict(year=2024, round=3, event=target.event, session='Q')
    legacy, _, _ = build_replay_inputs(target.sessions['Q'], events[:2], metadata=metadata)
    dnf, _, _ = build_replay_inputs(target.sessions['Q'], events[:2], metadata=metadata,
                                   feature_variant='decoupled_dnf_v1')
    for column in ['race_pace_score', 'quali_pace_score', 'strategy_score', 'performance_uncertainty']:
        pd.testing.assert_series_equal(legacy[column], dnf[column])
    first, _, _ = build_replay_inputs(target.sessions['Q'], events[:2], metadata=metadata,
                                     feature_variant='normalised_history_v1')
    target.sessions['R'].laps['LapTimeSeconds'] += 100
    target.sessions['R'].results['Position'] = [2, 1]
    second, _, _ = build_replay_inputs(target.sessions['Q'], events[:2], metadata=metadata,
                                      feature_variant='normalised_history_v1')
    pd.testing.assert_frame_equal(first, second)
    assert first.historical_reference_source.eq('current_session_true_pace').all()
    assert first.dnf_prob.equals(legacy.dnf_prob)
    with pytest.raises(ValueError, match='independent'):
        build_replay_inputs(target.sessions['Q'], events[:2], metadata=metadata,
                             candidate=True, feature_variant='decoupled_dnf_v1')


def test_pre_reference_uses_only_prior_same_event_or_explicit_assumption():
    events = races()
    metadata = dict(year=2024, round=3, event='Unseen GP', session='PRE')
    features, _, _ = build_replay_inputs(None, events[:2], metadata=metadata,
                                        feature_variant='normalised_history_v1')
    assert features.historical_reference_lap_seconds.eq(90).all()
    assert features.historical_reference_source.eq('default_lap_assumption').all()
    metadata['event'] = events[2].event
    features, _, _ = build_replay_inputs(None, events[:2], metadata=metadata,
                                        feature_variant='normalised_history_v1')
    assert features.historical_reference_source.eq('prior_same_event_2024_2').all()
