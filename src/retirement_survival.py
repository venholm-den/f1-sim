"""Experimental discrete competing-risk hazards with finished races censored.

Ten race-distance intervals and three cause categories. Unspecified retirements
remain their own cause; DNS, disqualification and unknown outcomes do not enter
the risk set. Declared shrinkage is not a calibration claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.result_status import NONFINISH_CLASSES, classify_result_status
from src.retirement_progress import PROGRESS_COLUMNS

CAUSES = sorted(NONFINISH_CLASSES)
HAZARD_COLUMNS = [f'retirement_hazard_bin_{i}' for i in range(10)]


def attach_survival_risk(features, recent_races, metadata):
    target = int(metadata['year']), int(metadata['round'])
    keys = [(int(m['year']), int(m['round'])) for _, m in recent_races]
    if len(keys) != len(set(keys)) or any(key >= target for key in keys):
        raise ValueError('Survival history must be unique and strictly before the target cutoff.')
    observations = []
    for age, (session, context) in enumerate(sorted(recent_races,
            key=lambda item: (item[1]['year'], item[1]['round']), reverse=True)):
        result = getattr(session, 'results', pd.DataFrame())
        if not {'Abbreviation', 'TeamName', 'Status', 'Laps'}.issubset(result):
            continue
        if result.Abbreviation.duplicated().any():
            raise ValueError('Duplicate survival observations.')
        distances = pd.to_numeric(result.Laps, errors='coerce')
        distance = distances.max()
        if not np.isfinite(distance) or distance <= 0:
            continue
        for row, laps in zip(result.itertuples(), distances):
            cause = classify_result_status(row.Status)
            if cause != 'finished' and cause not in NONFINISH_CLASSES:
                continue
            if cause != 'finished' and (not np.isfinite(laps) or not 0 <= laps <= distance):
                continue
            interval = 10 if cause == 'finished' else min(int(laps / distance * 10), 9)
            observations.append((str(row.Abbreviation), str(row.TeamName), cause, interval, .5 ** (age / 8)))
    fallback_hazard = 1 - .9 ** .1  # Explicit 10% full-distance prior.

    def estimate(rows, prior, strength):
        exposure = np.zeros(10); events = np.zeros((10, len(CAUSES)))
        for _, _, cause, interval, weight in rows:
            exposure[:min(interval + 1, 10)] += weight
            if interval < 10:
                events[interval, CAUSES.index(cause)] += weight
        return (events + prior * strength) / (exposure[:, None] + strength)

    global_hazard = estimate(observations, np.full((10, len(CAUSES)), fallback_hazard / len(CAUSES)), 40)
    output = features.copy(); hazards, occurrences, cause_probabilities = [], [], []
    for driver, team in zip(output.Driver, output.Team):
        team_hazard = estimate([r for r in observations if r[1] == str(team)], global_hazard, 20)
        driver_hazard = estimate([r for r in observations if r[0] == str(driver)], global_hazard, 12)
        by_cause = .6 * team_hazard + .4 * driver_hazard
        total = by_cause.sum(axis=1)
        survive_before = np.r_[1., np.cumprod(1 - total)[:-1]]
        mass = total * survive_before
        hazards.append(total); occurrences.append(mass)
        cause_probabilities.append((by_cause * survive_before[:, None]).sum(axis=0))
    hazard = np.asarray(hazards); mass = np.asarray(occurrences)
    probability = mass.sum(axis=1)
    for index, column in enumerate(HAZARD_COLUMNS):
        output[column] = hazard[:, index]
    for index, column in enumerate(PROGRESS_COLUMNS):
        output[column] = mass[:, index] / probability
    output['dnf_prob'] = probability
    output['reliability_score'] = probability
    for index, cause in enumerate(CAUSES):
        output[f'retirement_{cause}_prob'] = np.asarray(cause_probabilities)[:, index]
    output['retirement_model_version'] = 'competing_risk_survival_v1_experimental'
    output['retirement_known_observations'] = len(observations)
    output['retirement_progress_observations'] = sum(row[3] < 10 for row in observations)
    return output
