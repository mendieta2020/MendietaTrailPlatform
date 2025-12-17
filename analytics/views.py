from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.permissions import IsAuthenticated
from core.models import Entrenamiento, Alumno, InscripcionCarrera
from django.utils import timezone
from django.db.models import Q
import logging
import pandas as pd
import numpy as np
from datetime import date, timedelta

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
        try:
            # 1. IDENTIFICACIÓN
            user = request.user
            alumno_id = request.query_params.get('alumno_id')
            sport_filter = request.query_params.get('sport')

            is_athlete = hasattr(user, "perfil_alumno")

            # Atleta: siempre forzamos su propio alumno_id
            if is_athlete:
                alumno_id = user.perfil_alumno.id
            else:
                # Coach: si no elige alumno, usamos el primero de su tenant
                if not alumno_id:
                    first_active = Entrenamiento.objects.filter(alumno__entrenador=user).first()
                    if first_active:
                        alumno_id = first_active.alumno_id
                    else:
                        return Response([], status=200)

                # 🔒 Validación anti fuga: el alumno_id debe pertenecer al coach autenticado
                if not Alumno.objects.filter(id=alumno_id, entrenador=user).exists():
                    # No devolvemos 403/404 para no romper UX existente: devolvemos vacío
                    return Response([], status=200)

            # 2. QUERYSET
            filters = {'alumno_id': alumno_id}
            if sport_filter and sport_filter != 'ALL':
                if sport_filter == 'RUN': filters['tipo_actividad__in'] = ['RUN', 'TRAIL']
                elif sport_filter == 'BIKE': filters['tipo_actividad__in'] = ['BIKE', 'MTB', 'INDOOR_BIKE', 'CYCLING']
                elif sport_filter == 'STRENGTH': filters['tipo_actividad'] = 'STRENGTH'
                else: filters['tipo_actividad'] = sport_filter

            # 🔒 Scoping por tenant: atleta ve solo lo suyo, coach solo de sus alumnos
            base_qs = Entrenamiento.objects.all()
            if is_athlete:
                base_qs = base_qs.filter(alumno__usuario=user)
            else:
                base_qs = base_qs.filter(alumno__entrenador=user)

            qs = base_qs.filter(**filters).values(
                'fecha_asignada', 'tiempo_planificado_min', 'tiempo_real_min', 
                'distancia_planificada_km', 'distancia_real_km',
                'desnivel_planificado_m', 'desnivel_real_m',
                'rpe', 'rpe_planificado', 'completado', 'tipo_actividad'
            )

            objetivos_base = InscripcionCarrera.objects.all()
            if is_athlete:
                objetivos_base = objetivos_base.filter(alumno__usuario=user)
            else:
                objetivos_base = objetivos_base.filter(alumno__entrenador=user)

            objetivos_qs = objetivos_base.filter(alumno_id=alumno_id).select_related('carrera').values(
                'carrera__fecha', 'carrera__nombre', 'carrera__distancia_km', 'carrera__desnivel_positivo_m'
            )

            if not qs.exists(): return Response([], status=200)

            # 3. PANDAS ENGINE
            df = pd.DataFrame(list(qs))
            df['fecha_asignada'] = pd.to_datetime(df['fecha_asignada'])

            # Limpieza Inicial (NaN -> 0)
            cols_num = ['tiempo_planificado_min', 'tiempo_real_min', 'distancia_planificada_km', 'distancia_real_km', 'desnivel_planificado_m', 'desnivel_real_m', 'rpe', 'rpe_planificado']
            for col in cols_num:
                if col not in df.columns: df[col] = 0.0
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            # --- CÁLCULOS ---
            df['rpe_real'] = np.where(df['rpe'] > 0, df['rpe'], 4.0)
            df['real_load'] = np.where(df['completado'], df['tiempo_real_min'] * df['rpe_real'], 0.0)
            df['plan_load'] = df['tiempo_planificado_min'] * np.where(df['rpe_planificado'] > 0, df['rpe_planificado'], 6.0)

            df['real_dist'] = np.where(df['completado'], df['distancia_real_km'], 0.0)
            df['plan_dist'] = df['distancia_planificada_km']
            df['real_time'] = np.where(df['completado'], df['tiempo_real_min'], 0.0)
            df['plan_time'] = df['tiempo_planificado_min']
            
            df['real_elev'] = np.where(df['completado'], df['desnivel_real_m'], 0.0)
            df['plan_elev'] = df['desnivel_planificado_m']
            
            # Desnivel Negativo (Estimado)
            df['elev_loss'] = np.where((df['tipo_actividad'].isin(['TRAIL', 'RUN'])) & df['completado'], df['real_elev'], 0.0)
            
            # Calorías
            df['calories'] = np.where(df['completado'], (df['tiempo_real_min'] * df['rpe_real'] * 1.5), 0.0)

            # Agrupación
            df_daily = df.groupby('fecha_asignada').sum(numeric_only=True).reset_index()
            df_daily.set_index('fecha_asignada', inplace=True)

            # Reindexado
            start_date = timezone.now().date() - timedelta(days=365)
            end_date = timezone.now().date() + timedelta(days=180)
            idx = pd.date_range(start=start_date, end=end_date)
            df_daily = df_daily.reindex(idx, fill_value=0.0)

            # Banister
            df_daily['ctl'] = df_daily['real_load'].ewm(span=42, adjust=False).mean()
            df_daily['atl'] = df_daily['real_load'].ewm(span=7, adjust=False).mean()
            df_daily['tsb'] = df_daily['ctl'] - df_daily['atl']

            # Serialización
            objetivos_map = {obj['carrera__fecha'].strftime('%Y-%m-%d'): {"nombre": obj['carrera__nombre'], "km": obj['carrera__distancia_km'], "elev": obj['carrera__desnivel_positivo_m']} for obj in objetivos_qs}
            
            cutoff_date = pd.Timestamp(timezone.now().date() - timedelta(days=365))
            df_final = df_daily[df_daily.index >= cutoff_date]

            data = []
            today = timezone.now().date()

            for fecha, row in df_final.iterrows():
                f_str = fecha.strftime('%Y-%m-%d')
                is_future = fecha.date() > today
                
                data.append({
                    "fecha": f_str,
                    "is_future": is_future,
                    "ctl": round(float(row['ctl']), 1) if not is_future else 0,
                    "atl": round(float(row['atl']), 1) if not is_future else 0,
                    "tsb": round(float(row['tsb']), 1) if not is_future else 0,
                    "load": int(row['plan_load']) if is_future else int(row['real_load']),
                    "dist": round(float(row['plan_dist']), 1) if is_future else round(float(row['real_dist']), 1),
                    "time": int(row['plan_time']) if is_future else int(row['real_time']),
                    "elev_gain": int(row['plan_elev']) if is_future else int(row['real_elev']),
                    "elev_loss": int(row['elev_loss']), 
                    "calories": int(row['calories']),
                    "race": objetivos_map.get(f_str, None)
                })

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"❌ Analytics Error: {str(e)}")
            # Devolvemos array vacío para NO ROMPER el frontend
            return Response([], status=status.HTTP_200_OK)


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
        user = self.request.user
        qs = super().get_queryset()

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