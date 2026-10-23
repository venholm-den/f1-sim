import json

import pandas as pd
import pytest

from src.run_config import config_to_dict, load_app_config
from src.track import load_track_profile
from src.track_calibration import (DEFAULT_PATH, DIFFICULTY_BOUNDS, SC_LAYOUT_PRIOR_RACES,
                                   apply_track_calibration, build_calibration, grid_order_stats)


def test_grid_order_stats_uses_classified_finishers_and_pit_lane_last():
    results = pd.DataFrame({'GridPosition': [1, 2, 3, 0, 5, 6, 7, 8, 9, 10],
                            'Position': [2, 1, 3, 4, 5, 6, 7, 8, 9, 10],
                            'ClassifiedPosition': ['2', '1', '3', '4', '5', '6', '7', '8', '9', 'R']})
    stats = grid_order_stats(results)
    assert stats['classified'] == 9
    # Pit-lane starter ranks 9th on the grid and finishes 4th.
    assert stats['mean_abs_change'] == pytest.approx((1 + 1 + 5 + 1 + 1 + 1 + 1 + 1) / 9)
    assert 0 < stats['grid_finish_rho'] < 1
    assert grid_order_stats(results.head(5)) is None


def _report(rows):
    observations, candidates = [], []
    for i, (circuit, sc, rho, changes) in enumerate(rows):
        for year in (2024, 2025):
            observations.append({'year': year, 'round': i + 1, 'circuit_id': circuit,
                                 'layout_id': f'{circuit}_gp', 'events': {'safety_car': sc},
                                 'order_change_proxy': {'changes': changes, 'exposure': 1000}})
        candidates.append({'layout_id': f'{circuit}_gp', 'current_registry_layout': True})
    candidates.append({'layout_id': 'old_gp', 'current_registry_layout': False})
    grid = pd.DataFrame([{'year': o['year'], 'round': o['round'],
                          'grid_finish_rho': dict((r[0], r[2]) for r in rows)[o['circuit_id']]}
                         for o in observations])
    return {'observations': observations, 'candidates': candidates}, grid


def test_build_keeps_heuristics_and_fits_placeholders():
    report, grid = _report([('easy', 1, .5, 60), ('mid', 0, .7, 35), ('hard', 1, .9, 5),
                            ('open', 1, .55, 55), ('tight', 0, .92, 8)])
    profiles = pd.DataFrame({'CircuitId': ['easy', 'mid', 'hard', 'open', 'tight'],
        'OvertakingDifficulty': [.40, .55, .85, .55, .55], 'SafetyCarChance': [.4] * 5,
        'ProfileStatus': ['existing_circuit_heuristic'] * 3 + ['generic_uncalibrated'] * 2})
    table = build_calibration(report, grid, profiles, 'abc').set_index('CircuitId')
    assert set(table.index) == {'easy', 'mid', 'hard', 'open', 'tight'}
    assert table.loc['easy', 'OvertakingDifficulty'] == .40
    assert table.loc['hard', 'overtaking_source'] == 'kept_heuristic'
    assert table.loc['open', 'OvertakingDifficulty'] < table.loc['tight', 'OvertakingDifficulty']
    assert table.OvertakingDifficulty.between(*DIFFICULTY_BOUNDS).all()
    pooled = (6 + .4 * 4) / (10 + 4)
    expected = (2 + pooled * SC_LAYOUT_PRIOR_RACES) / (2 + SC_LAYOUT_PRIOR_RACES)
    assert table.loc['easy', 'SafetyCarChance'] == pytest.approx(expected, abs=1e-3)
    assert (table.SourceReportSha256 == 'abc').all()


def test_apply_matches_layout_and_reports_missing(tmp_path):
    path = tmp_path / 'cal.csv'
    pd.DataFrame({'CircuitId': ['spa'], 'LayoutId': ['spa_gp'], 'SafetyCarChance': [.57],
                  'OvertakingDifficulty': [.57], 'SourceReportSha256': ['x']}).to_csv(path, index=False)
    profile = {'circuit_id': 'spa', 'layout_id': 'spa_gp', 'safety_car_chance': .4,
               'overtaking_difficulty': .55, 'red_flag_base_chance': .035}
    calibrated = apply_track_calibration(profile, path)
    assert calibrated['safety_car_chance'] == .57 and calibrated['overtaking_difficulty'] == .57
    assert calibrated['red_flag_base_chance'] == .035 and calibrated['calibration_status'] == 'calibrated_v1'
    assert profile['safety_car_chance'] == .4
    other = apply_track_calibration({**profile, 'layout_id': 'spa_old'}, path)
    assert other['calibration_status'] == 'calibrated_v1_unavailable'
    assert other['overtaking_difficulty'] == .55


def test_shipped_table_covers_every_placeholder_current_circuit():
    table = pd.read_csv(DEFAULT_PATH)
    profiles = pd.read_csv('data/track_profiles.csv')
    current = profiles[(profiles.LastSeason >= 2026) & profiles.ProfileStatus.eq('generic_uncalibrated')]
    assert set(current.CircuitId) <= set(table.CircuitId)
    assert table.SafetyCarChance.between(.3, .8).all()
    heuristic = table[table.ProfileStatus.eq('existing_circuit_heuristic')]
    assert (heuristic.OvertakingDifficulty == heuristic.ActiveOvertakingDifficulty).all()
    spa = load_track_profile('Belgian Grand Prix', metadata={'year': 2026, 'round': 10,
                                                             'event': 'Belgian Grand Prix'})
    assert apply_track_calibration(spa)['calibration_status'] == 'calibrated_v1'


def test_config_defaults_to_active_and_calibrated_is_local_only(tmp_path, monkeypatch):
    monkeypatch.delenv('POST_TO_DISCORD', raising=False)
    config = config_to_dict(load_app_config())
    assert config['model']['track_profile_model'] == 'active'
    config['ignore_environment_overrides'] = True
    config['outputs']['post_to_discord'] = False
    config['model']['track_profile_model'] = 'calibrated_v1'
    path = tmp_path / 'cal.json'
    path.write_text(json.dumps(config))
    assert load_app_config(str(path)).model.track_profile_model == 'calibrated_v1'
    for section, key, value, message in [('outputs', 'post_to_discord', True, 'local output'),
                                         ('model', 'track_profile_model', 'fitted', 'track_profile_model')]:
        changed = json.loads(json.dumps(config))
        changed[section][key] = value
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match=message):
            load_app_config(str(path))
