from __future__ import annotations

import logging
from datetime import date as date_type, timedelta

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from analytics.models import HistorialFitness
from core.models import Actividad


logger = logging.getLogger(__name__)


def _safe_date(value) -> date_type | None:
    if value is None or value == "":
        return None
    if isinstance(value, date_type):
        return value
    if isinstance(value, str):
        try:
            return date_type.fromisoformat(value)
        except Exception:
            return None
    return None


def recompute_analytics_for_alumno_sync(alumno_id: int, start_date: str | date_type | None = None) -> str:
    """
    Recalcula agregados diarios y serie simple de fitness/fatiga/forma desde `Actividad`.

    Persistencia: upsert en `analytics.HistorialFitness` (unique por alumno+fecha).

    Load (aproximación inicial):
    - tss_diario = moving_time_s / 60.0  (minutos)
    """
    # Actividades válidas del alumno
    base_qs = Actividad.objects.filter(alumno_id=alumno_id, validity=Actividad.Validity.VALID)
    if not base_qs.exists():
        return "OK_NO_ACTIVITIES"

    earliest = base_qs.order_by("fecha_inicio").values_list("fecha_inicio", flat=True).first()
    earliest_date = timezone.localdate(earliest) if earliest else timezone.localdate()

    requested_start = _safe_date(start_date)
    if requested_start is None:
        effective_start = earliest_date
    else:
        # Si no hay historial previo para bootstrap de CTL/ATL, recomputamos desde earliest para estabilidad.
        prev = HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__lt=requested_start).order_by("-fecha").first()
        effective_start = requested_start if prev else earliest_date

    today = timezone.localdate()
    if effective_start > today:
        return "OK_EMPTY_RANGE"

    # Agregados DB por día
    daily_rows = (
        base_qs.filter(fecha_inicio__date__gte=effective_start, fecha_inicio__date__lte=today)
        .annotate(fecha=TruncDate("fecha_inicio"))
        .values("fecha")
        .annotate(distance_m=Sum("distancia"), moving_time_s=Sum("tiempo_movimiento"))
        .order_by("fecha")
    )
    daily = {r["fecha"]: r for r in daily_rows}

    # Bootstrap de CTL/ATL
    prev_day = effective_start - timedelta(days=1)
    prev_hist = HistorialFitness.objects.filter(alumno_id=alumno_id, fecha=prev_day).first()
    ctl_prev = float(prev_hist.ctl) if prev_hist else 0.0
    atl_prev = float(prev_hist.atl) if prev_hist else 0.0

    updated = 0
    with transaction.atomic():
        d = effective_start
        while d <= today:
            r = daily.get(d) or {}
            distance_m = float(r.get("distance_m") or 0.0)
            moving_time_s = int(r.get("moving_time_s") or 0)
            tss = float(moving_time_s) / 60.0

            # Banister/Coggan (misma forma que señales legacy)
            ctl = ctl_prev + (tss - ctl_prev) / 42.0
            atl = atl_prev + (tss - atl_prev) / 7.0
            tsb = ctl - atl

            HistorialFitness.objects.update_or_create(
                alumno_id=alumno_id,
                fecha=d,
                defaults={
                    "tss_diario": tss,
                    "distance_m": distance_m,
                    "moving_time_s": moving_time_s,
                    "ctl": ctl,
                    "atl": atl,
                    "tsb": tsb,
                },
            )

            ctl_prev = ctl
            atl_prev = atl
            updated += 1
            d += timedelta(days=1)

    logger.info(
        "analytics.recompute_done",
        extra={"alumno_id": alumno_id, "start": str(effective_start), "end": str(today), "days": updated},
    )
    return f"OK_UPDATED_{updated}"

