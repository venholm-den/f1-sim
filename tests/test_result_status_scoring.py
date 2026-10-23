from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from src.backtest import _extract_actual_results_from_race_session, _calculate_basic_actual_fantasy, _brier
from src.app_services.discord_reports import analysis_summary


def test_post_race_classification_uses_shared_policy_and_keeps_unknown_labels():
    session = SimpleNamespace(results=pd.DataFrame({'Abbreviation': list('ABCDE'), 'Position': range(1, 6),
        'Status': ['Lapped', 'Retired', 'Electrical', 'Did not start', 'Mystery']}))
    actual = _extract_actual_results_from_race_session(session)
    assert actual.actual_dnf.iloc[:3].tolist() == [False, True, True]
    assert actual.actual_dnf.iloc[3:].isna().all()
    assert np.isnan(_calculate_basic_actual_fantasy(pd.Series({'actual_dnf': pd.NA})))


def test_discord_retirement_context_counts_only_known_outcomes():
    comparison = pd.DataFrame({'avg_finish': [1., 2., 3.], 'actual_position': [1, 2, 3],
        'actual_dnf': [False, True, np.nan]})
    summary = analysis_summary(comparison)
    assert summary['retirements'] == 1 and summary['non_retirements'] == 1
    assert summary['unknown_retirement_labels'] == 1


def test_brier_does_not_count_unknown_outcomes_as_failures_or_finishes():
    assert _brier(pd.Series([.1, .99]), pd.Series([0, np.nan])) == pytest.approx(.01)
