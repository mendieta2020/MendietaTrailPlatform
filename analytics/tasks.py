import logging
from datetime import date as date_type, timedelta

from celery import shared_task
from django.utils import timezone

from core.models import Alumno
from analytics.models import HistorialFitness, InjuryRiskSnapshot
from analytics.injury_risk import compute_injury_risk


logger = logging.getLogger(__name__)


def _safe_localdate(d: str | None) -> date_type:
    if not d:
        return timezone.localdate()
    return date_type.fromisoformat(d)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
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


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
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

