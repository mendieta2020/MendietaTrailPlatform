"""
Suunto FIT file parser — provider-isolated (Law 4).

Parses binary .FIT files using the fitparse library.
All FIT-specific field names and sport mappings live here only.

Returns a normalized dict that the domain ingestion layer can consume
without knowing anything about FIT internals.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SPORT_MAP = {
    "running": "RUN",
    "trail_running": "TRAIL",
    "cycling": "CYCLING",
    "mountain_biking": "MTB",
    "swimming": "SWIMMING",
    "fitness_equipment": "STRENGTH",
    "training": "CARDIO",
    "indoor_cycling": "INDOOR_BIKE",
}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_fit_bytes(fit_bytes: bytes) -> dict:
    """
    Parse a .FIT binary blob and return a normalized activity dict.

    Returns:
        {
            "distance_m": float,
            "duration_s": int,
            "start_date": datetime | None,
            "sport": str,              # TIPO_ACTIVIDAD key ("RUN", "TRAIL", …)
            "elevation_gain_m": float | None,
            "calories_kcal": float | None,
            "avg_hr": float | None,
            "name": str,
            "raw_summary": dict,       # audit blob
        }

    Raises:
        ValueError: empty bytes or unparseable FIT data.
    """
    if not fit_bytes:
        raise ValueError("parse_fit_bytes: empty bytes — cannot parse FIT file")

    try:
        import fitparse  # noqa: PLC0415 — lazy import keeps dep optional at module load
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "fitparse is required for Suunto FIT parsing. "
            "Add 'fitparse' to requirements.txt."
        ) from exc

    try:
        fit_file = fitparse.FitFile(io.BytesIO(fit_bytes))
    except Exception as exc:
        logger.warning(
            "suunto.fit.parse_failed",
            extra={"event_name": "suunto.fit.parse_failed", "reason": str(exc)},
        )
        raise ValueError(f"parse_fit_bytes: failed to parse FIT data — {exc}") from exc

    distance_m: float = 0.0
    duration_s: int = 0
    start_date: datetime | None = None
    sport_raw: str = "generic"
    elevation_gain_m: float | None = None
    calories_kcal: float | None = None
    avg_hr: float | None = None
    raw_summary: dict = {}

    try:
        for message in fit_file.get_messages("session"):
            for field in message:
                raw_summary[field.name] = str(field.value)
                if field.name == "total_distance" and field.value is not None:
                    distance_m = float(field.value)
                elif field.name == "total_elapsed_time" and field.value is not None:
                    duration_s = int(float(field.value))
                elif field.name == "start_time" and field.value is not None:
                    v = field.value
                    if isinstance(v, datetime):
                        start_date = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
                elif field.name == "sport" and field.value is not None:
                    sport_raw = str(field.value).lower()
                elif field.name == "total_ascent" and field.value is not None:
                    elevation_gain_m = _safe_float(field.value)
                elif field.name == "total_calories" and field.value is not None:
                    calories_kcal = _safe_float(field.value)
                elif field.name == "avg_heart_rate" and field.value is not None:
                    avg_hr = _safe_float(field.value)
            break  # only the first session record is the summary
    except Exception as exc:
        logger.warning(
            "suunto.fit.session_error",
            extra={"event_name": "suunto.fit.session_error", "reason": str(exc)},
        )

    return {
        "distance_m": distance_m,
        "duration_s": duration_s,
        "start_date": start_date,
        "sport": _SPORT_MAP.get(sport_raw, "OTHER"),
        "elevation_gain_m": elevation_gain_m,
        "calories_kcal": calories_kcal,
        "avg_hr": avg_hr,
        "name": "",
        "raw_summary": raw_summary,
    }
