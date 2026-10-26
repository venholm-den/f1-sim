from pathlib import Path

import pandas as pd
import pytest

from src.retirement_evidence import apply_outcome_evidence
from src.result_status import retirement_outcome


def test_late_retirement_and_lapped_finishers_need_explicit_evidence():
    result = pd.DataFrame({'Abbreviation': ['NOR'], 'Status': ['Lapped'], 'ClassifiedPosition': ['20']})
    annotated = apply_outcome_evidence(result, {'year': 2024, 'round': 11, 'event': 'Austrian Grand Prix'})
    assert annotated.VerifiedRetirement.tolist() == [1.]
    assert retirement_outcome(next(annotated.itertuples())) == 1.
    assert 'VerifiedRetirement' not in result
    canada = pd.DataFrame({'Abbreviation': ['STR', 'BOT'], 'Status': ['Lapped']*2,
                           'ClassifiedPosition': ['15', '16']})
    annotated = apply_outcome_evidence(canada, {'year': 2026, 'round': 5, 'event': 'Canadian Grand Prix'})
    assert annotated.VerifiedRetirement.tolist() == [0., 0.]
    assert [retirement_outcome(row) for row in annotated.itertuples()] == [0., 0.]


def test_evidence_refuses_changed_source_or_another_event():
    result = pd.DataFrame({'Abbreviation': ['NOR'], 'Status': ['Lapped'], 'ClassifiedPosition': ['19']})
    with pytest.raises(ValueError, match='provider values changed'):
        apply_outcome_evidence(result, {'year': 2024, 'round': 11, 'event': 'Austrian Grand Prix'})
    assert apply_outcome_evidence(result, {'year': 2024, 'round': 11, 'event': 'Other GP'}) is result


def test_duplicate_or_unattributed_evidence_is_rejected(tmp_path):
    source = Path('data/retirement_labels/verified_outcomes_v1.csv')
    evidence = pd.read_csv(source)
    path = tmp_path/'evidence.csv'
    pd.concat([evidence, evidence.iloc[:1]]).to_csv(path, index=False)
    with pytest.raises(ValueError, match='duplicate'):
        apply_outcome_evidence(pd.DataFrame(), {'year': 2024, 'round': 1}, path=path)
    evidence.loc[0, 'SourceURL'] = 'https://unverified.example/guess'
    evidence.to_csv(path, index=False)
    with pytest.raises(ValueError, match='primary-source'):
        apply_outcome_evidence(pd.DataFrame(), {'year': 2024, 'round': 1}, path=path)
