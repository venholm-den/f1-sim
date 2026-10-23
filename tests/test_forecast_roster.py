from types import SimpleNamespace

import pandas as pd
import pytest

from src.forecast_roster import session_roster, validate_roster, pre_race_roster


def test_classification_includes_driver_without_laps_and_removes_old_substitute():
    session = SimpleNamespace(results=pd.DataFrame({'Abbreviation': ['A', 'B']}),
                              laps=pd.DataFrame({'Driver': ['A']}))
    features = pd.DataFrame({'Driver': ['A', 'B', 'OLD'], 'relative_pace': [0, 1, 2]})
    assert validate_roster(features, session_roster(session)).Driver.tolist() == ['A', 'B']


def test_missing_driver_and_duplicates_fail_closed():
    with pytest.raises(ValueError, match='lack model features'):
        validate_roster(pd.DataFrame({'Driver': ['A']}), ['A', 'B'])
    with pytest.raises(ValueError, match='duplicated'):
        validate_roster(pd.DataFrame({'Driver': ['A', 'A']}), ['A'])
    with pytest.raises(ValueError, match='No driver roster'):
        validate_roster(pd.DataFrame({'Driver': ['A']}), [])


def test_pre_roster_selects_dated_version_without_future_entries(tmp_path):
    path = tmp_path/'entries.csv'
    pd.DataFrame([dict(Year=2026, Round=3, Driver=driver, Team='T', PublishedAtUtc=stamp, EntryListId=version, ExpectedEntrants=2)
        for version, stamp, drivers in [('old', '2026-01-01T00:00:00Z', ['A', 'B']),
                                       ('new', '2026-01-03T00:00:00Z', ['A', 'C'])]
        for driver in drivers]).to_csv(path, index=False)
    meta = {'year': 2026, 'round': 3}
    roster, evidence = pre_race_roster(path, meta, None, '2026-01-02T00:00:00Z')
    assert roster == ['A', 'B'] and not evidence['roster_assumed']
    assert evidence['entry_list_id'] == 'old' and evidence['entry_list_sha256']
    baseline = SimpleNamespace(results=pd.DataFrame({'Abbreviation': ['X', 'Y']}))
    roster, evidence = pre_race_roster(path, meta, baseline, '2025-12-31T00:00:00Z')
    assert roster == ['X', 'Y'] and evidence['roster_assumed']


@pytest.mark.parametrize('count', [None, 3, 2.5, 'unknown'])
def test_incomplete_entry_versions_cannot_claim_verified_coverage(tmp_path, count):
    path = tmp_path/'entries.csv'
    rows = pd.DataFrame({'Year': [2026]*2, 'Round': [3]*2, 'Driver': ['A','B'],
        'Team': ['T']*2, 'PublishedAtUtc': ['2026-01-01T00:00:00Z']*2, 'EntryListId': ['v1']*2})
    if count is not None:
        rows['ExpectedEntrants'] = count
    rows.to_csv(path, index=False)
    with pytest.raises(ValueError, match='completeness'):
        pre_race_roster(path, {'year':2026,'round':3}, None, '2026-01-02T00:00:00Z')
