"""Race-target weather acquisition and conditional start windows, without live model changes.

Probabilities here are ensemble frequencies, not calibrated wet-track or delay
probabilities. Precipitation is the accumulation in the hour ENDING at its label.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENSEMBLE_MODEL = "ecmwf_ifs025"
DELAYS = (0, 30, 60, 120)
WET_HOUR_MM = 0.1
CORE_VARIABLES = ("precipitation", "temperature_2m", "relative_humidity_2m", "wind_speed_10m")


def utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("A timezone-aware race start is required.")
    return stamp.tz_convert("UTC")


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hourly(payload: dict) -> pd.DataFrame:
    if payload.get("utc_offset_seconds", 0) != 0:
        raise ValueError("Provider returned non-UTC hours.")
    frame = pd.DataFrame(payload.get("hourly", {}))
    if frame.empty or "time" not in frame:
        raise ValueError("Provider returned no hourly weather.")
    frame.index = pd.to_datetime(frame.pop("time"), utc=True, errors="raise")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Hourly timestamps must be unique and ordered.")
    return frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _rain_window(frame: pd.DataFrame, column: str, start: pd.Timestamp,
                 end: pd.Timestamp) -> dict:
    # Include every preceding-hour interval that intersects the requested window.
    times = pd.date_range(start.floor("h") + pd.Timedelta(hours=1), end.ceil("h"), freq="h")
    values = frame.reindex(times).get(column)
    if values is None or values.isna().any() or (values < 0).any():
        return {"complete": False, "rain_mm": None, "wet_hour": None}
    fractions = np.array([
        (min(time, end) - max(time - pd.Timedelta(hours=1), start)).total_seconds() / 3600
        for time in times
    ])
    return {"complete": True, "rain_mm": float(np.dot(values, fractions)),
            "wet_hour": bool((values > WET_HOUR_MM).any()),
            "max_hourly_rain_mm": float(values.max())}


def _instant_mean(frame: pd.DataFrame, column: str, start: pd.Timestamp,
                  end: pd.Timestamp) -> float | None:
    times = pd.date_range(start.floor("h"), end.ceil("h"), freq="h")
    values = frame.reindex(times).get(column)
    if values is None or values.isna().any():
        return None
    knots = pd.DatetimeIndex([start, *[t for t in times if start < t < end], end])
    origin = times[0]
    x = (times - origin).total_seconds().to_numpy()
    target_x = (knots - origin).total_seconds().to_numpy()
    y = np.interp(target_x, x, values.to_numpy())
    return float(np.sum((y[:-1] + y[1:]) / 2 * np.diff(target_x)) / (end - start).total_seconds())


def _member_window(frame: pd.DataFrame, suffix: str, start: pd.Timestamp,
                   end: pd.Timestamp) -> dict:
    rain = _rain_window(frame, "precipitation" + suffix, start, end)
    pre_rain = _rain_window(frame, "precipitation" + suffix,
                            start - pd.Timedelta(hours=2), start)
    row = {"member": suffix or "control", **rain,
           "pre_start_rain_mm": pre_rain["rain_mm"],
           "pre_start_max_hourly_rain_mm": pre_rain.get("max_hourly_rain_mm"),
           "air_temp_avg": _instant_mean(frame, "temperature_2m" + suffix, start, end),
           "humidity_avg": _instant_mean(frame, "relative_humidity_2m" + suffix, start, end),
           "wind_speed_avg": _instant_mean(frame, "wind_speed_10m" + suffix, start, end),
           "track_temp_avg": None}
    row["simulation_usable"] = bool(rain["complete"] and all(
        row[key] is not None for key in ("air_temp_avg", "humidity_avg", "wind_speed_avg")))
    return row


def analyse_windows(raw: dict, race_start: Any, duration_minutes: int = 120) -> list[dict]:
    start = utc(race_start)
    if not 30 <= duration_minutes <= 240:
        raise ValueError("Weather window duration must be 30 to 240 minutes.")
    deterministic = _hourly(raw["forecast"]["payload"]) if "forecast" in raw else None
    ensemble = _hourly(raw["ensemble"]["payload"]) if "ensemble" in raw else None
    suffixes = [] if ensemble is None else [column.removeprefix("precipitation") for column in ensemble
        if re.fullmatch(r"precipitation(?:_member\d+)?", column)]
    scenarios = []
    for delay in DELAYS:
        shifted = start + pd.Timedelta(minutes=delay)
        end = shifted + pd.Timedelta(minutes=duration_minutes)
        members = [] if ensemble is None else [_member_window(ensemble, suffix, shifted, end) for suffix in suffixes]
        complete = [member for member in members if member["complete"]]
        # Do not silently renormalise a partial or single-member ensemble.
        available = len(complete) >= 2 and len(complete) == len(members)
        pre_available = len(members) >= 2 and all(m['pre_start_rain_mm'] is not None for m in members)
        values = [member["rain_mm"] for member in complete]
        scenario = {"delay_minutes": delay, "start_utc": shifted.isoformat(), "end_utc": end.isoformat(),
                    "delay_probability": None, "members": members,
                    "member_count": len(members), "complete_member_count": len(complete),
                    "wet_hour_frequency": float(np.mean([m["wet_hour"] for m in complete])) if available else None,
                    "pre_start_heavy_hour_frequency": float(np.mean([m['pre_start_max_hourly_rain_mm'] >= 4 for m in members])) if pre_available else None,
                    "pre_start_rain_mm_p50": float(np.median([m['pre_start_rain_mm'] for m in members])) if pre_available else None,
                    "rain_mm_p10": float(np.quantile(values, .1)) if available else None,
                    "rain_mm_p50": float(np.quantile(values, .5)) if available else None,
                    "rain_mm_p90": float(np.quantile(values, .9)) if available else None}
        if deterministic is not None:
            scenario["best_match"] = _member_window(deterministic, "", shifted, end)
            times = pd.date_range(shifted.floor("h") + pd.Timedelta(hours=1), end.ceil("h"), freq="h")
            for variable, key, method in (("precipitation_probability", "max_hourly_rain_probability_pct", "max"),
                                          ("wind_gusts_10m", "max_wind_gust_ms", "max"),
                                          ("visibility", "min_visibility_m", "min")):
                series = deterministic.reindex(times).get(variable)
                scenario[key] = (float(getattr(series, method)()) if series is not None and series.notna().all() else None)
        scenarios.append(scenario)
    return scenarios


def collect_race_weather(race_start: Any, latitude: float | None, longitude: float | None,
                         *, now: Any = None, get=None, duration_minutes: int = 120) -> tuple[dict, dict]:
    start = utc(race_start)
    requested = utc(now or datetime.now(timezone.utc))
    report = {"schema_version": 1, "race_start_utc": start.isoformat(),
              "request_started_at_utc": requested.isoformat(), "duration_minutes": duration_minutes,
              "applied_to_live_predictions": False, "delay_probability": None,
              "delay_probability_status": "unavailable_requires_event_level_calibration",
              "provider": "Open-Meteo", "ensemble_model": ENSEMBLE_MODEL,
              "requested_coordinates": {"latitude": latitude, "longitude": longitude},
              "wet_hour_threshold_mm": WET_HOUR_MM, "scenarios": [], "errors": {},
              "pre_start_heavy_hour_threshold_mm": 4,
              "limitations": ["Ensemble frequencies are uncalibrated regional precipitation forecasts, not wet-track probabilities.",
                  "Delay windows are conditional what-if scenarios, not predictions of race-control decisions.",
                  "Sub-hour precipitation assumes a uniform hourly rate; global ensemble hours can be interpolated.",
                  "Track temperature, drainage, standing water and lightning are not modelled.",
                  "Pre-start heavy rain is a diagnostic at 4 mm/hour, not a race-delay threshold.",
                  "Window length is assumed; delayed or interrupted races can have different duration."]}
    raw = {}
    if not 30 <= duration_minutes <= 240:
        raise ValueError("Weather window duration must be 30 to 240 minutes.")
    valid_coords = (latitude is not None and longitude is not None and np.isfinite(latitude)
                    and np.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180)
    earliest = (start - pd.Timedelta(hours=2)).floor("h")
    latest = (start + pd.Timedelta(minutes=max(DELAYS) + duration_minutes)).ceil("h")
    if not valid_coords:
        report["status"] = "coordinates_unavailable"
    elif earliest < requested.floor("D") or start <= requested:
        report["status"] = "past_or_incomplete_future_window"
    elif latest >= requested.floor("D") + pd.Timedelta(days=15):
        report["status"] = "outside_forecast_horizon"
    else:
        params = {"latitude": latitude, "longitude": longitude, "timezone": "GMT", "wind_speed_unit": "ms",
                  "start_hour": earliest.strftime("%Y-%m-%dT%H:%M"), "end_hour": latest.strftime("%Y-%m-%dT%H:%M")}
        for key, endpoint, extra in (
            ("forecast", FORECAST_URL, {"hourly": ",".join((*CORE_VARIABLES, "precipitation_probability", "wind_gusts_10m", "visibility", "weather_code"))}),
            ("ensemble", ENSEMBLE_URL, {"models": ENSEMBLE_MODEL, "hourly": ",".join(CORE_VARIABLES)}),
        ):
            try:
                response = (get or requests.get)(endpoint, params={**params, **extra}, timeout=10)
                response.raise_for_status()
                payload = response.json()
                _hourly(payload)
                units = payload.get("hourly_units", {})
                if units.get("precipitation") != "mm" or units.get("wind_speed_10m") != "m/s":
                    raise ValueError("Unexpected precipitation or wind units.")
                raw[key] = {"endpoint": endpoint, "parameters": {**params, **extra},
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "payload": payload}
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                # No credential-bearing URL or remote body is written to logs.
                report["errors"][key] = type(exc).__name__
        report["scenarios"] = analyse_windows(raw, start, duration_minutes)
        complete = all(s["wet_hour_frequency"] is not None for s in report["scenarios"])
        report["status"] = "available" if complete and "forecast" in raw else "partial" if raw else "unavailable"
    report["retrieved_at_utc"] = max((r["retrieved_at_utc"] for r in raw.values()), default=requested.isoformat())
    report["raw_sha256"] = payload_hash(raw)
    report["provider_grid_coordinates"] = {key: {coord: entry["payload"].get(coord) for coord in ("latitude", "longitude")}
                                           for key, entry in raw.items()}
    return report, raw


def briefing(report: dict) -> str:
    if report.get("status") not in {"available", "partial"}:
        return f"Race weather unavailable ({report.get('status', 'unknown')}). Start-delay probability unavailable."
    lines = ["Regional ensemble rain guidance; not applied to driver probabilities."]
    scheduled = report['scenarios'][0]
    best_match = scheduled.get('best_match', {})
    temperature = best_match.get('air_temp_avg')
    gust = scheduled.get('max_wind_gust_ms')
    if temperature is not None:
        lines.append(f"Scheduled window: mean air {temperature:.1f} C" + (f", peak gust {gust:.1f} m/s." if gust is not None else '.'))
    for scenario in report["scenarios"]:
        label = "Scheduled start" if not scenario["delay_minutes"] else f"Start +{scenario['delay_minutes']} min"
        frequency = scenario["wet_hour_frequency"]
        text = "unknown" if frequency is None else f"{frequency:.0%} of members have a wet hourly interval"
        rain = scenario['rain_mm_p50']
        lines.append(f"{label}: {text}" + (f"; median {rain:.1f} mm." if rain is not None else '.'))
    lines.append("Start-delay probability unavailable; windows are conditional scenarios.")
    return "\n".join(lines)
