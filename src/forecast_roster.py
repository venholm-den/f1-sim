"""Keep historical substitute drivers out of target-event forecasts."""
from __future__ import annotations

import pandas as pd
from pathlib import Path


def pre_race_roster(entries_path, metadata, baseline_session, cutoff_utc):
    """Select a complete dated entry-list version available before the cutoff.

    The optional CSV has Year, Round, Driver, Team, PublishedAtUtc, EntryListId.
    Without an eligible list, retain the explicit latest-baseline assumption.
    """
    path = Path(entries_path)
    provenance = {'roster_source': 'latest_baseline_assumption', 'roster_assumed': True,
                  'roster_cutoff_utc': pd.to_datetime(cutoff_utc, utc=True).isoformat()}
    if path.is_file():
        entries = pd.read_csv(path)
        required = {'Year', 'Round', 'Driver', 'Team', 'PublishedAtUtc', 'EntryListId'}
        if not required.issubset(entries):
            raise ValueError('Dated entry lists lack required roster/provenance columns.')
        chosen = entries.loc[pd.to_numeric(entries.Year, errors='coerce').eq(int(metadata['year']))
                             & pd.to_numeric(entries.Round, errors='coerce').eq(int(metadata['round']))].copy()
        if not chosen.empty:
            if not chosen.PublishedAtUtc.astype(str).str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', regex=True).all():
                raise ValueError('Entry-list publication times require an explicit UTC offset.')
            chosen['published'] = pd.to_datetime(chosen.PublishedAtUtc, utc=True, errors='coerce')
            if chosen.published.isna().any() or chosen.EntryListId.isna().any():
                raise ValueError('Invalid entry-list provenance.')
            versions = chosen.groupby('EntryListId').published.nunique()
            if versions.ne(1).any():
                raise ValueError('Each entry-list version must have one publication time.')
            eligible = chosen.loc[chosen.published.le(pd.to_datetime(cutoff_utc, utc=True))]
            if not eligible.empty:
                stamp = eligible.published.max()
                selected = eligible.loc[eligible.published.eq(stamp)]
                if selected.EntryListId.nunique() != 1:
                    raise ValueError('Ambiguous entry-list versions at the same publication time.')
                identifiers = selected.Driver.fillna('').astype(str).str.strip()
                if len(identifiers) < 2 or identifiers.eq('').any() or identifiers.duplicated().any():
                    raise ValueError('Entry-list driver identifiers are missing or duplicated.')
                if 'ExpectedEntrants' not in selected:
                    raise ValueError('Entry-list completeness requires ExpectedEntrants on every row.')
                counts = pd.to_numeric(selected.ExpectedEntrants, errors='coerce')
                if (counts.isna().any() or counts.nunique() != 1
                        or not counts.eq(counts.round()).all() or int(counts.iloc[0]) != len(selected)):
                    raise ValueError('Entry-list completeness count differs from the selected version.')
                teams = selected.Team.fillna('').astype(str).str.strip()
                if teams.eq('').any():
                    raise ValueError('Entry-list teams are missing.')
                import hashlib
                provenance.update(roster_source='dated_entry_list', roster_assumed=False,
                    entry_list_id=str(selected.EntryListId.iloc[0]), expected_entrants=int(counts.iloc[0]),
                    entry_list_published_at_utc=stamp.isoformat(),
                    entry_list_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    roster_teams=dict(zip(identifiers, teams)))
                return identifiers.tolist(), provenance
    return session_roster(baseline_session), provenance


def session_roster(session) -> list[str]:
    results = getattr(session, 'results', pd.DataFrame())
    if 'Abbreviation' in results and not results.empty:
        values = results['Abbreviation']
    else:
        laps = getattr(session, 'laps', pd.DataFrame())
        values = laps.get('Driver', pd.Series(dtype=str))
    values = values.dropna().astype(str).str.strip()
    return list(dict.fromkeys(values[values.ne('')]))


def validate_roster(features: pd.DataFrame, expected: list[str]) -> pd.DataFrame:
    if not expected:
        raise ValueError('No driver roster is available; refusing to forecast.')
    if len(set(expected)) != len(expected) or any(not str(driver).strip() for driver in expected):
        raise ValueError('Expected roster identifiers are missing or duplicated.')
    if features['Driver'].isna().any() or features['Driver'].duplicated().any():
        raise ValueError('Model driver identifiers are missing or duplicated.')
    missing = set(expected) - set(features['Driver'])
    if missing:
        raise ValueError(f'Roster drivers lack model features: {sorted(missing)}')
    return features.set_index('Driver').loc[expected].reset_index()
