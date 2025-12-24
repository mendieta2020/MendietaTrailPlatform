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


def _upsert_open_alert(
    *,
    alumno_id: int,
    entrenador_id: int,
    equipo_id: int | None,
    type: str,
    severity: str,
    message: str,
    recommended_action: str,
    evidence: dict,
):
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
            "recommended_action": recommended_action,
            "evidence_json": evidence,
            # Requisito: si se vuelve a disparar/actualizar, vuelve a "nuevo"
            "visto_por_coach": False,
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
            severity=Alert.Severity.WARN,
            message="Anomalía detectada en Plan vs Actual.",
            recommended_action="Revisar la sesión y clasificarla (libre vs planificada) o ajustar el plan.",
            evidence={"comparison_id": comparison.id, "fecha": comparison.fecha.isoformat()},
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.ANOMALY)

    # 2) Compliance bajo repetido (legacy)
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
            severity=Alert.Severity.WARN,
            message="Cumplimiento bajo (<70%) en 2 sesiones consecutivas.",
            recommended_action="Revisar barreras (fatiga, tiempo, lesión) y ajustar la planificación de la semana.",
            evidence={"last_two_scores": recent},
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.LOW_COMPLIANCE)

    # 3) Overtraining risk (legacy) - mantenemos por compat
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
            severity=Alert.Severity.WARN,
            message="Riesgo de sobrecarga: carga 7d elevada vs tendencia 28d.",
            recommended_action="Bajar carga 24–48h, priorizar sueño/recuperación y revisar progresión semanal.",
            evidence={
                "load_7d": round(load_7d, 2),
                "load_28d": round(load_28d, 2),
                "baseline_7d_from_28d": round(avg_7d_from_28d, 2),
            },
        )
    else:
        _close_open_alert(alumno_id=alumno.id, type=Alert.Type.OVERTRAINING_RISK)

    # ==============================================================================
    # Coach Decision Layer v1 (5 triggers, accionables)
    # ==============================================================================
    from analytics.models import DailyActivityAgg, InjuryRiskSnapshot, PMCHistory
    from analytics.pmc_engine import PMC_SPORT_GROUPS

    # A) injury_risk_up_and_fatigue_high
    try:
        day = comparison.fecha
        snap_today = (
            InjuryRiskSnapshot.objects.filter(alumno_id=alumno.id, fecha__lte=day)
            .order_by("-fecha")
            .values("fecha", "risk_score", "risk_level", "ctl", "atl", "tsb")
            .first()
        )
        snap_prev = (
            InjuryRiskSnapshot.objects.filter(alumno_id=alumno.id, fecha__lt=(day - timedelta(days=7)))
            .order_by("-fecha")
            .values("fecha", "risk_score")
            .first()
        )
        if snap_today:
            risk_score = int(snap_today["risk_score"] or 0)
            prev_score = int((snap_prev or {}).get("risk_score") or 0)
            delta = risk_score - prev_score
            ctl = float(snap_today.get("ctl") or 0.0)
            atl = float(snap_today.get("atl") or 0.0)
            tsb = float(snap_today.get("tsb") or 0.0)
            fatigue_high = (tsb <= -10.0) or (ctl > 0 and atl >= (1.15 * ctl))

            if risk_score >= 70 and delta >= 10 and fatigue_high:
                severity = Alert.Severity.CRITICAL if (risk_score >= 85 or tsb <= -20.0) else Alert.Severity.WARN
                _upsert_open_alert(
                    alumno_id=alumno.id,
                    entrenador_id=entrenador_id,
                    equipo_id=equipo_id,
                    type=Alert.Type.INJURY_RISK_UP_AND_FATIGUE_HIGH,
                    severity=severity,
                    message="Riesgo de lesión en alza con fatiga alta.",
                    recommended_action="Reducir carga 2–3 días, priorizar recuperación y revisar dolor/alertas del atleta.",
                    evidence={
                        "snapshot_date": str(snap_today.get("fecha")),
                        "risk_score": risk_score,
                        "risk_score_delta_vs_prev": delta,
                        "ctl": round(ctl, 1),
                        "atl": round(atl, 1),
                        "tsb": round(tsb, 1),
                    },
                )
            else:
                _close_open_alert(alumno_id=alumno.id, type=Alert.Type.INJURY_RISK_UP_AND_FATIGUE_HIGH)
        else:
            _close_open_alert(alumno_id=alumno.id, type=Alert.Type.INJURY_RISK_UP_AND_FATIGUE_HIGH)
    except Exception:
        # No bloquear alert pipeline
        pass

    # B) compliance_drop_week (últimos 7d vs 7d prev)
    try:
        end = comparison.fecha
        cur_start = end - timedelta(days=6)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)

        cur_scores = list(
            SessionComparison.objects.filter(alumno_id=alumno.id, planned_session__isnull=False, fecha__range=[cur_start, end])
            .values_list("compliance_score", flat=True)
        )
        prev_scores = list(
            SessionComparison.objects.filter(alumno_id=alumno.id, planned_session__isnull=False, fecha__range=[prev_start, prev_end])
            .values_list("compliance_score", flat=True)
        )

        if len(cur_scores) >= 3 and len(prev_scores) >= 3:
            cur_avg = sum(cur_scores) / float(len(cur_scores))
            prev_avg = sum(prev_scores) / float(len(prev_scores))
            drop = prev_avg - cur_avg
            if drop >= 15 and cur_avg < 80:
                severity = Alert.Severity.CRITICAL if (drop >= 25 and cur_avg < 70) else Alert.Severity.WARN
                _upsert_open_alert(
                    alumno_id=alumno.id,
                    entrenador_id=entrenador_id,
                    equipo_id=equipo_id,
                    type=Alert.Type.COMPLIANCE_DROP_WEEK,
                    severity=severity,
                    message="Caída de cumplimiento semanal vs la semana anterior.",
                    recommended_action="Reducir complejidad/carga del plan y acordar objetivos realistas para recuperar adherencia.",
                    evidence={
                        "cur_window": {"start": str(cur_start), "end": str(end), "avg": round(cur_avg, 1), "n": len(cur_scores)},
                        "prev_window": {"start": str(prev_start), "end": str(prev_end), "avg": round(prev_avg, 1), "n": len(prev_scores)},
                        "drop_points": round(drop, 1),
                    },
                )
            else:
                _close_open_alert(alumno_id=alumno.id, type=Alert.Type.COMPLIANCE_DROP_WEEK)
        else:
            _close_open_alert(alumno_id=alumno.id, type=Alert.Type.COMPLIANCE_DROP_WEEK)
    except Exception:
        pass

    # C) acute_load_spike (7d vs baseline 28d)
    try:
        end = comparison.fecha
        start7 = end - timedelta(days=6)
        start28 = end - timedelta(days=27)

        sports = list(PMC_SPORT_GROUPS["ALL"])
        loads = list(
            DailyActivityAgg.objects.filter(alumno_id=alumno.id, fecha__range=[start28, end], sport__in=sports)
            .values("fecha", "load")
        )
        load_by_day = {}
        for r in loads:
            load_by_day[r["fecha"]] = load_by_day.get(r["fecha"], 0.0) + float(r.get("load") or 0.0)

        load_7d = sum(load_by_day.get(start7 + timedelta(days=i), 0.0) for i in range(7))
        load_28d = sum(load_by_day.get(start28 + timedelta(days=i), 0.0) for i in range(28))
        baseline = (load_28d / 28.0) * 7.0 if load_28d > 0 else 0.0
        ratio = (load_7d / baseline) if baseline > 0 else 0.0

        if baseline > 0 and ratio >= 1.6:
            severity = Alert.Severity.CRITICAL if ratio >= 2.0 else Alert.Severity.WARN
            _upsert_open_alert(
                alumno_id=alumno.id,
                entrenador_id=entrenador_id,
                equipo_id=equipo_id,
                type=Alert.Type.ACUTE_LOAD_SPIKE,
                severity=severity,
                message="Spike de carga aguda vs baseline 28d.",
                recommended_action="Implementar descarga (50–70% volumen) y controlar fatiga/dolor en próximos 3 días.",
                evidence={
                    "window_end": str(end),
                    "load_7d": round(load_7d, 1),
                    "baseline_7d_from_28d": round(baseline, 1),
                    "ratio": round(ratio, 2),
                },
            )
        else:
            _close_open_alert(alumno_id=alumno.id, type=Alert.Type.ACUTE_LOAD_SPIKE)
    except Exception:
        pass

    # D) form_too_negative_sustained (TSB <= -15 por 5 días)
    try:
        end = comparison.fecha
        start = end - timedelta(days=6)
        tsb_rows = list(
            PMCHistory.objects.filter(alumno_id=alumno.id, sport="ALL", fecha__range=[start, end])
            .order_by("fecha")
            .values_list("fecha", "tsb")
        )
        last5 = tsb_rows[-5:] if len(tsb_rows) >= 5 else []
        if len(last5) == 5 and all(float(tsb or 0.0) <= -15.0 for _, tsb in last5):
            min_tsb = min(float(tsb or 0.0) for _, tsb in last5)
            severity = Alert.Severity.CRITICAL if min_tsb <= -25.0 else Alert.Severity.WARN
            _upsert_open_alert(
                alumno_id=alumno.id,
                entrenador_id=entrenador_id,
                equipo_id=equipo_id,
                type=Alert.Type.FORM_TOO_NEGATIVE_SUSTAINED,
                severity=severity,
                message="Forma (TSB) muy negativa sostenida.",
                recommended_action="Priorizar recuperación (1–2 días fáciles) y reducir intensidad hasta que TSB mejore.",
                evidence={
                    "window": [str(d) for d, _ in last5],
                    "tsb_last5": [round(float(tsb or 0.0), 1) for _, tsb in last5],
                    "min_tsb": round(min_tsb, 1),
                },
            )
        else:
            _close_open_alert(alumno_id=alumno.id, type=Alert.Type.FORM_TOO_NEGATIVE_SUSTAINED)
    except Exception:
        pass

    # E) missed_sessions_vs_plan (sesiones planificadas sin completar)
    try:
        end = comparison.fecha
        start = end - timedelta(days=6)
        missed = list(
            Entrenamiento.objects.filter(alumno_id=alumno.id, fecha_asignada__range=[start, end])
            .filter(completado=False, fecha_asignada__lte=today)
            .values_list("id", "fecha_asignada", "titulo")[:20]
        )
        if len(missed) >= 2:
            severity = Alert.Severity.CRITICAL if len(missed) >= 3 else Alert.Severity.WARN
            _upsert_open_alert(
                alumno_id=alumno.id,
                entrenador_id=entrenador_id,
                equipo_id=equipo_id,
                type=Alert.Type.MISSED_SESSIONS_VS_PLAN,
                severity=severity,
                message="Sesiones planificadas no realizadas esta semana.",
                recommended_action="Contactar al atleta, entender causas y re-planificar (menos volumen / más flexibilidad).",
                evidence={
                    "window": {"start": str(start), "end": str(end)},
                    "missed_count": len(missed),
                    "missed_sessions": [{"id": i, "date": str(d), "title": t} for i, d, t in missed],
                },
            )
        else:
            _close_open_alert(alumno_id=alumno.id, type=Alert.Type.MISSED_SESSIONS_VS_PLAN)
    except Exception:
        pass
