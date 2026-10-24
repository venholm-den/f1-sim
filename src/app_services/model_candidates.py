"""Unpromoted model candidates that Race Setup can switch on for one local run.

Every candidate defaults to its established value. Choices are validated by the
same `run_config` rules the CLI uses, so the UI can never build a run the
pipeline would reject, and candidate runs never post to Discord.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

# key -> (label, default, {value: label}, note). Keys are config['model'] fields,
# except pair_pass_model, which lives in model.agent_settings.
CANDIDATES: dict[str, dict[str, Any]] = {
    'race_engine': {
        'label': 'Race engine', 'default': 'aggregate_legacy',
        'options': {'aggregate_legacy': 'Established', 'pit_scenarios_v1': 'Pit-stop scenarios',
                    'agent_laps_v1': 'Car agents (lap by lap)'},
        'note': 'Car agents model traffic, pit delays and their own safety cars.'},
    'pair_pass_model': {
        'label': 'Pair overtaking', 'default': 'off',
        'options': {'off': 'Off', 'pair_overtaking_v1': 'Fitted per pair'},
        'note': 'Car agents engine only.'},
    'safety_car_model': {
        'label': 'Safety cars', 'default': 'off',
        'options': {'off': 'Off', 'track_sc_v1': 'Track rate', 'multi_sc_v1': 'Multiple SC and VSC'},
        'note': 'Not with the car agents engine, which has its own.'},
    'retirement_model': {
        'label': 'Retirements', 'default': 'legacy',
        'options': {'legacy': 'Established', 'survival_dnf_v1': 'Survival model'}, 'note': ''},
    'weather_model': {
        'label': 'Race weather', 'default': 'session_legacy',
        'options': {'session_legacy': 'Established', 'race_window_v1': 'Race-window forecast'},
        'note': 'Needs the weather forecast option under Advanced options.'},
    'shared_noise_model': {
        'label': 'Shared team noise', 'default': 'off',
        'options': {'off': 'Off', 'team_noise_v1': 'On'}, 'note': 'Established engines only.'},
    'grid_sampling_model': {
        'label': 'Grid sampling', 'default': 'off',
        'options': {'off': 'Off', 'estimated_grid_v1': 'Sample estimated grid'},
        'note': 'Established engines only.'},
    'grid_penalty_model': {
        'label': 'Grid penalties', 'default': 'off',
        'options': {'off': 'Off', 'announced_v1': 'Apply announced penalties'}, 'note': ''},
    'sprint_model': {
        'label': 'Sprint weekend', 'default': 'off',
        'options': {'off': 'Off', 'sprint_v1': 'Sprint aware'}, 'note': ''},
    'track_profile_model': {
        'label': 'Track profile', 'default': 'active',
        'options': {'active': 'Established', 'calibrated_v1': 'Calibrated'}, 'note': ''},
}


def candidate_options() -> list[dict[str, Any]]:
    from src.promotion_evidence import lane_for
    return [{'key': key, 'label': item['label'], 'default': item['default'], 'note': item['note'],
             'options': [{'value': value, 'label': label,
                          'lane': None if value == item['default'] else lane_for(key, value)}
                         for value, label in item['options'].items()]}
            for key, item in CANDIDATES.items()]


def active_candidates(choices: dict[str, Any] | None) -> dict[str, str]:
    """Return only the candidates that differ from their default, rejecting unknown values."""
    active = {}
    for key, value in (choices or {}).items():
        if key not in CANDIDATES:
            raise ValueError(f'Unknown model candidate: {key}.')
        value = str(value)
        if value not in CANDIDATES[key]['options']:
            raise ValueError(f"Unknown value for {CANDIDATES[key]['label']}: {value}.")
        if value != CANDIDATES[key]['default']:
            active[key] = value
    return active


def candidate_labels(active: dict[str, str] | None) -> list[str]:
    return [f"{CANDIDATES[key]['label']}: {CANDIDATES[key]['options'][value]}"
            for key, value in (active or {}).items() if key in CANDIDATES and value in CANDIDATES[key]['options']]


def apply_candidates(config: dict[str, Any], choices: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, str]]:
    """Return a copy of config with the chosen candidates, validated by run_config."""
    active = active_candidates(choices)
    config = copy.deepcopy(config)
    model = config.setdefault('model', {})
    for key, value in active.items():
        if key == 'pair_pass_model':
            model['agent_settings'] = {**(model.get('agent_settings') or {}), 'pair_pass_model': value}
        else:
            model[key] = value
    if active:
        if config.get('outputs', {}).get('post_to_discord'):
            raise ValueError('Model candidates support local output only.')
        validate_config(config)
    return config, active


def validate_config(config: dict[str, Any]) -> None:
    from src.run_config import load_app_config
    with tempfile.TemporaryDirectory(prefix='f1-sim-candidates-') as folder:
        path = Path(folder)/'run_config.json'
        path.write_text(json.dumps({**config, 'ignore_environment_overrides': True}), encoding='utf-8')
        load_app_config(str(path))
