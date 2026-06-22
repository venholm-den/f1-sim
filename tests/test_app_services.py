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
from portable_app.web_backend import (
    QUALI_SESSIONS,
    PRACTICE_SESSIONS,
    available_sessions_for_event,
    available_event_names,
    fastest_lap,
    sector_times_table,
    sector_leaders,
    setup_options_payload,
    session_mode,
    session_screen_payloads,
)


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
        use_historical_model_calibration=True,
        historical_finish_weight=0.15,
        historical_dnf_weight=0.30,
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
    assert saved["model"]["use_historical_model_calibration"] is True
    assert saved["model"]["historical_finish_weight"] == 0.15


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
    assert settings.use_historical_model_calibration is True
    assert settings.historical_finish_weight == 0.15


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
            "historical_model_available": [True, True],
            "historical_predicted_finish": [1.7, 4.2],
            "historical_dnf_probability": [0.04, 0.08],
        }
    ).to_csv(output_dir / "driver_model_features.csv", index=False)
    (report_dir / "model_commentary.txt").write_text("Model read: test.", encoding="utf-8")

    signals = load_model_signals(output_dir)

    assert signals.features_exist is True
    assert signals.commentary == "Model read: test."
    assert signals.overview.loc[signals.overview["Metric"].eq("Drivers"), "Value"].iloc[0] == "2"
    assert signals.overview.loc[
        signals.overview["Metric"].eq("Historical model rows"),
        "Value",
    ].iloc[0] == "2"
    assert list(signals.driver_signals["Driver"]) == ["RUS", "HAM"]
    assert "historical_predicted_finish" in signals.driver_signals.columns


def test_session_mode_groups_f1_session_types() -> None:
    assert session_mode("PRE") == "pre"
    assert session_mode("FP2") == "practice"
    assert session_mode("SQ") == "quali"
    assert session_mode("R") == "race"
    assert session_mode("unknown") == "race"


def test_available_sessions_for_specific_event_follow_weekend_format(monkeypatch) -> None:
    now = pd.Timestamp("2026-06-22T12:00:00")
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1],
            "EventName": ["Canadian Grand Prix"],
            "EventDate": [pd.Timestamp("2026-06-23T20:00:00")],
            "Session1": ["Practice 1"],
            "Session1Date": [pd.Timestamp("2026-06-21T12:00:00")],
            "Session2": ["Practice 2"],
            "Session2Date": [pd.Timestamp("2026-06-22T10:00:00")],
            "Session3": ["Practice 3"],
            "Session3Date": [pd.Timestamp("2026-06-22T15:00:00")],
            "Session4": ["Qualifying"],
            "Session4Date": [pd.Timestamp("2026-06-22T18:00:00")],
            "Session5": ["Race"],
            "Session5Date": [pd.Timestamp("2026-06-23T20:00:00")],
        }
    )

    monkeypatch.setattr("portable_app.web_backend._event_schedule", lambda year: schedule)

    assert available_sessions_for_event(2026, "Canadian Grand Prix", now=now) == [
        "R",
        "Q",
        "FP3",
        "FP2",
        "FP1",
    ]


def test_event_names_fall_back_to_track_profiles_when_schedule_unavailable(monkeypatch, tmp_path) -> None:
    track_profiles = tmp_path / "track_profiles.csv"
    pd.DataFrame(
        {
            "Event": ["Monaco Grand Prix", "Canadian Grand Prix"],
            "OvertakingDifficulty": [0.88, 0.48],
        }
    ).to_csv(track_profiles, index=False)

    monkeypatch.setattr("portable_app.web_backend._event_schedule", lambda year: pd.DataFrame())

    assert available_event_names(2026, track_profiles_path=str(track_profiles)) == [
        "Monaco Grand Prix",
        "Canadian Grand Prix",
    ]


def test_specific_event_sessions_fall_back_to_race_weekend_when_schedule_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("portable_app.web_backend._event_schedule", lambda year: pd.DataFrame())

    assert available_sessions_for_event(2026, "Monaco Grand Prix") == [
        "R",
        "Q",
        "SQ",
        "S",
        "FP3",
        "FP2",
        "FP1",
    ]
    assert available_sessions_for_event(2026, "latest") == ["PRE"]


def test_latest_available_sessions_are_time_gated(monkeypatch) -> None:
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1],
            "EventName": ["Future Grand Prix"],
            "EventDate": [pd.Timestamp("2099-06-23T20:00:00")],
            "Session1": ["Practice 1"],
            "Session1Date": [pd.Timestamp("2099-06-21T12:00:00")],
            "Session2": ["Practice 2"],
            "Session2Date": [pd.Timestamp("2099-06-22T10:00:00")],
            "Session3": ["Practice 3"],
            "Session3Date": [pd.Timestamp("2099-06-22T15:00:00")],
            "Session4": ["Qualifying"],
            "Session4Date": [pd.Timestamp("2099-06-22T18:00:00")],
            "Session5": ["Race"],
            "Session5Date": [pd.Timestamp("2099-06-23T20:00:00")],
        }
    )

    monkeypatch.setattr("portable_app.web_backend._event_schedule", lambda year: schedule)

    assert available_sessions_for_event(
        2099,
        "latest",
        now=pd.Timestamp("2099-06-20T12:00:00"),
    ) == ["PRE"]
    assert available_sessions_for_event(
        2099,
        "latest",
        now=pd.Timestamp("2099-06-22T12:00:00"),
    ) == ["FP2", "FP1"]


def test_setup_options_payload_uses_selected_track_profile(monkeypatch, tmp_path) -> None:
    track_profiles = tmp_path / "track_profiles.csv"
    pd.DataFrame(
        {
            "Event": ["Monaco Grand Prix"],
            "OvertakingDifficulty": [0.88],
            "SafetyCarChance": [0.55],
            "RedFlagBaseChance": [0.08],
            "Latitude": [43.7347],
            "Longitude": [7.4206],
            "Notes": ["Very hard to overtake"],
        }
    ).to_csv(track_profiles, index=False)

    schedule = pd.DataFrame(
        {
            "RoundNumber": [1],
            "EventName": ["Monaco Grand Prix"],
            "EventDate": [pd.Timestamp("2099-06-23T20:00:00")],
            "Session1": ["Practice 1"],
            "Session1Date": [pd.Timestamp("2099-06-21T12:00:00")],
        }
    )

    monkeypatch.setattr("portable_app.web_backend._event_schedule", lambda year: schedule)

    payload = setup_options_payload(
        year=2026,
        event="Monaco Grand Prix",
        track_profiles_path=str(track_profiles),
    )

    assert payload["trackProfile"]["event"] == "Monaco Grand Prix"
    assert payload["trackProfile"]["overtaking_difficulty"] == 0.88
    assert payload["sessions"] == ["FP1"]


def test_sector_times_table_splits_practice_and_quali() -> None:
    laps = pd.DataFrame(
        {
            "Session": ["FP1", "FP2", "Q", "Q", "R"],
            "Driver": ["RUS", "HAM", "LEC", "VER", "NOR"],
            "Team": ["Mercedes", "Ferrari", "Ferrari", "Red Bull", "McLaren"],
            "LapNumber": [4, 7, 10, 11, 22],
            "CleanPushLap": [True, True, True, False, True],
            "Sector1Seconds": [30.2, 29.8, 28.9, 28.1, 31.0],
            "Sector2Seconds": [34.0, 33.6, 33.2, 32.8, 35.1],
            "Sector3Seconds": [22.5, 22.2, 21.9, 21.4, 23.0],
        }
    )

    practice = sector_times_table(laps, PRACTICE_SESSIONS)
    quali = sector_times_table(laps, QUALI_SESSIONS)

    assert practice.loc[practice["Sector"].eq("S1"), "Driver"].iloc[0] == "HAM"
    assert quali.loc[quali["Sector"].eq("S1"), "Driver"].iloc[0] == "LEC"
    assert "VER" not in set(quali["Driver"])


def test_session_screen_payloads_include_best_sector_tables(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    lap_dir = output_dir / "lap_details"
    strategy_dir = output_dir / "strategy"
    lap_dir.mkdir(parents=True)
    strategy_dir.mkdir()

    pd.DataFrame(
        {
            "Session": ["FP1", "Q"],
            "Driver": ["RUS", "LEC"],
            "Team": ["Mercedes", "Ferrari"],
            "LapNumber": [5, 9],
            "CleanPushLap": [True, True],
            "Sector1Seconds": [29.7, 28.8],
            "Sector2Seconds": [33.8, 33.1],
            "Sector3Seconds": [22.3, 21.8],
        }
    ).to_csv(lap_dir / "weekend_lap_details.csv", index=False)
    pd.DataFrame(
        {
            "Session": ["FP1"],
            "Driver": ["RUS"],
            "Team": ["Mercedes"],
            "Compound": ["SOFT"],
            "clean_laps": [4],
            "best_lap": [86.0],
            "median_lap": [86.4],
            "ideal_lap": [85.8],
        }
    ).to_csv(lap_dir / "practice_lap_summary.csv", index=False)
    pd.DataFrame(
        {
            "Driver": ["LEC"],
            "Team": ["Ferrari"],
            "quali_rank_from_laps": [1],
            "clean_laps": [3],
            "best_lap": [83.7],
            "gap_to_fastest": [0.0],
            "ideal_lap": [83.5],
            "ideal_gap_to_fastest": [-0.2],
        }
    ).to_csv(lap_dir / "quali_lap_summary.csv", index=False)

    payload = session_screen_payloads(
        output_dir,
        pd.DataFrame({"Driver": ["LEC"], "avg_finish": [1.8]}),
        pd.DataFrame({"Driver": ["LEC"], "predicted_strategy": ["S-M"]}),
    )

    assert payload["practice"]["sectors"]["rows"][0]["Driver"] == "RUS"
    assert payload["quali"]["sectors"]["rows"][0]["Driver"] == "LEC"
    assert payload["race"]["summary"]["rows"][0]["Driver"] == "LEC"


def test_track_cards_are_filtered_to_selected_session(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    lap_dir = output_dir / "lap_details"
    lap_dir.mkdir(parents=True)

    pd.DataFrame(
        {
            "Session": ["FP1", "Q", "Q"],
            "Driver": ["RUS", "LEC", "NOR"],
            "Team": ["Mercedes", "Ferrari", "McLaren"],
            "LapNumber": [4, 8, 9],
            "CleanPushLap": [True, True, True],
            "LapTimeSeconds": [84.1, 80.5, 80.1],
            "Sector1Seconds": [29.4, 28.4, 28.6],
            "Sector2Seconds": [33.2, 32.2, 32.0],
            "Sector3Seconds": [21.5, 20.7, 20.9],
        }
    ).to_csv(lap_dir / "weekend_lap_details.csv", index=False)

    quali_fastest = fastest_lap(output_dir, "Q")
    quali_sectors = sector_leaders(output_dir, "Q")
    practice_fastest = fastest_lap(output_dir, "FP1")

    assert quali_fastest["driver"] == "NOR"
    assert quali_sectors["S1"]["driver"] == "LEC"
    assert practice_fastest["driver"] == "RUS"
