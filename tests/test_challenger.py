from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from src import challenger

SPEC = {'name': 'v2', 'season': 2027, 'freeze_before_utc': '2027-03-01T00:00:00Z',
        'candidates': {'grid_penalty_model': 'announced_v1', 'safety_car_model': 'multi_sc_v1'}}
BEFORE = datetime(2026, 12, 1, tzinfo=timezone.utc)


def workspace(tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'simulate.py').write_text('x = 1\n')
    (tmp_path / 'main.py').write_text('print(1)\n')
    return tmp_path


def test_freeze_is_write_once_and_records_lanes(tmp_path):
    root = workspace(tmp_path)
    path = challenger.freeze(SPEC, root, tmp_path / 'out', now=BEFORE)
    record = challenger.load(path)
    assert record['lanes'] == {'grid_penalty_model': 'correctness', 'safety_car_model': 'accuracy'}
    assert set(record['source_hashes']) == {'main.py', 'src/simulate.py'}
    assert record['activated'] is False
    with pytest.raises(FileExistsError):
        challenger.freeze(SPEC, root, tmp_path / 'out', now=BEFORE)


def test_freeze_refuses_after_the_deadline_and_bad_specs(tmp_path):
    root = workspace(tmp_path)
    with pytest.raises(ValueError, match='deadline'):
        challenger.freeze(SPEC, root, tmp_path / 'out', now=datetime(2027, 3, 2, tzinfo=timezone.utc))
    for bad in ({**SPEC, 'candidates': {}}, {**SPEC, 'candidates': {'sprint_model': 'nope'}},
                {**SPEC, 'parameter_overrides': {'not_a_parameter': 1}},
                {**SPEC, 'freeze_before_utc': '2026-12-31T00:00:00Z'}):
        with pytest.raises(ValueError):
            challenger.freeze(bad, root, tmp_path / 'bad', now=BEFORE)


def test_verify_reports_changed_sources(tmp_path):
    root = workspace(tmp_path)
    path = challenger.freeze(SPEC, root, tmp_path / 'out', now=BEFORE)
    assert challenger.verify(path, root)['unchanged']
    (root / 'src' / 'simulate.py').write_text('x = 2\n')
    (root / 'src' / 'new.py').write_text('')
    result = challenger.verify(path, root)
    assert not result['unchanged'] and result['changed'] == ['src/simulate.py'] and result['added'] == ['src/new.py']


def test_run_config_never_posts(tmp_path):
    path = challenger.freeze(SPEC, workspace(tmp_path), tmp_path / 'out', now=BEFORE)
    base = json.loads(open('config/default_run_config.json', encoding='utf-8').read())
    base.setdefault('outputs', {})['post_to_discord'] = True
    config = challenger.run_config(path, base)
    assert config['outputs']['post_to_discord'] is False
    assert config['model']['safety_car_model'] == 'multi_sc_v1'
    assert config['challenger']['name'] == 'v2'


def test_season_evidence_uses_only_the_challenger_season(tmp_path):
    path = challenger.freeze(SPEC, workspace(tmp_path), tmp_path / 'out', now=BEFORE)
    rows = []
    for year in (2026, 2027):
        for round_ in range(1, 9):
            for arm, shift in (('live', 0.0), ('v2', -0.02)):
                rows.append({'year': year, 'round': round_, 'seed': 1, 'arm': arm, 'finish_mae': 3.0 + shift * 10,
                             'win_brier': .03, 'podium_brier': .07, 'top10_brier': .18, 'rps': .13 + shift})
    evidence = challenger.season_evidence(path, pd.DataFrame(rows))
    assert evidence['primary']['races'] == 8 and evidence['primary']['e_value'] > 1
    assert evidence['gate']['paired_races'] == 8 and evidence['activated'] is False
