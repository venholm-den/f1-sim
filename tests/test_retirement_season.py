from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.accuracy_benchmark import build_replay_inputs
from src.retirement_season import (MAX_STRENGTH, PROBABILITY_CAP, apply_season_retirement_risk,
                                   shrinkage_strength)
from src.simulate import simulate_races
from tests.test_accuracy_benchmark import races

DRIVERS = [f'D{i}' for i in range(20)]
TEAMS = [f'T{i // 2}' for i in range(20)]


def season(year, rounds, retired):
    """retired(round, driver index) -> bool."""
    history = []
    for rnd in range(1, rounds + 1):
        status = ['Retired' if retired(rnd, i) else 'Finished' for i in range(20)]
        results = pd.DataFrame({'Abbreviation': DRIVERS, 'TeamName': TEAMS, 'Status': status,
                                'ClassifiedPosition': ['R' if s == 'Retired' else str(i + 1)
                                                       for i, s in enumerate(status)]})
        history.append((SimpleNamespace(results=results), {'year': year, 'round': rnd}))
    return history


def features():
    return pd.DataFrame({'Driver': DRIVERS, 'Team': TEAMS, 'dnf_prob': .04})


def test_concentrated_retirements_follow_the_car_and_spread_ones_pool():
    # One car retires almost every race; everyone else rarely.
    concentrated = season(2026, 16, lambda rnd, i: i == 0 and rnd % 8 or (i + rnd) % 19 == 0)
    output = apply_season_retirement_risk(features(), concentrated, {'year': 2026, 'round': 17})
    assert output.loc[0, 'dnf_prob'] > .45
    assert output.loc[19, 'dnf_prob'] < .12
    assert output.retirement_driver_shrinkage_entries.iloc[0] < 30
    # Evenly spread retirements carry no driver signal, so every driver lands near the field rate.
    spread = season(2025, 16, lambda rnd, i: (i * 7 + rnd * 3) % 10 == 0)
    output = apply_season_retirement_risk(features(), spread, {'year': 2025, 'round': 17})
    assert output.dnf_prob.max() - output.dnf_prob.min() < .03
    assert output.dnf_prob.mean() == pytest.approx(output.retirement_field_prob.iloc[0], abs=.01)


def test_field_rate_starts_from_earlier_seasons_and_moves_with_this_one():
    earlier = season(2025, 10, lambda rnd, i: i % 10 == 0)  # 10% of starters
    output = apply_season_retirement_risk(features(), earlier, {'year': 2026, 'round': 1})
    assert output.retirement_season_observations.eq(0).all()
    assert output.dnf_prob.to_numpy() == pytest.approx(np.full(20, .10))
    now = earlier + season(2026, 6, lambda rnd, i: i % 2 == 0)  # 50% this year
    output = apply_season_retirement_risk(features(), now, {'year': 2026, 'round': 7})
    assert .10 < output.retirement_field_prob.iloc[0] < .50


def test_lap_quality_never_moves_retirement_risk_and_history_must_precede_target():
    history = season(2026, 5, lambda rnd, i: i == 3)
    meta = {'year': 2026, 'round': 6}
    first = apply_season_retirement_risk(features().assign(lap_std=1.), history, meta)
    second = apply_season_retirement_risk(features().assign(lap_std=99.), history, meta)
    pd.testing.assert_series_equal(first.dnf_prob, second.dnf_prob)
    with pytest.raises(ValueError, match='cutoff'):
        apply_season_retirement_risk(features(), history, {'year': 2026, 'round': 5})
    with pytest.raises(ValueError, match='unique'):
        apply_season_retirement_risk(features(), history + history[:1], meta)


def test_unknown_outcomes_are_not_counted_and_classified_r_is_a_retirement():
    results = pd.DataFrame({'Abbreviation': ['A', 'B', 'C', 'D'], 'TeamName': ['T'] * 4,
                            'Status': ['Lapped', 'Lapped', 'Did not start', 'Mystery'],
                            'ClassifiedPosition': ['1', 'R', 'W', '4']})
    output = apply_season_retirement_risk(pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T']}),
        [(SimpleNamespace(results=results), {'year': 2026, 'round': 1})], {'year': 2026, 'round': 2})
    assert output.retirement_season_observations.eq(2).all()
    assert output.retirement_driver_season_retirements.tolist() == [0, 1]


def test_shrinkage_strength_is_large_without_real_spread():
    assert shrinkage_strength([2, 2, 2, 2], [20, 20, 20, 20], .1) == MAX_STRENGTH
    assert shrinkage_strength([15, 1, 1, 1], [20, 20, 20, 20], .225) < 10


def test_engine_honours_the_declared_cap_and_keeps_the_old_one_otherwise():
    data = races()
    meta = dict(year=2024, round=3, event=data[2].event, session='Q')
    base, track, _ = build_replay_inputs(data[2].sessions['Q'], data[:2], metadata=meta)
    high = base.assign(reliability_score=.7, dnf_prob=.7)
    capped, _, _ = simulate_races(high, n_sims=400, seed=1)
    assert capped.dnf_chance.max() < .40
    declared, _, _ = simulate_races(high.assign(retirement_probability_cap=PROBABILITY_CAP), n_sims=400, seed=1)
    assert declared.dnf_chance.mean() > .6
    unchanged, _, _ = simulate_races(base, n_sims=400, seed=1)
    pd.testing.assert_frame_equal(unchanged, simulate_races(base.assign(retirement_probability_cap=.30),
                                                            n_sims=400, seed=1)[0])


def test_replay_variant_never_reads_the_target_race():
    data = races()
    target = data[2]
    meta = dict(year=2024, round=3, event=target.event, session='Q')
    before = build_replay_inputs(target.sessions['Q'], data[:2], metadata=meta, feature_variant='season_dnf_v1')[0]
    target.sessions['R'].results['Status'] = 'Engine'
    after = build_replay_inputs(target.sessions['Q'], data[:2], metadata=meta, feature_variant='season_dnf_v1')[0]
    pd.testing.assert_frame_equal(before, after)
    assert before.retirement_model_version.eq('season_outcomes_v1_experimental').all()
