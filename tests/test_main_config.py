from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace
from dataclasses import replace

import pandas as pd
import pytest

import main
from src.run_config import AppConfig, DataSettings, ModelSettings, OutputSettings, RunSettings


def _app_config(
    output_dir: str,
    fantasy_prices_path: str,
    fia_index_path: str,
) -> AppConfig:
    return AppConfig(
        run=RunSettings(
            year=2026,
            event="Bahrain Grand Prix",
            session="Q",
            n_sims=3,
            random_seed=777,
            n_baseline_races=2,
            default_overtaking_difficulty=0.55,
            historical_strategy_lookback_years=5,
        ),
        outputs=OutputSettings(
            output_dir=output_dir,
            save_prediction_snapshot=False,
            save_report_images=False,
            save_raw_results=False,
            post_to_discord=False,
        ),
        data=DataSettings(
            fantasy_prices_path=fantasy_prices_path,
            track_profiles_path="unused_track_profiles.csv",
            fia_document_index_path=fia_index_path,
            team_power_units_path="unused_team_power_units.csv",
        ),
        model=ModelSettings(
            model_version="test",
            use_fastf1_weather=True,
            use_race_control_context=True,
            use_track_red_flag_base_chance=True,
        ),
        source_path="test_config.json",
    )


@pytest.mark.parametrize('experimental', [False, True, 'next', 'agent', 'agent_full'])
def test_main_uses_config_seed_and_output_dir(monkeypatch, tmp_path, experimental) -> None:
    output_dir = tmp_path / "custom_outputs"
    fantasy_prices_path = tmp_path / "data" / "fantasy_prices.csv"
    fia_index_path = tmp_path / "data" / "fia_document_index.csv"
    captured: dict[str, int] = {}
    snapshot_called = False

    session = SimpleNamespace(laps=pd.DataFrame({"Driver": ["RUS", "HAM"]}))
    metadata = {
        "year": 2026,
        "event": "Bahrain Grand Prix",
        "round": 1,
        "session": "Q",
    }

    features = pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "grid_position": [1, 2],
        }
    )

    race_summary = pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "avg_finish": [1.2, 1.8],
            "avg_points": [22.0, 18.0],
            "win_chance": [0.7, 0.3],
            "podium_chance": [1.0, 1.0],
            "points_chance": [1.0, 1.0],
            "dnf_chance": [0.0, 0.0],
            "avg_fantasy_points": [31.0, 26.0],
        }
    )
    position_matrix = pd.DataFrame({"Driver": ["RUS", "HAM"], "P1": [0.7, 0.3], "P2": [0.3, 0.7]})
    results = pd.DataFrame({"Driver": ["RUS", "HAM"], "Team": ["Mercedes", "Ferrari"]})

    def fake_simulate_races(**kwargs):
        captured["n_sims"] = kwargs["n_sims"]
        captured["seed"] = kwargs["seed"]
        if experimental is True:
            assert kwargs['retirement_classification'] == 'completed_laps_v1'
            assert kwargs['features'].retirement_progress_version.notna().all()
            assert kwargs['features'].dnf_prob.tolist() == pytest.approx([.1, .1])
        elif experimental == 'next':
            assert kwargs['sample_pace_posterior'] is True
            assert kwargs['retirement_classification'] == 'completed_laps_v1'
            assert len(kwargs['pit_plans']) == 4
            assert kwargs['weather_modifiers']['weather_source'] == 'race_window_test'
            assert kwargs['features'].pace_posterior_sd_seconds.gt(0).all()
            assert kwargs['features'].retirement_model_version.eq('competing_risk_survival_v1_experimental').all()
        elif experimental in {'agent', 'agent_full'}:
            assert len(kwargs['pit_plans']) == 4
            assert kwargs['agent_settings']['season_year'] == 2026
            assert kwargs['agent_settings']['passability'] == pytest.approx(.45)
            assert kwargs['agent_settings']['initial_fuel_kg'] == 70.
        return race_summary, position_matrix, results

    def fake_snapshot(**kwargs):
        nonlocal snapshot_called
        snapshot_called = True
        return "should_not_be_called.csv"

    monkeypatch.setattr(main, "parse_config_args", lambda: Namespace(config="test_config.json"))
    config = _app_config(str(output_dir), str(fantasy_prices_path), str(fia_index_path))
    if experimental is True:
        config = replace(config, model=replace(config.model, pace_blend='single_pace_blend_v1',
                                               retirement_model='retirement_progress_v1'))
    elif experimental in {'agent', 'agent_full'}:
        features['estimated_race_laps'] = 66
        from dataclasses import asdict
        from src.agent_race import AgentSettings
        settings = asdict(AgentSettings()) if experimental == 'agent_full' else None
        config = replace(config, model=replace(config.model, race_engine='agent_laps_v1', agent_settings=settings))
    elif experimental == 'next':
        from src.qualifying_pace import fit_qualifying_pace
        from tests.test_accuracy_benchmark import races
        import src.qualifying_pace as pace_module
        import src.race_window_weather as weather_module
        data = races()
        artifact = fit_qualifying_pace([(r.sessions['Q'], r.sessions['R'],
            dict(year=r.year, round=r.round, event=r.event)) for r in data[:3]], metadata)
        monkeypatch.setattr(pace_module, 'load_qualifying_pace', lambda path: artifact)
        monkeypatch.setattr(weather_module, 'candidate_weather', lambda *args, **kwargs:
                            {'weather_source': 'race_window_test', 'rainfall_flag': False})
        session.results = pd.DataFrame({'Abbreviation': ['RUS', 'HAM'], 'Position': [1, 2]})
        session.laps['LapTime'] = pd.to_timedelta([90, 91], unit='s')
        features['race_pace_score'] = [0., .5]
        features['long_run_pace_score'] = [0., .5]
        features['estimated_race_laps'] = 66
        config = replace(config, model=replace(config.model, pace_blend='qualifying_partial_pooling_v1',
            qualifying_pace_model_path='test_candidate.json', weather_model='race_window_v1',
            race_engine='pit_scenarios_v1', retirement_model='survival_dnf_v1'))
    monkeypatch.setattr(
        main,
        "load_app_config",
        lambda config_path, args: config,
    )
    monkeypatch.setattr(main, "enable_fastf1_cache", lambda: None)
    monkeypatch.setattr(main, "load_session", lambda *args, **kwargs: (session, metadata))
    monkeypatch.setattr(main, "export_weekend_lap_details", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "build_tyre_csv_outputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        main,
        "load_track_profile",
        lambda *args, **kwargs: {"event": "Bahrain Grand Prix", "overtaking_difficulty": 0.55,
                                "safety_car_chance": 0.4, "red_flag_base_chance": 0.035,
                                "profile_status": "generic_uncalibrated"},
    )
    monkeypatch.setattr(main, "summarize_weather", lambda session: {})
    monkeypatch.setattr(main, "build_driver_features", lambda laps: features.copy())
    monkeypatch.setattr(main, "load_recent_race_sessions", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "_build_baseline_features", lambda recent_races: pd.DataFrame())
    monkeypatch.setattr(main, "build_model_features", lambda **kwargs: features.copy())
    monkeypatch.setattr(main, "build_grid_features", lambda **kwargs: kwargs["model_features"])
    monkeypatch.setattr(main, "add_performance_profile", lambda **kwargs: kwargs["model_features"])
    monkeypatch.setattr(main, "ensure_price_template", lambda *args, **kwargs: str(fantasy_prices_path))
    monkeypatch.setattr(main, "simulate_races", fake_simulate_races)
    monkeypatch.setattr(main, "calculate_fantasy_summary", lambda **kwargs: (race_summary, results))
    monkeypatch.setattr(main, "save_prediction_snapshot", fake_snapshot)
    monkeypatch.setattr(main, "build_season_projection_outputs", lambda **kwargs: {})
    monkeypatch.setattr(main, "build_clean_strategy_outputs", lambda **kwargs: {})
    monkeypatch.setattr(main, "build_model_commentary", lambda **kwargs: ["test commentary"])

    main.main()

    assert captured == {"n_sims": 3, "seed": 777}
    assert snapshot_called is False
    assert (output_dir / "current_session_features.csv").exists()
    assert (output_dir / "baseline_race_features.csv").exists()
    assert (output_dir / "driver_model_features.csv").exists()
    assert (output_dir / "simulation_summary.csv").exists()
    assert (output_dir / "position_matrix.csv").exists()
    assert (output_dir / "report" / "model_commentary.txt").exists()
