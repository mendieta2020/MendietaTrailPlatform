import hashlib
import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.utils.jsonable import to_jsonable


def compute_source_hash(raw_json: dict | None) -> str:
    """Hash estable (sha256) de un payload raw_json (best-effort)."""
    raw_json = raw_json or {}
    try:
        s = json.dumps(raw_json, sort_keys=True, separators=(",", ":"), cls=DjangoJSONEncoder)
    except Exception:
        s = json.dumps(raw_json, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def supported_strava_activity_type(strava_type: str) -> bool:
    """Tipos soportados para ingesta (ajustable)."""
    st = (strava_type or "").upper()
    return st in {"RUN", "TRAILRUN", "VIRTUALRUN", "WORKOUT"}


def _parse_strava_datetime(value: Any):
    """
    Parse robusto de datetime Strava (string ISO / datetime).

    - Strava suele enviar ISO8601 con Z/offset (UTC).
    - Si viene naive, lo marcamos como UTC para evitar crashes.
    """
    if not value:
        return None
    # datetime-like
    if hasattr(value, "tzinfo"):
        try:
            if value.tzinfo is None:
                return timezone.make_aware(value, timezone=timezone.utc)
            return value
        except Exception:
            return None
    if isinstance(value, str):
        try:
            dt = parse_datetime(value)
            if not dt:
                return None
            if dt.tzinfo is None:
                return timezone.make_aware(dt, timezone=timezone.utc)
            return dt
        except Exception:
            return None
    return None


def normalize_strava_activity_json(raw_activity_json: dict) -> dict:
    """
    Normaliza un payload raw JSON (Strava API / stravalib.to_dict()) a un shape estable.

    Unidades:
    - distance_m: metros
    - moving_time_s / elapsed_time_s: segundos
    """
    raw = to_jsonable(raw_activity_json or {}) or {}

    activity_id = raw.get("id")
    athlete_id = None
    try:
        athlete_id = int((raw.get("athlete") or {}).get("id"))
    except Exception:
        athlete_id = None

    # Preferimos sport_type si existe (Strava moderno), fallback a type (legacy).
    strava_type = raw.get("sport_type") or raw.get("type") or ""

    start_dt = _parse_strava_datetime(raw.get("start_date_local")) or _parse_strava_datetime(raw.get("start_date"))

    def _to_int(v: Any) -> int:
        try:
            return int(v or 0)
        except Exception:
            return 0

    def _to_float(v: Any) -> float:
        try:
            return float(v or 0.0)
        except Exception:
            return 0.0

    # Strava raw: distance (m), moving_time (s), elapsed_time (s), total_elevation_gain (m).
    distance_m = _to_float(raw.get("distance"))
    moving_time_s = _to_int(raw.get("moving_time"))
    elapsed_time_s = _to_int(raw.get("elapsed_time"))
    elev_m = _to_float(raw.get("total_elevation_gain"))

    polyline = None
    try:
        polyline = (raw.get("map") or {}).get("summary_polyline")
    except Exception:
        polyline = None

    avg_hr = raw.get("average_heartrate")
    max_hr = raw.get("max_heartrate")
    avg_watts = raw.get("average_watts")

    return {
        "id": int(activity_id) if activity_id is not None else None,
        "athlete_id": athlete_id,
        "name": str(raw.get("name") or ""),
        "type": str(strava_type or ""),
        "start_date_local": start_dt,
        "moving_time_s": int(moving_time_s),
        "elapsed_time_s": int(elapsed_time_s),
        "distance_m": float(distance_m or 0.0),
        "elevation_m": float(elev_m or 0.0),
        "avg_hr": float(avg_hr) if avg_hr is not None else None,
        "max_hr": float(max_hr) if max_hr is not None else None,
        "avg_watts": float(avg_watts) if avg_watts is not None else None,
        "polyline": polyline,
        "raw": raw,
        "raw_sanitized": False,
    }


def _normalized_payload_for_hash(normalized: dict) -> dict:
    """
    Payload determinístico para `source_hash`.

    Importante: NO incluimos el raw completo (puede variar sin cambiar métricas).
    """
    return {
        "id": normalized.get("id"),
        "name": normalized.get("name"),
        "type": normalized.get("type"),
        "start_date_local": normalized.get("start_date_local"),
        "moving_time_s": normalized.get("moving_time_s"),
        "elapsed_time_s": normalized.get("elapsed_time_s"),
        "distance_m": normalized.get("distance_m"),
        "elevation_m": normalized.get("elevation_m"),
        "avg_hr": normalized.get("avg_hr"),
        "max_hr": normalized.get("max_hr"),
        "avg_watts": normalized.get("avg_watts"),
        "polyline": normalized.get("polyline"),
    }


def normalize_strava_activity(activity: Any) -> dict:
    """Convierte objeto stravalib Activity a dict estable (unidades: m, s)."""
    # Raw JSON (best-effort)
    raw: dict = {}
    try:
        if hasattr(activity, "to_dict"):
            raw = activity.to_dict()
        elif hasattr(activity, "model_dump"):
            raw = activity.model_dump()
    except Exception:
        raw = {}

    # IMPORTANT: JSONFields/Celery serializer requieren payload JSON-serializable.
    # Strava/stravalib puede incluir datetime/Decimal/etc.
    raw_sanitized = False
    try:
        json.dumps(raw, sort_keys=True, separators=(",", ":"))
    except Exception:
        raw_sanitized = True
    raw = to_jsonable(raw) or {}

    athlete_id = None
    try:
        athlete_id = int(getattr(getattr(activity, "athlete", None), "id", None))
    except Exception:
        athlete_id = None

    start_dt = getattr(activity, "start_date_local", None) or getattr(activity, "start_date", None)

    def _to_seconds(v: Any) -> int:
        if v is None:
            return 0
        try:
            if hasattr(v, "total_seconds"):
                return int(v.total_seconds())
            if hasattr(v, "seconds"):
                return int(v.seconds)
            return int(v)
        except Exception:
            return 0

    def _to_float(v: Any) -> float:
        if v is None:
            return 0.0
        try:
            if hasattr(v, "magnitude"):
                return float(v.magnitude)
            return float(v)
        except Exception:
            return 0.0

    moving_time_s = _to_seconds(getattr(activity, "moving_time", None))
    elapsed_time_s = _to_seconds(getattr(activity, "elapsed_time", None))
    distance_m = _to_float(getattr(activity, "distance", None))
    elev_m = _to_float(getattr(activity, "total_elevation_gain", None))

    avg_hr = getattr(activity, "average_heartrate", None)
    max_hr = getattr(activity, "max_heartrate", None)
    avg_watts = getattr(activity, "average_watts", None)

    polyline = None
    try:
        polyline = getattr(getattr(activity, "map", None), "summary_polyline", None)
    except Exception:
        polyline = None

    return {
        "id": int(getattr(activity, "id")),
        "athlete_id": athlete_id,
        "name": str(getattr(activity, "name", "") or ""),
        "type": str(getattr(activity, "type", "") or ""),
        "start_date_local": start_dt,
        "moving_time_s": int(moving_time_s),
        "elapsed_time_s": int(elapsed_time_s),
        "distance_m": float(distance_m or 0.0),
        "elevation_m": float(elev_m or 0.0),
        "avg_hr": float(avg_hr) if avg_hr is not None else None,
        "max_hr": float(max_hr) if max_hr is not None else None,
        "avg_watts": float(avg_watts) if avg_watts is not None else None,
        "polyline": polyline,
        "raw": raw,
        "raw_sanitized": bool(raw_sanitized),
    }


def map_strava_activity_to_actividad(strava_activity_json: dict) -> dict:
    """Map Strava normalized json -> campos del modelo core.models.Actividad."""
    activity_id = strava_activity_json.get("id")
    source_object_id = str(activity_id) if activity_id is not None else ""

    distance_m = float(strava_activity_json.get("distance_m") or 0.0)
    moving_s = int(strava_activity_json.get("moving_time_s") or 0)
    raw = to_jsonable(strava_activity_json.get("raw") or {}) or {}

    return {
        "source": "strava",
        "source_object_id": source_object_id,
        # Hash determinístico del payload normalizado (no del raw completo).
        "source_hash": compute_source_hash(_normalized_payload_for_hash(strava_activity_json or {})),
        # compat
        "strava_id": int(activity_id) if activity_id is not None else None,
        # negocio
        "nombre": strava_activity_json.get("name") or "",
        "distancia": distance_m,
        "tiempo_movimiento": moving_s,
        "fecha_inicio": strava_activity_json.get("start_date_local"),
        "tipo_deporte": strava_activity_json.get("type") or "",
        "desnivel_positivo": float(strava_activity_json.get("elevation_m") or 0.0),
        "ritmo_promedio": (distance_m / moving_s) if (distance_m > 0 and moving_s > 0) else None,
        "mapa_polilinea": strava_activity_json.get("polyline"),
        "datos_brutos": raw,
    }


def map_strava_raw_activity_to_actividad_defaults(raw_activity_json: dict) -> dict:
    """
    Mapper canónico: Strava raw JSON activity -> defaults normalizados para `Actividad`.

    Útil para:
    - backfill de actividades existentes que solo tienen `datos_brutos`
    - flujos que reciben JSON Strava directo (sin stravalib)
    """
    normalized = normalize_strava_activity_json(raw_activity_json or {})
    return map_strava_activity_to_actividad(normalized)
