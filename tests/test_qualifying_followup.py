import json

import pandas as pd
import pytest

from scripts.audit_qualifying_classifications import parse_classification, complete_numeric_positions
from scripts import benchmark_qualifying_pace as benchmark


def page(positions):
    rows = ''.join('<tr>'+''.join(f'<td>{v}</td>' for v in
        [position, number, 'Driver', 'Team', '', '', '', '0'])+'</tr>'
        for number, position in enumerate(positions, 1))
    return '<h1>MONACO 2024 - QUALIFYING</h1><table>'+rows+'</table>'


@pytest.mark.parametrize('positions', [('1', 'DQ'), ('1', 'NC'), ('1', '1'), ('1', '')])
def test_special_or_duplicate_positions_never_become_numeric_order(positions):
    frame, _ = parse_classification(page(positions), 2024, 'MONACO')
    assert list(frame.OfficialPosition) == list(positions)
    assert not complete_numeric_positions(frame)


def test_official_page_identity_and_full_numeric_contract():
    frame, _ = parse_classification(page(['1', '2']), 2024, 'MONACO')
    assert complete_numeric_positions(frame)
    with pytest.raises(ValueError, match='identity'):
        parse_classification(page(['1', '2']), 2025, 'MONACO')
    with pytest.raises(ValueError, match='identity'):
        parse_classification(page(['1', '2']).replace('QUALIFYING', 'STARTING GRID'), 2024, 'MONACO')


def test_pace_screen_rejects_candidate_that_loses_to_qualifying_order(tmp_path, monkeypatch):
    from types import SimpleNamespace
    races = [SimpleNamespace(key=(2024, 1), year=2024), SimpleNamespace(key=(2025, 1), year=2025)]
    monkeypatch.setattr(benchmark, 'load_archive', lambda *_: (races, {}, [], [], []))

    def fake_run(races, output, prior, **kwargs):
        assert kwargs['sessions'] == ('Q',)
        assert kwargs['variants'] == ('legacy', 'qualifying_partial_pooling_v1')
        assert json.loads(prior.read_text())['holdout_races'] == [[2025, 1]]
        output.mkdir()
        rows, grids = [], []
        for round_number in range(1, 7):
            for variant, mae in [('legacy', 4.), ('qualifying_partial_pooling_v1', 3.5)]:
                rows.append(dict(variant=variant, year=2025, round=round_number,
                    split='previously_seen_diagnostic', session='Q', finish_mae=mae,
                    loss=mae+.1, win_brier=.1, podium_brier=.1, top10_brier=.1, dnf_brier=.1))
            grids.append(dict(variant='grid_order', split='previously_seen_diagnostic', finish_mae=3.3))
        pd.DataFrame(rows).to_csv(output/'race_metrics.csv', index=False)
        pd.DataFrame(grids).to_csv(output/'simple_baselines.csv', index=False)
        report = {'selected_on_development': {'qualifying_partial_pooling_v1': True}}
        (output/'report.json').write_text(json.dumps(report))
        return report

    monkeypatch.setattr(benchmark, 'benchmark_feature_ablations', fake_run)
    result = benchmark.run(tmp_path, tmp_path/'new', years=[2024, 2025], histories=(2,))
    decision = result['decisions'][0]
    assert decision['reasons'] == ['does_not_beat_qualifying_order']
    assert not decision['promising_for_new_shadow_review']
    assert not result['cohort_changed']
    assert not result['activated']
    with pytest.raises(FileExistsError):
        benchmark.run(tmp_path, tmp_path/'new', years=[2024, 2025], histories=(2,))
