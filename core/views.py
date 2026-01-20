import logging

from rest_framework import viewsets, permissions, filters, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser # <--- CRÍTICO PARA SUBIR VIDEOS
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from datetime import datetime, date as date_type, timedelta
from django.db.models import Prefetch, Max
from django.db.models import Q
from django.utils import timezone

# Importamos Modelos
from .models import (
    Alumno, Entrenamiento, Actividad, 
    PlantillaEntrenamiento, Carrera, 
    InscripcionCarrera, Pago,
    Equipo, VideoEjercicio,
    PlantillaEntrenamientoVersion,
)
from analytics.models import InjuryRiskSnapshot
from analytics.serializers import InjuryRiskSnapshotSerializer

# Permisos multi-tenant (coach-scoped)
from .permissions import IsCoachUser
from .tenancy import require_athlete_for_user

# Importamos Serializadores
from .serializers import (
    AlumnoSerializer, EntrenamientoSerializer,
    PlantillaEntrenamientoSerializer, CarreraSerializer,
    InscripcionCarreraSerializer, PagoSerializer,
    EquipoSerializer, VideoEjercicioSerializer, ActividadSerializer, ActividadRawPayloadSerializer # <--- NUEVO SERIALIZER IMPORTADO
)

from allauth.socialaccount.models import SocialToken
from .services import sincronizar_actividades_strava, asignar_plantilla_a_alumno
from .filters import ActividadFilter

logger = logging.getLogger(__name__)
# ==============================================================================
#  API REST (EL CEREBRO DE LA APP MÓVIL 📱)
# ==============================================================================

# ==============================================================================
#  MULTI-TENANT BASE (Semana 1 - Hardening)
# ==============================================================================
class TenantModelViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet con aislamiento multi-tenant automático.

    Reglas:
    - Staff: ve todo.
    - Alumno (User con `perfil_alumno`): filtra por `usuario=user` o `alumno__usuario=user`.
    - Coach (resto): filtra por `entrenador=user`, `uploaded_by=user`, `alumno__entrenador=user`
      (y `usuario=user` cuando aplique).

    Nota:
    - Política fail-closed: si el modelo no expone campos tenant soportados,
      se devuelve 403 para evitar fugas cross-tenant.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        user = getattr(self.request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()

        if getattr(user, "is_staff", False):
            return qs

        model = qs.model
        field_names = {f.name for f in model._meta.fields}

        def deny_without_tenant_filter():
            raise PermissionDenied("Tenant filter required for this resource.")

        # Alumno (atleta)
        if hasattr(user, "perfil_alumno"):
            if "usuario" in field_names:
                return qs.filter(usuario=user)
            if "alumno" in field_names:
                return qs.filter(alumno__usuario=user)
            deny_without_tenant_filter()

        # Coach (por defecto)
        tenant_filters = []
        if "entrenador" in field_names:
            tenant_filters.append(Q(entrenador=user))
        if "uploaded_by" in field_names:
            tenant_filters.append(Q(uploaded_by=user))
        if "alumno" in field_names:
            tenant_filters.append(Q(alumno__entrenador=user))
        if "usuario" in field_names:
            tenant_filters.append(Q(usuario=user))
        if "equipo" in field_names:
            tenant_filters.append(Q(equipo__entrenador=user))

        if not tenant_filters:
            deny_without_tenant_filter()

        tenant_q = Q()
        for tenant_filter in tenant_filters:
            tenant_q |= tenant_filter
        return qs.filter(tenant_q)


# --- 🚀 NUEVO ENDPOINT: SUBIDA DE VIDEOS (GIMNASIO PRO) ---
class VideoUploadViewSet(TenantModelViewSet):
    """
    Endpoint dedicado para subir videos cortos de ejercicios.
    Recibe un archivo, lo guarda y devuelve la URL.
    """
    queryset = VideoEjercicio.objects.all()
    serializer_class = VideoEjercicioSerializer
    parser_classes = (MultiPartParser, FormParser) # Habilita subida de archivos
    permission_classes = [permissions.IsAuthenticated, IsCoachUser]

    def create(self, request, *args, **kwargs):
        # 1. Validar y Guardar
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        video = serializer.save(uploaded_by=request.user)
        
        # 2. Construir URL Absoluta (Para que funcione en el reproductor)
        # Ej: http://localhost:8000/media/videos_ejercicios/sentadilla.mp4
        video_url = request.build_absolute_uri(video.archivo.url)
        
        return Response({
            "id": video.id,
            "url": video_url,
            "mensaje": "Video subido exitosamente 🎥"
        }, status=status.HTTP_201_CREATED)


class EquipoViewSet(TenantModelViewSet):
    """
    Gestión de Grupos de Entrenamiento (Clusters).
    Ej: "Inicial Montaña", "Avanzado Calle".
    Permite ver qué alumnos pertenecen a cada equipo.
    """
    queryset = Equipo.objects.all()
    serializer_class = EquipoSerializer
    permission_classes = [permissions.IsAuthenticated, IsCoachUser]

    def perform_create(self, serializer):
        # Multi-tenant: el owner del equipo es el coach autenticado
        serializer.save(entrenador=self.request.user)

    
    # Filtros
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'descripcion']

    # Acción Extra: Obtener alumnos de un equipo específico
    # Ruta: /api/equipos/{id}/alumnos/
    @action(detail=True, methods=['get'])
    def alumnos(self, request, pk=None):
        equipo = self.get_object()
        alumnos = equipo.alumnos.all()
        serializer = AlumnoSerializer(alumnos, many=True)
        return Response(serializer.data)


class AlumnoViewSet(TenantModelViewSet):
    """
    Gestión de Atletas.
    Permite buscar, filtrar por estado y ver detalles financieros.
    """
    serializer_class = AlumnoSerializer
    permission_classes = [permissions.IsAuthenticated] 
    queryset = Alumno.objects.all()
    pagination_class = PageNumberPagination
    
    # Potenciadores de Búsqueda
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['nombre', 'apellido', 'email', 'ciudad'] 
    filterset_fields = ['estado_actual', 'categoria', 'apto_medico_al_dia', 'equipo'] 
    ordering_fields = ['nombre', 'fecha_ultimo_pago']

    def get_queryset(self):
        qs = super().get_queryset().select_related("sync_state")

        # Contexto coach (para filtrar snapshots por tenant cuando aplique)
        user = self.request.user
        coach_user = user
        if hasattr(user, "perfil_alumno"):
            coach_user = getattr(user.perfil_alumno, "entrenador", None)

        # Optimización opcional (sin N+1): incluir riesgo del día si lo piden
        if self.request.query_params.get("include_injury_risk") in ("1", "true", "True"):
            today = timezone.localdate()
            snapshot_qs = InjuryRiskSnapshot.objects.filter(fecha=today)
            if coach_user is not None:
                snapshot_qs = snapshot_qs.filter(entrenador=coach_user)
            qs = qs.prefetch_related(
                Prefetch(
                    "injury_risk_snapshots",
                    queryset=snapshot_qs,
                    to_attr="injury_risk_today",
                )
            )

        return qs

    def perform_create(self, serializer):
        serializer.save(entrenador=self.request.user)

    # Ruta: /api/alumnos/{id}/injury-risk/ (y también /api/athletes/{id}/injury-risk/ vía alias de router)
    @action(detail=True, methods=["get"], url_path="injury-risk")
    def injury_risk(self, request, pk=None):
        alumno = self.get_object()  # ya está scopiado por entrenador

        # Query params: date=YYYY-MM-DD o start/end para rango
        date_q = request.query_params.get("date")
        start_q = request.query_params.get("start")
        end_q = request.query_params.get("end")

        def parse_iso(d: str) -> date_type:
            return date_type.fromisoformat(d)

        try:
            if date_q:
                target = parse_iso(date_q)
                qs = InjuryRiskSnapshot.objects.filter(entrenador=request.user, alumno=alumno, fecha=target)
                snap = qs.first()
                if not snap:
                    # Respuesta estable (no 404) para UX: sin datos
                    return Response(
                        {
                            "data_available": False,
                            "fecha": target.isoformat(),
                            "risk_level": "LOW",
                            "risk_score": 0,
                            "risk_reasons": ["Sin snapshot de riesgo para esa fecha"],
                        }
                    )
                data = InjuryRiskSnapshotSerializer(snap).data
                return Response({"data_available": True, **data})

            if start_q or end_q:
                start = parse_iso(start_q) if start_q else (timezone.localdate() - timedelta(days=30))
                end = parse_iso(end_q) if end_q else timezone.localdate()
                if start > end:
                    return Response({"error": "start no puede ser mayor que end"}, status=status.HTTP_400_BAD_REQUEST)
                if (end - start).days > 366:
                    return Response({"error": "Rango máximo: 366 días"}, status=status.HTTP_400_BAD_REQUEST)

                qs = InjuryRiskSnapshot.objects.filter(entrenador=request.user, alumno=alumno, fecha__range=[start, end]).order_by("fecha")
                data = InjuryRiskSnapshotSerializer(qs, many=True).data
                return Response({"data_available": bool(data), "results": data})

        except ValueError:
            return Response({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Default: último snapshot disponible
        snap = InjuryRiskSnapshot.objects.filter(entrenador=request.user, alumno=alumno).order_by("-fecha").first()
        if not snap:
            return Response(
                {
                    "data_available": False,
                    "fecha": None,
                    "risk_level": "LOW",
                    "risk_score": 0,
                    "risk_reasons": ["Sin datos PMC / riesgo aún no calculado"],
                }
            )

        data = InjuryRiskSnapshotSerializer(snap).data
        return Response({"data_available": True, **data})

    # Ruta: /api/alumnos/{id}/actividades/ (y también /api/athletes/{id}/actividades/)
    @action(detail=True, methods=["get"], url_path="actividades")
    def actividades(self, request, pk=None):
        """
        Listado de Actividad (negocio) para un alumno.

        WHY:
        - UX del frontend: endpoint nested por alumno (SaaS fitness típico).
        - Evita que el frontend tenga que filtrar /api/activities por su cuenta.
        """
        alumno = self.get_object()  # scopiado por entrenador (multi-tenant)
        qs = Actividad.objects.filter(alumno=alumno).order_by("-fecha_inicio")
        from .filters import ActividadFilter

        filterset = ActividadFilter(request.query_params, queryset=qs, request=request)
        qs = filterset.qs

        page = self.paginate_queryset(qs)
        if page is None:
            return Response(
                {"detail": "Pagination is required for this endpoint."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        serializer = ActividadSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)


class EntrenamientoViewSet(TenantModelViewSet):
    """
    Calendario de Entrenamientos.
    Soporta filtrado por fechas (vista mensual/semanal).
    """
    queryset = Entrenamiento.objects.select_related(
        "alumno",
        "plantilla_origen",
        "plantilla_version",
    ).all()
    serializer_class = EntrenamientoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alumno', 'fecha_asignada', 'completado']
    ordering_fields = ['fecha_asignada']

    # ======================================================================
    #  🔥 ACCIÓN ESPECIAL: FEEDBACK DEL ALUMNO (TÚNEL SEGURO)
    # ======================================================================
    @action(detail=True, methods=['patch'])
    def feedback(self, request, pk=None):
        """
        Permite al alumno marcar como completado y dejar RPE/Comentarios.
        NO permite modificar la estructura del entrenamiento.
        """
        entrenamiento = self.get_object()
        
        # Datos que permitimos tocar
        rpe = request.data.get('rpe')
        feedback = request.data.get('feedback_alumno')
        completado = request.data.get('completado', True) # Por defecto True si envían feedback
        
        # Métricas reales opcionales (si el alumno las carga manual)
        distancia_real = request.data.get('distancia_real_km')
        tiempo_real = request.data.get('tiempo_real_min')

        # Aplicamos cambios
        if rpe is not None: entrenamiento.rpe = rpe
        if feedback is not None: entrenamiento.feedback_alumno = feedback
        entrenamiento.completado = completado
        
        if distancia_real: entrenamiento.distancia_real_km = distancia_real
        if tiempo_real: entrenamiento.tiempo_real_min = tiempo_real

        entrenamiento.save() # Al guardar, el modelo recalcula % cumplimiento automáticamente

        return Response({
            "mensaje": "Feedback guardado. ¡Buen trabajo! 💪",
            "completado": entrenamiento.completado,
            "cumplimiento": entrenamiento.porcentaje_cumplimiento
        })


class PlantillaViewSet(TenantModelViewSet):
    """
    Librería de Entrenamientos (Recetas).
    Incluye motor de asignación masiva a equipos.
    """
    queryset = PlantillaEntrenamiento.objects.all()
    serializer_class = PlantillaEntrenamientoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['titulo', 'descripcion_global']
    filterset_fields = ['deporte', 'etiqueta_dificultad']
    ordering_fields = ['titulo', 'created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        plantilla = serializer.save(entrenador=self.request.user)
        PlantillaEntrenamientoVersion.objects.create(
            plantilla=plantilla,
            version=1,
            estructura=plantilla.estructura,
            descripcion=plantilla.descripcion_global,
        )

    def perform_update(self, serializer):
        plantilla = serializer.save()
        current_version = plantilla.versiones.aggregate(max_version=Max("version")).get("max_version") or 0
        PlantillaEntrenamientoVersion.objects.create(
            plantilla=plantilla,
            version=current_version + 1,
            estructura=plantilla.estructura,
            descripcion=plantilla.descripcion_global,
        )

    # ==========================================================================
    #  ⚡ MOTOR DE CLONACIÓN MASIVA (DROP & ASSIGN) - VERSIÓN JSON PRO
    # ==========================================================================
    @action(detail=True, methods=['post'])
    def aplicar_a_equipo(self, request, pk=None):
        """
        Recibe: { "equipo_id": 1, "fecha_inicio": "2025-12-15" }
        Acción: Clona la plantilla (incluyendo estructura JSON) para TODOS los alumnos.
        """
        plantilla = self.get_object()
        equipo_id = request.data.get('equipo_id')
        fecha_inicio_str = request.data.get('fecha_inicio')

        # 1. Validaciones
        if not equipo_id or not fecha_inicio_str:
            return Response(
                {"error": "Faltan datos: equipo_id y fecha_inicio son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Multi-tenant: el equipo debe pertenecer al coach autenticado
            equipo = Equipo.objects.get(pk=equipo_id, entrenador=request.user)
            # Parseamos la fecha que viene del frontend (Drop event)
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        except Equipo.DoesNotExist:
             return Response({"error": "El equipo no existe."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
             return Response({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        alumnos = equipo.alumnos.all()
        if not alumnos.exists():
             return Response({"error": "El equipo está vacío. Agrega atletas primero."}, status=status.HTTP_400_BAD_REQUEST)
        
        nuevos_entrenamientos = []
        plantilla_version = plantilla.versiones.order_by("-version").first()
        if not plantilla_version:
            plantilla_version = PlantillaEntrenamientoVersion.objects.create(
                plantilla=plantilla,
                version=1,
                estructura=plantilla.estructura,
                descripcion=plantilla.descripcion_global,
            )
        estructura_snapshot = plantilla_version.estructura

        # 2. Ejecución Atómica (Todo o Nada)
        try:
            with transaction.atomic():
                for alumno in alumnos:
                    # Clonamos la "Receta" en un "Plato Real" para este alumno
                    entrenamiento = Entrenamiento(
                        alumno=alumno,
                        plantilla_origen=plantilla,
                        plantilla_version=plantilla_version,
                        fecha_asignada=fecha_inicio,
                        titulo=plantilla.titulo,
                        tipo_actividad=plantilla.deporte,
                        descripcion_detallada=plantilla.descripcion_global,
                        
                        # --- CLAVE: CLONACIÓN DE ESTRUCTURA JSON ---
                        estructura=estructura_snapshot, # Copiamos los bloques tal cual
                        
                        # Métricas base (se recalcularán luego si es necesario)
                        # distancia_planificada_km y tiempo se pueden extraer del JSON aquí si quisiéramos
                        completado=False
                    )
                    nuevos_entrenamientos.append(entrenamiento)
                
                # Bulk Create: 50 veces más rápido que guardar uno por uno
                Entrenamiento.objects.bulk_create(nuevos_entrenamientos)

            return Response({
                "mensaje": "Plantilla aplicada exitosamente.",
                "plantilla": plantilla.titulo,
                "equipo": equipo.nombre,
                "alumnos_afectados": len(nuevos_entrenamientos),
                "fecha": fecha_inicio 
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='asignar_a_alumno')
    def asignar_a_alumno(self, request, pk=None):
        """
        Recibe: { "alumno_id": 1, "fecha": "2025-12-15" }
        Acción: Clona la plantilla para un alumno específico.
        """
        plantilla = self.get_object()
        alumno_id = request.data.get('alumno_id')
        fecha_str = request.data.get('fecha')

        if not alumno_id or not fecha_str:
            return Response(
                {"error": "Faltan datos: alumno_id y fecha son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        alumno = Alumno.objects.filter(pk=alumno_id).first()
        if not alumno:
            return Response({"error": "El alumno no existe."}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.is_staff and alumno.entrenador_id != request.user.id:
            return Response({"error": "No tienes permisos para asignar a este alumno."}, status=status.HTTP_403_FORBIDDEN)
        if not request.user.is_staff and plantilla.entrenador_id != alumno.entrenador_id:
            return Response({"error": "Plantilla y alumno no pertenecen al mismo entrenador."}, status=status.HTTP_403_FORBIDDEN)

        try:
            entrenamiento, created = asignar_plantilla_a_alumno(plantilla, alumno, fecha)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = EntrenamientoSerializer(entrenamiento, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CarreraViewSet(TenantModelViewSet):
    """
    Base de datos de Carreras (Eventos).
    """
    queryset = Carrera.objects.all().order_by('-fecha')
    serializer_class = CarreraSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'lugar']


class InscripcionViewSet(TenantModelViewSet):
    """
    Gestión de Objetivos (Quién corre qué).
    """
    queryset = InscripcionCarrera.objects.select_related("alumno", "carrera").all()
    serializer_class = InscripcionCarreraSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['alumno', 'estado']


class PagoViewSet(TenantModelViewSet):
    """
    Gestión Financiera.
    Permite al entrenador ver quién pagó y validar comprobantes.
    """
    queryset = Pago.objects.select_related("alumno").all()
    serializer_class = PagoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alumno', 'es_valido', 'metodo']
    ordering_fields = ['fecha_pago', 'monto']


class ActividadViewSet(TenantModelViewSet):
    """
    Listado de actividades importadas (Strava → Actividad).

    Multi-tenant:
    - Coach: ve actividades de sus alumnos.
    - Alumno: ve solo sus actividades.
    - Staff: ve todo.
    """
    queryset = Actividad.objects.select_related("alumno").all()
    serializer_class = ActividadSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]
    pagination_class = PageNumberPagination

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ActividadFilter
    search_fields = ["nombre"]
    ordering_fields = ["fecha_inicio", "distancia", "tiempo_movimiento"]
    ordering = ["-fecha_inicio"]

    def get_queryset(self):
        qs = super().get_queryset()
        athlete_id = self.request.query_params.get("athlete_id") or self.request.query_params.get("alumno_id")
        if athlete_id:
            require_athlete_for_user(user=self.request.user, athlete_id=athlete_id)
        return qs

    @action(detail=False, methods=["get"], url_path="raw", permission_classes=[permissions.IsAdminUser])
    def raw(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is None:
            return Response(
                {"detail": "Pagination is required for this endpoint."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        serializer = ActividadRawPayloadSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

# ==============================================================================
#  DASHBOARD LEGACY (Vista de Gestión / Admin - NO TOCAR)
# ==============================================================================

@login_required
def dashboard_entrenador(request):
    
    # --- LÓGICA DE BOTONES ---
    if request.method == 'POST':
        
        # A. Sincronización Rápida (Últimas 10)
        if 'sync_strava' in request.POST:
            if getattr(settings, "DISABLE_LEGACY_STRAVA_SYNC", True):
                messages.error(
                    request,
                    "⚠️ Legacy Strava sync está deshabilitado en este entorno.",
                )
                return redirect('dashboard_principal')
            nuevas, actualizadas, estado = sincronizar_actividades_strava(request.user)
            
            if estado == "OK":
                if nuevas == 0 and actualizadas == 0:
                    messages.info(request, "👍 Strava está al día.")
                else:
                    messages.success(request, f"✅ Sync Rápido: {nuevas} nuevas, {actualizadas} actualizadas.")
            else:
                messages.error(request, f"⚠️ Error: {estado}")

        # B. Sincronización Histórica (Últimos 60 días + Recálculo)
        elif 'sync_history' in request.POST:
            if getattr(settings, "DISABLE_LEGACY_STRAVA_SYNC", True):
                messages.error(
                    request,
                    "⚠️ Legacy Strava sync está deshabilitado en este entorno.",
                )
                return redirect('dashboard_principal')
            logger.info("strava.legacy_sync_history_request", extra={"user_id": request.user.id, "days": 60})
            nuevas, actualizadas, estado = sincronizar_actividades_strava(request.user, dias_historial=60)
            
            if estado == "OK":
                messages.success(request, f"📚 Historia Recuperada: {nuevas} importadas. Fitness (CTL) recalculado exitosamente.")
            else:
                messages.error(request, f"⚠️ Error Histórico: {estado}")
            
        return redirect('dashboard_principal')

    # --- CARGA DE DATOS PARA LA VISTA ---
    entrenamientos = Entrenamiento.objects.filter(
        alumno__entrenador=request.user
    ).select_related('alumno', 'plantilla_origen').order_by('-fecha_asignada')
    
    eventos = []
    for entreno in entrenamientos:
        color = '#28a745' if entreno.completado else '#3788d8'
        if entreno.plantilla_origen and entreno.plantilla_origen.deporte == 'REST': 
            color = '#6c757d'
        
        nombre_alumno = entreno.alumno.nombre if entreno.alumno else "Sin Asignar"
        titulo = f"{nombre_alumno}: {entreno.titulo}"
        
        eventos.append({
            'title': titulo, 
            'start': entreno.fecha_asignada.strftime('%Y-%m-%d'),
            'color': color, 
            'url': f"/admin/core/entrenamiento/{entreno.id}/change/"
        })

    actividades_db = Actividad.objects.filter(usuario=request.user).order_by('-fecha_inicio')[:5]
    strava_connected = SocialToken.objects.filter(account__user=request.user, account__provider='strava').exists()

    context = {
        'eventos': eventos,             
        'activities': actividades_db,
        'strava_connected': strava_connected,
    }
    return render(request, 'core/dashboard.html', context)
