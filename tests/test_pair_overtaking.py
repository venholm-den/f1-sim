import numpy as np
import pandas as pd
import pytest

from src.accuracy_candidates import candidate_simulation_options
from src.agent_race import AgentSettings
from src.pair_overtaking import (COEFFICIENTS, fit_logistic, fit_model, lap_probability, load_model,
                                 pair_laps, predict)
from src.simulate import simulate_races
from tests.test_agent_race import run
from tests.test_simulate import _minimal_features


def _lap(driver, lap, start, time, *, status='1', compound='MEDIUM', life=5, pit_in=False):
    return {'Driver': driver, 'LapNumber': lap, 'LapStartTimeSeconds': start, 'LapTimeSeconds': time,
            'TrackStatus': status, 'PitIn': pit_in, 'PitOut': False, 'Compound': compound, 'TyreLife': life}


def _race(pass_on_lap=4, status_on_pass='1'):
    rows = []
    for driver, offset, pace in (('AAA', 0., 91.), ('BBB', .9, 90.95)):
        start = offset
        for lap in range(1, 9):
            time = pace
            if driver == 'BBB' and lap == pass_on_lap:
                time = 89.
            rows.append(_lap(driver, lap, start, time, status=status_on_pass if lap == pass_on_lap else '1',
                             life=lap + (0 if driver == 'AAA' else -2)))
            start += time
    return pd.DataFrame(rows)


def test_pair_laps_label_a_reversal_with_follower_advantage_features():
    pairs = pair_laps(_race(), difficulty=.65)
    assert pairs.passed.sum() == 1
    passed = pairs[pairs.passed.eq(1)].iloc[0]
    assert (passed.leader, passed.follower, passed.lap) == ('AAA', 'BBB', 4)
    assert passed.pace_delta == pytest.approx(.05)  # follower slightly faster
    assert passed.tyre_age_delta == pytest.approx(2.)  # follower on fresher tyres
    assert passed.track == pytest.approx(.10)
    # After the pass BBB leads; the gap grows past the close-pair window.
    assert (pairs.lap < 5).all()


def test_non_green_and_pit_laps_are_not_observations():
    assert pair_laps(_race(status_on_pass='4'), difficulty=.55).query('lap == 4').empty
    race = _race()
    race.loc[(race.Driver == 'AAA') & (race.LapNumber == 4), 'PitIn'] = True
    assert pair_laps(race, difficulty=.55).query('lap == 4').empty


def test_logistic_fit_recovers_known_coefficients():
    rng = np.random.default_rng(3)
    n = 20_000
    data = pd.DataFrame({'pace_delta': rng.normal(0, 1, n), 'tyre_age_delta': rng.normal(0, 6, n),
                         'softness_delta': rng.integers(-1, 2, n), 'track': rng.uniform(-.2, .3, n)})
    truth = np.array([-2., 1.2, .06, .3, -3.])
    data['passed'] = (rng.random(n) < predict(data, truth)).astype(int)
    beta, se = fit_logistic(data, ridge=0.)
    assert np.all(np.abs(beta - truth) < 4 * se)


def test_saved_model_has_expected_signs_and_probability_responds_per_pair():
    model = load_model()
    assert model['pace'] > 0 and model['tyre_age'] > 0 and model['track'] < 0
    base = lap_probability(model, 0., 0., 0.)
    assert lap_probability(model, 1., 0., 0.) > base
    assert lap_probability(model, 0., 10., 0.) > base
    assert lap_probability({**model, 'track_difficulty': .85}, 1., 0., 0.) < lap_probability(model, 1., 0., 0.)
    assert 0 < base < .5


def test_fit_model_reports_provenance_counts():
    pairs = pd.concat([pair_laps(_race(p), .55).assign(year=2026, round=p) for p in (3, 4, 5)])
    model = fit_model(pairs)
    assert set(COEFFICIENTS) <= set(model)
    assert model['passes'] == 3 and model['races'] == ['2026-03', '2026-04', '2026-05']


def test_agent_settings_resolve_and_validate_pair_model():
    assert AgentSettings(pair_pass_model='pair_overtaking_v1').pair_pass_model['pace'] > 0
    with pytest.raises(ValueError):
        AgentSettings(pair_pass_model='unknown')
    with pytest.raises(ValueError):
        AgentSettings(pair_pass_model={'intercept': 0.})
    with pytest.raises(ValueError):
        AgentSettings(pair_pass_model={**dict.fromkeys(COEFFICIENTS, 0.), 'pace': np.nan})


def test_pair_model_decides_whether_a_faster_car_gets_past():
    never = {**dict.fromkeys(COEFFICIENTS, 0.), 'intercept': -50.}
    always = {**dict.fromkeys(COEFFICIENTS, 0.), 'intercept': 50.}
    blocked = run(laps=20, settings={'pair_pass_model': never, 'following_laps': 0.}, trace=False)
    permitted = run(laps=20, settings={'pair_pass_model': always, 'following_laps': 0.,
                                       'passability': 0.}, trace=False)
    assert blocked['overtakes'].sum() == 0
    # passability is ignored once a pair model is set.
    assert permitted['overtakes'][0, 1] >= 1


def test_candidate_variant_runs_through_simulate_races_with_track_difficulty():
    features = _minimal_features()
    options = candidate_simulation_options('agent_pair_overtaking_v1', features)
    assert options['agent_settings'] == {'pair_pass_model': 'pair_overtaking_v1'}
    summary, _, raw = simulate_races(features, n_sims=40, seed=5, overtaking_difficulty=.7, **options)
    assert len(summary) == len(features) and raw.race_engine.eq('agent_laps_v1').all()
    assert np.isclose(summary.win_chance.sum(), 1.)
