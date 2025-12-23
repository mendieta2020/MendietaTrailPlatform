import hashlib
import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

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
    # Nota: esta función queda por compat; la validación de producto vive en
    # `core.strava_activity_normalizer.decide_activity_creation`.
    return st in {
        "RUN",
        "TRAILRUN",
        "VIRTUALRUN",
        # Bike
        "RIDE",
        "VIRTUALRIDE",
        "EBIKERIDE",
        "MOUNTAINBIKERIDE",
        "GRAVELRIDE",
        "ROADBIKERIDE",
        # Walk-ish
        "WALK",
        "HIKE",
        # Otros
        "WORKOUT",
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

    def _to_float_or_zero(v: Any) -> float:
        if v is None:
            return 0.0
        try:
            if hasattr(v, "magnitude"):
                return float(v.magnitude)
            return float(v)
        except Exception:
            return 0.0

    def _to_float_or_none(v: Any) -> float | None:
        if v is None:
            return None
        try:
            if hasattr(v, "magnitude"):
                return float(v.magnitude)
            return float(v)
        except Exception:
            return None

    moving_time_s = _to_seconds(getattr(activity, "moving_time", None))
    elapsed_time_s = _to_seconds(getattr(activity, "elapsed_time", None))
    distance_m = _to_float_or_zero(getattr(activity, "distance", None))
    elev_m = _to_float_or_none(getattr(activity, "total_elevation_gain", None))

    # Métricas opcionales: NO usar 0 como faltante; si no existen, quedan NULL/None
    calories_kcal = _to_float_or_none(getattr(activity, "calories", None))
    relative_effort = _to_float_or_none(
        getattr(activity, "relative_effort", None)
        or getattr(activity, "relativeEffort", None)
        or getattr(activity, "suffer_score", None)
        or getattr(activity, "sufferScore", None)
    )

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
        "elevation_m": float(elev_m) if elev_m is not None else None,
        "calories_kcal": float(calories_kcal) if calories_kcal is not None else None,
        "effort": float(relative_effort) if relative_effort is not None else None,
        # elev_loss se calcula best-effort desde streams (si existen)
        "elev_loss_m": None,
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
    # Persistimos el string original (audit/debug). Preferimos `sport_type` si existe.
    raw_sport_type = (
        str(strava_activity_json.get("strava_sport_type") or "").strip()
        or str(raw.get("sport_type") or raw.get("type") or "").strip()
    )

    def _to_float_or_none(v: Any) -> float | None:
        if v is None:
            return None
        try:
            if hasattr(v, "magnitude"):
                return float(v.magnitude)
            return float(v)
        except Exception:
            return None

    # Fallbacks desde raw (por compat con distintos shapes de Strava/stravalib)
    calories_kcal = _to_float_or_none(strava_activity_json.get("calories_kcal"))
    if calories_kcal is None:
        calories_kcal = _to_float_or_none(raw.get("calories"))

    effort = _to_float_or_none(strava_activity_json.get("effort"))
    if effort is None:
        for k in ("relative_effort", "suffer_score", "sufferScore"):
            effort = _to_float_or_none(raw.get(k))
            if effort is not None:
                break

    elev_loss_m = _to_float_or_none(strava_activity_json.get("elev_loss_m"))
    elev_gain_m = _to_float_or_none(strava_activity_json.get("elevation_m"))

    return {
        "source": "strava",
        "source_object_id": source_object_id,
        "source_hash": compute_source_hash(raw),
        # compat
        "strava_id": int(activity_id) if activity_id is not None else None,
        # negocio
        "nombre": strava_activity_json.get("name") or "",
        "distancia": distance_m,
        "tiempo_movimiento": moving_s,
        "fecha_inicio": strava_activity_json.get("start_date_local"),
        # `tipo_deporte` debe ser el tipo de negocio normalizado (RUN/TRAIL/BIKE/...)
        # para UX consistente; si no viene, usamos type crudo por compat.
        "tipo_deporte": strava_activity_json.get("tipo_deporte") or (strava_activity_json.get("type") or ""),
        "strava_sport_type": raw_sport_type,
        "desnivel_positivo": float(elev_gain_m) if elev_gain_m is not None else None,
        "elev_loss_m": float(elev_loss_m) if elev_loss_m is not None else None,
        "calories_kcal": float(calories_kcal) if calories_kcal is not None else None,
        "effort": float(effort) if effort is not None else None,
        "ritmo_promedio": (distance_m / moving_s) if (distance_m > 0 and moving_s > 0) else None,
        "mapa_polilinea": strava_activity_json.get("polyline"),
        "datos_brutos": raw,
    }
