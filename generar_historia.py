import os
import django

# --- 1. CONFIGURACIÓN DEL ENTORNO DJANGO ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

# --- 2. TU LÓGICA DE MIGRACIÓN ---
from core.models import Actividad, Entrenamiento, Alumno
from core.tasks import procesar_metricas_entrenamiento
from analytics.utils import recalcular_historial_completo

print("🚀 Iniciando Generación Histórica de Entrenamientos...")

# Obtenemos el Alumno
alumno = Alumno.objects.first()

if not alumno:
    print("❌ ERROR: No hay ningún alumno creado en el sistema. Crea uno en el Admin primero.")
else:
    print(f"👤 Procesando para el atleta: {alumno.nombre} (ID: {alumno.id})")
    
    actividades = Actividad.objects.all()
    creados = 0
    
    for act in actividades:
        # Verificar si ya existe para no duplicar
        if Entrenamiento.objects.filter(strava_id=str(act.strava_id)).exists():
            continue
            
        # Mapeo simple de deportes
        tipo = 'RUN'
        t_dep = act.tipo_deporte
        if 'Ride' in t_dep: tipo = 'CYCLING'
        elif 'Swim' in t_dep: tipo = 'SWIMMING'
        elif 'Weight' in t_dep: tipo = 'STRENGTH'
        elif 'Trail' in t_dep or 'Run' in t_dep: tipo = 'TRAIL'

        # Crear el Entrenamiento retrospectivo
        entreno = Entrenamiento.objects.create(
            alumno=alumno,
            titulo=act.nombre,
            fecha_asignada=act.fecha_inicio.date(),
            tipo_actividad=tipo,
            
            # Datos Reales
            tiempo_real_min=int(act.tiempo_movimiento / 60),
            distancia_real_km=round(act.distancia / 1000, 2),
            desnivel_real_m=int(act.desnivel_positivo),
            
            # Simulamos datos planificados = reales (Cumplimiento 100%)
            tiempo_planificado_min=int(act.tiempo_movimiento / 60),
            distancia_planificada_km=round(act.distancia / 1000, 2),
            
            completado=True,
            strava_id=str(act.strava_id)
            # HE BORRADO LA LÍNEA 'fecha_ejecucion' QUE DABA ERROR
        )
        
        # Intentar extraer potencia/pulso del JSON crudo
        raw = act.datos_brutos
        if isinstance(raw, dict):
            if 'average_watts' in raw: entreno.potencia_promedio = raw['average_watts']
            if 'average_heartrate' in raw: entreno.frecuencia_cardiaca_promedio = raw['average_heartrate']
            entreno.save()

        # 🔥 CALCULAR TSS/FATIGA
        procesar_metricas_entrenamiento(entreno.id)
        
        creados += 1
        print(f"  ✅ Generado: {entreno.titulo} ({entreno.fecha_asignada})")

    print(f"\n🎉 Proceso finalizado. Se crearon {creados} entrenamientos históricos.")
    
    # Recalcular la curva PMC completa
    recalcular_historial_completo(alumno)