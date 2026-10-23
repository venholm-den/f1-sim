from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = "config/default_run_config.json"


@dataclass(frozen=True)
class RunSettings:
    year: int
    event: str | int
    session: str
    n_sims: int
    random_seed: int
    n_baseline_races: int
    default_overtaking_difficulty: float
    historical_strategy_lookback_years: int
    weekend_sessions: list[str] | None = None
    feature_cutoff_utc: str | None = None


@dataclass(frozen=True)
class OutputSettings:
    output_dir: str
    save_prediction_snapshot: bool
    save_report_images: bool
    save_raw_results: bool
    post_to_discord: bool


@dataclass(frozen=True)
class DataSettings:
    fantasy_prices_path: str
    track_profiles_path: str
    fia_document_index_path: str
    team_power_units_path: str


@dataclass(frozen=True)
class ModelSettings:
    model_version: str
    use_fastf1_weather: bool
    use_race_control_context: bool
    use_track_red_flag_base_chance: bool
    use_weather_forecast: bool = True
    use_historical_model_calibration: bool = False
    historical_model_dir: str = "data/models"
    historical_finish_weight: float = 0.15
    historical_dnf_weight: float = 0.30
    use_stint_pace: bool = False
    pace_blend: str = 'legacy'
    retirement_model: str = 'legacy'
    retirement_history_races: int = 30
    qualifying_pace_model_path: str | None = None
    qualifying_classifications_path: str | None = None
    race_engine: str = 'aggregate_legacy'
    pit_scenarios_path: str | None = None
    weather_model: str = 'session_legacy'
    race_weather_report_path: str | None = None
    agent_settings: dict | None = None

    def __post_init__(self):
        if self.pace_blend not in {'legacy', 'single_pace_blend_v1', 'qualifying_partial_pooling_v1'}:
            raise ValueError('Unknown pace_blend; choose legacy or single_pace_blend_v1.')
        if self.retirement_model not in {'legacy', 'all_cause_dnf_v2', 'retirement_progress_v1', 'survival_dnf_v1'}:
            raise ValueError('Unknown retirement_model.')
        if not 1 <= self.retirement_history_races <= 100:
            raise ValueError('retirement_history_races must be between 1 and 100.')
        if self.use_stint_pace and self.pace_blend != 'legacy':
            raise ValueError('Matched-stint and single-pass pace experiments must be tested separately.')
        if self.pace_blend == 'qualifying_partial_pooling_v1':
            if not self.qualifying_pace_model_path or self.use_historical_model_calibration:
                raise ValueError('Qualifying pace requires its own artifact and separate historical calibration.')
        if self.race_engine not in {'aggregate_legacy', 'pit_scenarios_v1', 'agent_laps_v1'}:
            raise ValueError('Unknown race_engine.')
        if self.agent_settings is not None:
            if self.race_engine != 'agent_laps_v1':
                raise ValueError('Agent settings require the agent race engine.')
            from src.agent_race import AgentSettings
            AgentSettings(**self.agent_settings)
        if self.weather_model not in {'session_legacy', 'race_window_v1'}:
            raise ValueError('Unknown weather_model.')
        if self.weather_model == 'race_window_v1' and not self.use_weather_forecast:
            raise ValueError('Race-window weather requires forecast acquisition enabled.')


@dataclass(frozen=True)
class AppConfig:
    run: RunSettings
    outputs: OutputSettings
    data: DataSettings
    model: ModelSettings
    source_path: str

    def __post_init__(self):
        next_candidate = (self.model.pace_blend == 'qualifying_partial_pooling_v1'
            or bool(self.model.qualifying_classifications_path)
            or self.model.race_engine != 'aggregate_legacy'
            or self.model.weather_model != 'session_legacy'
            or self.model.retirement_model == 'survival_dnf_v1')
        if next_candidate and self.outputs.post_to_discord:
            raise ValueError('Unpromoted simulation candidates support local output only.')


def _read_json(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Run config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    output = dict(base)

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(output.get(key), dict):
            output[key] = _deep_update(output[key], value)
        else:
            output[key] = value

    return output


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _apply_environment_overrides(config: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "run": {},
        "outputs": {},
    }

    if os.getenv("F1_SIM_YEAR"):
        updates["run"]["year"] = int(os.getenv("F1_SIM_YEAR", "0"))

    if os.getenv("F1_SIM_EVENT"):
        updates["run"]["event"] = os.getenv("F1_SIM_EVENT")

    if os.getenv("F1_SIM_SESSION"):
        updates["run"]["session"] = os.getenv("F1_SIM_SESSION")

    if os.getenv("F1_SIM_N_SIMS"):
        updates["run"]["n_sims"] = int(os.getenv("F1_SIM_N_SIMS", "0"))

    if os.getenv("F1_SIM_RANDOM_SEED"):
        updates["run"]["random_seed"] = int(os.getenv("F1_SIM_RANDOM_SEED", "0"))

    if os.getenv("POST_TO_DISCORD") is not None:
        updates["outputs"]["post_to_discord"] = _env_bool("POST_TO_DISCORD", False)

    return _deep_update(config, updates)


def _apply_cli_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "run": {},
        "outputs": {},
    }

    if args.year is not None:
        updates["run"]["year"] = args.year

    if args.event is not None:
        updates["run"]["event"] = args.event

    if args.session is not None:
        updates["run"]["session"] = args.session

    if args.n_sims is not None:
        updates["run"]["n_sims"] = args.n_sims

    if args.seed is not None:
        updates["run"]["random_seed"] = args.seed

    if args.post_to_discord is not None:
        updates["outputs"]["post_to_discord"] = args.post_to_discord

    if args.baseline_races is not None:
        updates["run"]["n_baseline_races"] = args.baseline_races

    if args.default_overtaking_difficulty is not None:
        updates["run"]["default_overtaking_difficulty"] = args.default_overtaking_difficulty

    if args.strategy_lookback_years is not None:
        updates["run"]["historical_strategy_lookback_years"] = args.strategy_lookback_years

    return _deep_update(config, updates)


def parse_config_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the F1 simulation.")

    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the run config JSON file.",
    )
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--event", default=None)
    parser.add_argument("--session", default=None)
    parser.add_argument("--n-sims", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--baseline-races", type=int, default=None)
    parser.add_argument("--default-overtaking-difficulty", type=float, default=None)
    parser.add_argument("--strategy-lookback-years", type=int, default=None)

    discord_group = parser.add_mutually_exclusive_group()
    discord_group.add_argument(
        "--post-to-discord",
        action="store_true",
        dest="post_to_discord",
        default=None,
    )
    discord_group.add_argument(
        "--no-discord",
        action="store_false",
        dest="post_to_discord",
        default=None,
    )

    return parser.parse_args()


def load_app_config(
    config_path: str = DEFAULT_CONFIG_PATH,
    args: argparse.Namespace | None = None,
) -> AppConfig:
    raw = _read_json(config_path)
    if not raw.get('ignore_environment_overrides', False):
        raw = _apply_environment_overrides(raw)

    if args is not None:
        raw = _apply_cli_overrides(raw, args)

    run = raw.get("run", {})
    outputs = raw.get("outputs", {})
    data = raw.get("data", {})
    model = raw.get("model", {})

    return AppConfig(
        run=RunSettings(
            weekend_sessions=run.get('weekend_sessions'),
            feature_cutoff_utc=run.get('feature_cutoff_utc'),
            year=int(run.get("year", 2026)),
            event=run.get("event", "latest"),
            session=str(run.get("session", "Q")),
            n_sims=int(run.get("n_sims", 50000)),
            random_seed=int(run.get("random_seed", 42)),
            n_baseline_races=int(run.get("n_baseline_races", 5)),
            default_overtaking_difficulty=float(run.get("default_overtaking_difficulty", 0.55)),
            historical_strategy_lookback_years=int(
                run.get("historical_strategy_lookback_years", 5)
            ),
        ),
        outputs=OutputSettings(
            output_dir=str(outputs.get("output_dir", "outputs")),
            save_prediction_snapshot=bool(outputs.get("save_prediction_snapshot", True)),
            save_report_images=bool(outputs.get("save_report_images", True)),
            save_raw_results=bool(outputs.get("save_raw_results", True)),
            post_to_discord=bool(outputs.get("post_to_discord", False)),
        ),
        data=DataSettings(
            fantasy_prices_path=str(data.get("fantasy_prices_path", "data/fantasy_prices.csv")),
            track_profiles_path=str(data.get("track_profiles_path", "data/track_profiles.csv")),
            fia_document_index_path=str(
                data.get("fia_document_index_path", "data/fia_documents/fia_document_index.csv")
            ),
            team_power_units_path=str(
                data.get("team_power_units_path", "data/team_power_units.csv")
            ),
        ),
        model=ModelSettings(
            model_version=str(model.get("model_version", "phase_1_performance_profile")),
            use_fastf1_weather=bool(model.get("use_fastf1_weather", True)),
            use_race_control_context=bool(model.get("use_race_control_context", True)),
            use_track_red_flag_base_chance=bool(
                model.get("use_track_red_flag_base_chance", True)
            ),
            use_weather_forecast=bool(model.get("use_weather_forecast", True)),
            use_historical_model_calibration=bool(
                model.get("use_historical_model_calibration", False)
            ),
            historical_model_dir=str(model.get("historical_model_dir", "data/models")),
            historical_finish_weight=float(model.get("historical_finish_weight", 0.15)),
            historical_dnf_weight=float(model.get("historical_dnf_weight", 0.30)),
            use_stint_pace=bool(model.get('use_stint_pace', False)),
            pace_blend=str(model.get('pace_blend', 'legacy')),
            retirement_model=str(model.get('retirement_model', 'legacy')),
            retirement_history_races=int(model.get('retirement_history_races', 30)),
            qualifying_pace_model_path=model.get('qualifying_pace_model_path'),
            qualifying_classifications_path=model.get('qualifying_classifications_path'),
            race_engine=str(model.get('race_engine', 'aggregate_legacy')),
            pit_scenarios_path=model.get('pit_scenarios_path'),
            weather_model=str(model.get('weather_model', 'session_legacy')),
            race_weather_report_path=model.get('race_weather_report_path'),
            agent_settings=model.get('agent_settings'),
        ),
        source_path=str(config_path),
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "run": {
            "year": config.run.year,
            "event": config.run.event,
            "session": config.run.session,
            "n_sims": config.run.n_sims,
            "random_seed": config.run.random_seed,
            "n_baseline_races": config.run.n_baseline_races,
            "default_overtaking_difficulty": config.run.default_overtaking_difficulty,
            "historical_strategy_lookback_years": config.run.historical_strategy_lookback_years,
            "weekend_sessions": config.run.weekend_sessions,
            "feature_cutoff_utc": config.run.feature_cutoff_utc,
        },
        "outputs": {
            "output_dir": config.outputs.output_dir,
            "save_prediction_snapshot": config.outputs.save_prediction_snapshot,
            "save_report_images": config.outputs.save_report_images,
            "post_to_discord": config.outputs.post_to_discord,
            "save_raw_results": config.outputs.save_raw_results,
        },
        "data": {
            "fantasy_prices_path": config.data.fantasy_prices_path,
            "track_profiles_path": config.data.track_profiles_path,
            "fia_document_index_path": config.data.fia_document_index_path,
            "team_power_units_path": config.data.team_power_units_path,
        },
        "model": {
            "model_version": config.model.model_version,
            "use_fastf1_weather": config.model.use_fastf1_weather,
            "use_race_control_context": config.model.use_race_control_context,
            "use_track_red_flag_base_chance": config.model.use_track_red_flag_base_chance,
            "use_weather_forecast": config.model.use_weather_forecast,
            "use_historical_model_calibration": config.model.use_historical_model_calibration,
            "historical_model_dir": config.model.historical_model_dir,
            "historical_finish_weight": config.model.historical_finish_weight,
            "historical_dnf_weight": config.model.historical_dnf_weight,
            "use_stint_pace": config.model.use_stint_pace,
            "pace_blend": config.model.pace_blend,
            "retirement_model": config.model.retirement_model,
            "retirement_history_races": config.model.retirement_history_races,
            "qualifying_pace_model_path": config.model.qualifying_pace_model_path,
            "qualifying_classifications_path": config.model.qualifying_classifications_path,
            "race_engine": config.model.race_engine,
            "pit_scenarios_path": config.model.pit_scenarios_path,
            "weather_model": config.model.weather_model,
            "race_weather_report_path": config.model.race_weather_report_path,
            "agent_settings": config.model.agent_settings,
        },
        "source_path": config.source_path,
    }
