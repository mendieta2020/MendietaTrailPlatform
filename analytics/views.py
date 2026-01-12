import logging
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.cache import get_range_cache, set_range_cache
from analytics.models import DailyActivityAgg
from analytics.pmc import get_pmc_for_range
from analytics.pmc_engine import PMC_SPORT_GROUPS, ensure_pmc_materialized
from analytics.range_utils import max_range_days, parse_date_range_params
from core.models import Actividad, Alumno, Entrenamiento, InscripcionCarrera

from analytics.models import AlertaRendimiento
from analytics.serializers import AlertaRendimientoSerializer
from analytics.pagination import OptionalPageNumberPagination

logger = logging.getLogger(__name__)

class PMCDataView(APIView):
    """
    API Científica 6.0 (Full Elite Data - Sanitized).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")
        try:
            user = request.user
            alumno_id = request.query_params.get("alumno_id")
            sport_filter = (request.query_params.get("sport") or "ALL").upper().strip()
            sport_filter = sport_filter if sport_filter in {"ALL", "RUN", "BIKE"} else "ALL"

            is_athlete = hasattr(user, "perfil_alumno")

            if is_athlete:
                alumno_id = user.perfil_alumno.id
            else:
                if not alumno_id:
                    alumno_id = (
                        Actividad.objects.filter(alumno__entrenador=user)
                        .values_list("alumno_id", flat=True)
                        .order_by("-fecha_inicio")
                        .first()
                        or Entrenamiento.objects.filter(alumno__entrenador=user).values_list("alumno_id", flat=True).first()
                    )
                    if not alumno_id:
                        return Response([], status=200)

                # 🔒 Validación anti fuga
                if not Alumno.objects.filter(id=alumno_id, entrenador=user).exists():
                    return Response([], status=200)

            alumno_id = int(alumno_id)

            try:
                start_date, end_date, _ = parse_date_range_params(
                    start_param,
                    end_param,
                    default_days=365,
                    enforce_max_for_custom=True,
                )
            except ValueError as exc:
                reason = str(exc)
                if reason == "start_end_required":
                    return Response({"detail": "start_date and end_date must be provided together."}, status=400)
                if reason == "start_after_end":
                    return Response({"detail": "start_date must be before end_date."}, status=400)
                if reason == "range_too_large":
                    return Response(
                        {"detail": "Requested range too large.", "max_days": max_range_days()},
                        status=400,
                    )
                return Response({"detail": "Invalid date range."}, status=400)

            cached = get_range_cache(
                cache_type="PMC",
                alumno_id=alumno_id,
                sport=sport_filter,
                start_date=start_date,
                end_date=end_date,
            )
            if cached is not None:
                return Response(cached, status=status.HTTP_200_OK)

            data = get_pmc_for_range(
                alumno_id=alumno_id,
                sport_filter=sport_filter,
                start_date=start_date,
                end_date=end_date,
                user=user,
                is_athlete=is_athlete,
            )
            set_range_cache(
                cache_type="PMC",
                alumno_id=alumno_id,
                sport=sport_filter,
                start_date=start_date,
                end_date=end_date,
                payload=data,
            )
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("analytics.pmc.error", extra={"error": str(e)})
            # Devolvemos array vacío para NO ROMPER el frontend
            return Response([], status=status.HTTP_200_OK)


class AnalyticsSummaryView(APIView):
    """
    GET /api/analytics/summary/?alumno_id=<id>
    Resumen rápido (km/desnivel) 7d/28d + últimos días (para widgets).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        alumno_id = request.query_params.get("alumno_id")
        is_athlete = hasattr(user, "perfil_alumno")

        if is_athlete:
            alumno_id = user.perfil_alumno.id
        else:
            if not alumno_id:
                alumno_id = (
                    Actividad.objects.filter(alumno__entrenador=user)
                    .values_list("alumno_id", flat=True)
                    .order_by("-fecha_inicio")
                    .first()
                )
                if not alumno_id:
                    return Response({"alumno_id": None, "ranges": {}, "last_days": []}, status=200)
            if not Alumno.objects.filter(id=alumno_id, entrenador=user).exists():
                return Response({"alumno_id": None, "ranges": {}, "last_days": []}, status=200)

        alumno_id = int(alumno_id)
        ensure_pmc_materialized(alumno_id=alumno_id)

        today = timezone.localdate()
        start_28 = today - timedelta(days=27)
        start_7 = today - timedelta(days=6)

        base = DailyActivityAgg.objects.filter(
            alumno_id=alumno_id,
            fecha__range=[start_28, today],
            sport__in=list(PMC_SPORT_GROUPS["ALL"]),
        ).values("fecha", "distance_m", "elev_gain_m", "duration_s", "load")

        by_day = {}
        for r in base.iterator(chunk_size=1000):
            d = r["fecha"]
            prev = by_day.get(d) or {"distance_m": 0.0, "elev_gain_m": 0.0, "duration_s": 0, "load": 0.0}
            prev["distance_m"] += float(r.get("distance_m") or 0.0)
            prev["elev_gain_m"] += float(r.get("elev_gain_m") or 0.0)
            prev["duration_s"] += int(r.get("duration_s") or 0)
            prev["load"] += float(r.get("load") or 0.0)
            by_day[d] = prev

        def rollup(start_d: date) -> dict:
            days = [start_d + timedelta(days=i) for i in range((today - start_d).days + 1)]
            dist_m = sum((by_day.get(d) or {}).get("distance_m", 0.0) for d in days)
            elev_m = sum((by_day.get(d) or {}).get("elev_gain_m", 0.0) for d in days)
            dur_s = sum((by_day.get(d) or {}).get("duration_s", 0) for d in days)
            load = sum((by_day.get(d) or {}).get("load", 0.0) for d in days)
            return {
                "km": round(float(dist_m) / 1000.0, 2),
                "elev_gain_m": int(round(float(elev_m))),
                "time_min": int(round(float(dur_s) / 60.0)),
                "load": int(round(float(load))),
            }

        last_days = []
        for i in range(14):  # últimos 14 días para widgets
            d = today - timedelta(days=i)
            v = by_day.get(d) or {"distance_m": 0.0, "elev_gain_m": 0.0, "duration_s": 0, "load": 0.0}
            last_days.append(
                {
                    "fecha": d.isoformat(),
                    "km": round(float(v["distance_m"]) / 1000.0, 2),
                    "elev_gain_m": int(round(float(v["elev_gain_m"]))),
                    "time_min": int(round(float(v["duration_s"]) / 60.0)),
                    "load": int(round(float(v["load"]))),
                }
            )
        last_days.reverse()

        return Response(
            {
                "alumno_id": alumno_id,
                "ranges": {"7d": rollup(start_7), "28d": rollup(start_28)},
                "last_days": last_days,
            },
            status=200,
        )


class AlertaRendimientoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/analytics/alerts/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AlertaRendimientoSerializer
    pagination_class = OptionalPageNumberPagination
    queryset = AlertaRendimiento.objects.select_related("alumno").order_by("-fecha", "-id")

    def list(self, request, *args, **kwargs):
        """
        Opt-in pagination:
        - legacy: sin `page` ni `page_size` => lista JSON plana (compatibilidad)
        - con `page` o `page_size` => respuesta paginada DRF estándar
        """
        qp = request.query_params
        if "page" not in qp and "page_size" not in qp:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Fallback defensivo (no debería ocurrir porque la paginación se activa con qp)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        qs = super().get_queryset()

        if getattr(self, "swagger_fake_view", False):
            return qs.none()

        user = self.request.user
        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()

        # 🔒 Multi-tenant fail-closed (sin romper compatibilidad):
        # - Superuser: ve todo
        # - Atleta (perfil_alumno): ve solo sus alertas
        # - Coach: ve alertas de sus alumnos (alumno.entrenador) y/o de equipos a su nombre (alumno.equipo.entrenador)
        if not getattr(user, "is_superuser", False):
            if hasattr(user, "perfil_alumno") and getattr(user, "perfil_alumno", None):
                qs = qs.filter(alumno__usuario=user)
            else:
                # En este proyecto el "tenant" es el coach (User)
                qs = qs.filter(Q(alumno__entrenador=user) | Q(alumno__equipo__entrenador=user))

        # Filtros por querystring
        alumno_id = self.request.query_params.get("alumno_id")
        if alumno_id:
            try:
                qs = qs.filter(alumno_id=int(alumno_id))
            except (TypeError, ValueError):
                logger.warning(
                    "analytics.alerts.invalid_param",
                    extra={"param": "alumno_id", "value": str(alumno_id), "user_id": getattr(user, "id", None)},
                )
                pass

        visto = self.request.query_params.get("visto_por_coach")
        if visto is not None:
            visto_l = str(visto).strip().lower()
            if visto_l in {"true", "1", "yes"}:
                qs = qs.filter(visto_por_coach=True)
            elif visto_l in {"false", "0", "no"}:
                qs = qs.filter(visto_por_coach=False)

        fecha_gte = self.request.query_params.get("fecha_gte")
        if fecha_gte:
            try:
                qs = qs.filter(fecha__gte=date.fromisoformat(fecha_gte))
            except ValueError:
                logger.warning(
                    "analytics.alerts.invalid_param",
                    extra={"param": "fecha_gte", "value": str(fecha_gte), "user_id": getattr(user, "id", None)},
                )
                pass

        fecha_lte = self.request.query_params.get("fecha_lte")
        if fecha_lte:
            try:
                qs = qs.filter(fecha__lte=date.fromisoformat(fecha_lte))
            except ValueError:
                logger.warning(
                    "analytics.alerts.invalid_param",
                    extra={"param": "fecha_lte", "value": str(fecha_lte), "user_id": getattr(user, "id", None)},
                )
                pass

        return qs
