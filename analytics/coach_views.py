from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Avg, Case, Count, ExpressionWrapper, F, FloatField, Max, Sum, Value, When
from django.db.models.functions import Coalesce
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound
from rest_framework.settings import api_settings

from analytics.cache import get_range_cache, set_range_cache
from analytics.models import Alert, DailyActivityAgg, InjuryRiskSnapshot, PMCHistory
from analytics.pmc_engine import PMC_SPORT_GROUPS, ensure_pmc_materialized
from analytics.range_utils import max_range_days, parse_date_range_params, parse_iso_week_param
from core.models import Actividad, Alumno, Entrenamiento, Equipo


def _sessions_by_type(*, athlete_id: int, start: date, end: date) -> dict[str, int]:
    qs = (
        Actividad.objects.filter(
            alumno_id=int(athlete_id),
            validity=Actividad.Validity.VALID,
            fecha_inicio__date__range=[start, end],
        )
        .values("tipo_deporte")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    return {row["tipo_deporte"]: int(row["count"] or 0) for row in qs}


def _totals_by_type(*, athlete_id: int, start: date, end: date) -> dict[str, dict]:
    qs = (
        Actividad.objects.filter(
            alumno_id=int(athlete_id),
            validity=Actividad.Validity.VALID,
            fecha_inicio__date__range=[start, end],
        )
        .values("tipo_deporte")
        .annotate(
            sessions_count=Count("id"),
            distance_m=Coalesce(Sum("distancia"), Value(0.0), output_field=FloatField()),
            duration_s=Coalesce(Sum("tiempo_movimiento"), Value(0.0), output_field=FloatField()),
            elev_gain_m=Coalesce(Sum("desnivel_positivo"), Value(0.0), output_field=FloatField()),
            elev_loss_m=Coalesce(Sum("elev_loss_m"), Value(0.0), output_field=FloatField()),
            calories_kcal=Coalesce(Sum("calories_kcal"), Value(0.0), output_field=FloatField()),
        )
        .order_by("-sessions_count")
    )
    totals = {}
    for row in qs:
        distance_m = float(row["distance_m"] or 0.0)
        duration_s = float(row["duration_s"] or 0.0)
        elev_gain_m = float(row["elev_gain_m"] or 0.0)
        elev_loss_m = float(row["elev_loss_m"] or 0.0)
        calories_kcal = float(row["calories_kcal"] or 0.0)
        totals[row["tipo_deporte"]] = {
            "distance_km": round(distance_m / 1000.0, 2),
            "duration_minutes": int(round(duration_s / 60.0)),
            "kcal": int(round(calories_kcal)),
            "elevation_gain_m": int(round(elev_gain_m)),
            "elevation_loss_m": int(round(elev_loss_m)),
            "elevation_total_m": int(round(elev_gain_m + elev_loss_m)),
            "sessions_count": int(row["sessions_count"] or 0),
        }
    return totals


def _require_athlete_for_coach(*, coach, athlete_id: int) -> Alumno:
    try:
        return Alumno.objects.select_related("equipo").get(id=int(athlete_id), entrenador=coach)
    except Alumno.DoesNotExist as exc:
        raise NotFound("Athlete not found") from exc


def _require_group_for_coach(*, coach, group_id: int) -> Equipo:
    try:
        return Equipo.objects.get(id=int(group_id), entrenador=coach)
    except Equipo.DoesNotExist as exc:
        raise NotFound("Group not found") from exc


def _severity_order_case(field_name: str = "severity"):
    """
    Ordena severities (desc) con compat legacy.
    critical/HIGH > warn/MEDIUM > info/LOW
    """
    return Case(
        When(**{f"{field_name}__in": ["critical", "HIGH"]}, then=Value(3)),
        When(**{f"{field_name}__in": ["warn", "MEDIUM"]}, then=Value(2)),
        When(**{f"{field_name}__in": ["info", "LOW"]}, then=Value(1)),
        default=Value(0),
        output_field=FloatField(),
    )


def _pct_and_delta(*, planned: float | None, actual: float | None) -> dict:
    if planned is None or planned <= 0:
        return {"planned": planned, "actual": actual, "pct": None, "delta": None}
    pct = (float(actual or 0.0) / float(planned)) * 100.0
    return {"planned": planned, "actual": actual, "pct": round(pct, 1), "delta": round(float(actual or 0.0) - float(planned), 2)}


def _alerts_top_for_athlete(*, coach, athlete_id: int, limit: int = 5) -> list[dict]:
    qs = (
        Alert.objects.filter(entrenador=coach, alumno_id=int(athlete_id), status=Alert.Status.OPEN)
        .annotate(sev_order=_severity_order_case())
        .order_by("-sev_order", "-created_at", "-id")
    )[: int(limit)]
    return [
        {
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "status": a.status,
            "message": a.message,
            "recommended_action": a.recommended_action,
            "evidence_json": a.evidence_json,
            "visto_por_coach": bool(a.visto_por_coach),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in qs
    ]


def _week_summary_totals(*, athlete_id: int, start: date, end: date) -> dict:
    activities = Actividad.objects.filter(
        alumno_id=int(athlete_id),
        validity=Actividad.Validity.VALID,
        fecha_inicio__date__range=[start, end],
    )
    agg = DailyActivityAgg.objects.filter(alumno_id=int(athlete_id), fecha__range=[start, end]).aggregate(
        duration_s=Sum("duration_s"),
        distance_m=Sum("distance_m"),
        elev_gain_m=Sum("elev_gain_m"),
    )
    activity_agg = activities.aggregate(
        elev_loss_m=Sum("elev_loss_m"),
        calories_kcal=Sum("calories_kcal"),
    )
    sessions_count = activities.count()

    duration_s = float(agg["duration_s"] or 0.0)
    distance_m = float(agg["distance_m"] or 0.0)
    elev_gain_m = float(agg["elev_gain_m"] or 0.0)
    elev_loss_m = float(activity_agg["elev_loss_m"] or 0.0)
    calories_kcal = float(activity_agg["calories_kcal"] or 0.0)

    distance_km = round(distance_m / 1000.0, 2)
    duration_minutes = int(round(duration_s / 60.0))
    elevation_gain_m = int(round(elev_gain_m))
    elevation_loss_m = int(round(elev_loss_m))
    kcal = int(round(calories_kcal))
    elevation_total_m = int(round(elev_gain_m + elev_loss_m))
    return {
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "kcal": kcal,
        "elevation_gain_m": elevation_gain_m,
        "elevation_loss_m": elevation_loss_m,
        "elevation_total_m": elevation_total_m,
        "total_distance_km": distance_km,
        "total_duration_minutes": duration_minutes,
        "total_elevation_gain_m": elevation_gain_m,
        "total_elevation_loss_m": elevation_loss_m,
        "total_calories": kcal,
        "sessions_count": int(sessions_count),
        "sessions_by_type": _sessions_by_type(athlete_id=athlete_id, start=start, end=end),
        "totals_by_type": _totals_by_type(athlete_id=athlete_id, start=start, end=end),
    }


def _pmc_for_athlete(*, athlete_id: int, day: date) -> dict:
    ensure_pmc_materialized(alumno_id=int(athlete_id))
    row = (
        PMCHistory.objects.filter(alumno_id=int(athlete_id), sport="ALL", fecha=day)
        .values("ctl", "atl", "tsb")
        .first()
    )
    if not row:
        return {"fitness": None, "fatigue": None, "form": None, "date": str(day)}
    return {
        "fitness": round(float(row["ctl"] or 0.0), 1),
        "fatigue": round(float(row["atl"] or 0.0), 1),
        "form": round(float(row["tsb"] or 0.0), 1),
        "date": str(day),
    }


def _compliance_for_athlete(*, athlete_id: int, start: date, end: date) -> dict:
    # Planned
    plan_qs = Entrenamiento.objects.filter(alumno_id=int(athlete_id), fecha_asignada__range=[start, end])
    plan_agg = plan_qs.aggregate(
        duration_min=Sum("tiempo_planificado_min"),
        distance_km=Sum("distancia_planificada_km"),
        elev_m=Sum("desnivel_planificado_m"),
    )
    # Planned load proxy
    plan_load_qs = plan_qs.filter(tiempo_planificado_min__isnull=False).annotate(
        load=ExpressionWrapper(
            F("tiempo_planificado_min") * (Value(1.0) + (F("rpe_planificado") / Value(10.0))),
            output_field=FloatField(),
        )
    )
    plan_load = plan_load_qs.aggregate(v=Sum("load"))["v"]

    # Actual (from Entrenamiento completado) for duration/distance/elev
    real_qs = Entrenamiento.objects.filter(
        alumno_id=int(athlete_id),
        fecha_asignada__range=[start, end],
        completado=True,
    )
    real_agg = real_qs.aggregate(
        duration_min=Sum("tiempo_real_min"),
        distance_km=Sum("distancia_real_km"),
        elev_m=Sum("desnivel_real_m"),
    )

    # Actual load: suma de DailyActivityAgg (ALL sports) en la semana
    sports = list(PMC_SPORT_GROUPS["ALL"])
    real_load = (
        DailyActivityAgg.objects.filter(alumno_id=int(athlete_id), fecha__range=[start, end], sport__in=sports)
        .aggregate(v=Sum("load"))
        .get("v")
    )

    planned_duration = float(plan_agg["duration_min"]) if plan_agg["duration_min"] is not None else None
    planned_distance = float(plan_agg["distance_km"]) if plan_agg["distance_km"] is not None else None
    planned_elev = float(plan_agg["elev_m"]) if plan_agg["elev_m"] is not None else None
    planned_load = float(plan_load) if plan_load is not None else None

    actual_duration = float(real_agg["duration_min"]) if real_agg["duration_min"] is not None else None
    actual_distance = float(real_agg["distance_km"]) if real_agg["distance_km"] is not None else None
    actual_elev = float(real_agg["elev_m"]) if real_agg["elev_m"] is not None else None
    actual_load = float(real_load) if real_load is not None else None

    return {
        "duration": _pct_and_delta(planned=planned_duration, actual=actual_duration),
        "distance": _pct_and_delta(planned=planned_distance, actual=actual_distance),
        "elev": _pct_and_delta(planned=planned_elev, actual=actual_elev),
        "load": _pct_and_delta(planned=planned_load, actual=actual_load),
    }


def _week_summary_core(*, athlete_id: int, start: date, end: date) -> dict:
    return {
        **_week_summary_totals(athlete_id=athlete_id, start=start, end=end),
        "pmc": _pmc_for_athlete(athlete_id=athlete_id, day=end),
        "compliance": _compliance_for_athlete(athlete_id=athlete_id, start=start, end=end),
    }


class CoachAthleteWeekSummaryView(APIView):
    # Usamos exactamente el mismo stack de auth que el resto de endpoints coach (defaults de DRF).
    # Esto asegura soporte para JWT en cookie (401 solo cuando no hay credenciales).
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("week", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="ISO week YYYY-Www"),
            openapi.Parameter("start_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="ISO date YYYY-MM-DD"),
            openapi.Parameter("end_date", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="ISO date YYYY-MM-DD"),
        ]
    )
    def get(self, request, athlete_id: int):
        """
        Week summary payload (200):
        {
          "athlete_id": 7,
          "sport": "ALL",
          "week": "2026-W03",
          "start_date": "2026-01-12",
          "end_date": "2026-01-18",
          "distance_km": 112.0,
          "duration_minutes": 724,
          "kcal": 8500,
          "elevation_gain_m": 2797,
          "elevation_loss_m": 2797,
          "elevation_total_m": 5594,
          "sessions_count": 6,
          "sessions_by_type": {"RUN": 4, "BIKE": 1, "STRENGTH": 1},
          "totals_by_type": {"RUN": {"distance_km": 90, ...}},
          "pmc": {"fitness": 52.1, "fatigue": 61.4, "form": -9.3, "date": "2026-01-18"},
          "compliance": {"duration": {...}, "distance": {...}, "elev": {...}, "load": {...}},
          "alerts": [...]
        }
        """
        # Nota: devolvemos 401 si falta auth; 404 si el atleta no pertenece al coach autenticado.
        athlete = _require_athlete_for_coach(coach=request.user, athlete_id=int(athlete_id))
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")
        week_param = request.query_params.get("week")

        if start_param or end_param:
            try:
                start, end, _ = parse_date_range_params(
                    start_param,
                    end_param,
                    default_days=7,
                    enforce_max_for_custom=True,
                )
            except ValueError as exc:
                reason = str(exc)
                if reason == "start_end_required":
                    return Response({"detail": "start_date and end_date must be provided together."}, status=400)
                if reason == "start_after_end":
                    return Response({"detail": "start_date must be before end_date."}, status=400)
                if reason == "range_too_large":
                    return Response({"detail": "Requested range too large.", "max_days": max_range_days()}, status=400)
                return Response({"detail": "Invalid date range."}, status=400)

            week = None
            if (end - start).days == 6 and start.isocalendar()[2] == 1:
                week = f"{start.isocalendar()[0]}-W{start.isocalendar()[1]:02d}"
        else:
            try:
                start, end, week = parse_iso_week_param(week_param)
            except Exception:
                return Response({"detail": "Invalid week format. Use week=YYYY-Www"}, status=400)

        cached_core = get_range_cache(
            cache_type="WEEK_SUMMARY",
            alumno_id=athlete.id,
            sport="ALL",
            start_date=start,
            end_date=end,
        )
        if cached_core is None:
            cached_core = _week_summary_core(athlete_id=athlete.id, start=start, end=end)
            set_range_cache(
                cache_type="WEEK_SUMMARY",
                alumno_id=athlete.id,
                sport="ALL",
                start_date=start,
                end_date=end,
                payload=cached_core,
            )

        data = {
            "athlete_id": athlete.id,
            "sport": "ALL",
            "week": week,
            "start_date": str(start),
            "end_date": str(end),
            **cached_core,
            "alerts": _alerts_top_for_athlete(coach=request.user, athlete_id=athlete.id, limit=5),
        }
        return Response(data, status=200)


class CoachGroupWeekSummaryView(APIView):
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("week", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="ISO week YYYY-Www"),
        ]
    )
    def get(self, request, group_id: int):
        group = _require_group_for_coach(coach=request.user, group_id=int(group_id))
        try:
            start, end, week = parse_iso_week_param(request.query_params.get("week"))
        except Exception:
            return Response({"detail": "Invalid week format. Use week=YYYY-Www"}, status=400)

        athlete_ids = list(Alumno.objects.filter(entrenador=request.user, equipo_id=group.id).values_list("id", flat=True))
        # KPIs group (sum)
        acts = Actividad.objects.filter(
            alumno_id__in=athlete_ids,
            validity=Actividad.Validity.VALID,
            fecha_inicio__date__range=[start, end],
        )
        kpi_agg = acts.aggregate(
            duration_s=Sum("tiempo_movimiento"),
            distance_m=Sum("distancia"),
            elev_gain_m=Sum("desnivel_positivo"),
            elev_loss_m=Sum("elev_loss_m"),
            calories_kcal=Sum("calories_kcal"),
            effort=Sum("effort"),
        )
        dur_s = int(kpi_agg["duration_s"] or 0)
        kpis = {
            "duration_min": round(dur_s / 60.0, 1),
            "distance_km": round(float(kpi_agg["distance_m"] or 0.0) / 1000.0, 2),
            "elev_gain_m": int(round(float(kpi_agg["elev_gain_m"]))) if kpi_agg.get("elev_gain_m") is not None else None,
            "elev_loss_m": int(round(float(kpi_agg["elev_loss_m"]))) if kpi_agg.get("elev_loss_m") is not None else None,
            "calories_kcal": int(round(float(kpi_agg["calories_kcal"]))) if kpi_agg.get("calories_kcal") is not None else None,
            "effort": round(float(kpi_agg["effort"]), 1) if kpi_agg.get("effort") is not None else None,
        }

        # Group PMC: promedio al cierre de semana (ALL)
        ensure_pmc_materialized(alumno_id=athlete_ids[0]) if athlete_ids else None
        pmc_row = (
            PMCHistory.objects.filter(alumno_id__in=athlete_ids, sport="ALL", fecha=end)
            .aggregate(fitness=Avg("ctl"), fatigue=Avg("atl"), form=Avg("tsb"))
        )
        pmc = {
            "fitness": round(float(pmc_row["fitness"] or 0.0), 1) if pmc_row.get("fitness") is not None else None,
            "fatigue": round(float(pmc_row["fatigue"] or 0.0), 1) if pmc_row.get("fatigue") is not None else None,
            "form": round(float(pmc_row["form"] or 0.0), 1) if pmc_row.get("form") is not None else None,
            "date": str(end),
        }

        # Compliance group (sum)
        plan_qs = Entrenamiento.objects.filter(alumno_id__in=athlete_ids, fecha_asignada__range=[start, end])
        plan_agg = plan_qs.aggregate(
            duration_min=Sum("tiempo_planificado_min"),
            distance_km=Sum("distancia_planificada_km"),
            elev_m=Sum("desnivel_planificado_m"),
        )
        plan_load = (
            plan_qs.filter(tiempo_planificado_min__isnull=False)
            .annotate(
                load=ExpressionWrapper(
                    F("tiempo_planificado_min") * (Value(1.0) + (F("rpe_planificado") / Value(10.0))),
                    output_field=FloatField(),
                )
            )
            .aggregate(v=Sum("load"))
            .get("v")
        )
        real_qs = Entrenamiento.objects.filter(alumno_id__in=athlete_ids, fecha_asignada__range=[start, end], completado=True)
        real_agg = real_qs.aggregate(
            duration_min=Sum("tiempo_real_min"),
            distance_km=Sum("distancia_real_km"),
            elev_m=Sum("desnivel_real_m"),
        )
        sports = list(PMC_SPORT_GROUPS["ALL"])
        real_load = (
            DailyActivityAgg.objects.filter(alumno_id__in=athlete_ids, fecha__range=[start, end], sport__in=sports)
            .aggregate(v=Sum("load"))
            .get("v")
        )
        compliance = {
            "duration": _pct_and_delta(
                planned=float(plan_agg["duration_min"]) if plan_agg["duration_min"] is not None else None,
                actual=float(real_agg["duration_min"]) if real_agg["duration_min"] is not None else None,
            ),
            "distance": _pct_and_delta(
                planned=float(plan_agg["distance_km"]) if plan_agg["distance_km"] is not None else None,
                actual=float(real_agg["distance_km"]) if real_agg["distance_km"] is not None else None,
            ),
            "elev": _pct_and_delta(
                planned=float(plan_agg["elev_m"]) if plan_agg["elev_m"] is not None else None,
                actual=float(real_agg["elev_m"]) if real_agg["elev_m"] is not None else None,
            ),
            "load": _pct_and_delta(
                planned=float(plan_load) if plan_load is not None else None,
                actual=float(real_load) if real_load is not None else None,
            ),
        }

        # Alerts top 5 (group)
        alerts_qs = (
            Alert.objects.filter(entrenador=request.user, equipo_id=group.id, status=Alert.Status.OPEN)
            .annotate(sev_order=_severity_order_case())
            .order_by("-sev_order", "-created_at", "-id")
        )[:5]
        alerts = [
            {
                "id": a.id,
                "athlete_id": a.alumno_id,
                "type": a.type,
                "severity": a.severity,
                "message": a.message,
                "recommended_action": a.recommended_action,
                "visto_por_coach": bool(a.visto_por_coach),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts_qs
        ]

        # Top 10 atletas en riesgo (score)
        latest_snaps = (
            InjuryRiskSnapshot.objects.filter(entrenador=request.user, alumno_id__in=athlete_ids, fecha__lte=end)
            .order_by("-fecha")
            .values("alumno_id", "alumno__nombre", "alumno__apellido", "risk_score", "risk_level", "fecha")
        )
        snap_by_athlete: dict[int, dict] = {}
        for r in latest_snaps.iterator(chunk_size=1000):
            aid = int(r["alumno_id"])
            if aid not in snap_by_athlete:
                snap_by_athlete[aid] = r

        alert_scores = (
            Alert.objects.filter(entrenador=request.user, alumno_id__in=athlete_ids, status=Alert.Status.OPEN)
            .annotate(sev_score=_severity_order_case())
            .values("alumno_id")
            .annotate(max_sev=Max("sev_score"))
        )
        sev_by_athlete = {int(r["alumno_id"]): float(r["max_sev"] or 0.0) for r in alert_scores}

        risk_list = []
        for aid, snap in snap_by_athlete.items():
            risk_score = int(snap.get("risk_score") or 0)
            sev = sev_by_athlete.get(aid, 0.0)
            risk_list.append(
                {
                    "athlete_id": aid,
                    "name": f"{snap.get('alumno__nombre') or ''} {snap.get('alumno__apellido') or ''}".strip(),
                    "risk_score": risk_score,
                    "risk_level": snap.get("risk_level"),
                    "risk_date": str(snap.get("fecha")),
                    "open_alert_severity_score": sev,
                    "severity_score": round((sev * 50.0) + risk_score, 1),
                }
            )
        risk_list.sort(key=lambda x: (x["severity_score"]), reverse=True)
        risk_list = risk_list[:10]

        return Response(
            {
                "group_id": group.id,
                "week": week,
                "range": {"start": str(start), "end": str(end)},
                "kpis": kpis,
                "pmc": pmc,
                "compliance": compliance,
                "alerts": alerts,
                "top_risk_athletes": risk_list,
            },
            status=200,
        )


class CoachAthleteAlertsListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=["open", "all"]),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=50),
        ]
    )
    def get(self, request, athlete_id: int):
        _require_athlete_for_coach(coach=request.user, athlete_id=int(athlete_id))
        status_param = (request.query_params.get("status") or "open").strip().lower()
        limit = int(request.query_params.get("limit") or 50)
        limit = max(1, min(limit, 200))

        qs = Alert.objects.filter(entrenador=request.user, alumno_id=int(athlete_id))
        if status_param != "all":
            qs = qs.filter(status=Alert.Status.OPEN)

        qs = qs.annotate(sev_order=_severity_order_case()).order_by("-sev_order", "-created_at", "-id")[:limit]
        items = [
            {
                "id": a.id,
                "type": a.type,
                "severity": a.severity,
                "status": a.status,
                "message": a.message,
                "recommended_action": a.recommended_action,
                "evidence_json": a.evidence_json,
                "visto_por_coach": bool(a.visto_por_coach),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in qs
        ]
        return Response(
            {"athlete_id": int(athlete_id), "status": status_param, "limit": limit, "results": items},
            status=200,
        )


class CoachAlertPatchView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={"visto_por_coach": openapi.Schema(type=openapi.TYPE_BOOLEAN)},
            required=["visto_por_coach"],
        )
    )
    def patch(self, request, alert_id: int):
        visto = request.data.get("visto_por_coach", None)
        if not isinstance(visto, bool):
            return Response({"detail": "visto_por_coach must be boolean"}, status=400)

        updated = (
            Alert.objects.filter(id=int(alert_id), entrenador=request.user)
            .update(visto_por_coach=bool(visto))
        )
        if not updated:
            return Response({"detail": "Not found"}, status=404)
        return Response({"id": int(alert_id), "visto_por_coach": bool(visto)}, status=200)
