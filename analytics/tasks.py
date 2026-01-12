import logging
from datetime import date as date_type, timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.models import Alumno
from analytics.models import HistorialFitness, InjuryRiskSnapshot
from analytics.injury_risk import compute_injury_risk
from core.models import AthleteSyncState


logger = logging.getLogger(__name__)


def _safe_localdate(d: str | None) -> date_type:
    if not d:
        return timezone.localdate()
    return date_type.fromisoformat(d)


@shared_task(
    name="analytics.recompute_injury_risk_for_athlete",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def recompute_injury_risk_for_athlete(self, alumno_id: int, fecha_iso: str | None = None) -> str:
    """
    Recalcula el snapshot de riesgo para un atleta y fecha (idempotente).
    """
    fecha = _safe_localdate(fecha_iso)

    try:
        alumno = Alumno.objects.select_related("entrenador").get(pk=alumno_id)
    except Alumno.DoesNotExist:
        logger.warning("injury_risk.skip_unknown_athlete", extra={"alumno_id": alumno_id, "fecha": str(fecha)})
        return "SKIP_UNKNOWN_ATHLETE"

    entrenador_id = alumno.entrenador_id
    if not entrenador_id:
        logger.warning(
            "injury_risk.skip_no_tenant",
            extra={"alumno_id": alumno_id, "fecha": str(fecha)},
        )
        return "SKIP_NO_TENANT"

    # Traemos ventana mínima para reglas (D, D-1, D-2, D-7)
    start = fecha - timedelta(days=7)
    rows = list(
        HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__range=[start, fecha])
        .values("fecha", "ctl", "atl", "tsb", "tss_diario")
        .order_by("fecha")
    )

    if not rows:
        # Sin PMC: snapshot estable para no romper UX
        defaults = dict(
            entrenador_id=entrenador_id,
            risk_level=InjuryRiskSnapshot.RiskLevel.LOW,
            risk_score=0,
            risk_reasons=["Sin datos PMC para calcular riesgo"],
            ctl=0,
            atl=0,
            tsb=0,
            version="v1",
        )
        InjuryRiskSnapshot.objects.update_or_create(alumno_id=alumno_id, fecha=fecha, defaults=defaults)
        return "OK_NO_PMC"

    # Elegimos el registro del día; si falta, usamos el último disponible <= fecha (v1 conservador)
    today_row = None
    for r in reversed(rows):
        if r["fecha"] <= fecha:
            today_row = r
            break
    if not today_row:
        today_row = rows[-1]

    # ATL 7d ago (si existe exacto)
    atl_7d_ago = None
    for r in rows:
        if r["fecha"] == (fecha - timedelta(days=7)):
            atl_7d_ago = r["atl"]
            break

    # Últimos 3 días de TSS (D, D-1, D-2) si existen
    tss_by_date = {r["fecha"]: (r["tss_diario"] or 0) for r in rows}
    last_3_tss = [tss_by_date.get(fecha - timedelta(days=i), 0) for i in range(0, 3)]

    result = compute_injury_risk(
        ctl=float(today_row["ctl"] or 0),
        atl=float(today_row["atl"] or 0),
        tsb=float(today_row["tsb"] or 0),
        atl_7d_ago=float(atl_7d_ago) if atl_7d_ago is not None else None,
        last_3_days_tss=last_3_tss,
    )

    defaults = dict(
        entrenador_id=entrenador_id,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        risk_reasons=result.risk_reasons,
        ctl=float(today_row["ctl"] or 0),
        atl=float(today_row["atl"] or 0),
        tsb=float(today_row["tsb"] or 0),
        version="v1",
    )

    InjuryRiskSnapshot.objects.update_or_create(alumno_id=alumno_id, fecha=fecha, defaults=defaults)

    logger.info(
        "injury_risk.snapshot_upserted",
        extra={"alumno_id": alumno_id, "entrenador_id": entrenador_id, "fecha": str(fecha), "level": result.risk_level, "score": result.risk_score},
    )
    return "OK"


@shared_task(
    name="analytics.recompute_injury_risk_for_coach",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def recompute_injury_risk_for_coach(self, entrenador_id: int, fecha_iso: str | None = None) -> str:
    """
    Recalcula riesgo para todos los atletas de un entrenador (multi-tenant).
    """
    fecha = _safe_localdate(fecha_iso)
    alumnos = Alumno.objects.filter(entrenador_id=entrenador_id).exclude(estado_actual="BAJA").values_list("id", flat=True)

    count = 0
    for alumno_id in alumnos:
        recompute_injury_risk_for_athlete.delay(alumno_id, fecha.isoformat())
        count += 1

    logger.info("injury_risk.coach_enqueued", extra={"entrenador_id": entrenador_id, "fecha": str(fecha), "athletes": count})
    return f"ENQUEUED_{count}"


@shared_task(
    name="analytics.recompute_injury_risk_daily",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def recompute_injury_risk_daily(self, fecha_iso: str | None = None) -> str:
    """
    Orquestador diario (idempotente): encola por entrenador.
    """
    fecha = _safe_localdate(fecha_iso)

    # Entrenadores con al menos un alumno
    coach_ids = (
        Alumno.objects.exclude(entrenador_id__isnull=True)
        .values_list("entrenador_id", flat=True)
        .distinct()
    )

    enqueued = 0
    for coach_id in coach_ids:
        recompute_injury_risk_for_coach.delay(int(coach_id), fecha.isoformat())
        enqueued += 1

    logger.info("injury_risk.daily_enqueued", extra={"fecha": str(fecha), "coaches": enqueued})
    return f"ENQUEUED_COACHES_{enqueued}"


@shared_task(
    name="analytics.recompute_pmc_from_activities",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def recompute_pmc_from_activities(self, alumno_id: int, affected_date_iso: str | None = None) -> dict:
    """
    Recalcula PMC desde `core.Actividad` de forma incremental e idempotente.

    Concurrency control:
    - usa `core.AthleteSyncState` como lock/coalescing store por atleta.
    - múltiples eventos pueden encolar esta task; se "colapsan" vía metrics_pending_from.
    """
    from analytics.pmc_engine import build_daily_aggs_for_alumno, recompute_pmc_for_alumno

    alumno_id = int(alumno_id)
    now = timezone.now()
    affected_date = None
    if affected_date_iso:
        try:
            affected_date = date_type.fromisoformat(str(affected_date_iso))
        except Exception:
            affected_date = None

    # Coalescing + lock (DB)
    with transaction.atomic():
        state, _ = AthleteSyncState.objects.select_for_update().get_or_create(
            alumno_id=alumno_id,
            defaults={"provider": "strava"},
        )

        # Registrar la mínima fecha afectada
        if affected_date:
            if state.metrics_pending_from is None or affected_date < state.metrics_pending_from:
                state.metrics_pending_from = affected_date

        # Si ya hay un recompute corriendo (con TTL corto), salimos
        if state.metrics_status == AthleteSyncState.Status.RUNNING and state.metrics_last_run_at:
            if (now - state.metrics_last_run_at).total_seconds() < 60:
                state.save(update_fields=["metrics_pending_from"])
                return {"status": "SKIP_RUNNING", "alumno_id": alumno_id}

        start_date = state.metrics_pending_from or affected_date or timezone.localdate()

        state.metrics_status = AthleteSyncState.Status.RUNNING
        state.metrics_last_error = ""
        # usamos metrics_last_run_at como "started_at" para TTL simple
        state.metrics_last_run_at = now
        state.metrics_pending_from = None
        state.save(
            update_fields=[
                "metrics_status",
                "metrics_last_error",
                "metrics_last_run_at",
                "metrics_pending_from",
            ]
        )

    try:
        aggs = build_daily_aggs_for_alumno(alumno_id=alumno_id, start_date=start_date)
        pmc = recompute_pmc_for_alumno(alumno_id=alumno_id, start_date=start_date)
        with transaction.atomic():
            AthleteSyncState.objects.filter(alumno_id=alumno_id).update(metrics_status=AthleteSyncState.Status.DONE)
        logger.info(
            "analytics.pmc.recompute.done",
            extra={"alumno_id": alumno_id, "start_date": str(start_date), "daily_aggs": aggs, **pmc},
        )
        return {"status": "OK", "alumno_id": alumno_id, "start_date": str(start_date), "daily_aggs": aggs, **pmc}
    except Exception as exc:
        with transaction.atomic():
            AthleteSyncState.objects.filter(alumno_id=alumno_id).update(
                metrics_status=AthleteSyncState.Status.FAILED,
                metrics_last_error=str(exc),
            )
        logger.exception(
            "analytics.pmc.recompute.failed",
            extra={"alumno_id": alumno_id, "start_date": str(start_date), "error": str(exc)},
        )
        raise
