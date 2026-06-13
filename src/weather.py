from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


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


def summarize_weather(session: Any) -> dict[str, Any]:
    weather_df = _get_weather_dataframe(session)

    if weather_df.empty:
        return DEFAULT_WEATHER_SUMMARY.copy()

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
        "notes": notes,
    }

    summary.update(modifiers)

    return summary


# UK spelling alias, so either import style works.
def summarise_weather(session: Any) -> dict[str, Any]:
    return summarize_weather(session)