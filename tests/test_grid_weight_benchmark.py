import json

import pandas as pd
import pytest

from src.grid_weight_benchmark import benchmark_grid_weights, select_grid_weight
from tests.test_accuracy_benchmark import races


def test_selection_cannot_use_later_diagnostic_results():
    metrics = pd.DataFrame([
        dict(split='development', weight=1.65, year=2024, round=3, loss=4),
        dict(split='development', weight=3.3, year=2024, round=3, loss=3),
        dict(split='previously_seen_diagnostic', weight=1.65, year=2024, round=5, loss=0),
        dict(split='previously_seen_diagnostic', weight=3.3, year=2024, round=5, loss=100),
    ])
    assert select_grid_weight(metrics) == 3.3
    metrics.loc[metrics['split'].ne('development'), 'loss'] *= 100
    assert select_grid_weight(metrics) == 3.3
    with pytest.raises(ValueError, match='No development'):
        select_grid_weight(metrics[metrics['split'].ne('development')])


def test_report_labels_seen_races_and_never_sweeps_on_them(tmp_path):
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 3], [2024, 4]],
                                'holdout_races': [[2024, 5]]}))
    report = benchmark_grid_weights(races(), tmp_path / 'output', prior,
                                   weights=[1.65, 3.3, 6.6], seeds=[42, 123], n_sims=100)
    assert report['fresh_validation_race_count'] == 1
    assert report['development_race_count'] == 2
    assert not report['promotion_gate_passed']
    metrics = pd.read_csv(tmp_path / 'output/seed_metrics.csv')
    expected = {1.65, report['selected_on_development']}
    later = metrics[metrics['split'].ne('development')]
    assert set(later.weight) == expected
    assert set(later['split']) == {'previously_seen_diagnostic', 'fresh_validation'}
    assert report['source_sha256'] and report['input_sha256']
    with pytest.raises(FileExistsError):
        benchmark_grid_weights(races(), tmp_path / 'output', prior, n_sims=100)


def test_invalid_partitions_and_weights_are_rejected(tmp_path):
    prior = tmp_path / 'prior.json'
    prior.write_text(json.dumps({'development_races': [[2024, 5]], 'holdout_races': [[2024, 4]]}))
    with pytest.raises(ValueError, match='chronological'):
        benchmark_grid_weights(races(), tmp_path / 'output', prior)
    prior.write_text(json.dumps({'development_races': [[2024, 3]], 'holdout_races': [[2024, 4]]}))
    with pytest.raises(ValueError, match='Weights'):
        benchmark_grid_weights(races(), tmp_path / 'output', prior, weights=[float('nan')])
