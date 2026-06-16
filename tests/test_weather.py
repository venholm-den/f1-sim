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


class EmptyWeatherSession:
    date = "2026-06-16T14:00:00"
    weather_data = pd.DataFrame()

    def load(self, **kwargs) -> None:
        return None


class FakeForecastResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "hourly": {
                "time": [
                    "2026-06-16T13:00",
                    "2026-06-16T14:00",
                    "2026-06-16T15:00",
                ],
                "temperature_2m": [19.0, 22.0, 24.0],
                "relative_humidity_2m": [60.0, 82.0, 70.0],
                "surface_pressure": [1012.0, 1010.0, 1009.0],
                "precipitation_probability": [10.0, 60.0, 20.0],
                "precipitation": [0.0, 0.1, 0.0],
                "wind_speed_10m": [2.0, 6.5, 3.0],
            }
        }


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
        "weather_source",
        "forecast_provider",
        "rain_probability",
        "forecast_time",
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


def test_summarize_weather_uses_open_meteo_forecast_when_session_weather_missing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeForecastResponse()

    monkeypatch.setattr("src.weather.requests.get", fake_get)

    summary = summarize_weather(
        EmptyWeatherSession(),
        track_profile={"latitude": 41.57, "longitude": 2.2611},
        use_forecast=True,
    )

    assert captured["url"] == "https://api.open-meteo.com/v1/forecast"
    assert captured["params"]["latitude"] == 41.57
    assert captured["params"]["longitude"] == 2.2611
    assert summary["weather_source"] == "open_meteo_forecast"
    assert summary["forecast_provider"] == "open-meteo"
    assert summary["air_temp_avg"] == 22.0
    assert summary["wind_speed_avg"] == 6.5
    assert summary["rain_probability"] == 60.0
    assert summary["rainfall_flag"] is True
    assert summary["forecast_time"] == "2026-06-16T14:00:00"
    assert "Forecast rain probability 60%" in " ".join(summary["notes"])


def test_summarize_weather_can_disable_forecast() -> None:
    summary = summarize_weather(
        EmptyWeatherSession(),
        track_profile={"latitude": 41.57, "longitude": 2.2611},
        use_forecast=False,
    )

    assert summary["weather_source"] == "neutral_default"
    assert summary["air_temp_avg"] is None
