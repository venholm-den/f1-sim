import pandas as pd

from src.features import build_driver_features
from src.long_run_pace import estimate_long_run_pace
from src.performance import add_performance_profile


def practice_laps():
    rows = []
    for driver, quick, long in [('A', 80, 92), ('B', 81, 90)]:
        for lap in range(1, 13):
            sprint = lap <= 4
            rows.append({'Driver': driver, 'Team': driver, 'Compound': 'SOFT' if sprint else 'MEDIUM',
                'Stint': 1 if sprint else 2, 'LapNumber': lap, 'TyreLife': lap if sprint else lap - 4,
                'LapTimeSeconds': quick if sprint else long + .03 * (lap - 4),
                'LapStartTimeSeconds': 100 + lap * 100, 'IsAccurate': True,
                'TrackStatus': '1', 'FreshTyre': True})
    return pd.DataFrame(rows)


def test_long_runs_are_retained_despite_fast_lap_filter():
    legacy = build_driver_features(practice_laps()).set_index('Driver')
    revised = build_driver_features(practice_laps(), use_stint_pace=True).set_index('Driver')
    assert legacy.loc['A', 'clean_laps'] == 4
    assert revised.loc['A', 'long_run_laps'] == 8
    assert revised.loc['A', 'long_run_relative_pace'] > revised.loc['B', 'long_run_relative_pace']
    assert revised.loc['A', 'dnf_prob'] == revised.loc['B', 'dnf_prob'] == .045


def test_unmatched_times_and_compounds_do_not_create_precise_pace():
    laps = practice_laps().query('Stint == 2').copy()
    laps.loc[laps.Driver.eq('B'), 'LapStartTimeSeconds'] += 3600
    assert estimate_long_run_pace(laps).empty
    laps = practice_laps().query('Stint == 2').copy()
    laps.loc[laps.Driver.eq('B'), 'Compound'] = 'HARD'
    assert estimate_long_run_pace(laps).empty


def test_sparse_runs_keep_risk_prior_and_reduce_confidence():
    sparse = practice_laps().query('Stint == 1')
    features = build_driver_features(sparse, use_stint_pace=True)
    assert features.long_run_confidence.eq(0).all()
    assert features.dnf_prob.eq(.045).all()


def test_performance_uses_long_run_order_independently_of_fast_laps():
    current = build_driver_features(practice_laps(), use_stint_pace=True)
    model = pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['A', 'B'], 'model_pace': [0., 0.],
        'relative_pace': [0., 1.], 'current_relative_pace_capped': [0., 1.],
        'baseline_relative_pace': [0., 0.], 'current_signal_quality': [.5, .5]})
    output = add_performance_profile(model, current, current_session_type='FP2').set_index('Driver')
    assert output.loc['A', 'race_pace_score'] > output.loc['B', 'race_pace_score']
    assert output.loc['A', 'quali_pace_score'] < output.loc['B', 'quali_pace_score']
