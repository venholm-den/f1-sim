"""Declared grid-difficulty mappings shared by replay and prospective shadows."""
from __future__ import annotations

import numpy as np

from src.circuit_calibration import proxy_posterior

MAPPINGS = ('active_profile', 'uniform_055', 'active_times_125', 'earlier_order_proxy')


def mapped_difficulty(mapping, active, context, observations):
    if mapping not in MAPPINGS:
        raise ValueError('Unknown grid mapping')
    active = float(active)
    if not np.isfinite(active) or not 0 <= active <= 1:
        raise ValueError('Active difficulty must be in [0, 1]')
    evidence = {'mapping': mapping, 'active_difficulty': active}
    if mapping == 'active_profile':
        value = active
    elif mapping == 'uniform_055':
        value = .55
    elif mapping == 'active_times_125':
        value = min(.95, active*1.25)
    else:
        target = int(context['year']), int(context['round'])
        layout = context.get('venue', {}).get('layout_id')
        earlier = [r for r in observations if (int(r['year']), int(r['round'])) < target]
        local = proxy_posterior(earlier, layout) if layout else {'races': 0}
        eligible = [r['order_change_proxy'] for r in earlier if r['order_change_proxy']['changes'] is not None]
        exposure = sum(r['exposure'] for r in eligible)
        # With fewer than two local races, retain the existing coefficient.
        if local['races'] < 2 or not exposure:
            value = active
            evidence['fallback'] = 'fewer than two strictly earlier same-layout proxy races'
        else:
            pool = 1000*(sum(r['changes'] for r in eligible)+1)/(exposure+1)
            value = float(np.clip(.55*pool/local['mean_per_1000'], .25, .90))
            evidence.update(local_proxy=local, pooled_changes_per_1000=pool)
        evidence.update(prior_layout_races=local['races'], layout_id=layout,
            interpretation='Declared inverse proxy mapping, not a physically calibrated overtake cost')
    evidence['mapped_difficulty'] = value
    return value, evidence


def select_mapping(seed_metrics, stage):
    """Equal race weighting after averaging seeds; never inspect later scores."""
    d = seed_metrics[(seed_metrics['session'] == stage) & (seed_metrics['split'] == 'development')]
    if d.empty:
        raise ValueError(f'No development episodes for {stage}')
    counts = d.groupby(['year', 'round']).mapping.nunique()
    if not counts.eq(len(MAPPINGS)).all():
        raise ValueError('Development episodes must contain every declared mapping')
    means = d.groupby(['mapping', 'year', 'round']).loss.mean().groupby('mapping').mean()
    # Baseline wins exact ties; do not replace a coefficient without benefit.
    return min(MAPPINGS, key=lambda name: (means[name], MAPPINGS.index(name)))
