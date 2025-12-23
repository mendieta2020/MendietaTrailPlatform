from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict

from django.utils import timezone


SportType = Literal["RUN", "TRAIL", "BIKE", "STRENGTH", "WALK", "OTHER"]


class NormalizedStravaBusinessActivity(TypedDict):
    tipo_deporte: SportType
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


def _normalize_strava_sport_type(raw: dict) -> SportType:
    """
    Normaliza tipos Strava a tipos de negocio.

    Nota de producto:
    - Strava puede mandar `type` (legacy) y/o `sport_type` (más granular). Preferimos sport_type si existe.
    """
    st = str(_coalesce(raw.get("sport_type"), raw.get("type"), "") or "").strip().upper()

    # Running
    if st in {"RUN", "VIRTUALRUN"}:
        return "RUN"
    if st in {"TRAILRUN"}:
        return "TRAIL"

    # Bike
    if st in {
        "RIDE",
        "VIRTUALRIDE",
        "EBIKERIDE",
        "MOUNTAINBIKERIDE",
        "GRAVELRIDE",
        "ROADBIKERIDE",
    }:
        return "BIKE"

    # Strength (no distance required)
    # Strava: `sport_type` suele venir como WEIGHTTRAINING / WORKOUT / CROSSFIT.
    if st in {"WEIGHTTRAINING", "WORKOUT", "CROSSFIT"}:
        return "STRENGTH"

    # Walk-ish
    if st in {"WALK", "HIKE"}:
        return "WALK"

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
    Reglas de producto (SaaS):
    - Crear actividad "válida" si:
      - tipo_deporte ∈ [RUN, TRAIL, BIKE] y distancia > 0
      - tipo_deporte == STRENGTH y duracion > 0 (no requiere distancia)
    - Si no, reason explícita (no genérica)
    """
    sport = normalized.get("tipo_deporte")
    if sport not in {"RUN", "TRAIL", "BIKE", "STRENGTH"}:
        return ProductDecision(False, f"sport_type_not_allowed:{sport}")
    if sport != "STRENGTH":
        if float(normalized.get("distancia") or 0.0) <= 0:
            return ProductDecision(False, "distance_non_positive")
    else:
        if int(normalized.get("duracion") or 0) <= 0:
            return ProductDecision(False, "duration_non_positive")
    return ProductDecision(True, "")

