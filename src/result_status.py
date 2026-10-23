"""Shared race outcome semantics. A non-finish does not identify its cause."""
from __future__ import annotations

import re
import numpy as np
import pandas as pd

STATUS_POLICY_VERSION = 'race_outcomes_v2'
NONFINISH_CLASSES = {'mechanical_dnf', 'non_mechanical_dnf', 'unspecified_dnf'}
MECHANICAL_WORDS = ('brake', 'clutch', 'electrical', 'electronics', 'engine',
    'gearbox', 'hydraulic', 'mechanical', 'oil', 'overheating', 'power unit',
    'powerunit', 'puncture', 'radiator', 'suspension', 'transmission', 'water leak')
INCIDENT_WORDS = ('accident', 'collision', 'crash', 'damage', 'spun off')


def classify_result_status(status) -> str:
    if status is None or pd.isna(status):
        return 'unknown'
    text = ' '.join(str(status).strip().lower().replace('_', ' ').split())
    if text in {'finished', 'lapped'} or re.fullmatch(r'\+\s*\d+\s*lap(?:s)?', text):
        return 'finished'
    if text in {'did not start', 'dns', 'withdrawn', 'did not qualify', 'did not prequalify'}:
        return 'did_not_start'
    if text in {'disqualified', 'excluded', 'dsq', 'dq'}:
        return 'disqualified'
    if any(word in text for word in INCIDENT_WORDS):
        return 'non_mechanical_dnf'
    if any(word in text for word in MECHANICAL_WORDS):
        return 'mechanical_dnf'
    if text in {'retired', 'retirement', 'dnf', 'not classified', 'power loss', 'rear wing', 'illness'}:
        return 'unspecified_dnf'
    return 'unknown'


def retirement_label(status) -> float:
    outcome = classify_result_status(status)
    if outcome == 'finished':
        return 0.0
    return 1.0 if outcome in NONFINISH_CLASSES else np.nan


def mechanical_label(status) -> float:
    outcome = classify_result_status(status)
    if outcome == 'mechanical_dnf':
        return 1.0
    if outcome in {'finished', 'non_mechanical_dnf'}:
        return 0.0
    return np.nan
