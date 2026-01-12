from __future__ import annotations

from datetime import date

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from analytics.models import DailyActivityAgg, HistorialFitness, PMCHistory
from analytics.pmc_engine import PMC_SPORT_GROUPS, ensure_pmc_materialized
from core.models import Actividad, Entrenamiento, InscripcionCarrera


def get_pmc_for_range(
    *,
    alumno_id: int,
    sport_filter: str,
    start_date: date,
    end_date: date,
    user,
    is_athlete: bool,
) -> list[dict]:
    """
    Devuelve la serie PMC (incluye métricas auxiliares) para un rango.
    """
    ensure_pmc_materialized(alumno_id=alumno_id)

    pmc_rows = list(
        PMCHistory.objects.filter(alumno_id=alumno_id, sport=sport_filter, fecha__range=[start_date, end_date])
        .order_by("fecha")
        .values("fecha", "tss_diario", "ctl", "atl", "tsb")
    )
    if not pmc_rows:
        hf_rows = list(
            HistorialFitness.objects.filter(alumno_id=alumno_id, fecha__range=[start_date, end_date])
            .order_by("fecha")
            .values("fecha", "tss_diario", "ctl", "atl", "tsb")
        )
        if not hf_rows:
            if Entrenamiento.objects.filter(alumno_id=alumno_id).exists():
                today = timezone.localdate()
                return [
                    {
                        "fecha": today.isoformat(),
                        "is_future": False,
                        "ctl": 0.0,
                        "atl": 0.0,
                        "tsb": 0.0,
                        "load": 0,
                        "dist": 0.0,
                        "time": 0,
                        "elev_gain": 0,
                        "elev_loss": None,
                        "calories": None,
                        "effort": None,
                        "race": None,
                    }
                ]
            return []
        pmc_rows = hf_rows

    included_sports = PMC_SPORT_GROUPS[sport_filter]
    agg_rows = DailyActivityAgg.objects.filter(
        alumno_id=alumno_id,
        fecha__range=[start_date, end_date],
        sport__in=list(included_sports),
    ).values("fecha", "distance_m", "elev_gain_m", "duration_s")

    by_date: dict[date, dict] = {}
    for r in agg_rows.iterator(chunk_size=1000):
        d = r["fecha"]
        prev = by_date.get(d) or {"distance_m": 0.0, "elev_gain_m": 0.0, "duration_s": 0}
        prev["distance_m"] += float(r.get("distance_m") or 0.0)
        prev["elev_gain_m"] += float(r.get("elev_gain_m") or 0.0)
        prev["duration_s"] += int(r.get("duration_s") or 0)
        by_date[d] = prev

    opt_rows = (
        Actividad.objects.filter(alumno_id=alumno_id, validity=Actividad.Validity.VALID)
        .filter(fecha_inicio__date__range=[start_date, end_date])
        .annotate(d=TruncDate("fecha_inicio"))
        .values("d")
        .annotate(
            calories_kcal=Sum("calories_kcal"),
            elev_loss_m=Sum("elev_loss_m"),
            effort=Sum("effort"),
        )
    )
    opt_by_date = {r["d"]: r for r in opt_rows.iterator(chunk_size=1000)}

    objetivos_base = InscripcionCarrera.objects.all()
    if is_athlete:
        objetivos_base = objetivos_base.filter(alumno__usuario=user)
    else:
        objetivos_base = objetivos_base.filter(alumno__entrenador=user)

    objetivos_qs = objetivos_base.filter(alumno_id=alumno_id).select_related("carrera").values(
        "carrera__fecha", "carrera__nombre", "carrera__distancia_km", "carrera__desnivel_positivo_m"
    )
    objetivos_map = {
        obj["carrera__fecha"].strftime("%Y-%m-%d"): {
            "nombre": obj["carrera__nombre"],
            "km": obj["carrera__distancia_km"],
            "elev": obj["carrera__desnivel_positivo_m"],
        }
        for obj in objetivos_qs
    }

    data: list[dict] = []
    for row in pmc_rows:
        d = row["fecha"]
        f_str = d.isoformat()
        agg = by_date.get(d) or {"distance_m": 0.0, "elev_gain_m": 0.0, "duration_s": 0}
        opt = opt_by_date.get(d) or {}
        data.append(
            {
                "fecha": f_str,
                "is_future": False,
                "ctl": round(float(row["ctl"] or 0.0), 1),
                "atl": round(float(row["atl"] or 0.0), 1),
                "tsb": round(float(row["tsb"] or 0.0), 1),
                "load": int(float(row["tss_diario"] or 0.0)),
                "dist": round(float(agg["distance_m"] or 0.0) / 1000.0, 2),
                "time": int(round(float(agg["duration_s"] or 0) / 60.0)),
                "elev_gain": int(round(float(agg["elev_gain_m"] or 0.0))),
                "elev_loss": int(round(float(opt["elev_loss_m"]))) if opt.get("elev_loss_m") is not None else None,
                "calories": int(round(float(opt["calories_kcal"]))) if opt.get("calories_kcal") is not None else None,
                "effort": float(opt["effort"]) if opt.get("effort") is not None else None,
                "race": objetivos_map.get(f_str, None),
            }
        )

    return data
