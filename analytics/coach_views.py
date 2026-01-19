from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db.models import Avg, Case, Count, ExpressionWrapper, F, FloatField, Max, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.settings import api_settings

from analytics.cache import is_cache_fresh, set_range_cache
from analytics.models import AlertaRendimiento, Alert, AnalyticsRangeCache, DailyActivityAgg, InjuryRiskSnapshot, PMCHistory
from analytics.pagination import CoachPlanningPagination
from analytics.serializers import AlertaRendimientoSerializer
from analytics.pmc_engine import PMC_SPORT_GROUPS, _normalize_business_sport, ensure_pmc_materialized
from analytics.range_utils import max_range_days, parse_date_range_params, parse_iso_week_param
from core.models import Actividad, Alumno, Entrenamiento
from core.serializers import PlanningSessionSerializer, PlanningSessionWriteSerializer
from core.tenancy import CoachTenantAPIViewMixin

logger = logging.getLogger(__name__)


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
    sessions_by_type = _sessions_by_type(athlete_id=athlete_id, start=start, end=end)
    qs = (
        DailyActivityAgg.objects.filter(alumno_id=int(athlete_id), fecha__range=[start, end])
        .values("sport")
        .annotate(
            distance_m=Coalesce(Sum("distance_m"), Value(0.0), output_field=FloatField()),
            duration_s=Coalesce(Sum("duration_s"), Value(0.0), output_field=FloatField()),
            elev_gain_m=Coalesce(Sum("elev_gain_m"), Value(0.0), output_field=FloatField()),
            elev_loss_m=Coalesce(Sum("elev_loss_m"), Value(0.0), output_field=FloatField()),
            elev_total_m=Coalesce(Sum("elev_total_m"), Value(0.0), output_field=FloatField()),
            calories_kcal=Coalesce(Sum("calories_kcal"), Value(0.0), output_field=FloatField()),
        )
        .order_by("sport")
    )
    totals = {}
    for row in qs:
        distance_m = float(row["distance_m"] or 0.0)
        duration_s = float(row["duration_s"] or 0.0)
        elev_gain_m = float(row["elev_gain_m"] or 0.0)
        elev_loss_m = float(row["elev_loss_m"] or 0.0)
        elev_total_m = float(row["elev_total_m"] or (elev_gain_m + elev_loss_m))
        calories_kcal = float(row["calories_kcal"] or 0.0)
        sport = row["sport"]
        totals[sport] = {
            "distance_km": round(distance_m / 1000.0, 2),
            "duration_minutes": int(round(duration_s / 60.0)),
            "kcal": int(round(calories_kcal)),
            "elevation_gain_m": int(round(elev_gain_m)),
            "elevation_loss_m": int(round(elev_loss_m)),
            "elevation_total_m": int(round(elev_total_m)),
            "sessions_count": int(sessions_by_type.get(sport, 0)),
        }
    return totals


_DISTANCE_SPORTS = {"RUN", "TRAIL", "BIKE", "WALK"}
_NON_DISTANCE_SPORTS = {"STRENGTH", "FUNCTIONAL", "WORKOUT", "CARDIO", "OTHER"}


def _normalize_summary_sport(raw_sport: str | None) -> str:
    st = str(raw_sport or "").strip().upper()
    if st in _NON_DISTANCE_SPORTS:
        return st
    return _normalize_business_sport(st)


def _sessions_by_summary_sport(*, athlete_id: int, start: date, end: date) -> dict[str, int]:
    qs = (
        Actividad.objects.filter(
            alumno_id=int(athlete_id),
            validity=Actividad.Validity.VALID,
            fecha_inicio__date__range=[start, end],
        )
        .values("tipo_deporte")
        .annotate(count=Count("id"))
    )
    sessions: dict[str, int] = {}
    for row in qs:
        sport = _normalize_summary_sport(row["tipo_deporte"])
        sessions[sport] = sessions.get(sport, 0) + int(row["count"] or 0)
    return sessions


def _per_sport_totals(*, athlete_id: int, start: date, end: date) -> dict[str, dict]:
    sessions_by_type = _sessions_by_summary_sport(athlete_id=athlete_id, start=start, end=end)
    qs = (
        DailyActivityAgg.objects.filter(alumno_id=int(athlete_id), fecha__range=[start, end])
        .values("sport")
        .annotate(
            distance_m=Coalesce(Sum("distance_m"), Value(0.0), output_field=FloatField()),
            duration_s=Coalesce(Sum("duration_s"), Value(0.0), output_field=FloatField()),
            elev_gain_m=Coalesce(Sum("elev_gain_m"), Value(0.0), output_field=FloatField()),
            elev_loss_m=Coalesce(Sum("elev_loss_m"), Value(0.0), output_field=FloatField()),
            elev_total_m=Coalesce(Sum("elev_total_m"), Value(0.0), output_field=FloatField()),
            calories_kcal=Coalesce(Sum("calories_kcal"), Value(0.0), output_field=FloatField()),
            load=Coalesce(Sum("load"), Value(0.0), output_field=FloatField()),
        )
        .order_by("sport")
    )
    totals: dict[str, dict] = {}
    for row in qs:
        sport = row["sport"]
        duration_s = float(row["duration_s"] or 0.0)
        calories_kcal = float(row["calories_kcal"] or 0.0)
        load = float(row["load"] or 0.0)
        payload = {
            "sessions": int(sessions_by_type.get(sport, 0)),
            "duration_s": int(round(duration_s)),
            "duration_minutes": int(round(duration_s / 60.0)),
            "calories_kcal": int(round(calories_kcal)),
            "load": round(load, 2),
        }
        if sport in _DISTANCE_SPORTS:
            distance_m = float(row["distance_m"] or 0.0)
            elev_gain_m = float(row["elev_gain_m"] or 0.0)
            elev_loss_m = float(row["elev_loss_m"] or 0.0)
            elev_total_m = float(row["elev_total_m"] or (elev_gain_m + elev_loss_m))
            payload.update(
                {
                    "distance_km": round(distance_m / 1000.0, 2),
                    "elevation_gain_m": int(round(elev_gain_m)),
                    "elevation_loss_m": int(round(elev_loss_m)),
                    "elevation_total_m": int(round(elev_total_m)),
                }
            )
        totals[sport] = payload
    for sport in _NON_DISTANCE_SPORTS:
        if sport not in totals:
            totals[sport] = {
                "sessions": int(sessions_by_type.get(sport, 0)),
                "duration_s": 0,
                "duration_minutes": 0,
                "calories_kcal": 0,
                "load": 0.0,
            }
    return totals


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


def _alert_queryset_for_user(user):
    """
    Coach-scoped alert queryset. Fail-closed:
    - superuser/staff => all alerts
    - athlete profile => only own alerts
    - coach => alerts for athletes owned by that coach
    """
    qs = Alert.objects.select_related("alumno")
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return qs
    if hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None):
        return qs.filter(alumno=user.perfil_alumno)
    return qs.filter(alumno__entrenador=user)


def _performance_alert_queryset_for_user(user):
    """
    Coach-scoped performance alert queryset (AlertaRendimiento). Fail-closed:
    - superuser/staff => all alerts
    - athlete profile => only own alerts
    - coach => alerts for athletes owned by that coach
    """
    qs = AlertaRendimiento.objects.select_related("alumno")
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return qs
    if hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None):
        return qs.filter(alumno=user.perfil_alumno)
    return qs.filter(alumno__entrenador=user)


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
        elev_loss_m=Sum("elev_loss_m"),
        elev_total_m=Sum("elev_total_m"),
        calories_kcal=Sum("calories_kcal"),
    )
    sessions_count = activities.count()

    duration_s = float(agg["duration_s"] or 0.0)
    distance_m = float(agg["distance_m"] or 0.0)
    elev_gain_m = float(agg["elev_gain_m"] or 0.0)
    elev_loss_m = float(agg["elev_loss_m"] or 0.0)
    elev_total_m = float(agg["elev_total_m"] or (elev_gain_m + elev_loss_m))
    calories_kcal = float(agg["calories_kcal"] or 0.0)

    distance_km = round(distance_m / 1000.0, 2)
    duration_minutes = int(round(duration_s / 60.0))
    elevation_gain_m = int(round(elev_gain_m))
    elevation_loss_m = int(round(elev_loss_m))
    kcal = int(round(calories_kcal))
    elevation_total_m = int(round(elev_total_m))
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
        "total_elevation_total_m": elevation_total_m,
        "total_calories": kcal,
        "total_calories_kcal": kcal,
        "sessions_count": int(sessions_count),
        "sessions_by_type": _sessions_by_type(athlete_id=athlete_id, start=start, end=end),
        "totals_by_type": _totals_by_type(athlete_id=athlete_id, start=start, end=end),
        "per_sport_totals": _per_sport_totals(athlete_id=athlete_id, start=start, end=end),
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


_PLANNING_DEFAULT_DAYS = 42
_PLANNING_MAX_DAYS = 84


def _get_request_id(request) -> str | None:
    meta = getattr(request, "META", {}) or {}
    return meta.get("HTTP_X_REQUEST_ID") or meta.get("HTTP_X_CORRELATION_ID")


def _parse_planning_range(request) -> tuple[date, date]:
    start_param = request.query_params.get("from")
    end_param = request.query_params.get("to")
    if start_param or end_param:
        if not (start_param and end_param):
            raise ValueError("from_to_required")
        start = date.fromisoformat(str(start_param))
        end = date.fromisoformat(str(end_param))
    else:
        end = timezone.localdate()
        start = end - timedelta(days=_PLANNING_DEFAULT_DAYS - 1)
    if start > end:
        raise ValueError("start_after_end")
    range_days = (end - start).days + 1
    if range_days > _PLANNING_MAX_DAYS:
        raise ValueError("range_too_large")
    return start, end


def _build_compliance_summary(*, athlete_id: int, start: date, end: date) -> dict:
    plan_qs = Entrenamiento.objects.filter(alumno_id=int(athlete_id), fecha_asignada__range=[start, end])
    plan_agg = plan_qs.aggregate(
        duration_min=Coalesce(Sum("tiempo_planificado_min"), Value(0.0), output_field=FloatField()),
        distance_km=Coalesce(Sum("distancia_planificada_km"), Value(0.0), output_field=FloatField()),
        elev_m=Coalesce(Sum("desnivel_planificado_m"), Value(0.0), output_field=FloatField()),
    )
    plan_load_qs = plan_qs.filter(tiempo_planificado_min__isnull=False).annotate(
        load=ExpressionWrapper(
            F("tiempo_planificado_min") * (Value(1.0) + (F("rpe_planificado") / Value(10.0))),
            output_field=FloatField(),
        )
    )
    plan_load = plan_load_qs.aggregate(v=Coalesce(Sum("load"), Value(0.0), output_field=FloatField())).get("v") or 0.0

    actual_agg = DailyActivityAgg.objects.filter(alumno_id=int(athlete_id), fecha__range=[start, end]).aggregate(
        duration_s=Coalesce(Sum("duration_s"), Value(0.0), output_field=FloatField()),
        distance_m=Coalesce(Sum("distance_m"), Value(0.0), output_field=FloatField()),
        elev_gain_m=Coalesce(Sum("elev_gain_m"), Value(0.0), output_field=FloatField()),
        load=Coalesce(Sum("load"), Value(0.0), output_field=FloatField()),
    )

    planned_totals = {
        "duration_s": int(round(float(plan_agg["duration_min"] or 0.0) * 60.0)),
        "distance_m": int(round(float(plan_agg["distance_km"] or 0.0) * 1000.0)),
        "elev_pos_m": int(round(float(plan_agg["elev_m"] or 0.0))),
        "load": round(float(plan_load or 0.0), 2),
    }
    actual_totals = {
        "duration_s": int(round(float(actual_agg["duration_s"] or 0.0))),
        "distance_m": int(round(float(actual_agg["distance_m"] or 0.0))),
        "elev_pos_m": int(round(float(actual_agg["elev_gain_m"] or 0.0))),
        "load": round(float(actual_agg["load"] or 0.0), 2),
    }

    deltas = {}
    compliance_pct = {}
    for key in planned_totals:
        planned_value = float(planned_totals[key])
        actual_value = float(actual_totals[key])
        deltas[key] = round(actual_value - planned_value, 2)
        if planned_value <= 0:
            compliance_pct[key] = 0.0
        else:
            compliance_pct[key] = round((actual_value / planned_value) * 100.0, 1)

    return {
        "planned_totals": planned_totals,
        "actual_totals": actual_totals,
        "deltas": deltas,
        "compliance_pct": compliance_pct,
        "top_anomalies": [],
        "data_source": {
            "planned": "entrenamiento",
            "actual": "daily_activity_agg",
            "generated_at": timezone.now().isoformat(),
        },
    }


class CoachAthleteWeekSummaryView(CoachTenantAPIViewMixin, APIView):
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
          "total_elevation_total_m": 5594,
          "total_calories_kcal": 8500,
          "sessions_count": 6,
          "sessions_by_type": {"RUN": 4, "BIKE": 1, "STRENGTH": 1},
          "totals_by_type": {"RUN": {"distance_km": 90, ...}},
          "per_sport_totals": {"RUN": {"distance_km": 90, "duration_minutes": 420, "load": 450.5}},
          "pmc": {"fitness": 52.1, "fatigue": 61.4, "form": -9.3, "date": "2026-01-18"},
          "compliance": {"duration": {...}, "distance": {...}, "elev": {...}, "load": {...}},
          "alerts": [...]
        }
        """
        # Nota: devolvemos 401 si falta auth; 404 si el atleta no pertenece al coach autenticado.
        athlete = self.require_athlete(request, athlete_id)
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

        daily_qs = DailyActivityAgg.objects.filter(alumno_id=athlete.id, fecha__range=[start, end])
        latest_daily_update = daily_qs.aggregate(latest=Max("updated_at")).get("latest")
        cache_record = (
            AnalyticsRangeCache.objects.filter(
                cache_type="WEEK_SUMMARY",
                alumno_id=athlete.id,
                sport="ALL",
                start_date=start,
                end_date=end,
            )
            .only("payload", "last_computed_at")
            .first()
        )
        cached_core = None
        if cache_record and is_cache_fresh(cache_record):
            if not latest_daily_update or cache_record.last_computed_at >= latest_daily_update:
                cached_core = cache_record.payload

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


class CoachAthletePlanningView(CoachTenantAPIViewMixin, generics.GenericAPIView):
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES
    pagination_class = CoachPlanningPagination

    def get_serializer_class(self):
        if self.request.method == "GET":
            return PlanningSessionSerializer
        return PlanningSessionWriteSerializer

    def get(self, request, athlete_id: int):
        athlete = self.require_athlete(request, athlete_id)
        try:
            start, end = _parse_planning_range(request)
        except ValueError as exc:
            reason = str(exc)
            if reason == "from_to_required":
                return Response({"detail": "from and to must be provided together."}, status=400)
            if reason == "start_after_end":
                return Response({"detail": "from must be before to."}, status=400)
            if reason == "range_too_large":
                return Response({"detail": "Requested range too large.", "max_days": _PLANNING_MAX_DAYS}, status=400)
            return Response({"detail": "Invalid date range."}, status=400)

        qs = (
            Entrenamiento.objects.filter(alumno_id=athlete.id, fecha_asignada__range=[start, end])
            .select_related("alumno")
            .order_by("fecha_asignada", "id")
        )
        page = self.paginate_queryset(qs)
        serializer = PlanningSessionSerializer(page, many=True, context={"request": request})
        response = self.get_paginated_response(serializer.data)
        response.data["version"] = "v1"
        response.data["athlete_id"] = athlete.id
        response.data["from"] = str(start)
        response.data["to"] = str(end)
        return response

    def post(self, request, athlete_id: int):
        athlete = self.require_athlete(request, athlete_id)
        data = request.data.copy()
        if "alumno" in data and str(data.get("alumno")) != str(athlete.id):
            return Response({"detail": "alumno must match athlete in path."}, status=400)
        data["alumno"] = athlete.id
        serializer = PlanningSessionWriteSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        planned = serializer.save()
        logger.info(
            "coach.planning.create",
            extra={
                "coach_id": request.user.id,
                "athlete_id": athlete.id,
                "planned_id": planned.id,
                "request_id": _get_request_id(request),
            },
        )
        out = PlanningSessionSerializer(planned, context={"request": request}).data
        return Response({"version": "v1", "data": out}, status=status.HTTP_201_CREATED)


class CoachPlanningDetailView(CoachTenantAPIViewMixin, APIView):
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def patch(self, request, planned_id: int):
        user = request.user
        qs = Entrenamiento.objects.select_related("alumno")
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            qs = qs.filter(alumno__entrenador=user)
        planned = get_object_or_404(qs, id=int(planned_id))
        data = request.data.copy()
        if "alumno" in data and str(data.get("alumno")) != str(planned.alumno_id):
            return Response({"detail": "alumno cannot be changed."}, status=400)
        serializer = PlanningSessionWriteSerializer(planned, data=data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        planned = serializer.save(alumno=planned.alumno)
        logger.info(
            "coach.planning.update",
            extra={
                "coach_id": request.user.id,
                "athlete_id": planned.alumno_id,
                "planned_id": planned.id,
                "request_id": _get_request_id(request),
            },
        )
        out = PlanningSessionSerializer(planned, context={"request": request}).data
        return Response({"version": "v1", "data": out}, status=200)


class CoachAthleteComplianceSummaryView(CoachTenantAPIViewMixin, APIView):
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def get(self, request, athlete_id: int):
        athlete = self.require_athlete(request, athlete_id)
        try:
            start, end = _parse_planning_range(request)
        except ValueError as exc:
            reason = str(exc)
            if reason == "from_to_required":
                return Response({"detail": "from and to must be provided together."}, status=400)
            if reason == "start_after_end":
                return Response({"detail": "from must be before to."}, status=400)
            if reason == "range_too_large":
                return Response({"detail": "Requested range too large.", "max_days": _PLANNING_MAX_DAYS}, status=400)
            return Response({"detail": "Invalid date range."}, status=400)

        summary = _build_compliance_summary(athlete_id=athlete.id, start=start, end=end)
        logger.info(
            "coach.compliance.summary",
            extra={
                "coach_id": request.user.id,
                "athlete_id": athlete.id,
                "date_range": {"from": str(start), "to": str(end)},
                "request_id": _get_request_id(request),
            },
        )
        return Response(
            {
                "version": "v1",
                "athlete_id": athlete.id,
                "from": str(start),
                "to": str(end),
                **summary,
            },
            status=200,
        )


class CoachGroupWeekSummaryView(CoachTenantAPIViewMixin, APIView):
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("week", openapi.IN_QUERY, type=openapi.TYPE_STRING, description="ISO week YYYY-Www"),
        ]
    )
    def get(self, request, group_id: int):
        group = self.require_group(request, group_id)
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
            elev_gain_m=Sum("elev_gain_m"),
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


class CoachAthleteAlertsListView(CoachTenantAPIViewMixin, APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter("status", openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=["open", "all"]),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=50),
        ]
    )
    def get(self, request, athlete_id: int):
        athlete = self.require_athlete(request, athlete_id)
        status_param = (request.query_params.get("status") or "open").strip().lower()
        limit = int(request.query_params.get("limit") or 50)
        limit = max(1, min(limit, 200))

        qs = _performance_alert_queryset_for_user(request.user).filter(alumno_id=athlete.id)

        if status_param not in {"open", "all"}:
            status_param = "open"

        qs = qs.order_by("-fecha", "-id")[:limit]
        items = AlertaRendimientoSerializer(qs, many=True).data
        return Response(
            {"athlete_id": athlete.id, "status": status_param, "limit": limit, "results": items},
            status=200,
        )


class CoachAlertPatchView(CoachTenantAPIViewMixin, APIView):
    """
    PATCH visto_por_coach for a coach-scoped alert.
    Cross-tenant access returns 404 to avoid leaking existence.
    """

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

        alert = _alert_queryset_for_user(request.user).filter(id=int(alert_id)).first()
        if alert is not None:
            alert.visto_por_coach = bool(visto)
            alert.save(update_fields=["visto_por_coach"])
            return Response({"id": alert.id, "visto_por_coach": alert.visto_por_coach}, status=200)

        perf_alert = _performance_alert_queryset_for_user(request.user).filter(id=int(alert_id)).first()
        if perf_alert is None:
            return Response({"detail": "Not found."}, status=404)
        perf_alert.visto_por_coach = bool(visto)
        perf_alert.save(update_fields=["visto_por_coach"])
        return Response({"id": perf_alert.id, "visto_por_coach": perf_alert.visto_por_coach}, status=200)
