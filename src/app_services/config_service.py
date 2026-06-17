from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.app_services.app_paths import resource_path

DEFAULT_CONFIG_PATH = Path("config/default_run_config.json")
DATA_PATH_KEYS = [
    "fantasy_prices_path",
    "track_profiles_path",
    "fia_document_index_path",
    "team_power_units_path",
]


@dataclass(frozen=True)
class PortableRunSettings:
    year: int
    event: str
    session: str
    n_sims: int
    random_seed: int
    n_baseline_races: int
    historical_strategy_lookback_years: int
    default_overtaking_difficulty: float
    output_dir: str
    save_prediction_snapshot: bool
    save_report_images: bool
    save_raw_results: bool
    post_to_discord: bool
    use_weather_forecast: bool
    use_race_control_context: bool
    use_track_red_flag_base_chance: bool


def load_json_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = resource_path(path)

    with config_path.open("r", encoding="utf-8") as file:
        return normalize_data_paths(json.load(file))


def normalize_data_paths(config: dict[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(config)
    data = config.get("data")

    if not isinstance(data, dict):
        return config

    for key in DATA_PATH_KEYS:
        path_text = data.get(key)

        if path_text:
            data[key] = str(resource_path(str(path_text)))

    return config


def build_run_config(
    base_config: dict[str, Any],
    settings: PortableRunSettings,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    run = config.setdefault("run", {})
    outputs = config.setdefault("outputs", {})
    model = config.setdefault("model", {})

    run["year"] = settings.year
    run["event"] = settings.event
    run["session"] = settings.session
    run["n_sims"] = settings.n_sims
    run["random_seed"] = settings.random_seed
    run["n_baseline_races"] = settings.n_baseline_races
    run["historical_strategy_lookback_years"] = settings.historical_strategy_lookback_years
    run["default_overtaking_difficulty"] = settings.default_overtaking_difficulty

    outputs["output_dir"] = settings.output_dir
    outputs["save_prediction_snapshot"] = settings.save_prediction_snapshot
    outputs["save_report_images"] = settings.save_report_images
    outputs["save_raw_results"] = settings.save_raw_results
    outputs["post_to_discord"] = settings.post_to_discord

    model["use_weather_forecast"] = settings.use_weather_forecast
    model["use_race_control_context"] = settings.use_race_control_context
    model["use_track_red_flag_base_chance"] = settings.use_track_red_flag_base_chance

    return config


def write_temp_run_config(config: dict[str, Any]) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="f1-sim-portable-"))
    config_path = temp_dir / "run_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return config_path


def settings_from_config(config: dict[str, Any]) -> PortableRunSettings:
    run = config.get("run", {})
    outputs = config.get("outputs", {})
    model = config.get("model", {})

    return PortableRunSettings(
        year=int(run.get("year", 2026)),
        event=str(run.get("event", "latest")),
        session=str(run.get("session", "Q")),
        n_sims=int(run.get("n_sims", 50000)),
        random_seed=int(run.get("random_seed", 42)),
        n_baseline_races=int(run.get("n_baseline_races", 5)),
        historical_strategy_lookback_years=int(
            run.get("historical_strategy_lookback_years", 5)
        ),
        default_overtaking_difficulty=float(run.get("default_overtaking_difficulty", 0.55)),
        output_dir=str(outputs.get("output_dir", "outputs")),
        save_prediction_snapshot=bool(outputs.get("save_prediction_snapshot", True)),
        save_report_images=bool(outputs.get("save_report_images", True)),
        save_raw_results=bool(outputs.get("save_raw_results", True)),
        post_to_discord=bool(outputs.get("post_to_discord", False)),
        use_weather_forecast=bool(model.get("use_weather_forecast", True)),
        use_race_control_context=bool(model.get("use_race_control_context", True)),
        use_track_red_flag_base_chance=bool(
            model.get("use_track_red_flag_base_chance", True)
        ),
    )
