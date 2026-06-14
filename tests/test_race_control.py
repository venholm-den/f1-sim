from __future__ import annotations

import pandas as pd

from src.race_control import (
    merge_race_control_into_weather_modifiers,
    summarise_race_control,
)


class FakeRaceSession:
    def __init__(self) -> None:
        self.track_status = pd.DataFrame(
            {
                "Time": [
                    pd.Timedelta(seconds=0),
                    pd.Timedelta(seconds=60),
                    pd.Timedelta(seconds=180),
                    pd.Timedelta(seconds=260),
                    pd.Timedelta(seconds=400),
                ],
                "Status": ["1", "4", "1", "6", "1"],
                "Message": [
                    "All clear",
                    "Safety car",
                    "All clear",
                    "Virtual safety car",
                    "All clear",
                ],
            }
        )

        self.race_control_messages = pd.DataFrame(
            {
                "Time": [
                    pd.Timedelta(seconds=60),
                    pd.Timedelta(seconds=260),
                    pd.Timedelta(seconds=300),
                ],
                "Category": ["SafetyCar", "Other", "Other"],
                "Message": [
                    "SAFETY CAR DEPLOYED",
                    "VIRTUAL SAFETY CAR DEPLOYED",
                    "INCIDENT INVOLVING CAR 63 NOTED",
                ],
            }
        )


def test_race_control_summary_detects_safety_car_and_vsc() -> None:
    summary = summarise_race_control(FakeRaceSession())

    assert summary["track_status_available"] is True
    assert summary["race_control_available"] is True
    assert summary["safety_car_flag"] is True
    assert summary["vsc_flag"] is True
    assert summary["red_flag_flag"] is False
    assert summary["safety_car_windows"] == 1
    assert summary["vsc_windows"] == 1
    assert summary["race_control_chaos_factor"] > 1.0
    assert summary["race_control_strategy_factor"] > 1.0


def test_race_control_summary_is_neutral_without_data() -> None:
    summary = summarise_race_control(None)

    assert summary["race_control_available"] is False
    assert summary["track_status_available"] is False
    assert summary["race_control_chaos_factor"] == 1.0
    assert summary["race_control_strategy_factor"] == 1.0
    assert summary["race_control_dnf_factor"] == 1.0


def test_race_control_modifiers_merge_into_weather_summary() -> None:
    weather = {
        "chaos_factor": 1.0,
        "strategy_factor": 1.0,
        "dnf_factor": 1.0,
        "uncertainty_factor": 1.0,
        "notes": ["Weather neutral."],
    }

    race_control = summarise_race_control(FakeRaceSession())

    merged = merge_race_control_into_weather_modifiers(weather, race_control)

    assert merged["chaos_factor"] > 1.0
    assert merged["strategy_factor"] > 1.0
    assert merged["race_control_available"] is True
    assert len(merged["notes"]) >= 2