"""Race identities already examined in benchmark, training and trial reports.

Only declared race fields are consumed; input/source paths are never followed.
Repeated simulations or stages still identify just one inspected race.
"""
from __future__ import annotations

import json
from pathlib import Path


RACE_FIELDS = (
    'development_races', 'holdout_races', 'holdout_races_evaluated',
    'evaluated_races', 'attempted_races', 'inspected_races', 'fit_races',
    'train_races', 'validation_races', 'calibration_races',
    'fresh_validation_races', 'previously_inspected_holdout_races',
    'skipped', 'captures', 'race_metrics',
)
REPORT_ROOTS = (
    'accuracy_benchmarks', 'feature_ablations', 'grid_weight_benchmarks',
    'grid_influence', 'qualifying_pace_followup', 'multi_score_tuning',
    'stage_ensemble', 'model_revision', 'model_training', 'prediction_data',
    'project_next_steps', 'prediction_audit',
)


def race_keys(report: dict) -> set[tuple[int, int]]:
    keys = set()
    for field in RACE_FIELDS:
        for row in report.get(field, []) or []:
            if isinstance(row, dict):
                year, round_ = row.get('year', row.get('Year')), row.get('round', row.get('Round'))
                if year is None or round_ is None:
                    continue  # A load failure may not identify a race.
            else:
                if not isinstance(row, (list, tuple)) or len(row) != 2:
                    raise ValueError(f'Invalid race identity in {field}: {row!r}')
                year, round_ = row
            if int(year) != float(year) or int(round_) != float(round_) or int(round_) < 1:
                raise ValueError(f'Invalid race identity in {field}: {row!r}')
            keys.add((int(year), int(round_)))
    # Historical training stores its split inside metrics; ensemble stages
    # store training and calibration races separately.
    for field in ('metrics', 'calibration'):
        if isinstance(report.get(field), dict):
            keys.update(race_keys(report[field]))
    for stage in report.get('stages', {}).values() if isinstance(report.get('stages'), dict) else ():
        if isinstance(stage, dict):
            keys.update(race_keys(stage))
    return keys


def inspected_race_keys(paths) -> set[tuple[int, int]]:
    keys = set()
    for path in paths:
        keys.update(race_keys(json.loads(Path(path).read_text(encoding='utf-8'))))
    return keys


def discover_reports(root: str | Path) -> list[Path]:
    """Known local evidence only, excluding large hourly report histories."""
    outputs = Path(root) / 'outputs'
    paths = set()
    for name in REPORT_ROOTS:
        folder = outputs / name
        for filename in ('report.json', 'protocol.json', 'training_result.json',
                         'historical_model_metrics.json', 'candidate.json'):
            paths.update(folder.rglob(filename))
    paths.update((outputs / 'prediction_trials' / 'suites').glob('*/suite.json'))
    return sorted(paths)
