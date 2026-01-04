from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from django.db import transaction

from .models import Alumno, Entrenamiento, PlantillaEntrenamiento


@dataclass(frozen=True)
class PlannedMetrics:
    distancia_km: Optional[float] = None
    tiempo_min: Optional[int] = None
    desnivel_m: Optional[int] = None
    rpe: Optional[int] = None


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _extract_metrics_from_endurance_3(estructura: Dict[str, Any]) -> PlannedMetrics:
    """
    Extrae métricas planned desde el JSON usado por el editor actual:
    estructura = { version: "ENDURANCE_3.0", bloques: [{ type, repeats, steps: [{duration_value, duration_unit, intensity}] }]}
    """
    bloques = estructura.get("bloques") or []
    if not isinstance(bloques, list):
        return PlannedMetrics()

    total_seconds = 0.0
    total_meters = 0.0
    rpe_weighted = 0.0
    rpe_weight = 0.0

    for b in bloques:
        if not isinstance(b, dict):
            continue
        repeats = _safe_int(b.get("repeats")) or 1
        steps = b.get("steps") or []
        if not isinstance(steps, list):
            continue

        for s in steps:
            if not isinstance(s, dict):
                continue
            dv = _safe_float(s.get("duration_value")) or 0.0
            unit = (s.get("duration_unit") or "").lower()
            intensity = _safe_int(s.get("intensity"))

            # ENDURANCE builder: min / km / m
            step_seconds = 0.0
            step_meters = 0.0
            if unit == "min":
                step_seconds = dv * 60.0
            elif unit == "km":
                step_meters = dv * 1000.0
            elif unit == "m" or unit == "mts":
                step_meters = dv

            step_seconds *= repeats
            step_meters *= repeats
            total_seconds += step_seconds
            total_meters += step_meters

            # Proxy RPE: zona 1..5 -> rpe 2..9 (heurística suave)
            if intensity is not None:
                step_rpe = 2 + max(0, min(5, intensity)) * 1.5
                w = max(step_seconds, 1.0)  # ponderar por tiempo si existe
                rpe_weighted += step_rpe * w
                rpe_weight += w

    tiempo_min = int(round(total_seconds / 60.0)) if total_seconds > 0 else None
    distancia_km = round(total_meters / 1000.0, 2) if total_meters > 0 else None
    rpe = int(round(rpe_weighted / rpe_weight)) if rpe_weight > 0 else None
    return PlannedMetrics(distancia_km=distancia_km, tiempo_min=tiempo_min, rpe=rpe)


def extract_planned_metrics(estructura: Any) -> PlannedMetrics:
    """
    Parser tolerante: si no reconoce el shape, devuelve vacíos.
    """
    if not isinstance(estructura, dict):
        return PlannedMetrics()
    version = str(estructura.get("version") or "")
    if version.startswith("ENDURANCE_3"):
        return _extract_metrics_from_endurance_3(estructura)
    # Compat: algunos renders usan estructura.bloques [{type, content}]
    return PlannedMetrics()


def render_descripcion_detallada_from_estructura(estructura: Any) -> str:
    """
    Render “Trainer Plan style” simple para cards/legacy.
    No reemplaza el JSON: solo genera una vista humana.
    """
    if not isinstance(estructura, dict):
        return ""
    bloques = estructura.get("bloques") or []
    if not isinstance(bloques, list):
        return ""

    lines = []
    for b in bloques:
        if not isinstance(b, dict):
            continue
        btype = b.get("type") or "BLOCK"
        reps = _safe_int(b.get("repeats")) or 1
        header = f"[{btype}] x{reps}" if reps > 1 else f"[{btype}]"
        lines.append(header)
        steps = b.get("steps") or []
        if isinstance(steps, list):
            for s in steps:
                if not isinstance(s, dict):
                    continue
                dv = s.get("duration_value")
                du = s.get("duration_unit")
                intensity = s.get("intensity")
                desc = (s.get("description") or "").strip()
                chunk = f" • {dv}{du or ''}"
                if intensity is not None:
                    chunk += f" @ Z{intensity}"
                if desc:
                    chunk += f" ({desc})"
                lines.append(chunk)
        lines.append("")  # separación

    return "\n".join(lines).strip()


@transaction.atomic
def apply_template_to_student(
    *,
    plantilla: PlantillaEntrenamiento,
    alumno: Alumno,
    fecha_asignada,
) -> Entrenamiento:
    """
    Crea una instancia individual (editable) desde una plantilla (maestro).
    La instancia NO comparte referencias mutables (dict) con la plantilla.
    """
    estructura = plantilla.estructura or {}
    # Copia defensiva (evita mutación compartida)
    estructura_clon = dict(estructura) if isinstance(estructura, dict) else {}

    metrics = extract_planned_metrics(estructura_clon)
    descripcion_render = render_descripcion_detallada_from_estructura(estructura_clon)

    entreno = Entrenamiento.objects.create(
        alumno=alumno,
        plantilla_origen=plantilla,
        fecha_asignada=fecha_asignada,
        titulo=plantilla.titulo,
        tipo_actividad=plantilla.deporte,
        # Mantener campo legacy como “vista humana” + fallback a resumen
        descripcion_detallada=(descripcion_render or (plantilla.descripcion_global or "")),
        estructura=estructura_clon,
        distancia_planificada_km=metrics.distancia_km,
        tiempo_planificado_min=metrics.tiempo_min,
        desnivel_planificado_m=metrics.desnivel_m,
        rpe_planificado=metrics.rpe or 0,
        completado=False,
    )
    return entreno


def build_bulk_entrenamientos_for_team(
    *,
    plantilla: PlantillaEntrenamiento,
    alumnos,
    fecha_asignada,
) -> Tuple[list[Entrenamiento], PlannedMetrics, str]:
    """
    Prepara objetos Entrenamiento para bulk_create, reutilizando métricas/render.
    """
    estructura = plantilla.estructura or {}
    estructura_clon = dict(estructura) if isinstance(estructura, dict) else {}
    metrics = extract_planned_metrics(estructura_clon)
    descripcion_render = render_descripcion_detallada_from_estructura(estructura_clon)

    base_kwargs = dict(
        plantilla_origen=plantilla,
        fecha_asignada=fecha_asignada,
        titulo=plantilla.titulo,
        tipo_actividad=plantilla.deporte,
        descripcion_detallada=(descripcion_render or (plantilla.descripcion_global or "")),
        estructura=estructura_clon,
        distancia_planificada_km=metrics.distancia_km,
        tiempo_planificado_min=metrics.tiempo_min,
        desnivel_planificado_m=metrics.desnivel_m,
        rpe_planificado=metrics.rpe or 0,
        completado=False,
    )

    items: list[Entrenamiento] = []
    for alumno in alumnos:
        items.append(Entrenamiento(alumno=alumno, **base_kwargs))
    return items, metrics, descripcion_render

