"""
core/services_weather.py

PR-145d: OpenWeatherMap integration for per-assignment weather forecast.

Design decisions:
- OWM API key is optional; graceful degradation if absent or call fails.
- Fetches current weather (delta=0) or 3-hourly forecast (delta 1–4 days).
- Normalizes to a minimal snapshot dict to avoid storing raw OWM payloads.
- Does NOT import from integrations/ — this is a lightweight service call,
  not a provider boundary (OWM is not an athlete data provider).
"""

import logging
import os
from datetime import date

import requests

logger = logging.getLogger(__name__)

OWM_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")
OWM_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def get_weather_for_date(lat: float, lon: float, target_date: date) -> dict | None:
    """
    Returns a minimal weather snapshot for the given lat/lon on target_date.

    Uses current weather if target_date is today; 3-hourly forecast for
    next 1–4 days. Returns None if:
    - OWM key is not configured
    - lat/lon are None
    - target_date is in the past or > 4 days ahead (free tier limit)
    - the OWM API call fails for any reason
    """
    if not OWM_KEY or lat is None or lon is None:
        return None
    try:
        today = date.today()
        delta = (target_date - today).days

        if delta < 0 or delta > 4:
            return None  # outside free forecast window

        if delta == 0:
            resp = requests.get(
                OWM_CURRENT_URL,
                params={"lat": lat, "lon": lon, "appid": OWM_KEY, "units": "metric", "lang": "es"},
                timeout=5,
            )
        else:
            resp = requests.get(
                OWM_FORECAST_URL,
                params={
                    "lat": lat, "lon": lon,
                    "appid": OWM_KEY, "units": "metric", "lang": "es",
                    "cnt": delta * 8,  # ~3h intervals
                },
                timeout=5,
            )

        if resp.status_code != 200:
            logger.warning(
                "weather.fetch_failed",
                extra={
                    "event_name": "weather.fetch_failed",
                    "status_code": resp.status_code,
                    "lat": lat, "lon": lon,
                },
            )
            return None

        data = resp.json()

        if delta == 0:
            item = data
        else:
            items = [
                i for i in data.get("list", [])
                if target_date.isoformat() in i.get("dt_txt", "")
            ]
            item = next(
                (i for i in items if "12:00" in i.get("dt_txt", "")),
                items[0] if items else None,
            )
            if not item:
                return None

        return {
            "temp_c": round(item["main"]["temp"]),
            "feels_like": round(item["main"]["feels_like"]),
            "description": item["weather"][0]["description"].capitalize(),
            "icon": item["weather"][0]["icon"],
            "humidity": item["main"]["humidity"],
        }
    except Exception as exc:
        logger.warning(
            "weather.fetch_error",
            extra={"event_name": "weather.fetch_error", "error": str(exc)},
        )
        return None


def enrich_assignment_weather(assignment) -> bool:
    """
    Fetches OWM forecast and stores weather_snapshot on the assignment.

    Only acts if the assignment's athlete has location_lat configured.
    Uses update_fields to avoid triggering full_clean() / compliance recalc.
    Returns True if snapshot was written, False otherwise.
    """
    athlete = getattr(assignment, "athlete", None)
    if not athlete or athlete.location_lat is None:
        return False

    snapshot = get_weather_for_date(
        athlete.location_lat,
        athlete.location_lon,
        assignment.scheduled_date,
    )
    if snapshot:
        assignment.weather_snapshot = snapshot
        assignment.save(update_fields=["weather_snapshot"])
        return True
    return False
