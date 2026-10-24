import json

from src.inspection_ledger import discover_reports, inspected_race_keys, race_keys


def test_all_report_formats_preserve_inspected_outcomes():
    report = {'holdout_races_evaluated': [[2024, 1], [2024, 2]],
              'inspected_races': [[2023, 1]],
              'metrics': {'train_races': [{'Year': 2022, 'Round': 1}],
                          'validation_races': [{'Year': 2024, 'Round': 3}]},
              'stages': {'Q': {'calibration': {'calibration_races': [[2023, 2]]}}},
              'skipped': [{'year': 2024, 'round': 4}, {'reason': 'unknown identity'}]}
    assert race_keys(report) == {(2024, r) for r in range(1, 5)} | {(2022, 1), (2023, 1), (2023, 2)}


def test_discovery_includes_prior_suites_and_tuning_but_not_hourly_reports(tmp_path):
    for name in ('multi_score_tuning/old/report.json', 'prediction_trials/suites/old/suite.json',
                 'prediction_trials/reports/hourly/report.json'):
        p = tmp_path/'outputs'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'inspected_races': [[2024, 1]]}))
    paths = discover_reports(tmp_path)
    assert len(paths) == 2
    assert inspected_race_keys(paths) == {(2024, 1)}
