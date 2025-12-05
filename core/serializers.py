from rest_framework import serializers
from .models import Alumno, Entrenamiento

# 1. SERIALIZER DE ALUMNO (Estándar)
class AlumnoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alumno
        fields = '__all__'

# 2. SERIALIZER DE ENTRENAMIENTO (Enriquecido)
class EntrenamientoSerializer(serializers.ModelSerializer):
    # MAGIA: Traemos datos del alumno automáticamente para no ver solo un ID numérico
    alumno_nombre = serializers.CharField(source='alumno.nombre', read_only=True)
    alumno_apellido = serializers.CharField(source='alumno.apellido', read_only=True)

    class Meta:
        model = Entrenamiento
        # Definimos explícitamente el orden para que el JSON sea legible
        fields = [
            'id',
            'alumno',           # El ID (necesario para actualizaciones)
            'alumno_nombre',    # Extra: Para mostrar en pantalla
            'alumno_apellido',  # Extra: Para mostrar en pantalla
            
            # --- Planificación ---
            'fecha_asignada',
            # 'tipo',  <--- ELIMINAMOS ESTA LÍNEA QUE CAUSABA EL ERROR
            'titulo',
            # 'descripcion_coach', <--- TAMPOCO EXISTE EN EL MODELO ACTUAL, LO COMENTO POR SEGURIDAD
            # 'distancia_planificada_km', <--- LO MISMO, NO ESTÁ EN EL MODELO QUE ME PASASTE
            # 'tiempo_planificado_min',   <--- LO MISMO
            # 'desnivel_planificado_m',   <--- LO MISMO
            
            # --- Ejecución Real ---
            'completado',
            # 'fecha_ejecucion', <--- NO ESTÁ EN EL MODELO (Usas fecha_asignada)
            'distancia_real_km',
            'tiempo_real_min',
            'desnivel_real_m',
            
            # --- Feedback ---
            'rpe',
            'feedback_alumno',
            
            # --- Integraciones ---
            'strava_id',
            'garmin_id'
        ]