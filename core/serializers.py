from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import (
    Alumno, Carrera, InscripcionCarrera, 
    PlantillaEntrenamiento, Entrenamiento, Actividad, Pago,
    Equipo, VideoEjercicio # <--- NUEVO MODELO IMPORTADO
)
from analytics.models import InjuryRiskSnapshot

# ==============================================================================
#  0. GESTIÓN DE EQUIPOS
# ==============================================================================
class EquipoSerializer(serializers.ModelSerializer):
    cantidad_alumnos = serializers.ReadOnlyField()
    
    class Meta:
        model = Equipo
        fields = ['id', 'nombre', 'descripcion', 'color_identificador', 'cantidad_alumnos', 'created_at']

# ==============================================================================
#  1. ESTRUCTURA DE ENTRENAMIENTO (JSON POWERED)
# ==============================================================================

class PlantillaEntrenamientoSerializer(serializers.ModelSerializer):
    # díficultad_display es un campo calculado en el serializer, no en el modelo
    dificultad_display = serializers.SerializerMethodField()
    version_actual = serializers.SerializerMethodField()
    ultima_actualizacion = serializers.SerializerMethodField()

    class Meta:
        model = PlantillaEntrenamiento
        fields = [
            'id',
            'titulo',
            'deporte',
            'etiqueta_dificultad',
            'dificultad_display',
            'descripcion_global',
            'estructura',
            'created_at',
            'version_actual',
            'ultima_actualizacion',
        ]

    def get_dificultad_display(self, obj):
        return obj.get_etiqueta_dificultad_display()

    def get_version_actual(self, obj):
        version = obj.versiones.order_by("-version").first()
        return version.version if version else None

    def get_ultima_actualizacion(self, obj):
        version = obj.versiones.order_by("-version").first()
        if version:
            return version.created_at.isoformat()
        return obj.created_at.isoformat() if obj.created_at else None

class EntrenamientoSerializer(serializers.ModelSerializer):
    alumno_nombre = serializers.CharField(source='alumno.nombre', read_only=True)
    alumno_apellido = serializers.CharField(source='alumno.apellido', read_only=True)
    
    class Meta:
        model = Entrenamiento
        fields = [
            'id', 'alumno', 'alumno_nombre', 'alumno_apellido',
            'fecha_asignada', 'titulo', 'tipo_actividad', 'completado',
            'porcentaje_cumplimiento',
            # Métricas Planificadas
            'distancia_planificada_km', 'tiempo_planificado_min', 'desnivel_planificado_m',
            'rpe_planificado', 'descripcion_detallada',
            # EL CEREBRO NUEVO (JSON)
            'estructura',
            'plantilla_version',
            # Métricas Reales
            'distancia_real_km', 'tiempo_real_min', 'desnivel_real_m',
            'rpe', 'feedback_alumno',
            'strava_id' 
        ]
        read_only_fields = ['porcentaje_cumplimiento', 'plantilla_version']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PR4: If using nested route, 'alumno' is derived from URL, so it's not required in body.
        # We check if view is present and has the specific kwargs.
        view = self.context.get('view')
        if view and hasattr(view, 'kwargs'):
            url_alumno_id = view.kwargs.get('alumno_id') or view.kwargs.get('athlete_id')
            if url_alumno_id and 'alumno' in self.fields:
                self.fields['alumno'].required = False

    def validate(self, attrs):
        # 1. PR4 Hardening: Validate Body vs URL Alumno correctness
        # We check self.initial_data to catch explicit mismatch even if DRF field validation passed or skipped
        view = self.context.get('view')
        if view and hasattr(view, 'kwargs'):
            url_alumno_id = view.kwargs.get('alumno_id') or view.kwargs.get('athlete_id')
            if url_alumno_id:
                # Check if 'alumno' key exists in raw input
                if 'alumno' in self.initial_data:
                    raw_alumno = self.initial_data['alumno']
                    # Extract ID safely (handle dict or scalar)
                    body_id = None
                    if isinstance(raw_alumno, dict):
                         body_id = raw_alumno.get('id')
                    else:
                         body_id = raw_alumno
                    
                    # Strict string comparison
                    if str(body_id) != str(url_alumno_id):
                        raise serializers.ValidationError({"alumno": "Body alumno does not match URL alumno_id"})

        # 2. Tenant Permission Check
        # Only needed if non-nested route (url_alumno_id is None). 
        # If nested, View perform_create checks URL ID with 404 (Fail-closed).
        # We skip check here to avoid returning 403 (Leak) if body ID matches URL ID but is forbidden.
        if not url_alumno_id and 'alumno' in attrs:
            alumno = attrs['alumno']
            request = self.context.get("request")
            if request and getattr(request, "user", None) and request.user.is_authenticated:
                user = request.user
                # Si es atleta, no permitimos setear alumno arbitrario
                if hasattr(user, "perfil_alumno") and not user.is_staff:
                    raise PermissionDenied("No autorizado.")
                # Si es coach, solo sus alumnos
                if alumno.entrenador_id and alumno.entrenador_id != user.id and not user.is_staff:
                    raise PermissionDenied("No autorizado.")

        # 3. PR5 Hardening: Data Integrity (Real fields are read-only via API)
        request = self.context.get("request")
        # Bloquear solo si hay request (API call) y el usuario NO es staff/system
        if request and getattr(request, "user", None) and not request.user.is_staff:
            restricted_fields = {
                'distancia_real_km', 
                'tiempo_real_min', 
                'desnivel_real_m', 
                'rpe', 
                'feedback_alumno',
                'completado'
            }
            # Chequear tanto initial_data (raw) como attrs (validado) para mayor seguridad
            # initial_data catcha intentos de enviar el campo aunque DRF lo ignore por read_only
            incoming_keys = set(self.initial_data.keys()) if hasattr(self, 'initial_data') else set()
            
            # Intersección: si manda algún campo restringido -> 400
            forbidden = incoming_keys.intersection(restricted_fields)
            if forbidden:
                raise serializers.ValidationError({
                    "detail": f"Campos de ejecución 'Real' son de solo lectura vía API: {', '.join(forbidden)}",
                    "reason": "real_fields_read_only"
                })

        return attrs


class PlanningSessionSerializer(serializers.ModelSerializer):
    athlete_id = serializers.IntegerField(source="alumno_id", read_only=True)
    date = serializers.DateField(source="fecha_asignada")
    sport = serializers.CharField(source="tipo_actividad")
    title = serializers.CharField(source="titulo")
    description = serializers.CharField(source="descripcion_detallada", allow_blank=True, allow_null=True)
    structure = serializers.JSONField(source="estructura")
    planned_metrics = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Entrenamiento
        fields = [
            "id",
            "athlete_id",
            "date",
            "sport",
            "title",
            "description",
            "structure",
            "planned_metrics",
            "status",
        ]

    def get_status(self, obj):
        return "completed" if obj.completado else "planned"

    def get_planned_metrics(self, obj):
        duration_min = obj.tiempo_planificado_min
        distance_km = obj.distancia_planificada_km
        elev_m = obj.desnivel_planificado_m
        rpe = obj.rpe_planificado or 0
        duration_s = int(duration_min * 60) if duration_min is not None else None
        distance_m = int(round(float(distance_km) * 1000.0)) if distance_km is not None else None
        elev_pos_m = int(elev_m) if elev_m is not None else None
        load = None
        if duration_min is not None:
            load = round(float(duration_min) * (1.0 + (float(rpe) / 10.0)), 2)
        return {
            "duration_s": duration_s,
            "distance_m": distance_m,
            "elev_pos_m": elev_pos_m,
            "load": load,
        }


class PlanningSessionWriteSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=["planned", "completed"], required=False)

    class Meta:
        model = Entrenamiento
        fields = [
            "alumno",
            "fecha_asignada",
            "tipo_actividad",
            "titulo",
            "descripcion_detallada",
            "estructura",
            "distancia_planificada_km",
            "tiempo_planificado_min",
            "desnivel_planificado_m",
            "rpe_planificado",
            "status",
        ]
        extra_kwargs = {
            "estructura": {"required": False},
            "descripcion_detallada": {"required": False},
        }

    def validate_alumno(self, alumno: Alumno):
        """
        Multi-tenant: un coach no puede crear/editar entrenamientos de atletas ajenos.
        """
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return alumno
        user = request.user
        if hasattr(user, "perfil_alumno") and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        if alumno.entrenador_id and alumno.entrenador_id != user.id and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        return alumno

    def validate(self, attrs):
        status = attrs.pop("status", None)
        if status is not None:
            attrs["completado"] = status == "completed"
        return attrs

# ==============================================================================
#  2. GESTIÓN FINANCIERA
# ==============================================================================

class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = ['id', 'fecha_pago', 'monto', 'metodo', 'es_valido', 'created_at']
        read_only_fields = ['es_valido']

# ==============================================================================
#  3. ALUMNO Y PERFIL
# ==============================================================================

class AlumnoSerializer(serializers.ModelSerializer):
    # Usamos PrimaryKeyRelatedField para escritura y String para lectura si queremos
    equipo_nombre = serializers.CharField(source='equipo.nombre', read_only=True)
    # El queryset se scopea dinámicamente por request.user en __init__
    equipo = serializers.PrimaryKeyRelatedField(queryset=Equipo.objects.none(), allow_null=True)
    pagos = PagoSerializer(many=True, read_only=True)
    injury_risk = serializers.SerializerMethodField()
    sync_state = serializers.SerializerMethodField()

    class Meta:
        model = Alumno
        fields = '__all__'
        read_only_fields = ['fecha_alta', 'entrenador', 'equipo_nombre']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return
        user = request.user
        if user.is_staff:
            self.fields["equipo"].queryset = Equipo.objects.all()
        else:
            # Multi-tenant: un coach solo puede asignar equipos propios
            self.fields["equipo"].queryset = Equipo.objects.filter(entrenador=user)

    def get_injury_risk(self, obj):
        """
        Devuelve el snapshot de riesgo del día (si fue prefetched).
        Para evitar N+1, solo se completa cuando el queryset fue armado con prefetch.
        """
        # Prefetch convention: obj.injury_risk_today = [InjuryRiskSnapshot] o []
        prefetched = getattr(obj, "injury_risk_today", None)
        if prefetched is None:
            return None
        if not prefetched:
            return None
        snap: InjuryRiskSnapshot = prefetched[0]
        return {
            "date": snap.fecha.isoformat(),
            "risk_level": snap.risk_level,
            "risk_score": snap.risk_score,
            "risk_reasons": snap.risk_reasons,
        }

    def get_sync_state(self, obj):
        """
        Estado de sync/import (Strava) para UX (progreso, errores, timestamps).
        """
        try:
            st = getattr(obj, "sync_state", None)
        except Exception:
            st = None
        if not st:
            return None
        return {
            "provider": st.provider,
            "sync_status": st.sync_status,
            "started_at": st.started_at.isoformat() if st.started_at else None,
            "finished_at": st.finished_at.isoformat() if st.finished_at else None,
            "last_sync_at": st.last_sync_at.isoformat() if st.last_sync_at else None,
            "processed_count": int(st.processed_count or 0),
            "target_count": int(st.target_count or 0),
            "last_backfill_count": int(st.last_backfill_count or 0),
            "last_error": st.last_error or "",
        }

# ==============================================================================
#  4. CARRERAS
# ==============================================================================

class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrera
        fields = '__all__'

class InscripcionCarreraSerializer(serializers.ModelSerializer):
    carrera = CarreraSerializer(read_only=True)
    carrera_id = serializers.PrimaryKeyRelatedField(queryset=Carrera.objects.all(), source='carrera', write_only=True)
    
    class Meta:
        model = InscripcionCarrera
        fields = ['id', 'alumno', 'carrera', 'carrera_id', 'estado']

    def validate_alumno(self, alumno: Alumno):
        """
        Multi-tenant: un coach no puede crear objetivos para atletas ajenos.
        """
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return alumno
        user = request.user
        if hasattr(user, "perfil_alumno") and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        if alumno.entrenador_id and alumno.entrenador_id != user.id and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        return alumno

# ==============================================================================
#  5. MULTIMEDIA (VIDEOS DE EJERCICIOS)
# ==============================================================================

class VideoEjercicioSerializer(serializers.ModelSerializer):
    """
    Serializer para la subida y lectura de videos de gimnasio.
    """
    class Meta:
        model = VideoEjercicio
        fields = ['id', 'titulo', 'archivo', 'uploaded_at']
        read_only_fields = ['uploaded_at']


# ==============================================================================
#  6. ACTIVIDADES (STRAVA → ACTIVIDAD INTERNA)
# ==============================================================================
class ActividadSerializer(serializers.ModelSerializer):
    alumno_nombre = serializers.CharField(source="alumno.nombre", read_only=True)
    alumno_apellido = serializers.CharField(source="alumno.apellido", read_only=True)

    class Meta:
        model = Actividad
        fields = [
            "id",
            "usuario",
            "alumno",
            "alumno_nombre",
            "alumno_apellido",
            "strava_id",
            "strava_sport_type",
            "nombre",
            "tipo_deporte",
            "fecha_inicio",
            "distancia",
            "tiempo_movimiento",
            "desnivel_positivo",
            "elev_gain_m",
            "elev_loss_m",
            "elev_total_m",
            "ritmo_promedio",
            "mapa_polilinea",
            "validity",
            "invalid_reason",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = fields


class ActividadRawPayloadSerializer(serializers.ModelSerializer):
    alumno_nombre = serializers.CharField(source="alumno.nombre", read_only=True)
    alumno_apellido = serializers.CharField(source="alumno.apellido", read_only=True)

    class Meta:
        model = Actividad
        fields = [
            "id",
            "usuario",
            "alumno",
            "alumno_nombre",
            "alumno_apellido",
            "strava_id",
            "strava_sport_type",
            "nombre",
            "tipo_deporte",
            "fecha_inicio",
            "distancia",
            "tiempo_movimiento",
            "desnivel_positivo",
            "elev_gain_m",
            "elev_loss_m",
            "elev_total_m",
            "ritmo_promedio",
            "mapa_polilinea",
            "validity",
            "invalid_reason",
            "creado_en",
            "actualizado_en",
            "datos_brutos",
        ]
        read_only_fields = fields
