from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict

from django.utils import timezone


SportType = Literal["RUN", "TRAIL", "BIKE", "WALK", "SWIM", "STRENGTH", "OTHER"]


class NormalizedStravaBusinessActivity(TypedDict):
    tipo_deporte: SportType
    # Raw (audit/debug): el string original de Strava (sport_type/type), uppercased/trimmed.
    # Ej: "TRAILRUN", "RUN", "RIDE"
    strava_sport_type: str
    distancia: float
    duracion: int
    fecha_inicio: datetime
    source: Literal["strava"]


def _coalesce(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _to_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        # Strava/stravalib puede traer Quantity con .magnitude
        if hasattr(v, "magnitude"):
            return float(v.magnitude)
        return float(v)
    except Exception:
        return 0.0


def _to_int(v: Any) -> int:
    try:
        if v is None:
            return 0
        if hasattr(v, "total_seconds"):
            return int(v.total_seconds())
        if hasattr(v, "seconds"):
            return int(v.seconds)
        return int(v)
    except Exception:
        return 0


def _ensure_tz_aware(dt: Any) -> datetime | None:
    if not dt:
        return None
    if not isinstance(dt, datetime):
        return None
    if timezone.is_aware(dt):
        return dt
    # Best-effort: Strava start_date_local suele venir "local". Si llega naive, usamos TZ actual.
    return timezone.make_aware(dt, timezone.get_current_timezone())


def extract_strava_sport_type(raw: dict) -> str:
    """
    Extrae el sport_type/type original de Strava de forma robusta.

    El pipeline actual pasa a veces un dict "normalizado" (con keys top-level)
    y otras veces el dict crudo bajo `raw`.
    """
    raw = raw or {}
    nested = raw.get("raw") if isinstance(raw.get("raw"), dict) else {}

    st = _coalesce(
        raw.get("sport_type"),
        raw.get("sportType"),
        nested.get("sport_type"),
        nested.get("sportType"),
        # `type` legacy (menos granular). Lo dejamos al final para que NO pise nested sport_type.
        raw.get("type"),
        nested.get("type"),
    )
    return str(st or "").strip().upper()


def _normalize_strava_sport_type(raw: dict) -> SportType:
    """
    Normaliza tipos Strava a tipos de negocio.

    Priority: sport_type (granular) > type (legacy).

    Product principle (2026-04-22): every activity Strava sends becomes a
    persisted domain activity — "todo suma" (every effort is physiological load).
    Unknown sports fall to OTHER but are still created (see decide_activity_creation).
    Applies only to Strava (Law 4); other providers follow the same pattern
    in their own normalizer when activated.
    """
    st = extract_strava_sport_type(raw)

    # Run family
    if st in {"RUN", "VIRTUALRUN", "VIRTUAL_RUN"}:
        return "RUN"
    if st in {"TRAILRUN", "TRAIL_RUN"}:
        return "TRAIL"

    # Bike family
    if st in {
        "RIDE", "VIRTUALRIDE", "VIRTUAL_RIDE",
        "EBIKERIDE", "E_BIKE_RIDE",
        "MOUNTAINBIKERIDE", "MOUNTAIN_BIKE_RIDE",
        "GRAVELRIDE", "GRAVEL_RIDE",
        "ROADBIKERIDE", "ROAD_BIKE_RIDE",
        "HANDCYCLE", "VELOMOBILE",
    }:
        return "BIKE"

    # Swim
    if st in {"SWIM", "SWIMMING"}:
        return "SWIM"

    # Walk / Hike
    if st in {"WALK", "HIKE", "WHEELCHAIR"}:
        return "WALK"

    # Strength / recovery family
    if st in {
        "WEIGHTTRAINING", "WEIGHT_TRAINING",
        "WORKOUT",
        "CROSSFIT",
        "YOGA", "PILATES",
    }:
        return "STRENGTH"

    # All other sports persist as OTHER (cardio equipment, winter, water, climbing, golf…)
    return "OTHER"


def normalize_strava_activity_payload(raw: dict) -> NormalizedStravaBusinessActivity:
    """
    Capa SaaS de normalización entre ingesta cruda (Strava) y Actividad de negocio.

    Input:
    - dict de Strava (puede ser el dict normalizado de `core.strava_mapper.normalize_strava_activity`)

    Output (contrato estable):
    - tipo_deporte (RUN, TRAIL, BIKE, WALK, OTHER)
    - distancia (metros)
    - duracion (segundos)
    - fecha_inicio (timezone aware)
    - source = "strava"
    """
    raw_sport = extract_strava_sport_type(raw or {})
    tipo = _normalize_strava_sport_type(raw or {})

    # Distancia: ya normalizada en `distance_m`, fallback a keys Strava API
    distancia = _to_float(_coalesce(raw.get("distance_m"), raw.get("distance"), raw.get("distance_in_meters")))

    # Duración: preferimos moving_time, fallback elapsed_time
    duracion = _to_int(
        _coalesce(raw.get("moving_time_s"), raw.get("moving_time"), raw.get("elapsed_time_s"), raw.get("elapsed_time"))
    )

    # Fecha: preferimos start_date_local, fallback start_date
    fecha = _ensure_tz_aware(_coalesce(raw.get("start_date_local"), raw.get("start_date")))
    if fecha is None:
        # Mantener contrato: si falta, devolvemos aware "now" para evitar excepciones downstream,
        # pero el pipeline debe descartarla con reason explícita.
        fecha = timezone.now()

    return {
        "tipo_deporte": tipo,
        "strava_sport_type": raw_sport,
        "distancia": float(distancia or 0.0),
        "duracion": int(duracion or 0),
        "fecha_inicio": fecha,
        "source": "strava",
    }


@dataclass(frozen=True)
class ProductDecision:
    should_create: bool
    reason: str  # empty cuando should_create=True


def decide_activity_creation(*, normalized: NormalizedStravaBusinessActivity) -> ProductDecision:
    """
    Reglas de producto (2026-04-22) — "todo suma":
    - TODA actividad con duracion > 0 se crea.
    - Deportes con distancia (RUN/TRAIL/BIKE/SWIM/WALK) requieren distance > 0.
    - Deportes sin distancia (STRENGTH/OTHER) solo requieren duracion > 0.
    """
    sport = normalized.get("tipo_deporte")
    duration = int(normalized.get("duracion") or 0)
    distance = float(normalized.get("distancia") or 0.0)

    if duration <= 0:
        return ProductDecision(False, "duration_non_positive")

    if sport in {"RUN", "TRAIL", "BIKE", "SWIM", "WALK"}:
        if distance <= 0:
            return ProductDecision(False, f"distance_non_positive_for_{sport}")

    return ProductDecision(True, "")
