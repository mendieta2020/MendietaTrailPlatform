from __future__ import annotations

import math
from typing import Any


def _normalize_sport(sport: str | None) -> str:
    st = str(sport or "").strip().upper()
    if st in {"RUN", "TRAILRUN", "VIRTUALRUN", "TRAIL", "VIRTUAL_RUN", "TRAIL_RUN"}:
        return "TRAIL" if st in {"TRAIL", "TRAILRUN", "TRAIL_RUN"} else "RUN"
    if st in {
        "RIDE",
        "VIRTUALRIDE",
        "BIKE",
        "CYCLING",
        "MTB",
        "INDOOR_BIKE",
        "ROADBIKERIDE",
        "MOUNTAINBIKERIDE",
        "GRAVELRIDE",
    }:
        return "BIKE"
    if st in {"WALK", "HIKE"}:
        return "WALK"
    return "OTHER"


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if hasattr(value, "magnitude"):
            return float(value.magnitude)
        return float(value)
    except Exception:
        return default


def compute_calories_kcal(activity: Any, *, fallback_weight_kg: float = 70.0) -> float:
    """
    Calcula calorías en kcal garantizando salida numérica (>=(0)).

    Política:
    - Si Strava/actividad trae calories válidas (>0 y finitas) => se usan como fuente primaria.
    - Si falta/invalid:
      - RUN/TRAIL: ~1.0 kcal/kg/km (coste energético estándar running).
      - WALK: ~0.75 kcal/kg/km (costo menor que running).
      - BIKE: MET 6.8 (ciclismo moderado) => kcal = MET * kg * horas.
      - OTHER: MET 3.5 (actividad ligera) si hay duración; si no, 0.
    Referencia práctica: coste energético por km (kcal/kg/km) es un estándar clínico/deportivo.
    """
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    raw_kcal = _get(activity, "calories_kcal", None)
    if raw_kcal is None:
        raw_kcal = _get(activity, "calories", None)
    kcal = _safe_float(raw_kcal)
    if kcal is not None and math.isfinite(kcal) and kcal > 0:
        return float(kcal)

    alumno = _get(activity, "alumno", None)
    peso = _safe_float(_get(activity, "alumno__peso", None))
    if peso is None and alumno is not None:
        peso = _safe_float(getattr(alumno, "peso", None))
    peso = float(peso) if (peso is not None and peso > 0) else float(fallback_weight_kg)

    distance_m = _safe_float(
        _get(activity, "distancia", None)
        or _get(activity, "distance_m", None)
        or _get(activity, "distancia_m", None),
        default=0.0,
    )
    duration_s = _safe_float(
        _get(activity, "tiempo_movimiento", None)
        or _get(activity, "moving_time_s", None)
        or _get(activity, "duracion", None),
        default=0.0,
    )

    sport = _normalize_sport(
        _get(activity, "tipo_deporte", None)
        or _get(activity, "sport", None)
        or _get(activity, "strava_sport_type", None)
    )

    distance_km = max(float(distance_m or 0.0) / 1000.0, 0.0)
    duration_h = max(float(duration_s or 0.0) / 3600.0, 0.0)

    kcal_estimate = 0.0
    if sport in {"RUN", "TRAIL"} and distance_km > 0:
        kcal_estimate = distance_km * peso * 1.0
    elif sport in {"WALK"} and distance_km > 0:
        kcal_estimate = distance_km * peso * 0.75
    elif sport in {"BIKE"} and duration_h > 0:
        kcal_estimate = 6.8 * peso * duration_h
    elif duration_h > 0:
        kcal_estimate = 3.5 * peso * duration_h

    if not math.isfinite(kcal_estimate) or kcal_estimate < 0:
        return 0.0
    return float(kcal_estimate)
