from __future__ import annotations

import json

import numpy as np
import pytest

from src.run_config import config_to_dict, load_app_config
from src.safety_car import apply_safety_cars


def test_compression_keeps_post_restart_gap_and_queue_residual() -> None:
    times = np.array([[100.0, 110.0, 130.0]] * 2000)
    adjusted, deployed, fraction = apply_safety_cars(
        times, 1.0, seed=3, restart_noise_seconds=0.0, pit_saving_seconds=0.0)
    assert deployed.all()
    expected_gap = 30.0 * ((1 - fraction) + fraction * 0.10)
    assert adjusted[:, 2] - adjusted[:, 0] == pytest.approx(expected_gap)
    assert (adjusted[:, 2] - adjusted[:, 0] < 30.0).all()


def test_pit_saving_only_inside_window() -> None:
    times = np.zeros((4000, 2))
    adjusted, _, fraction = apply_safety_cars(
        times, 1.0, seed=5, restart_noise_seconds=0.0, pit_take_rate=1.0)
    inside = (fraction >= 0.15) & (fraction <= 0.80)
    assert (adjusted[inside] == -10.0).all()
    assert (adjusted[~inside] == 0.0).all()


def test_zero_probability_is_identity() -> None:
    times = np.random.default_rng(1).normal(5000, 10, size=(50, 5))
    adjusted, deployed, fraction = apply_safety_cars(times, 0.0, seed=1)
    assert not deployed.any() and np.isnan(fraction).all()
    assert (adjusted == times).all()


def test_config_roundtrip_is_local_only_and_excludes_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv('POST_TO_DISCORD', raising=False)
    config = config_to_dict(load_app_config())
    assert config['model']['safety_car_model'] == 'off'
    config['ignore_environment_overrides'] = True
    config['outputs']['post_to_discord'] = False
    config['model']['safety_car_model'] = 'track_sc_v1'
    path = tmp_path / 'sc.json'
    path.write_text(json.dumps(config))
    assert load_app_config(str(path)).model.safety_car_model == 'track_sc_v1'

    for update, message in [({'outputs': {'post_to_discord': True}}, 'local output'),
                            ({'model': {'safety_car_model': 'always'}}, 'safety_car_model'),
                            ({'model': {'race_engine': 'agent_laps_v1'}}, 'neutralisation')]:
        changed = json.loads(json.dumps(config))
        for section, values in update.items():
            changed[section].update(values)
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match=message):
            load_app_config(str(path))


def test_multi_none_is_identity_and_counts_are_capped() -> None:
    from src.safety_car import MAX_PHASES, apply_neutralisations
    rng = np.random.default_rng(2)
    times = rng.normal(5000, 15, size=(4000, 10))
    retired = rng.random((4000, 10)) < 0.1
    adjusted, n_sc, n_vsc = apply_neutralisations(times, retired, 0.0, 57, seed=1, vsc_probability=0.0)
    assert (adjusted == times).all() and not n_sc.any() and not n_vsc.any()

    _, n_sc, n_vsc = apply_neutralisations(times, retired, 0.55, 57, seed=1)
    assert n_sc.max() == MAX_PHASES and n_vsc.max() == MAX_PHASES
    assert (n_sc > 0).mean() == pytest.approx(0.55, abs=0.03)
    assert (n_vsc > 0).mean() == pytest.approx(0.40, abs=0.03)
    # Archive: races with an SC had 1.36 on average.
    assert n_sc[n_sc > 0].mean() == pytest.approx(1.36, abs=0.05)


def test_multi_neutralisations_follow_retirements() -> None:
    from src.safety_car import apply_neutralisations
    times = np.zeros((20000, 10))
    retired = np.zeros((20000, 10), dtype=bool)
    retired[10000:, :3] = True
    _, n_sc, n_vsc = apply_neutralisations(times, retired, 0.5, 57, seed=4)
    assert (n_sc[10000:] > 0).mean() > (n_sc[:10000] > 0).mean() + 0.2
    assert (n_vsc[10000:] > 0).mean() > (n_vsc[:10000] > 0).mean() + 0.2
    assert (n_sc > 0).mean() == pytest.approx(0.5, abs=0.02)


def test_multi_sc_compresses_more_than_vsc_only() -> None:
    from src.safety_car import apply_neutralisations
    times = np.tile([0.0, 30.0], (5000, 1))
    retired = np.zeros_like(times, dtype=bool)
    kwargs = dict(sc_restart_noise_seconds=0.0, vsc_restart_noise_seconds=0.0,
                  sc_pit_saving_seconds=0.0, vsc_pit_saving_seconds=0.0)
    sc, n_sc, _ = apply_neutralisations(times, retired, 1.0, 57, seed=3, vsc_probability=0.0, **kwargs)
    vsc, _, n_vsc = apply_neutralisations(times, retired, 0.0, 57, seed=3, vsc_probability=1.0, **kwargs)
    sc_gap, vsc_gap = sc[:, 1] - sc[:, 0], vsc[:, 1] - vsc[:, 0]
    assert (n_sc >= 1).all() and (n_vsc >= 1).all()
    # A VSC keeps time gaps; each SC erases what was built before it.
    assert vsc_gap == pytest.approx(30.0)
    # A lap-1 SC alone erases nothing.
    assert (sc_gap <= 30.0 + 1e-9).all() and (sc_gap > 0).all() and sc_gap.mean() < 25.0
    assert sc_gap[n_sc == 3].mean() < sc_gap[n_sc == 1].mean()


def test_multi_one_discounted_stop_per_driver() -> None:
    from src.safety_car import apply_neutralisations
    times = np.zeros((5000, 4))
    retired = np.zeros_like(times, dtype=bool)
    adjusted, _, _ = apply_neutralisations(times, retired, 1.0, 57, seed=8, vsc_probability=1.0,
                                           sc_restart_noise_seconds=0.0, vsc_restart_noise_seconds=0.0,
                                           pit_take_rate=1.0)
    assert set(np.unique(adjusted)) <= {0.0, -5.0, -10.0}
    assert (adjusted == -10.0).any() and (adjusted == -5.0).any()


def test_multi_rejects_bad_inputs() -> None:
    from src.safety_car import apply_neutralisations
    times = np.zeros((10, 3))
    with pytest.raises(ValueError):
        apply_neutralisations(times, np.zeros((10, 2), dtype=bool), 0.4, 57, seed=1)
    with pytest.raises(ValueError):
        apply_neutralisations(times, np.zeros((10, 3), dtype=bool), 1.4, 57, seed=1)


def test_multi_config_value_is_accepted(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv('POST_TO_DISCORD', raising=False)
    config = config_to_dict(load_app_config())
    config['ignore_environment_overrides'] = True
    config['outputs']['post_to_discord'] = False
    config['model']['safety_car_model'] = 'multi_sc_v1'
    path = tmp_path / 'multi.json'
    path.write_text(json.dumps(config))
    assert load_app_config(str(path)).model.safety_car_model == 'multi_sc_v1'
    config['model']['race_engine'] = 'agent_laps_v1'
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='neutralisation'):
        load_app_config(str(path))
