from __future__ import annotations

from django.conf import settings


def strength_load_factor() -> float:
    """
    Factor configurable de carga por minuto para sesiones STRENGTH.
    """
    try:
        return float(getattr(settings, "STRENGTH_LOAD_FACTOR", 4.0) or 4.0)
    except Exception:
        return 4.0


def compute_training_load(*, tipo_actividad: str | None, tiempo_real_min: float | int | None, rpe: float | int | None, tss) -> float:
    """
    Carga fisiológica (escala unificada) para CTL/ATL/TSB.

    Reglas:
    - Si existe `tss` (y es >0), se prioriza.
    - STRENGTH: minutos * factor configurable (no depende de distancia).
    - OTHER: no suma carga (actividades ignoradas).
    - Fallback: minutos * (1 + rpe/10) (heurística MVP, rpe clamp 0..10).
    """
    tipo = str(tipo_actividad or "").upper()

    # 1) Señal explícita (tss) cuando existe
    if tss is not None:
        try:
            tss_f = float(tss or 0.0)
            if tss_f > 0:
                return tss_f
        except Exception:
            pass

    # 2) OTHER no suma (requerimiento de negocio)
    if tipo == "OTHER":
        return 0.0

    # 3) Tiempo es la base común (fuerza no requiere distancia)
    try:
        dur = float(tiempo_real_min or 0.0)
    except Exception:
        dur = 0.0
    if dur <= 0:
        return 0.0

    # 4) Fuerza: minutos * factor
    if tipo == "STRENGTH":
        return dur * strength_load_factor()

    # 5) Heurística general: minutos * (1 + rpe/10)
    try:
        rpe_f = float(rpe or 0.0)
    except Exception:
        rpe_f = 0.0
    rpe_f = max(0.0, min(10.0, rpe_f))
    intensity = 1.0 + (rpe_f / 10.0)
    return dur * intensity

