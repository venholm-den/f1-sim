from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts.benchmark_retirement_models import audit_labels, decisions
from src.feature_ablation_benchmark import evaluate_with_dnf
from src.retirement_season import apply_season_retirement_risk
from src.retirement_risk import apply_retirement_risk


def results():
    return pd.DataFrame({'Abbreviation': ['A', 'B', 'C', 'D'], 'TeamName': ['T']*4,
        'Position': [1, 2, 3, 4], 'Status': ['Lapped', 'Turbo', 'Brakes', 'Mystery'],
        'ClassifiedPosition': ['1', 'R', 'W', '4'], 'Laps': [70, 60, 0, 65]})


def test_models_and_benchmark_agree_on_classified_retirements_and_exclusions():
    actual = results()
    history = [(SimpleNamespace(results=actual), {'year': 2026, 'round': 1})]
    features = pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T']})
    season = apply_season_retirement_risk(features, history, {'year': 2026, 'round': 2})
    assert season.retirement_season_observations.eq(2).all()
    assert season.retirement_driver_season_retirements.tolist() == [0, 1]
    cause = apply_retirement_risk(features, history, {'year': 2026, 'round': 2})
    assert cause.retirement_known_observations.eq(2).all()
    prediction = pd.DataFrame({'Driver': list('ABCD'), 'avg_finish': [1., 2., 3., 4.],
        'win_chance': [1., 0., 0., 0.], 'podium_chance': [1., 1., 1., 0.],
        'points_chance': [1.]*4, 'dnf_chance': [.1, .9, .99, .99]})
    metrics, scored = evaluate_with_dnf(prediction, actual)
    assert scored.actual_dnf.iloc[:2].tolist() == [0., 1.]
    assert scored.actual_dnf.iloc[2:].isna().all()
    assert metrics['dnf_known_drivers'] == 2 and np.isclose(metrics['dnf_brier'], .01)


def test_lap_deficit_alone_does_not_change_the_season_model():
    actual = results().iloc[:2].copy()
    actual['Status'] = 'Lapped'
    actual['ClassifiedPosition'] = ['1', '2']
    data = pd.DataFrame({'Driver': ['A', 'B'], 'Team': ['T', 'T']})
    first = apply_season_retirement_risk(data, [(SimpleNamespace(results=actual), {'year': 2026, 'round': 1})],
                                         {'year': 2026, 'round': 2})
    assert first.retirement_driver_season_retirements.eq(0).all()
    audited = audit_labels([SimpleNamespace(year=2026, round=1, event='GP',
                                            sessions={'R': SimpleNamespace(results=results())})])
    assert audited.actual_dnf.iloc[:2].tolist() == [0., 1.]
    assert audited.actual_dnf.iloc[2:].isna().all()


def test_diagnostic_screen_keeps_q_baseline_and_never_promotes():
    rows, baselines = [], []
    for year, split in ((2024, 'development'), (2025, 'previously_seen_diagnostic')):
        for stage in ('PRE', 'FP2', 'Q'):
            for rnd in range(1, 7):
                key = dict(year=year, round=rnd, session=stage, split=split)
                baselines.append({**key, 'finish_mae': 2.9})
                for arm in ('established', 'all_cause_dnf_v2', 'season_dnf_v1', 'season_grid_dnf_v1'):
                    new = arm != 'established'
                    rows.append({**key, 'arm': arm, 'rps': .18 if new else .20,
                        'finish_mae': 3.9 if new else 4., 'finishers_finish_mae': 3.,
                        'dnf_brier': .10 if new else .12, 'win_brier': .03,
                        'podium_brier': .08, 'top10_brier': .15})
    result = decisions(pd.DataFrame(rows), pd.DataFrame(baselines))
    assert all(row['fresh_races'] == 0 and row['promotion_approved'] is False for row in result)
    assert all(row['diagnostic_decision'] == 'collect_fresh_evidence' for row in result if row['stage'] != 'Q')
    assert all('does_not_beat_qualifying_order' in row['reasons'] for row in result if row['stage'] == 'Q')
