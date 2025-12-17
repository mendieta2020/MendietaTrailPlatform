from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from analytics.models import Alert, SessionComparison
from core.models import Entrenamiento


def _compute_simple_load_for_entrenamientos(qs) -> float:
    """Heurística MVP: sum(tiempo_real_min * (1 + rpe/10))."""
    total = 0.0
    for e in qs:
        dur = float(e.tiempo_real_min or 0)
        rpe = float(e.rpe or 0)
        intensity = 1.0 + (max(0.0, min(10.0, rpe)) / 10.0)
        total += dur * intensity
    return total


def _upsert_open_alert(*, alumno_id: int, entrenador_id: int, equipo_id: int | None, type: str, severity: str, message: str, payload: dict):
    """Crea o actualiza (idempotente) la alerta OPEN por (alumno,type)."""
    Alert.objects.update_or_create(
        alumno_id=alumno_id,
        type=type,
        status=Alert.Status.OPEN,
        defaults={
            "entrenador_id": entrenador_id,
            "equipo_id": equipo_id,
            "severity": severity,
            "message": message,
            "payload_json": payload,
        },
    )


def _close_open_alert(*, alumno_id: int, type: str):
    Alert.objects.filter(alumno_id=alumno_id, type=type, status=Alert.Status.OPEN).update(
        status=Alert.Status.CLOSED,
        closed_at=timezone.now(),
    )


@transaction.atomic
def run_alert_triggers_for_comparison(comparison: SessionComparison):
    """
    Disparadores iniciales (MVP robusto):
    - anomaly
    - low compliance (<70% 2 veces seguidas)
    - overtraining risk (carga 7d vs 28d)

    Multi-tenant: toda la data viene scopiada por `comparison.entrenador`/`comparison.alumno`.
    """

    alumno = comparison.alumno
    entrenador_id = comparison.entrenador_id
    equipo_id = comparison.equipo_id

    # 1) Anomalías
    if comparison.classification == SessionComparison.Classification.ANOMALY:
        _upsert_open_alert(
            alumno_id=alumno.id,
            entrenador_id=entrenador_id,
            equipo_id=equipo_id,
            type=Alert.Type.ANOMALY,
            severity=Alert.Severity.HIGH,
            message="Anomalía detectada en Plan vs Actual.",
            payload={"comparison_id": comparison.id, "fecha": comparison.fecha.isoformat()},
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.ANOMALY)

    # 2) Compliance bajo repetido
    recent = (
        SessionComparison.objects.filter(alumno=alumno, planned_session__isnull=False)
        .order_by("-fecha", "-created_at")
        .values_list("compliance_score", flat=True)[:2]
    )
    recent = list(recent)
    if len(recent) == 2 and all(x < 70 for x in recent):
        _upsert_open_alert(
            alumno_id=alumno.id,
            entrenador_id=entrenador_id,
            equipo_id=equipo_id,
            type=Alert.Type.LOW_COMPLIANCE,
            severity=Alert.Severity.MEDIUM,
            message="Cumplimiento bajo (<70%) en 2 sesiones consecutivas.",
            payload={"last_two_scores": recent},
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.LOW_COMPLIANCE)

    # 3) Overtraining risk (simple)
    today = timezone.localdate()
    start_7d = today - timedelta(days=7)
    start_28d = today - timedelta(days=28)

    entrenos = Entrenamiento.objects.filter(alumno=alumno, completado=True, fecha_asignada__gte=start_28d).only(
        "tiempo_real_min", "rpe", "fecha_asignada", "alumno_id"
    )
    load_28d = _compute_simple_load_for_entrenamientos(entrenos)

    entrenos_7d = [e for e in entrenos if e.fecha_asignada >= start_7d]
    load_7d = _compute_simple_load_for_entrenamientos(entrenos_7d)

    avg_7d_from_28d = (load_28d / 28.0) * 7.0 if load_28d > 0 else 0.0

    if avg_7d_from_28d > 0 and load_7d > (1.5 * avg_7d_from_28d):
        _upsert_open_alert(
            alumno_id=alumno.id,
            entrenador_id=entrenador_id,
            equipo_id=equipo_id,
            type=Alert.Type.OVERTRAINING_RISK,
            severity=Alert.Severity.HIGH,
            message="Riesgo de sobrecarga: carga 7d elevada vs tendencia 28d.",
            payload={
                "load_7d": round(load_7d, 2),
                "load_28d": round(load_28d, 2),
                "baseline_7d_from_28d": round(avg_7d_from_28d, 2),
            },
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.OVERTRAINING_RISK)
