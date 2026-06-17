from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.app_services.config_service import (
    PortableRunSettings,
    build_run_config,
    load_json_config,
    settings_from_config,
    write_temp_run_config,
)
from src.app_services.data_health import read_csv_preview, validate_data_sources
from src.app_services.model_signals import load_model_signals
from src.app_services.output_index import list_core_outputs, read_output_table


def _settings() -> PortableRunSettings:
    return PortableRunSettings(
        year=2026,
        event="Barcelona Grand Prix",
        session="Q",
        n_sims=100,
        random_seed=7,
        n_baseline_races=3,
        historical_strategy_lookback_years=5,
        default_overtaking_difficulty=0.55,
        output_dir="outputs-test",
        save_prediction_snapshot=True,
        save_report_images=False,
        save_raw_results=False,
        post_to_discord=False,
        use_weather_forecast=True,
        use_race_control_context=True,
        use_track_red_flag_base_chance=True,
    )


def test_build_run_config_and_temp_write() -> None:
    config = build_run_config(
        {
            "run": {},
            "outputs": {},
            "model": {},
        },
        _settings(),
    )
    config_path = write_temp_run_config(config)
    saved = json.loads(config_path.read_text(encoding="utf-8"))

    assert saved["run"]["year"] == 2026
    assert saved["run"]["event"] == "Barcelona Grand Prix"
    assert saved["outputs"]["output_dir"] == "outputs-test"
    assert saved["model"]["use_weather_forecast"] is True


def test_settings_from_config_reads_defaults() -> None:
    settings = settings_from_config(
        {
            "run": {"year": 2025, "event": "latest"},
            "outputs": {"output_dir": "custom"},
            "model": {"use_weather_forecast": False},
        }
    )

    assert settings.year == 2025
    assert settings.event == "latest"
    assert settings.output_dir == "custom"
    assert settings.use_weather_forecast is False


def test_load_json_config_resolves_bundled_paths(tmp_path, monkeypatch) -> None:
    bundle_root = tmp_path / "bundle"
    config_dir = bundle_root / "config"
    data_dir = bundle_root / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir()
    (data_dir / "fantasy_prices.csv").write_text("Driver\nRUS\n", encoding="utf-8")
    (config_dir / "default_run_config.json").write_text(
        json.dumps(
            {
                "run": {},
                "outputs": {},
                "model": {},
                "data": {"fantasy_prices_path": "data/fantasy_prices.csv"},
            }
        ),
        encoding="utf-8",
    )

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(bundle_root), raising=False)

    config = load_json_config("config/default_run_config.json")

    assert config["data"]["fantasy_prices_path"] == str(data_dir / "fantasy_prices.csv")


def test_validate_data_sources_and_preview(tmp_path) -> None:
    fantasy = tmp_path / "fantasy.csv"
    track = tmp_path / "track.csv"
    fia = tmp_path / "fia.csv"
    power_units = tmp_path / "power.csv"

    pd.DataFrame({"Driver": ["RUS"], "fantasy_price": [25.0]}).to_csv(fantasy, index=False)
    pd.DataFrame({"Event": ["Barcelona"], "OvertakingDifficulty": [0.72]}).to_csv(track, index=False)
    pd.DataFrame({"year": [2026], "event": ["Barcelona"], "document_type": ["grid"]}).to_csv(
        fia,
        index=False,
    )
    pd.DataFrame({"Year": [2026], "Team": ["Mercedes"], "PowerUnitSupplier": ["Mercedes"]}).to_csv(
        power_units,
        index=False,
    )

    config = {
        "data": {
            "fantasy_prices_path": str(fantasy),
            "track_profiles_path": str(track),
            "fia_document_index_path": str(fia),
            "team_power_units_path": str(power_units),
        }
    }
    statuses = validate_data_sources(config)
    preview = read_csv_preview(fantasy)

    assert {status.status for status in statuses} == {"valid"}
    assert preview.iloc[0]["Driver"] == "RUS"


def test_output_index_reads_known_files(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    pd.DataFrame({"Driver": ["RUS"], "win_chance": [0.5]}).to_csv(
        output_dir / "simulation_summary.csv",
        index=False,
    )

    files = list_core_outputs(output_dir)
    table = read_output_table(output_dir, "simulation_summary.csv")

    assert any(file.label == "Simulation Summary" and file.exists for file in files)
    assert table.iloc[0]["Driver"] == "RUS"


def test_load_model_signals_summarises_feature_outputs(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "grid_position": [1, 2],
            "grid_source": ["actual_session_results", "fia_document_index"],
            "current_signal_quality": [0.8, 0.6],
            "effective_current_weight": [0.4, 0.3],
            "model_uncertainty": [0.2, 0.4],
            "performance_uncertainty": [0.3, 0.5],
            "current_pace_outlier_flag": [False, True],
            "quali_pace_score": [0.9, 0.8],
            "projected_lap_time": [80.1, 80.4],
        }
    ).to_csv(output_dir / "driver_model_features.csv", index=False)
    (report_dir / "model_commentary.txt").write_text("Model read: test.", encoding="utf-8")

    signals = load_model_signals(output_dir)

    assert signals.features_exist is True
    assert signals.commentary == "Model read: test."
    assert signals.overview.loc[signals.overview["Metric"].eq("Drivers"), "Value"].iloc[0] == "2"
    assert list(signals.driver_signals["Driver"]) == ["RUS", "HAM"]
