from __future__ import annotations

from datetime import datetime
from typing import Any

from src.race_control import merge_race_control_into_weather_modifiers, summarise_race_control

import numpy as np
import pandas as pd
import requests


DEFAULT_WEATHER_SUMMARY = {
    "air_temp_avg": None,
    "track_temp_avg": None,
    "humidity_avg": None,
    "pressure_avg": None,
    "wind_speed_avg": None,
    "rainfall_flag": False,
    "chaos_factor": 1.00,
    "strategy_factor": 1.00,
    "dnf_factor": 1.00,
    "degradation_factor": 1.00,
    "uncertainty_factor": 1.00,
    "weather_source": "neutral_default",
    "forecast_provider": None,
    "rain_probability": None,
    "forecast_time": None,
    "notes": "No weather data available; neutral weather modifiers used.",
}


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None

    return float(number)


def _safe_mean(df: pd.DataFrame, column: str) -> float | None:
    if column not in df.columns:
        return None

    values = pd.to_numeric(df[column], errors="coerce").dropna()

    if values.empty:
        return None

    return float(values.mean())


def _safe_bool_any(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False

    series = df[column]

    if str(series.dtype) == "bool":
        return bool(series.fillna(False).any())

    text = series.astype(str).str.strip().str.lower()

    return bool(text.isin({"true", "1", "yes", "y"}).any())


def _session_datetime(session: Any) -> datetime | None:
    for attribute in ["date", "session_date", "session_start_time", "start_time"]:
        value = getattr(session, attribute, None)

        if value is None:
            continue

        timestamp = pd.to_datetime(value, errors="coerce")

        if pd.notna(timestamp):
            return timestamp.to_pydatetime()

    return None


def _get_weather_dataframe(session: Any) -> pd.DataFrame:
    weather_data = getattr(session, "weather_data", None)

    if weather_data is not None:
        try:
            df = weather_data.copy()

            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception:
            pass

    try:
        session.load(weather=True, laps=False, telemetry=False, messages=False)
        weather_data = getattr(session, "weather_data", None)

        if weather_data is not None:
            df = weather_data.copy()

            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
    except Exception:
        pass

    return pd.DataFrame()


def _calculate_modifiers(
    air_temp: float | None,
    track_temp: float | None,
    humidity: float | None,
    wind_speed: float | None,
    rainfall: bool,
) -> dict[str, float]:
    chaos_factor = 1.00
    strategy_factor = 1.00
    dnf_factor = 1.00
    degradation_factor = 1.00
    uncertainty_factor = 1.00

    if rainfall:
        chaos_factor += 0.35
        strategy_factor += 0.45
        dnf_factor += 0.25
        degradation_factor -= 0.10
        uncertainty_factor += 0.35

    if track_temp is not None:
        if track_temp >= 45:
            degradation_factor += 0.22
            strategy_factor += 0.10
            uncertainty_factor += 0.08
        elif track_temp >= 38:
            degradation_factor += 0.12
            strategy_factor += 0.05
        elif track_temp <= 20:
            degradation_factor -= 0.08
            uncertainty_factor += 0.05

    if air_temp is not None:
        if air_temp >= 32:
            degradation_factor += 0.06
            dnf_factor += 0.04
        elif air_temp <= 12:
            uncertainty_factor += 0.05

    if humidity is not None:
        if humidity >= 80:
            chaos_factor += 0.06
            uncertainty_factor += 0.05

    if wind_speed is not None:
        if wind_speed >= 6:
            chaos_factor += 0.10
            uncertainty_factor += 0.10
        elif wind_speed >= 4:
            chaos_factor += 0.05
            uncertainty_factor += 0.05

    return {
        "chaos_factor": float(np.clip(chaos_factor, 0.80, 1.80)),
        "strategy_factor": float(np.clip(strategy_factor, 0.80, 1.85)),
        "dnf_factor": float(np.clip(dnf_factor, 0.80, 1.65)),
        "degradation_factor": float(np.clip(degradation_factor, 0.70, 1.60)),
        "uncertainty_factor": float(np.clip(uncertainty_factor, 0.85, 1.80)),
    }


def _build_notes(
    air_temp: float | None,
    track_temp: float | None,
    humidity: float | None,
    wind_speed: float | None,
    rainfall: bool,
) -> str:
    notes: list[str] = []

    if rainfall:
        notes.append("Rain detected; increased chaos, strategy variance, DNF risk and uncertainty.")

    if track_temp is not None:
        if track_temp >= 45:
            notes.append("Very hot track; tyre degradation increased.")
        elif track_temp >= 38:
            notes.append("Warm track; tyre degradation slightly increased.")
        elif track_temp <= 20:
            notes.append("Cool track; tyre degradation reduced but warm-up uncertainty increased.")

    if air_temp is not None and air_temp >= 32:
        notes.append("High air temperature; small reliability and degradation penalty applied.")

    if humidity is not None and humidity >= 80:
        notes.append("High humidity; small chaos and uncertainty increase applied.")

    if wind_speed is not None:
        if wind_speed >= 6:
            notes.append("High wind; increased driver variance and instability.")
        elif wind_speed >= 4:
            notes.append("Moderate wind; small uncertainty increase applied.")

    if not notes:
        notes.append("Stable weather profile; neutral modifiers used.")

    return " ".join(notes)


def _track_coordinate(track_profile: dict[str, Any] | None, *keys: str) -> float | None:
    if not track_profile:
        return None

    for key in keys:
        value = _to_float_or_none(track_profile.get(key))

        if value is not None:
            return value

    return None


def _fetch_open_meteo_forecast(
    latitude: float,
    longitude: float,
    target_time: datetime | None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "surface_pressure",
                "precipitation_probability",
                "precipitation",
                "wind_speed_10m",
            ]
        ),
        "forecast_days": 7,
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=10,
    )
    response.raise_for_status()

    payload = response.json()
    hourly = payload.get("hourly", {})
    times = hourly.get("time") or []

    if not times:
        return None

    forecast = pd.DataFrame(hourly)

    if forecast.empty or "time" not in forecast.columns:
        return None

    forecast["time"] = pd.to_datetime(forecast["time"], errors="coerce")
    forecast = forecast.dropna(subset=["time"]).reset_index(drop=True)

    if forecast.empty:
        return None

    if target_time is None:
        index = 0
    else:
        target = pd.Timestamp(target_time).tz_localize(None)
        forecast["time_delta"] = (forecast["time"] - target).abs()
        index = int(forecast["time_delta"].idxmin())

    row = forecast.iloc[index]
    rain_probability = _to_float_or_none(row.get("precipitation_probability"))
    precipitation = _to_float_or_none(row.get("precipitation"))
    rainfall = bool(
        (rain_probability is not None and rain_probability >= 35)
        or (precipitation is not None and precipitation > 0.2)
    )

    return {
        "air_temp_avg": _to_float_or_none(row.get("temperature_2m")),
        "track_temp_avg": None,
        "humidity_avg": _to_float_or_none(row.get("relative_humidity_2m")),
        "pressure_avg": _to_float_or_none(row.get("surface_pressure")),
        "wind_speed_avg": _to_float_or_none(row.get("wind_speed_10m")),
        "rainfall_flag": rainfall,
        "rain_probability": rain_probability,
        "forecast_time": row.get("time").isoformat() if pd.notna(row.get("time")) else None,
        "forecast_provider": "open-meteo",
        "weather_source": "open_meteo_forecast",
    }


def _forecast_weather_summary(
    session: Any,
    track_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    latitude = _track_coordinate(track_profile, "latitude", "Latitude")
    longitude = _track_coordinate(track_profile, "longitude", "Longitude")

    if latitude is None or longitude is None:
        summary = DEFAULT_WEATHER_SUMMARY.copy()
        summary["notes"] = (
            "No session weather data available and no track coordinates were configured; "
            "neutral weather modifiers used."
        )
        return summary

    try:
        forecast = _fetch_open_meteo_forecast(
            latitude=latitude,
            longitude=longitude,
            target_time=_session_datetime(session),
        )
    except Exception as exc:
        summary = DEFAULT_WEATHER_SUMMARY.copy()
        summary["weather_source"] = "forecast_unavailable"
        summary["forecast_provider"] = "open-meteo"
        summary["notes"] = (
            f"Open-Meteo forecast unavailable ({exc}); neutral weather modifiers used."
        )
        return summary

    if forecast is None:
        summary = DEFAULT_WEATHER_SUMMARY.copy()
        summary["weather_source"] = "forecast_unavailable"
        summary["forecast_provider"] = "open-meteo"
        summary["notes"] = "Open-Meteo forecast returned no usable hourly data; neutral weather modifiers used."
        return summary

    modifiers = _calculate_modifiers(
        air_temp=forecast["air_temp_avg"],
        track_temp=forecast["track_temp_avg"],
        humidity=forecast["humidity_avg"],
        wind_speed=forecast["wind_speed_avg"],
        rainfall=forecast["rainfall_flag"],
    )

    notes = _build_notes(
        air_temp=forecast["air_temp_avg"],
        track_temp=forecast["track_temp_avg"],
        humidity=forecast["humidity_avg"],
        wind_speed=forecast["wind_speed_avg"],
        rainfall=forecast["rainfall_flag"],
    )

    rain_probability = forecast.get("rain_probability")

    if rain_probability is not None:
        notes = f"Forecast rain probability {rain_probability:.0f}%. {notes}"

    forecast["notes"] = notes
    forecast.update(modifiers)

    return forecast


def summarize_weather(
    session: Any,
    track_profile: dict[str, Any] | None = None,
    use_forecast: bool = True,
) -> dict[str, Any]:
    weather_df = _get_weather_dataframe(session)

    if weather_df.empty:
        summary = (
            _forecast_weather_summary(session, track_profile)
            if use_forecast
            else DEFAULT_WEATHER_SUMMARY.copy()
        )
        race_control_summary = summarise_race_control(session)
        return merge_race_control_into_weather_modifiers(summary, race_control_summary)

    air_temp = _safe_mean(weather_df, "AirTemp")
    track_temp = _safe_mean(weather_df, "TrackTemp")
    humidity = _safe_mean(weather_df, "Humidity")
    pressure = _safe_mean(weather_df, "Pressure")
    wind_speed = _safe_mean(weather_df, "WindSpeed")
    rainfall = _safe_bool_any(weather_df, "Rainfall")

    modifiers = _calculate_modifiers(
        air_temp=air_temp,
        track_temp=track_temp,
        humidity=humidity,
        wind_speed=wind_speed,
        rainfall=rainfall,
    )

    notes = _build_notes(
        air_temp=air_temp,
        track_temp=track_temp,
        humidity=humidity,
        wind_speed=wind_speed,
        rainfall=rainfall,
    )

    summary = {
        "air_temp_avg": air_temp,
        "track_temp_avg": track_temp,
        "humidity_avg": humidity,
        "pressure_avg": pressure,
        "wind_speed_avg": wind_speed,
        "rainfall_flag": rainfall,
        "rain_probability": None,
        "forecast_provider": None,
        "forecast_time": None,
        "weather_source": "fastf1_session_weather",
        "notes": notes,
    }

    summary.update(modifiers)

    race_control_summary = summarise_race_control(session)
    summary = merge_race_control_into_weather_modifiers(summary, race_control_summary)

    return summary


# UK spelling alias, so either import style works.
def summarise_weather(
    session: Any,
    track_profile: dict[str, Any] | None = None,
    use_forecast: bool = True,
) -> dict[str, Any]:
    return summarize_weather(
        session,
        track_profile=track_profile,
        use_forecast=use_forecast,
    )
