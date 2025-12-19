import hashlib
import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder


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
    }


def map_strava_activity_to_actividad(strava_activity_json: dict) -> dict:
    """Map Strava normalized json -> campos del modelo core.models.Actividad."""
    activity_id = strava_activity_json.get("id")
    source_object_id = str(activity_id) if activity_id is not None else ""

    distance_m = float(strava_activity_json.get("distance_m") or 0.0)
    moving_s = int(strava_activity_json.get("moving_time_s") or 0)

    return {
        "source": "strava",
        "source_object_id": source_object_id,
        "source_hash": compute_source_hash(strava_activity_json.get("raw") or {}),
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
        "datos_brutos": strava_activity_json.get("raw") or {},
    }
