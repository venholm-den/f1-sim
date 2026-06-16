from __future__ import annotations

import json

from app_gui import GuiRunSettings, build_run_config, load_default_config, write_temp_config


def test_build_run_config_applies_gui_settings() -> None:
    base_config = {
        "run": {
            "year": 2026,
            "event": "latest",
            "session": "Q",
            "n_sims": 50000,
            "random_seed": 42,
            "n_baseline_races": 5,
            "historical_strategy_lookback_years": 5,
        },
        "outputs": {
            "output_dir": "outputs",
            "save_prediction_snapshot": True,
            "save_report_images": True,
            "save_raw_results": True,
            "post_to_discord": False,
        },
        "data": {
            "fantasy_prices_path": "data/fantasy_prices.csv",
        },
    }
    settings = GuiRunSettings(
        year=2027,
        event="Monaco Grand Prix",
        session="FP2",
        n_sims=1234,
        random_seed=99,
        n_baseline_races=3,
        historical_strategy_lookback_years=4,
        output_dir="custom_outputs",
        save_prediction_snapshot=False,
        save_report_images=False,
        save_raw_results=False,
        post_to_discord=True,
    )

    config = build_run_config(base_config, settings)

    assert config["run"]["year"] == 2027
    assert config["run"]["event"] == "Monaco Grand Prix"
    assert config["run"]["session"] == "FP2"
    assert config["run"]["n_sims"] == 1234
    assert config["run"]["random_seed"] == 99
    assert config["run"]["n_baseline_races"] == 3
    assert config["run"]["historical_strategy_lookback_years"] == 4
    assert config["outputs"]["output_dir"] == "custom_outputs"
    assert config["outputs"]["save_prediction_snapshot"] is False
    assert config["outputs"]["save_report_images"] is False
    assert config["outputs"]["save_raw_results"] is False
    assert config["outputs"]["post_to_discord"] is True
    assert base_config["run"]["year"] == 2026


def test_write_temp_config_round_trips_json() -> None:
    config = load_default_config()
    path = write_temp_config(config)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["run"]["year"] == config["run"]["year"]
