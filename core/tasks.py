from celery import shared_task
from .models import Entrenamiento
from .metrics import (
    calcular_trimp, 
    calcular_tss_estimado, 
    calcular_load_rpe, 
    determinar_carga_final
)

@shared_task
def procesar_metricas_entrenamiento(entrenamiento_id):
    """
    Tarea asíncrona: Recibe un ID, calcula la fatiga y actualiza la DB.
    Se ejecuta automáticamente cuando Strava envía datos o el coach edita manualmente.
    """
    try:
        # 1. Buscamos el entrenamiento y los datos del alumno (FTP, FC, etc)
        entreno = Entrenamiento.objects.select_related('alumno').get(pk=entrenamiento_id)
        alumno = entreno.alumno
        
        print(f"🧮 [CALCULADORA] Procesando: {entreno} para {alumno.nombre}")

        # 2. Obtenemos la duración real
        tiempo = entreno.tiempo_real_min
        if not tiempo:
            print("⚠️ No hay tiempo registrado. No se puede calcular carga.")
            return "SKIPPED"

        # --- A. CÁLCULO CARDÍACO (TRIMP) ---
        avg_hr = entreno.frecuencia_cardiaca_promedio
        if avg_hr:
            entreno.trimp = calcular_trimp(
                tiempo_min=tiempo,
                avg_hr=avg_hr,
                max_hr=alumno.fcm,
                rest_hr=alumno.fcreposo,
                es_hombre=True # TODO: En el futuro, leer 'sexo' del modelo Alumno
            )

        # --- B. CÁLCULO DE POTENCIA (TSS) ---
        avg_watts = entreno.potencia_promedio
        if avg_watts:
            entreno.tss, entreno.intensity_factor = calcular_tss_estimado(
                tiempo_min=tiempo,
                avg_power=avg_watts,
                ftp=alumno.ftp
            )
            # Kilojoules = Energía mecánica total
            entreno.kilojoules = int((avg_watts * tiempo * 60) / 1000)

        # --- C. CÁLCULO SUBJETIVO (RPE) ---
        rpe_load = calcular_load_rpe(tiempo, entreno.rpe)

        # 3. Determinar la Carga Final (Load)
        entreno.load_final = determinar_carga_final(entreno.tss, entreno.trimp, rpe_load)
        
        # 4. Guardar cambios en la base de datos
        entreno.save()
        
        print(f"✅ [ÉXITO] Carga calculada: {entreno.load_final} (TSS:{entreno.tss} | TRIMP:{entreno.trimp})")
        return f"OK Load: {entreno.load_final}"

    except Entrenamiento.DoesNotExist:
        return "ERROR: Entrenamiento no encontrado"
    except Exception as e:
        print(f"❌ ERROR CRÍTICO: {e}")
        return f"FAIL: {e}"