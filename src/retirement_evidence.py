"""Small, source-backed outcome annotations; original provider rows stay intact."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

EVIDENCE_PATH = 'data/retirement_labels/verified_outcomes_v1.csv'
EVIDENCE_COLUMN = 'VerifiedRetirement'


def apply_outcome_evidence(results, metadata, *, path=None):
    """Annotate matching historical rows only after verifying their raw values.

    This does not download anything, change status/position or infer cause.
    Event identity and expected provider fields prevent stale corrections from
    silently applying to another race or a revised result.
    """
    from src.app_services.app_paths import resource_path
    path = Path(path) if path is not None else resource_path(EVIDENCE_PATH)
    if not path.is_file():
        return results
    evidence = pd.read_csv(path, dtype={'Driver': str, 'ExpectedStatus': str,
                                       'ExpectedClassifiedPosition': str})
    required = {'Year', 'Round', 'Event', 'Driver', 'Retired', 'ExpectedStatus',
                'ExpectedClassifiedPosition', 'SourceURL', 'SourceNote'}
    if required-set(evidence) or evidence.duplicated(['Year', 'Round', 'Driver']).any():
        raise ValueError('Invalid or duplicate retirement outcome evidence.')
    if (evidence.Retired.isna().any() or not evidence.Retired.isin([0, 1]).all()
            or evidence[list(required)].isna().any().any()):
        raise ValueError('Retirement evidence requires known labels and provenance.')
    for url in evidence.SourceURL:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'www.fia.com', 'api.fia.com', 'www.formula1.com'}:
            raise ValueError('Retirement evidence must name a primary-source HTTPS page.')
    selected = evidence[evidence.Year.eq(int(metadata['year']))
                        & evidence.Round.eq(int(metadata['round']))
                        & evidence.Event.eq(str(metadata.get('event', '')))]
    if selected.empty:
        return results
    output = results.copy()
    if EVIDENCE_COLUMN not in output:
        output[EVIDENCE_COLUMN] = np.nan
    for row in selected.itertuples():
        matched = output.Abbreviation.eq(row.Driver)
        if matched.sum() != 1:
            raise ValueError('Retirement evidence driver coverage differs.')
        original = output.loc[matched].iloc[0]
        classification = str(original.get('ClassifiedPosition', '')).strip().removesuffix('.0')
        if (str(original.get('Status', '')).strip() != row.ExpectedStatus
                or classification != row.ExpectedClassifiedPosition):
            raise ValueError('Retirement evidence provider values changed; review required.')
        output.loc[matched, EVIDENCE_COLUMN] = float(row.Retired)
    return output
