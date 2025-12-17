from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser # <--- CRÍTICO PARA SUBIR VIDEOS
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction 
from datetime import datetime, date as date_type, timedelta
from django.db.models import Prefetch
from django.utils import timezone

# Importamos Modelos
from .models import (
    Alumno, Entrenamiento, Actividad, 
    PlantillaEntrenamiento, Carrera, 
    InscripcionCarrera, Pago,
    Equipo, VideoEjercicio # <--- NUEVO MODELO IMPORTADO
)
from analytics.models import InjuryRiskSnapshot
from analytics.serializers import InjuryRiskSnapshotSerializer

# Permisos multi-tenant (coach-scoped)
from .permissions import IsCoachUser

# Importamos Serializadores
from .serializers import (
    AlumnoSerializer, EntrenamientoSerializer,
    PlantillaEntrenamientoSerializer, CarreraSerializer,
    InscripcionCarreraSerializer, PagoSerializer,
    EquipoSerializer, VideoEjercicioSerializer # <--- NUEVO SERIALIZER IMPORTADO
)

from allauth.socialaccount.models import SocialToken
from .services import sincronizar_actividades_strava

# ==============================================================================
#  API REST (EL CEREBRO DE LA APP MÓVIL 📱)
# ==============================================================================

# --- 🚀 NUEVO ENDPOINT: SUBIDA DE VIDEOS (GIMNASIO PRO) ---
class VideoUploadViewSet(viewsets.ModelViewSet):
    """
    Endpoint dedicado para subir videos cortos de ejercicios.
    Recibe un archivo, lo guarda y devuelve la URL.
    """
    queryset = VideoEjercicio.objects.all()
    serializer_class = VideoEjercicioSerializer
    parser_classes = (MultiPartParser, FormParser) # Habilita subida de archivos
    permission_classes = [permissions.IsAuthenticated, IsCoachUser]

    def get_queryset(self):
        # Multi-tenant: cada coach ve solo sus videos (staff puede ver todo)
        user = self.request.user
        if user.is_staff:
            return VideoEjercicio.objects.all()
        return VideoEjercicio.objects.filter(uploaded_by=user)

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


class EquipoViewSet(viewsets.ModelViewSet):
    """
    Gestión de Grupos de Entrenamiento (Clusters).
    Ej: "Inicial Montaña", "Avanzado Calle".
    Permite ver qué alumnos pertenecen a cada equipo.
    """
    queryset = Equipo.objects.all()
    serializer_class = EquipoSerializer
    permission_classes = [permissions.IsAuthenticated, IsCoachUser]
    def get_queryset(self):
        # Multi-tenant: cada coach ve solo sus equipos (staff puede ver todo)
        user = self.request.user
        if user.is_staff:
            return Equipo.objects.all()
        return Equipo.objects.filter(entrenador=user)

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
        # Multi-tenant: solo alumnos del mismo entrenador
        alumnos = equipo.alumnos.filter(entrenador=request.user)
        serializer = AlumnoSerializer(alumnos, many=True)
        return Response(serializer.data)


class AlumnoViewSet(viewsets.ModelViewSet):
    """
    Gestión de Atletas.
    Permite buscar, filtrar por estado y ver detalles financieros.
    """
    serializer_class = AlumnoSerializer
    permission_classes = [permissions.IsAuthenticated] 
    
    # Potenciadores de Búsqueda
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['nombre', 'apellido', 'email', 'ciudad'] 
    filterset_fields = ['estado_actual', 'categoria', 'apto_medico_al_dia', 'equipo'] 
    ordering_fields = ['nombre', 'fecha_ultimo_pago']

    def get_queryset(self):
        # MULTI-TENANT: Solo mis alumnos
        qs = Alumno.objects.filter(entrenador=self.request.user)

        # Optimización opcional (sin N+1): incluir riesgo del día si lo piden
        if self.request.query_params.get("include_injury_risk") in ("1", "true", "True"):
            today = timezone.localdate()
            qs = qs.prefetch_related(
                Prefetch(
                    "injury_risk_snapshots",
                    queryset=InjuryRiskSnapshot.objects.filter(fecha=today, entrenador=self.request.user),
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


class EntrenamientoViewSet(viewsets.ModelViewSet):
    """
    Calendario de Entrenamientos.
    Soporta filtrado por fechas (vista mensual/semanal).
    """
    serializer_class = EntrenamientoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alumno', 'fecha_asignada', 'completado']
    ordering_fields = ['fecha_asignada']

    def get_queryset(self):
        # Lógica inteligente:
        # 1. Si soy Entrenador: Veo los de mis alumnos.
        # 2. Si soy Alumno: Veo SOLO los míos (Seguridad).
        user = self.request.user
        
        # Caso A: Soy Entrenador (tengo alumnos asociados)
        if hasattr(user, 'alumnos') and user.alumnos.exists(): 
             return Entrenamiento.objects.select_related('alumno', 'plantilla_origen').filter(
                alumno__entrenador=user
            ).order_by('-fecha_asignada')
        
        # Caso B: Soy Alumno (tengo un perfil de alumno)
        elif hasattr(user, 'perfil_alumno'):
             return Entrenamiento.objects.select_related('alumno', 'plantilla_origen').filter(
                alumno__usuario=user
            ).order_by('-fecha_asignada')
            
        # Caso C: Admin / Fallback (o entrenador sin alumnos aún)
        # Intentamos ver si es entrenador aunque no tenga alumnos asignados
        if user.is_staff or (hasattr(user, 'alumnos')): # Asumiendo staff o entrenador
             return Entrenamiento.objects.select_related('alumno', 'plantilla_origen').filter(
                alumno__entrenador=user
            ).order_by('-fecha_asignada')

        return Entrenamiento.objects.none()

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


class PlantillaViewSet(viewsets.ModelViewSet):
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

        # 2. Ejecución Atómica (Todo o Nada)
        try:
            with transaction.atomic():
                for alumno in alumnos:
                    # Clonamos la "Receta" en un "Plato Real" para este alumno
                    entrenamiento = Entrenamiento(
                        alumno=alumno,
                        plantilla_origen=plantilla,
                        fecha_asignada=fecha_inicio,
                        titulo=plantilla.titulo,
                        tipo_actividad=plantilla.deporte,
                        descripcion_detallada=plantilla.descripcion_global,
                        
                        # --- CLAVE: CLONACIÓN DE ESTRUCTURA JSON ---
                        estructura=plantilla.estructura, # Copiamos los bloques tal cual
                        
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


class CarreraViewSet(viewsets.ModelViewSet):
    """
    Base de datos de Carreras (Eventos).
    """
    queryset = Carrera.objects.all().order_by('-fecha')
    serializer_class = CarreraSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre', 'lugar']


class InscripcionViewSet(viewsets.ModelViewSet):
    """
    Gestión de Objetivos (Quién corre qué).
    """
    serializer_class = InscripcionCarreraSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['alumno', 'estado']

    def get_queryset(self):
        return InscripcionCarrera.objects.filter(alumno__entrenador=self.request.user)


class PagoViewSet(viewsets.ModelViewSet):
    """
    Gestión Financiera.
    Permite al entrenador ver quién pagó y validar comprobantes.
    """
    serializer_class = PagoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alumno', 'es_valido', 'metodo']
    ordering_fields = ['fecha_pago', 'monto']

    def get_queryset(self):
        # Solo veo los pagos de mis alumnos
        return Pago.objects.filter(alumno__entrenador=self.request.user).order_by('-fecha_pago')

# ==============================================================================
#  DASHBOARD LEGACY (Vista de Gestión / Admin - NO TOCAR)
# ==============================================================================

@login_required
def dashboard_entrenador(request):
    
    # --- LÓGICA DE BOTONES ---
    if request.method == 'POST':
        
        # A. Sincronización Rápida (Últimas 10)
        if 'sync_strava' in request.POST:
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
            print("📚 Iniciando carga histórica de 60 días...")
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