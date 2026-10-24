"""Named simulation-setting overrides kept as shadow candidates.

Each entry is a set of ``parameter_overrides`` for ``simulate_races`` plus the
evidence it came from. Nothing here changes SIMULATION_PARAMETERS, the run
config or any live forecast; offline benchmarks pass the overrides per call.
"""
from __future__ import annotations

from src.model_config import SIMULATION_PARAMETERS

SHADOW_SETTINGS = {
    'multi_score_tuned_v1': {
        'overrides': {'race_pace_seconds_multiplier': 0.52, 'grid_loss_multiplier': 11.0},
        'lane': 'accuracy',
        'evidence': (
            'docs/multi-score-tuning.md and the 23-24 Oct held-out runs (fit 2022-2023, score 2024, Q stage): '
            'pace peaked near 0.52 and grid trust near 11-12.5 in the wide run, and landed at 0.54 and 11.5 '
            'again with race noise held at its live value. Race noise is left live because its optimum was '
            'still rising at the search limit, which points to missing uncertainty elsewhere. 2024 has been '
            'scored more than once, so it is no longer untouched evidence.'),
    },
}


def shadow_overrides(name: str) -> dict[str, float]:
    if name not in SHADOW_SETTINGS:
        raise ValueError(f'Unknown shadow settings: {name}.')
    overrides = dict(SHADOW_SETTINGS[name]['overrides'])
    unknown = set(overrides) - set(SIMULATION_PARAMETERS)
    if unknown:
        raise ValueError(f'Unknown simulation parameters: {sorted(unknown)}.')
    return overrides
