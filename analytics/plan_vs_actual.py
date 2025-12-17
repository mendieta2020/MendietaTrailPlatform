from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.models import Entrenamiento, Actividad


@dataclass(frozen=True)
class ComparisonResult:
    metrics: Dict[str, Any]
    compliance_score: int
    classification: str
    explanation: str
    next_action: str


class PlannedVsActualComparator:
    """
    Comparador Plan vs Actual (base para insights/IA/alertas).

    Diseñado para ser:
    - explicable (metrics_json + explanation)
    - estable (inputs mínimos)
    - recalculable (en updates de Strava)
    """

    def compare(self, planned: Optional[Entrenamiento], activity: Actividad) -> ComparisonResult:
        actual_distance_km = float(activity.distancia or 0.0) / 1000.0
        actual_duration_min = float(activity.tiempo_movimiento or 0) / 60.0
        actual_elev_m = float(activity.desnivel_positivo or 0.0)

        metrics: Dict[str, Any] = {
            "actual": {
                "distance_km": round(actual_distance_km, 3),
                "duration_min": round(actual_duration_min, 1),
                "elevation_m": round(actual_elev_m, 0),
                "type": activity.tipo_deporte,
            }
        }

        if planned is None:
            # Sesión no planificada: no hay % de cumplimiento, pero sí dejamos base de métricas.
            return ComparisonResult(
                metrics=metrics,
                compliance_score=0,
                classification="anomaly",
                explanation="Actividad registrada sin sesión planificada asociada.",
                next_action="Revisar y clasificar como libre o ajustar planificación.",
            )

        plan_distance_km = float(planned.distancia_planificada_km or 0.0)
        plan_duration_min = float(planned.tiempo_planificado_min or 0.0)
        plan_elev_m = float(planned.desnivel_planificado_m or 0.0)

        metrics["planned"] = {
            "distance_km": round(plan_distance_km, 3),
            "duration_min": round(plan_duration_min, 1),
            "elevation_m": round(plan_elev_m, 0),
            "type": planned.tipo_actividad,
            "rpe_plan": int(planned.rpe_planificado or 0),
        }

        def ratio(real: float, plan: float) -> Optional[float]:
            if plan and plan > 0:
                return real / plan
            return None

        r_dist = ratio(actual_distance_km, plan_distance_km)
        r_dur = ratio(actual_duration_min, plan_duration_min)
        r_elev = ratio(actual_elev_m, plan_elev_m)

        # Compliance por dimensión (0–200 cap) y score global 0–100.
        dims = []
        for name, r in (("distance", r_dist), ("duration", r_dur), ("elevation", r_elev)):
            if r is None:
                continue
            dims.append((name, r))

        per_dim = {}
        for name, r in dims:
            per_dim[name] = {
                "ratio": round(r, 3),
                "compliance_pct": int(max(0, min(200, round(r * 100)))),
                "delta_abs": None,
                "delta_rel": round(r - 1.0, 3),
            }

        # Deltas absolutos
        if r_dist is not None:
            per_dim["distance"]["delta_abs"] = round(actual_distance_km - plan_distance_km, 3)
        if r_dur is not None:
            per_dim["duration"]["delta_abs"] = round(actual_duration_min - plan_duration_min, 1)
        if r_elev is not None:
            per_dim["elevation"]["delta_abs"] = round(actual_elev_m - plan_elev_m, 0)

        metrics["comparison"] = per_dim

        if not dims:
            return ComparisonResult(
                metrics=metrics,
                compliance_score=0,
                classification="anomaly",
                explanation="Sesión planificada sin métricas cuantificables (distancia/tiempo/desnivel).",
                next_action="Completar métricas planificadas para comparar automáticamente.",
            )

        # Score global: promedio simple del % (cap 100) de dimensiones disponibles.
        compliance_components = [min(100, per_dim[name]["compliance_pct"]) for name, _ in dims]
        compliance_score = int(round(sum(compliance_components) / len(compliance_components)))

        # Clasificación por desviación promedio (con límites simples y explicables)
        avg_rel_delta = sum(per_dim[name]["delta_rel"] for name, _ in dims) / len(dims)
        abs_avg_rel_delta = abs(avg_rel_delta)

        if abs_avg_rel_delta <= 0.10:
            classification = "on_track"
            explanation = "Cumplimiento dentro de ±10% del plan."
            next_action = "Mantener el plan y continuar con la progresión."
        elif avg_rel_delta < -0.15:
            classification = "under"
            explanation = "Por debajo del plan (≥15% menos en promedio)."
            next_action = "Revisar causas (fatiga/tiempo/lesión) y ajustar la carga próxima."
        elif avg_rel_delta > 0.15:
            classification = "over"
            explanation = "Por encima del plan (≥15% más en promedio)."
            next_action = "Considerar compensación (descanso/recuperación) y vigilar fatiga."
        else:
            classification = "anomaly"
            explanation = "Desviación relevante vs el plan."
            next_action = "Revisar el contexto; puede requerir ajuste del plan o datos." 

        # Placeholder LoadScore (simple, documentado): duración * (1 + rpe/10)
        rpe_actual = int(getattr(planned, "rpe", 0) or 0)
        intensity_factor = 1.0 + (max(0, min(10, rpe_actual)) / 10.0)
        metrics["load"] = {
            "load_score": round(actual_duration_min * intensity_factor, 2),
            "method": "duration_min * (1 + rpe/10)",
        }

        return ComparisonResult(
            metrics=metrics,
            compliance_score=compliance_score,
            classification=classification,
            explanation=explanation,
            next_action=next_action,
        )
