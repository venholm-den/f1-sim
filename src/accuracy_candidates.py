"""Small, independent accuracy experiments; no live defaults are changed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.model_config import DEFAULT_BASE_LAP_TIME
from src.reliability import DEFAULT_MECHANICAL_DNF_RATE


FEATURE_VARIANTS = ('legacy', 'decoupled_dnf_v1', 'normalised_history_v1')
AUDIT_VARIANTS = ('legacy', 'all_cause_dnf_v2', 'single_pace_blend_v1', 'q_grid_3_3_v1')
REVISION_VARIANTS = ('legacy', 'single_pace_blend_v1', 'all_cause_dnf_v2',
                     'retirement_progress_v1', 'single_pace_retirement_v1')
NEXT_VARIANTS = ('qualifying_partial_pooling_v1', 'pit_scenarios_v1', 'survival_dnf_v1', 'agent_laps_v1')
SUPPORTED_VARIANTS = tuple(dict.fromkeys(FEATURE_VARIANTS + AUDIT_VARIANTS + REVISION_VARIANTS + NEXT_VARIANTS))


def candidate_retirement_options(variant):
    return ({'retirement_classification': 'completed_laps_v1'}
            if variant in {'retirement_progress_v1', 'single_pace_retirement_v1', 'survival_dnf_v1'} else {})


def candidate_simulation_options(variant, features):
    options = candidate_retirement_options(variant)
    if variant == 'qualifying_partial_pooling_v1':
        options['sample_pace_posterior'] = True
    if variant == 'pit_scenarios_v1':
        from src.pit_scenarios import assumed_plans
        options['pit_plans'] = assumed_plans(features, features.estimated_race_laps.median())
    if variant == 'agent_laps_v1':
        options['agent_settings'] = {}  # track difficulty supplies an explicit passability proxy
    return options


def single_pace_blend(features: pd.DataFrame, session: str) -> pd.DataFrame:
    """Blend raw current/history gaps once, retaining an explicit evidence weight."""
    from src.model_config import SESSION_WEIGHTS
    output = features.copy()
    current = pd.to_numeric(output['current_relative_pace_capped'], errors='coerce')
    baseline = pd.to_numeric(output['baseline_relative_pace'], errors='coerce')
    current = current - current.min()
    baseline = baseline - baseline.min()
    quality = output.current_signal_quality.fillna(0).clip(0, 1)
    weight = quality * SESSION_WEIGHTS.get(session.upper(), {}).get('race', .25)
    weight = weight.mask(current.isna(), 0).mask(baseline.isna() & current.notna(), 1)
    current = current.fillna(baseline).fillna(0)
    baseline = baseline.fillna(current).fillna(0)
    pace = weight * current + (1 - weight) * baseline
    output['race_pace_score'] = pace - pace.min()
    old_race = features.race_pace_score
    long_run = features.long_run_pace_score - old_race + output.race_pace_score
    output['long_run_pace_score'] = long_run - long_run.min()
    output['projected_lap_time'] = features.projected_lap_time - old_race + output.race_pace_score
    output['race_weight_used'] = weight
    output['race_pace_current_weight'] = weight
    output['race_pace_history_weight'] = 1 - weight
    output['race_pace_blend_version'] = 'single_pace_blend_v1_experimental'
    return output


def candidate_grid_multiplier(variant: str, session: str):
    # A modest predeclared sensitivity, not the earlier inspected optimum 13.2.
    return 3.3 if variant == 'q_grid_3_3_v1' and session.upper() == 'Q' else None


def decouple_feature_dnf(features: pd.DataFrame) -> pd.DataFrame:
    output = features.copy()
    if not output.empty:
        # Sparse/noisy laps already affect pace quality and model uncertainty.
        # Retain those signals, but do not infer a failure from a poor sample.
        # Actual prior race statuses still inform reliability downstream.
        output['dnf_prob'] = DEFAULT_MECHANICAL_DNF_RATE
    return output


def session_reference_lap(features: pd.DataFrame) -> float | None:
    if 'true_pace' not in features:
        return None
    values = pd.to_numeric(features['true_pace'], errors='coerce')
    valid = values[np.isfinite(values) & values.gt(0)]
    return None if valid.empty else float(valid.min())


def normalise_historical_pace(features: pd.DataFrame, target_reference_seconds: float) -> pd.DataFrame:
    """Express prior relative gaps as lap fractions, then in target-lap seconds.

    Absolute lap times/degradation are deliberately untouched: this isolates
    comparable relative pace rather than claiming a fuel/tyre correction.
    """
    target = float(target_reference_seconds)
    if not np.isfinite(target) or target <= 0:
        raise ValueError('Target reference lap must be finite and positive.')
    output = features.copy()
    if output.empty:
        return output
    source = session_reference_lap(output)
    if source is None:
        raise ValueError('Historical features have no valid true-pace reference lap.')
    output['relative_pace'] = pd.to_numeric(output['relative_pace'], errors='coerce') / source * target
    if 'model_pace' in output:
        output['model_pace'] = output['relative_pace']
    output['source_reference_lap_seconds'] = source
    output['target_reference_lap_seconds'] = target
    return output


def target_reference_lap(current_features, previous, event, build_features):
    """Only current/prior inputs: never read the target race's laps."""
    current = session_reference_lap(current_features)
    if current is not None:
        return current, 'current_session_true_pace'
    event_key = str(event).strip().casefold()
    for race in reversed(previous):
        if str(race.event).strip().casefold() == event_key:
            reference = session_reference_lap(build_features(race.sessions['R'].laps))
            if reference is not None:
                return reference, f'prior_same_event_{race.year}_{race.round}'
    return float(DEFAULT_BASE_LAP_TIME), 'default_lap_assumption'
