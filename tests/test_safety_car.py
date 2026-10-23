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
