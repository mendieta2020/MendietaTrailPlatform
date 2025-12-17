from rest_framework import serializers
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

    class Meta:
        model = PlantillaEntrenamiento
        fields = ['id', 'titulo', 'deporte', 'etiqueta_dificultad', 'dificultad_display', 'descripcion_global', 'estructura', 'created_at']

    def get_dificultad_display(self, obj):
        return obj.get_etiqueta_dificultad_display()

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
            # Métricas Reales
            'distancia_real_km', 'tiempo_real_min', 'desnivel_real_m',
            'rpe', 'feedback_alumno',
            'strava_id' 
        ]
        read_only_fields = ['porcentaje_cumplimiento']

    def validate_alumno(self, alumno: Alumno):
        """
        Multi-tenant: un coach no puede crear/editar entrenamientos de atletas ajenos.
        """
        request = self.context.get("request")
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return alumno
        user = request.user
        # Si es atleta, no permitimos setear alumno arbitrario (este endpoint es de coach)
        if hasattr(user, "perfil_alumno") and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        if alumno.entrenador_id and alumno.entrenador_id != user.id and not user.is_staff:
            raise serializers.ValidationError("No autorizado.")
        return alumno

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