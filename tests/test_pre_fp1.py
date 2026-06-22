from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.collect import is_pre_fp1_session, load_pre_fp1_session
from src.model import build_model_features


def test_pre_fp1_session_aliases() -> None:
    assert is_pre_fp1_session("PRE")
    assert is_pre_fp1_session("pre-test")
    assert is_pre_fp1_session("before_fp1")
    assert not is_pre_fp1_session("FP1")


def test_load_pre_fp1_session_selects_upcoming_latest_event(monkeypatch) -> None:
    now = datetime.utcnow()
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2],
            "EventName": ["Past Grand Prix", "Future Grand Prix"],
            "OfficialEventName": ["Past Grand Prix", "Future Grand Prix"],
            "EventDate": [now - timedelta(days=7), now + timedelta(days=3)],
        }
    )

    monkeypatch.setattr("src.collect.enable_fastf1_cache", lambda: None)
    monkeypatch.setattr("src.collect.fastf1.get_event_schedule", lambda year: schedule)

    session, metadata = load_pre_fp1_session(2026, "latest")

    assert metadata == {
        "year": 2026,
        "event": "Future Grand Prix",
        "round": 2,
        "session": "PRE",
    }
    assert session.laps.empty
    assert session.weather_data.empty


def test_pre_fp1_model_uses_baseline_only() -> None:
    current_features = pd.DataFrame(
        columns=[
            "Driver",
            "Team",
            "relative_pace",
            "race_pace",
            "best_lap",
            "lap_std",
            "deg_per_lap",
            "clean_laps",
            "raw_laps",
            "dnf_prob",
        ]
    )
    baseline_features = pd.DataFrame(
        {
            "Driver": ["RUS", "HAM"],
            "Team": ["Mercedes", "Ferrari"],
            "relative_pace": [0.0, 0.4],
            "race_pace": [90.0, 90.4],
            "best_lap": [89.0, 89.4],
            "lap_std": [1.0, 1.1],
            "deg_per_lap": [0.02, 0.03],
            "clean_laps": [50, 50],
            "raw_laps": [55, 55],
            "dnf_prob": [0.04, 0.05],
            "baseline_age": [0, 0],
            "source_round": [1, 1],
        }
    )

    model = build_model_features(
        current_features=current_features,
        baseline_features=baseline_features,
        current_session_type="PRE",
    ).set_index("Driver")

    assert model.loc["RUS", "current_weight"] == 0
    assert model.loc["RUS", "effective_current_weight"] == 0
    assert model.loc["RUS", "relative_pace"] == 0.0
    assert model.loc["HAM", "relative_pace"] == 0.4
    assert model["model_uncertainty"].min() > 1.0
