import hashlib
import json

import pandas as pd
import pytest

import src.safety_car as safety_car
import src.season_packets as season_packets
from scripts.benchmark_safety_car import arm_settings
from src.season_packets import build_season_packet, neutralisation_counts


def laps():
    return pd.DataFrame([{'Driver': driver, 'LapNumber': n, 'LapStartTimeSeconds': n * 100 + offset - 90,
                          'LapTimeSeconds': 90} for n in (1, 2, 3, 4) for driver, offset in (('A', 0), ('B', 2))])


def feed(times, codes):
    return pd.DataFrame({'Time': pd.to_timedelta(times, unit='s'), 'Status': codes})


def test_upgraded_vsc_counts_once_as_sc_and_prestart_is_ignored():
    counts = neutralisation_counts(laps(), feed([0, 5, 120, 150, 200, 300, 330], [4, 1, 6, 4, 1, 6, 1]))
    assert counts == {'safety_car_flag': True, 'vsc_flag': True, 'sc_count': 1, 'vsc_count': 1}
    assert neutralisation_counts(laps(), feed([0], ['1.0']))['sc_count'] == 0
    with pytest.raises(ValueError):
        neutralisation_counts(laps(), feed([100], [1]))


def write_session(root, round_, results, status='complete'):
    folder = root / 'data/historical_library/2024/detailed' / f'{round_:02d}_test_grand_prix_R'
    version = folder / 'versions' / 'v1'
    version.mkdir(parents=True)
    tables = {'laps': laps(), 'results': results, 'track_status': feed([0, 150, 200], [1, 4, 1])}
    files = {}
    for table, frame in tables.items():
        path = version / f'{table}.csv.gz'
        frame.to_csv(path, index=False)
        files[f'versions\\v1\\{table}.csv.gz'] = {'table': table, 'bytes': path.stat().st_size,
                                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {'year': 2024, 'round': round_, 'event': 'Test Grand Prix', 'session': 'R', 'status': status, 'files': files}
    (folder / 'session.json').write_text(json.dumps(manifest), encoding='utf-8')
    return version


def test_packet_drops_non_starters_and_skips_changed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(season_packets, 'build_driver_features',
                        lambda laps: pd.DataFrame({'Driver': ['A', 'B'], 'relative_pace': [0.0, 0.4]}))
    results = pd.DataFrame({'Abbreviation': ['A', 'B', 'C'], 'TeamName': ['X', 'Y', 'Z'],
                            'Position': [1, 2, None], 'GridPosition': [2, 1, 0]})
    write_session(tmp_path, 1, results)
    changed = write_session(tmp_path, 2, results)
    (changed / 'laps.csv.gz').write_bytes(b'changed')
    write_session(tmp_path, 3, results, status='partial')
    report = build_season_packet(tmp_path, 2024, tmp_path / 'packet')
    assert report['races'] == 1 and report['safety_car_races'] == 1
    assert [row['Round'] for row in report['skipped']] == [2, 3]
    classified = pd.read_csv(tmp_path / 'packet/fastf1_race_results.csv')
    assert classified.Abbreviation.tolist() == ['A', 'B']
    control = pd.read_csv(tmp_path / 'packet/fastf1_race_control_summary.csv')
    assert control.sc_count.tolist() == [1]
    with pytest.raises(FileExistsError):
        build_season_packet(tmp_path, 2024, tmp_path / 'packet')


def test_gap_reset_arm_patches_only_inside_the_block():
    original = safety_car.apply_neutralisations
    with arm_settings('multi_sc_gap_reset'):
        assert safety_car.apply_neutralisations.keywords == {'gap_retention': 0.0}
    with arm_settings('multi_sc_v1'):
        assert safety_car.apply_neutralisations is original
    assert safety_car.apply_neutralisations is original


def test_gate_keeps_seasons_with_the_same_round_apart():
    from scripts.promotion_check import gate
    rows = pd.DataFrame([{'year': year, 'round': round_, 'seed': seed, 'arm': arm,
                          'rps': 0.10 if arm == 'candidate' else 0.12, 'finish_mae': 3.0}
                         for year in (2024, 2025) for round_ in range(1, 5) for seed in (1, 2)
                         for arm in ('candidate', 'established')])
    decision = gate(rows, 'candidate', 'established', 'accuracy')
    assert decision['paired_races'] == 8 and decision['passed']
