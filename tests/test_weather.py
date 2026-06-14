from __future__ import annotations

import pandas as pd

from src.weather import summarise_weather, summarize_weather


class FakeWeatherSession:
    def __init__(self) -> None:
        self.weather_data = pd.DataFrame(
            {
                "AirTemp": [20.0, 21.0, 22.0],
                "TrackTemp": [30.0, 32.0, 34.0],
                "Humidity": [50.0, 55.0, 60.0],
                "Pressure": [1010.0, 1011.0, 1012.0],
                "WindSpeed": [2.0, 3.0, 4.0],
                "Rainfall": [False, False, False],
            }
        )


def test_summarize_weather_returns_expected_keys() -> None:
    summary = summarize_weather(FakeWeatherSession())

    required_keys = {
        "air_temp_avg",
        "track_temp_avg",
        "humidity_avg",
        "pressure_avg",
        "wind_speed_avg",
        "rainfall_flag",
        "chaos_factor",
        "strategy_factor",
        "dnf_factor",
        "degradation_factor",
        "uncertainty_factor",
        "notes",
    }

    assert required_keys.issubset(summary.keys())
    assert summary["rainfall_flag"] is False
    assert summary["air_temp_avg"] == 21.0
    assert summary["track_temp_avg"] == 32.0


def test_summarise_weather_alias_matches_summarize_weather() -> None:
    session = FakeWeatherSession()

    us = summarize_weather(session)
    uk = summarise_weather(session)

    assert us == uk