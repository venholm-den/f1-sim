"""Experimental all-cause retirement prior, independent of pace sample quality."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.result_status import NONFINISH_CLASSES, classify_result_status, retirement_label


def apply_retirement_risk(features, recent_races, metadata):
    """Use earlier race outcomes only; hyperparameters are explicit assumptions.

    Team, driver and circuit estimates share a shrunk population prior rather
    than adding overlapping failure probabilities. Cause shares are descriptive;
    a generic retirement remains unspecified, never a healthy engine outcome.
    """
    target = int(metadata['year']), int(metadata['round'])
    races = sorted(recent_races, key=lambda item: (int(item[1]['year']), int(item[1]['round'])), reverse=True)
    keys = [(int(meta['year']), int(meta['round'])) for _, meta in races]
    if len(set(keys)) != len(keys) or any(key >= target for key in keys):
        raise ValueError('Retirement history must contain unique races strictly before the target cutoff.')
    rows = []
    for age, (session, meta) in enumerate(races):
        results = getattr(session, 'results', pd.DataFrame())
        if not {'Abbreviation', 'TeamName', 'Status'}.issubset(results):
            continue
        if results.Abbreviation.duplicated().any():
            raise ValueError('Retirement history has duplicate driver/race observations.')
        for row in results.itertuples():
            rows.append({'Driver': str(row.Abbreviation), 'Team': str(row.TeamName).strip().casefold(),
                'circuit': str(meta.get('circuit_id') or meta.get('venue', {}).get('circuit_id')
                               or meta.get('event', '')).strip().casefold(),
                'label': retirement_label(row.Status), 'cause': classify_result_status(row.Status),
                'weight': .5 ** (age / 8.)})
    history = pd.DataFrame(rows, columns=['Driver', 'Team', 'circuit', 'label', 'cause', 'weight'])
    known = history.loc[history.label.notna()]
    # This 10% fallback is a declared prior, not fitted to the inspected seven races.
    global_prior = ((known.label * known.weight).sum() + .10 * 40) / (known.weight.sum() + 40)

    def rate(column, value, strength):
        group = known.loc[known[column].eq(value)]
        return ((group.label * group.weight).sum() + strength * global_prior) / (group.weight.sum() + strength)

    output = features.copy()
    output['retirement_prior_prob'] = global_prior
    circuit = str(metadata.get('circuit_id') or metadata.get('venue', {}).get('circuit_id')
                  or metadata.get('event', '')).strip().casefold()
    output['retirement_team_prob'] = [rate('Team', str(team).strip().casefold(), 20) for team in output.Team]
    output['retirement_driver_prob'] = [rate('Driver', str(driver), 12) for driver in output.Driver]
    output['retirement_circuit_prob'] = rate('circuit', circuit, 40)
    output['dnf_prob'] = (.5 * output.retirement_team_prob + .3 * output.retirement_driver_prob
                          + .2 * output.retirement_circuit_prob).clip(.005, .30)
    output['reliability_score'] = output.dnf_prob
    retirements = known.loc[known.cause.isin(NONFINISH_CLASSES)]
    # Dirichlet shrinkage for cause shares keeps missing/unspecified causes explicit.
    denominator = retirements.weight.sum() + 3
    for cause in sorted(NONFINISH_CLASSES):
        share = (retirements.loc[retirements.cause.eq(cause), 'weight'].sum() + 1) / denominator
        output[f'retirement_{cause}_prob'] = output.dnf_prob * share
    output['retirement_known_observations'] = len(known)
    output['retirement_unknown_observations'] = len(history) - len(known)
    output['retirement_history_races'] = len(races)
    output['retirement_model_version'] = 'all_cause_shrunk_v1_experimental'
    return output
