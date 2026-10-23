import json

import pandas as pd
import pytest

from src.feature_ablation_benchmark import (benchmark_feature_ablations, choose_on_development,
                                           evaluate_with_dnf)
from tests.test_accuracy_benchmark import races


def test_unknown_result_status_is_not_silently_counted_as_a_finish():
    prediction = pd.DataFrame({'Driver': ['A', 'B', 'C'], 'avg_finish': [1., 2., 3.],
        'win_chance': [1., 0., 0.], 'podium_chance': [1., 1., 1.],
        'points_chance': [1., 1., 1.], 'dnf_chance': [.1, .9, .9]})
    actual = pd.DataFrame({'Abbreviation': ['A', 'B', 'C'], 'Position': [1, 2, 3],
                          'Status': ['Finished', 'Engine', 'Unspecified']})
    metrics, data = evaluate_with_dnf(prediction, actual)
    assert metrics['dnf_brier'] == pytest.approx(.01)
    assert metrics['dnf_known_drivers'] == 2
    assert metrics['dnf_unknown_drivers'] == 1
    assert pd.isna(data.loc[data.Driver.eq('C'), 'actual_dnf'].iloc[0])
    actual.loc[actual.Abbreviation.eq('C'), 'Status'] = 'Retired'
    metrics, data = evaluate_with_dnf(prediction, actual)
    assert metrics['dnf_known_drivers'] == 3
    assert metrics['dnf_unknown_drivers'] == 0
    assert data.loc[data.Driver.eq('C'), 'actual_dnf'].iloc[0] == 1
    assert metrics['dnf_brier'] == pytest.approx(.01)


def test_selection_requires_direct_dnf_improvement_and_ignores_diagnostics():
    rows = [dict(variant=variant, split='development', loss=loss, dnf_brier=brier)
            for variant, loss, brier in [('legacy', 4., .1), ('decoupled_dnf_v1', 3., .2),
                                         ('normalised_history_v1', 3., .1)]]
    rows += [dict(variant='decoupled_dnf_v1', split='previously_seen_diagnostic',
                  loss=0., dnf_brier=0.)]
    selected = choose_on_development(pd.DataFrame(rows))
    assert not selected['decoupled_dnf_v1']
    assert selected['normalised_history_v1']


def test_audit_candidates_use_identical_episodes_and_preserve_inspection_ledger(tmp_path):
    from src.accuracy_candidates import AUDIT_VARIANTS
    prior = tmp_path/'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 3], [2024, 4]], 'holdout_races': [[2024, 5]]}))
    inspected = tmp_path/'inspected.json'
    inspected.write_text(json.dumps({'evaluated_races': [[2024, 6]]}))
    report = benchmark_feature_ablations(races(), tmp_path/'new', prior, seeds=[42], n_sims=100,
        sessions=['Q'], variants=AUDIT_VARIANTS, inspected_reports=[inspected])
    rows = pd.read_csv(tmp_path/'new/race_metrics.csv')
    assert set(rows.variant) == set(AUDIT_VARIANTS)
    assert rows.groupby(['year', 'round', 'session']).variant.nunique().eq(4).all()
    assert report['fresh_validation_races'] == []
    assert len(report['session_weather_availability']) == 4
    assert not any(gate['passed'] for gate in report['promotion_gates'].values())


def test_ablation_report_preserves_partitions_coverage_and_prior_inspections(tmp_path):
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 3], [2024, 4]],
                                'holdout_races': [[2024, 5]]}))
    output = tmp_path / 'ablations/first'
    report = benchmark_feature_ablations(races(), output, prior, seeds=[42], n_sims=100,
                                         sessions=['PRE', 'Q'])
    assert report['fresh_validation_races'] == [[2024, 6]]
    assert not any(gate['passed'] for gate in report['promotion_gates'].values())
    summary = pd.read_csv(output / 'summary.csv')
    assert set(summary.variant) == {'legacy', 'decoupled_dnf_v1', 'normalised_history_v1'}
    assert summary.dnf_known_drivers.gt(0).all()
    calibration = pd.read_csv(output / 'calibration_bins.csv')
    assert 'dnf_chance' in set(calibration.outcome)
    assert report['source_sha256'] and report['input_sha256']
    second = benchmark_feature_ablations(races(), tmp_path / 'ablations/second', prior,
                                         seeds=[42], n_sims=100, sessions=['PRE', 'Q'])
    assert second['fresh_validation_races'] == []
    assert [2024, 6] in second['inspected_races']
    with pytest.raises(FileExistsError):
        benchmark_feature_ablations(races(), output, prior, n_sims=100)


def test_repeated_seeds_do_not_inflate_calibration_sample_counts(tmp_path):
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 3], [2024, 4]],
                                'holdout_races': [[2024, 5]]}))
    report = benchmark_feature_ablations(races(), tmp_path / 'output', prior,
                                         seeds=[42, 123], n_sims=100, sessions=['Q'])
    bins = pd.read_csv(tmp_path / 'output/calibration_bins.csv')
    counts = bins.groupby(['variant', 'split', 'outcome'])['count'].sum()
    assert counts.loc[('legacy', 'development', 'dnf_chance')] == 4
    assert counts.loc[('legacy', 'development', 'win_chance')] == 4
    assert next(row for row in report['summary'] if row['variant'] == 'legacy'
                and row['split'] == 'development')['dnf_known_drivers'] == 4


def test_previously_skipped_outcome_is_not_fresh_validation(tmp_path):
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 3], [2024, 4]],
        'holdout_races': [[2024, 5]], 'skipped': [{'year': 2024, 'round': 6, 'reason': 'coverage'}]}))
    report = benchmark_feature_ablations(races(), tmp_path / 'output', prior,
                                         seeds=[42], n_sims=100, sessions=['Q'])
    assert report['fresh_validation_races'] == []
    assert [2024, 6] in report['inspected_races']
