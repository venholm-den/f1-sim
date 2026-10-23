"""Calibrated track factors (opt-in candidate `calibrated_v1`).

Builds per-layout safety-car chances and overtaking difficulties from a saved
circuit-calibration report plus archived race classifications, and applies
them to a loaded track profile on request. Nothing here edits
data/track_profiles.csv; the default forecast keeps the active profile values.

Safety car: chronological scoring of the 2021-2026 archive showed layout
history barely beats the pooled rate, so each layout is shrunk hard (20
pseudo-races) toward the pooled rate. Overtaking difficulty: two independent
race measures (grid-to-finish rank correlation of classified finishers, and
the clean green-flag order-change proxy) are averaged as z-scores, shrunk by
race count and mapped onto the existing difficulty scale by a linear fit to
the heuristic tracks. Only generic placeholder rows receive a fitted value;
heuristic rows keep theirs. Red-flag base chances are not changed: observed
red-flag frequency is not the simulation's pre-adjustment base parameter.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = 'calibrated_v1'
DEFAULT_PATH = 'data/track_calibration/track_calibration_v1.csv'
SC_DEFAULT = 0.40
SC_POOL_PRIOR_RACES = 4.0
SC_LAYOUT_PRIOR_RACES = 20.0
OVERTAKING_PRIOR_RACES = 3.0
DIFFICULTY_BOUNDS = (0.35, 0.90)


def grid_order_stats(results: pd.DataFrame) -> dict | None:
    """Rank correlation and mean absolute change between grid and finish.

    Only classified finishers count. A pit-lane start (grid 0) ranks last.
    Both series are ranks, so Pearson on them is Spearman's rho.
    """
    data = results[pd.to_numeric(results.ClassifiedPosition, errors='coerce').notna()]
    if len(data) < 8:
        return None
    grid = pd.to_numeric(data.GridPosition, errors='coerce').replace(0, np.nan).fillna(99).rank(method='first')
    finish = pd.to_numeric(data.Position, errors='coerce').rank(method='first')
    return {'classified': int(len(data)), 'grid_finish_rho': float(grid.corr(finish)),
            'mean_abs_change': float((grid - finish).abs().mean())}


def safety_car_estimates(observations: list[dict]) -> pd.DataFrame:
    events = pd.DataFrame([{'layout_id': o['layout_id'], 'sc': o['events']['safety_car']}
                           for o in observations if o.get('events') is not None])
    pooled = (events.sc.sum() + SC_DEFAULT * SC_POOL_PRIOR_RACES) / (len(events) + SC_POOL_PRIOR_RACES)
    grouped = events.groupby('layout_id').sc.agg(sc_races='size', sc_events='sum')
    grouped['SafetyCarChance'] = ((grouped.sc_events + pooled * SC_LAYOUT_PRIOR_RACES)
                                  / (grouped.sc_races + SC_LAYOUT_PRIOR_RACES))
    grouped['sc_pooled_rate'] = pooled
    return grouped


def overtaking_estimates(observations: list[dict], grid_stats: pd.DataFrame,
                         active: pd.DataFrame) -> pd.DataFrame:
    """Passing index per layout, mapped to difficulty via heuristic tracks."""
    identity = pd.DataFrame([{'year': o['year'], 'round': o['round'], 'layout_id': o['layout_id'],
                              'CircuitId': o['circuit_id'],
                              'changes': o['order_change_proxy']['changes'],
                              'exposure': o['order_change_proxy']['exposure']} for o in observations])
    races = identity.merge(grid_stats, on=['year', 'round'], how='inner').dropna(subset=['changes'])
    layouts = races.groupby('layout_id').agg(CircuitId=('CircuitId', 'first'), ot_races=('round', 'size'),
        grid_finish_rho=('grid_finish_rho', 'mean'), changes=('changes', 'sum'), exposure=('exposure', 'sum'))
    layouts['order_changes_per_1000'] = 1000 * layouts.changes / layouts.exposure
    weights = layouts.ot_races

    def z(values):
        mean = np.average(values, weights=weights)
        return (values - mean) / np.sqrt(np.average((values - mean) ** 2, weights=weights))

    raw = (z(layouts.grid_finish_rho) + z(-np.log(layouts.order_changes_per_1000))) / 2
    layouts['passing_index'] = raw * weights / (weights + OVERTAKING_PRIOR_RACES)
    status = layouts.CircuitId.map(active.ProfileStatus)
    anchors = layouts[status.eq('existing_circuit_heuristic')]
    slope, intercept = np.polyfit(anchors.passing_index, anchors.CircuitId.map(active.OvertakingDifficulty), 1)
    fitted = (intercept + slope * layouts.passing_index).clip(*DIFFICULTY_BOUNDS).round(2)
    layouts['OvertakingDifficulty'] = np.where(status.eq('generic_uncalibrated'), fitted,
                                               layouts.CircuitId.map(active.OvertakingDifficulty))
    layouts['overtaking_source'] = np.where(status.eq('generic_uncalibrated'),
                                            'fitted_passing_index', 'kept_heuristic')
    layouts.attrs['fit'] = {'slope': float(slope), 'intercept': float(intercept),
                            'anchor_layouts': int(len(anchors)),
                            'anchor_correlation': float(np.corrcoef(
                                anchors.passing_index, anchors.CircuitId.map(active.OvertakingDifficulty))[0, 1])}
    return layouts.drop(columns=['changes', 'exposure'])


def build_calibration(report: dict, grid_stats: pd.DataFrame, profiles: pd.DataFrame,
                      report_sha256: str) -> pd.DataFrame:
    """One row per current layout with observations; values are inactive until opted in."""
    active = profiles.drop_duplicates('CircuitId').set_index('CircuitId')
    current = {c['layout_id'] for c in report['candidates'] if c.get('current_registry_layout')}
    sc = safety_car_estimates(report['observations'])
    ot = overtaking_estimates(report['observations'], grid_stats, active)
    table = ot.join(sc, how='inner')
    table = table[table.index.isin(current)].reset_index().rename(columns={'layout_id': 'LayoutId'})
    table['ActiveSafetyCarChance'] = table.CircuitId.map(active.SafetyCarChance)
    table['ActiveOvertakingDifficulty'] = table.CircuitId.map(active.OvertakingDifficulty)
    table['ProfileStatus'] = table.CircuitId.map(active.ProfileStatus)
    table['SafetyCarChance'] = table.SafetyCarChance.round(3)
    table['Version'] = VERSION
    table['SourceReportSha256'] = report_sha256
    columns = ['CircuitId', 'LayoutId', 'ProfileStatus', 'SafetyCarChance', 'ActiveSafetyCarChance',
               'sc_races', 'sc_events', 'sc_pooled_rate', 'OvertakingDifficulty',
               'ActiveOvertakingDifficulty', 'overtaking_source', 'ot_races', 'grid_finish_rho',
               'order_changes_per_1000', 'passing_index', 'Version', 'SourceReportSha256']
    table = table[columns].sort_values('CircuitId').reset_index(drop=True)
    table.attrs['fit'] = ot.attrs['fit']
    return table


def apply_track_calibration(profile: dict, path: str | Path = DEFAULT_PATH) -> dict:
    """Return a copy of profile with calibrated SC chance and overtaking difficulty.

    Matches on resolved circuit and layout. An unmatched or unresolved venue
    keeps the active values and says so in calibration_status.
    """
    from src.app_services.app_paths import resource_path
    result = dict(profile)
    table = pd.read_csv(resource_path(path))
    match = table[(table.CircuitId == profile.get('circuit_id')) & (table.LayoutId == profile.get('layout_id'))]
    if match.empty:
        result['calibration_status'] = f'{VERSION}_unavailable'
        return result
    row = match.iloc[0]
    result.update(safety_car_chance=float(row.SafetyCarChance),
                  overtaking_difficulty=float(row.OvertakingDifficulty),
                  calibration_status=VERSION,
                  calibration_source=str(row.SourceReportSha256))
    return result


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_report(path: str | Path) -> tuple[dict, str]:
    return json.loads(Path(path).read_text(encoding='utf-8')), file_sha256(path)
