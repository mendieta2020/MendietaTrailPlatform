from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import ExtractIsoWeek, ExtractIsoYear, TruncDate
from django.utils import timezone

from analytics.models import DailyActivityAgg, HistorialFitness, PMCHistory
from core.models import Actividad


PMC_SPORT_GROUPS: dict[str, set[str]] = {
    "RUN": {"RUN", "TRAIL"},
    "BIKE": {"BIKE"},
    "ALL": {"RUN", "TRAIL", "BIKE"},
}


def _to_localdate(dt) -> date:
    if isinstance(dt, date) and not hasattr(dt, "date"):
        return dt
    try:
        return timezone.localtime(dt).date()
    except Exception:
        return timezone.localdate()


def _normalize_business_sport(tipo_deporte: str | None) -> str:
    """
    Normaliza valores legacy del campo `Actividad.tipo_deporte` a los canónicos.
    """
    st = str(tipo_deporte or "").strip().upper()
    if st in {"RUN", "VIRTUALRUN", "TRAILRUN", "TRAIL", "VIRTUAL_RUN", "TRAIL_RUN"}:
        return "TRAIL" if st in {"TRAIL", "TRAILRUN", "TRAIL_RUN"} else "RUN"
    if st in {"RIDE", "VIRTUALRIDE", "BIKE", "CYCLING", "MTB", "INDOOR_BIKE", "ROADBIKERIDE", "MOUNTAINBIKERIDE", "GRAVELRIDE"}:
        return "BIKE"
    if st in {"WALK", "HIKE"}:
        return "WALK"
    return "OTHER"


def _extract_activity_load(raw_json: dict | None, duration_s: int) -> float:
    """
    MVP robusto: intenta usar señales típicas de Strava; si no existen, usa proxy por duración.

    Prioridad:
    - relative_effort (Strava)
    - suffer_score (legacy)
    - proxy: horas * 50
    """
    raw_json = raw_json or {}

    for key in ("relative_effort", "suffer_score", "sufferScore"):
        v = raw_json.get(key)
        if v is None:
            continue
        try:
            vv = float(v)
            if vv > 0:
                return vv
        except Exception:
            pass

    # Proxy conservador (evita 0s si faltan campos en el payload)
    try:
        hrs = max(float(duration_s or 0) / 3600.0, 0.0)
    except Exception:
        hrs = 0.0
    return hrs * 50.0


@dataclass(frozen=True)
class DailyAggRow:
    fecha: date
    sport: str
    load: float
    distance_m: float
    elev_gain_m: float
    duration_s: int


def build_daily_aggs_for_alumno(*, alumno_id: int, start_date: date) -> int:
    """
    Reconstruye DailyActivityAgg desde `start_date` (inclusive).
    Idempotente: borra rango y re-crea.
    """
    start_date = date.fromisoformat(str(start_date))

    acts = (
        Actividad.objects.filter(alumno_id=alumno_id, validity=Actividad.Validity.VALID)
        .filter(fecha_inicio__date__gte=start_date)
        .values("fecha_inicio", "tipo_deporte", "distancia", "desnivel_positivo", "tiempo_movimiento", "datos_brutos")
    )

    by_key: dict[tuple[date, str], DailyAggRow] = {}
    for a in acts.iterator(chunk_size=500):
        d = _to_localdate(a["fecha_inicio"])
        sport = _normalize_business_sport(a.get("tipo_deporte"))
        distance_m = float(a.get("distancia") or 0.0)
        elev_m = float(a.get("desnivel_positivo") or 0.0)
        dur_s = int(a.get("tiempo_movimiento") or 0)
        load = float(_extract_activity_load(a.get("datos_brutos") or {}, dur_s) or 0.0)

        key = (d, sport)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = DailyAggRow(d, sport, load, distance_m, elev_m, dur_s)
        else:
            by_key[key] = DailyAggRow(
                d,
                sport,
                prev.load + load,
                prev.distance_m + distance_m,
                prev.elev_gain_m + elev_m,
                prev.duration_s + dur_s,
            )

    rows = list(by_key.values())
    with transaction.atomic():
        DailyActivityAgg.objects.filter(alumno_id=alumno_id, fecha__gte=start_date).delete()
        DailyActivityAgg.objects.bulk_create(
            [
                DailyActivityAgg(
                    alumno_id=alumno_id,
                    fecha=r.fecha,
                    sport=r.sport,
                    load=float(r.load or 0.0),
                    distance_m=float(r.distance_m or 0.0),
                    elev_gain_m=float(r.elev_gain_m or 0.0),
                    duration_s=int(r.duration_s or 0),
                )
                for r in rows
            ],
            batch_size=1000,
        )

    return len(rows)


def _daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def recompute_pmc_for_alumno(*, alumno_id: int, start_date: date) -> dict[str, int]:
    """
    Recalcula PMC incremental desde `start_date` (inclusive) para ALL/RUN/BIKE.
    - Seedea con el día anterior si existe PMCHistory previa, sino 0.
    - Idempotente: borra rango y re-crea.
    - Mantiene `analytics.HistorialFitness` sincronizado para ALL (compat + injury_risk).
    """
    start_date = date.fromisoformat(str(start_date))

    # Rango efectivo: desde start_date hasta hoy (o último día con agg, si fuese > hoy)
    last_agg = (
        DailyActivityAgg.objects.filter(alumno_id=alumno_id).order_by("-fecha").values_list("fecha", flat=True).first()
    )
    end_date = max(timezone.localdate(), last_agg) if last_agg else timezone.localdate()

    # Pre-cargamos loads por día+sport canónico (RUN/TRAIL/BIKE/...)
    aggs = DailyActivityAgg.objects.filter(alumno_id=alumno_id, fecha__range=[start_date, end_date]).values(
        "fecha", "sport", "load"
    )
    load_by_day_sport: dict[tuple[date, str], float] = {}
    for r in aggs.iterator(chunk_size=1000):
        load_by_day_sport[(r["fecha"], r["sport"])] = float(r["load"] or 0.0)

    def tss_for_group(day: date, group: str) -> float:
        sports = PMC_SPORT_GROUPS[group]
        return float(sum(load_by_day_sport.get((day, s), 0.0) for s in sports))

    seed_day = start_date - timedelta(days=1)
    seeds: dict[str, tuple[float, float]] = {}
    for group in ("ALL", "RUN", "BIKE"):
        prev = (
            PMCHistory.objects.filter(alumno_id=alumno_id, sport=group, fecha=seed_day)
            .values("ctl", "atl")
            .first()
        )
        seeds[group] = (float(prev["ctl"]), float(prev["atl"])) if prev else (0.0, 0.0)

    new_rows: list[PMCHistory] = []
    new_hf: list[HistorialFitness] = []

    ctl_prev, atl_prev = seeds["ALL"]
    ctl_prev_run, atl_prev_run = seeds["RUN"]
    ctl_prev_bike, atl_prev_bike = seeds["BIKE"]

    for d in _daterange(start_date, end_date):
        tss_all = tss_for_group(d, "ALL")
        tss_run = tss_for_group(d, "RUN")
        tss_bike = tss_for_group(d, "BIKE")

        ctl_prev = ctl_prev + (tss_all - ctl_prev) / 42.0
        atl_prev = atl_prev + (tss_all - atl_prev) / 7.0
        tsb_all = ctl_prev - atl_prev

        ctl_prev_run = ctl_prev_run + (tss_run - ctl_prev_run) / 42.0
        atl_prev_run = atl_prev_run + (tss_run - atl_prev_run) / 7.0
        tsb_run = ctl_prev_run - atl_prev_run

        ctl_prev_bike = ctl_prev_bike + (tss_bike - ctl_prev_bike) / 42.0
        atl_prev_bike = atl_prev_bike + (tss_bike - atl_prev_bike) / 7.0
        tsb_bike = ctl_prev_bike - atl_prev_bike

        new_rows.extend(
            [
                PMCHistory(alumno_id=alumno_id, fecha=d, sport="ALL", tss_diario=tss_all, ctl=ctl_prev, atl=atl_prev, tsb=tsb_all),
                PMCHistory(
                    alumno_id=alumno_id, fecha=d, sport="RUN", tss_diario=tss_run, ctl=ctl_prev_run, atl=atl_prev_run, tsb=tsb_run
                ),
                PMCHistory(
                    alumno_id=alumno_id,
                    fecha=d,
                    sport="BIKE",
                    tss_diario=tss_bike,
                    ctl=ctl_prev_bike,
                    atl=atl_prev_bike,
                    tsb=tsb_bike,
                ),
            ]
        )

        # Compat: HistorialFitness = ALL
        new_hf.append(HistorialFitness(alumno_id=alumno_id, fecha=d, tss_diario=tss_all, ctl=ctl_prev, atl=atl_prev, tsb=tsb_all))

    with transaction.atomic():
        PMCHistory.objects.filter(alumno_id=alumno_id, fecha__gte=start_date).delete()
        PMCHistory.objects.bulk_create(new_rows, batch_size=1000)

        HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__gte=start_date).delete()
        HistorialFitness.objects.bulk_create(new_hf, batch_size=1000)

    return {"pmc_rows": len(new_rows), "historial_fitness_rows": len(new_hf)}


def ensure_pmc_materialized(*, alumno_id: int) -> bool:
    """
    Best-effort para UX: si no hay PMC persistido pero sí hay actividades, lo materializa.
    """
    if PMCHistory.objects.filter(alumno_id=alumno_id).exists():
        return True

    first = (
        Actividad.objects.filter(alumno_id=alumno_id, validity=Actividad.Validity.VALID)
        .order_by("fecha_inicio")
        .values_list("fecha_inicio", flat=True)
        .first()
    )
    if not first:
        return False

    start = _to_localdate(first)
    build_daily_aggs_for_alumno(alumno_id=alumno_id, start_date=start)
    recompute_pmc_for_alumno(alumno_id=alumno_id, start_date=start)
    return True


def weekly_activity_stats_for_alumno(
    *,
    alumno_id: int,
    weeks: int = 26,
    end_date: date | None = None,
    sport_group: str = "ALL",
) -> list[dict]:
    """
    Agrega métricas por semana ISO (YYYY-WW) para UX (vista semanal).

    Contracto estable (frontend-safe):
    - Siempre devuelve lista (nunca None).
    - Si no hay datos: [].
    - Valores numéricos normalizados: km (float), elev_gain_m (int), calories_kcal (int).
    """
    try:
        weeks = int(weeks or 0)
    except Exception:
        weeks = 0
    if weeks <= 0:
        return []

    end = end_date or timezone.localdate()
    # Ventana cerrada por semanas completas hacia atrás (aprox), pero agrupamos por ISO week real.
    start = end - timedelta(days=(weeks * 7) - 1)

    sport_group = str(sport_group or "ALL").upper().strip()
    if sport_group not in PMC_SPORT_GROUPS:
        sport_group = "ALL"
    included_sports = list(PMC_SPORT_GROUPS[sport_group])

    # Sumas por ISO week desde DailyActivityAgg (distancia y desnivel)
    weekly_aggs = (
        DailyActivityAgg.objects.filter(
            alumno_id=int(alumno_id),
            fecha__range=[start, end],
            sport__in=included_sports,
        )
        .annotate(iso_year=ExtractIsoYear("fecha"), iso_week=ExtractIsoWeek("fecha"))
        .values("iso_year", "iso_week")
        .annotate(distance_m=Sum("distance_m"), elev_gain_m=Sum("elev_gain_m"))
        .order_by("iso_year", "iso_week")
    )

    # Calorías por ISO week desde Actividad (opcional; algunos atletas no lo tienen)
    weekly_cals = (
        Actividad.objects.filter(
            alumno_id=int(alumno_id),
            validity=Actividad.Validity.VALID,
            fecha_inicio__date__range=[start, end],
        )
        .annotate(d=TruncDate("fecha_inicio"))
        .annotate(iso_year=ExtractIsoYear("d"), iso_week=ExtractIsoWeek("d"))
        .values("iso_year", "iso_week")
        .annotate(calories_kcal=Sum("calories_kcal"))
        .order_by("iso_year", "iso_week")
    )
    cals_by_week = {(int(r["iso_year"]), int(r["iso_week"])): r.get("calories_kcal") for r in weekly_cals}

    out: list[dict] = []
    for r in weekly_aggs:
        y = int(r["iso_year"])
        w = int(r["iso_week"])
        week_start = date.fromisocalendar(y, w, 1)
        week_end = week_start + timedelta(days=6)

        dist_m = float(r.get("distance_m") or 0.0)
        elev_m = float(r.get("elev_gain_m") or 0.0)
        calories = cals_by_week.get((y, w), 0)  # None si la suma es NULL

        out.append(
            {
                "week": f"{y}-{w:02d}",
                "range": {"start": week_start.isoformat(), "end": week_end.isoformat()},
                "km": round(dist_m / 1000.0, 2),
                "elev_gain_m": int(round(elev_m)),
                "calories_kcal": int(round(float(calories or 0.0))),
            }
        )

    # Si no hay filas de DailyActivityAgg, igual devolvemos [] (no inventamos semanas)
    return out

