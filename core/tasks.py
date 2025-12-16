from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
import openai
import logging
import traceback
from .models import Entrenamiento, Alumno, InscripcionCarrera
from analytics.models import HistorialFitness 

# Logger profesional para monitoreo (Sentry/Datadog ready)
logger = logging.getLogger(__name__)

# Importación segura de métricas (Fail-safe architecture)
try:
    from .metrics import (
        calcular_trimp, 
        calcular_tss_estimado, # Legacy support
        calcular_load_rpe, 
        determinar_carga_final,
        # Fase 4: Trail Science
        calcular_pendiente,
        calcular_gap_minetti,
        calcular_tss_gap,
        calcular_tss_power,
        velocidad_a_pace
    )
except ImportError:
    logger.error("Error importando métricas científicas. El sistema usará valores por defecto.")
    pass

# --- UTILIDADES INTERNAS (ROBUST DATA EXTRACTION) ---

def safe_duration_minutes(obj_duration):
    """Extrae minutos de cualquier objeto de tiempo de forma segura."""
    if not obj_duration: return 0
    try:
        if hasattr(obj_duration, 'total_seconds'): return int(obj_duration.total_seconds() / 60)
        if hasattr(obj_duration, 'seconds'): return int(obj_duration.seconds / 60)
        return int(float(obj_duration) / 60)
    except: return 0

def safe_float_value(obj_metric):
    """Extrae float de objetos con unidades (pint library compat)."""
    if not obj_metric: return 0.0
    try:
        if hasattr(obj_metric, 'magnitude'): return float(obj_metric.magnitude)
        return float(obj_metric)
    except: return 0.0

def map_strava_type_internal(strava_type):
    """Mapeo estándar de tipos de actividad Strava -> Mendieta."""
    st = str(strava_type).upper()
    if 'RUN' in st: return 'RUN'
    if 'RIDE' in st or 'EBIKE' in st: return 'CYCLING'
    if 'SWIM' in st: return 'SWIMMING'
    if 'WEIGHT' in st or 'CROSSFIT' in st: return 'STRENGTH'
    if 'HIKE' in st or 'WALK' in st: return 'TRAIL'
    if 'VIRTUALRIDE' in st: return 'INDOOR_BIKE'
    return 'OTHER'

# ==============================================================================
#  TAREA 1: MOTOR DE CÁLCULO (CIENCIA TRAIL V2)
# ==============================================================================
@shared_task
def procesar_metricas_entrenamiento(entrenamiento_id):
    try:
        entreno = Entrenamiento.objects.select_related('alumno').get(pk=entrenamiento_id)
        alumno = entreno.alumno
        logger.info(f"🧮 [CIENCIA TRAIL] Procesando: {entreno.titulo} (ID: {entreno.id})")

        tiempo_min = entreno.tiempo_real_min
        distancia_km = entreno.distancia_real_km
        desnivel_m = entreno.desnivel_real_m or 0
        
        if not tiempo_min or tiempo_min <= 0:
            logger.warning(f"⚠️ [SKIP] ID {entreno.id}: Sin tiempo registrado.")
            return "SKIPPED"

        # --- A. CÁLCULOS FISIOLÓGICOS BÁSICOS ---
        # 1. TRIMP (Carga Cardíaca)
        if entreno.frecuencia_cardiaca_promedio:
            entreno.trimp = calcular_trimp(
                tiempo_min, entreno.frecuencia_cardiaca_promedio, 
                alumno.fcm, alumno.fcreposo
            )

        # --- B. CÁLCULOS ESPECÍFICOS (POTENCIA vs GAP) ---
        tss_calculado = 0
        if_calculado = 0

        # Caso 1: Hay Potencia Real (Prioridad Absoluta - Stryd/Garmin)
        if entreno.potencia_promedio:
            tss_calculado, if_calculado = calcular_tss_power(
                tiempo_min, entreno.potencia_promedio, alumno.ftp
            )
            entreno.kilojoules = int((entreno.potencia_promedio * tiempo_min * 60) / 1000)
            logger.info(f"   ⚡ Potencia: {entreno.potencia_promedio}w | TSS Power: {tss_calculado}")
        
        # Caso 2: Trail Running sin Potencia (Usamos GAP + Minetti)
        elif distancia_km and distancia_km > 0:
            # 1. Calcular variables del terreno
            ritmo_real_seg_km = (tiempo_min * 60) / distancia_km
            pendiente = calcular_pendiente(distancia_km * 1000, desnivel_m)
            
            # 2. Aplicar MINETTI (Aplanar la montaña)
            gap_seg_km = calcular_gap_minetti(ritmo_real_seg_km, pendiente)
            
            # 3. Obtener Umbral del Alumno (VAM/UANAE)
            umbral_velocidad = alumno.velocidad_uanae or alumno.vam_actual
            if umbral_velocidad > 0:
                umbral_ritmo = velocidad_a_pace(umbral_velocidad)
            else:
                umbral_ritmo = 240 # Placeholder: 4:00 min/km

            # 4. Calcular rTSS basado en GAP
            tss_calculado, if_calculado = calcular_tss_gap(tiempo_min, gap_seg_km, umbral_ritmo)
            
            logger.info(f"   ⛰️ Trail Data: Pendiente {pendiente:.1f}% | GAP {int(gap_seg_km)}s/km | rTSS {tss_calculado}")

        # --- C. GUARDADO INTELIGENTE ---
        if tss_calculado > 0:
            entreno.tss = tss_calculado
            entreno.intensity_factor = if_calculado

        rpe_load = calcular_load_rpe(tiempo_min, entreno.rpe)
        entreno.load_final = determinar_carga_final(entreno.tss, entreno.tss, entreno.trimp, rpe_load)
        
        # --- D. ACTUALIZACIÓN DE CARRERA (EVENTO FINALIZADO) ---
        # Si este entreno es el día de una carrera inscrita, cerramos el ciclo.
        try:
            carrera_match = InscripcionCarrera.objects.filter(
                alumno=alumno, 
                carrera__fecha__range=[
                    entreno.fecha_asignada - timezone.timedelta(days=1), 
                    entreno.fecha_asignada + timezone.timedelta(days=1)
                ]
            ).first()
            
            if carrera_match:
                carrera_match.estado = 'FINALIZADO'
                carrera_match.tiempo_oficial = timezone.timedelta(minutes=tiempo_min)
                # Aquí podríamos guardar feedback automático en la inscripción
                carrera_match.save()
                logger.info(f"   🏅 Carrera '{carrera_match.carrera.nombre}' finalizada automáticamente.")
        except Exception as e:
            logger.error(f"Error actualizando carrera: {e}")

        entreno.save()
        print(f"✅ [RESULTADO] Carga Final: {entreno.load_final:.1f}")
        return "OK"

    except Exception as e:
        print(f"❌ [ERROR CIENCIA]: {e}")
        traceback.print_exc()
        return "FAIL"

# ==============================================================================
#  TAREA 2: ENTRENADOR IA (LLM - CEREBRO CUALITATIVO)
# ==============================================================================
@shared_task
def generar_feedback_ia(entrenamiento_id):
    if not settings.OPENAI_API_KEY: return "SKIPPED"
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    try:
        entreno = Entrenamiento.objects.select_related('alumno').get(pk=entrenamiento_id)
        fitness = HistorialFitness.objects.filter(alumno=entreno.alumno).order_by('-fecha').first()
        tsb = fitness.tsb if fitness else 0
        
        # Contexto Trail Avanzado
        contexto_trail = ""
        km_esfuerzo = entreno.distancia_real_km
        if entreno.desnivel_real_m and entreno.desnivel_real_m > 0:
            km_esfuerzo += (entreno.desnivel_real_m / 100) # Regla ITRA
            contexto_trail = f"Desnivel: +{entreno.desnivel_real_m}m. Km-Esfuerzo: {km_esfuerzo:.1f}km."

        prompt = f"""
        Actúa como entrenador de Trail Running experto. Analiza para {entreno.alumno.nombre}:
        - Sesión: {entreno.titulo} ({entreno.distancia_real_km}km en {entreno.tiempo_real_min}min).
        - {contexto_trail}
        - Carga (TSS): {entreno.tss} | Fatiga (TSB): {tsb:.1f}
        
        Dame un feedback de 1 frase motivadora y 1 consejo técnico específico (nutrición/bajada/subida). Usa emojis.
        """
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        entreno.feedback_ia = response.choices[0].message.content
        entreno.save()
        return "OK IA"
    except Exception as e:
        print(f"❌ [ERROR IA]: {e}")
        return "FAIL IA"

# ==============================================================================
#  TAREA 3: INGESTA DE DATOS (STRAVA BLINDADO & SCALABLE)
# ==============================================================================
@shared_task(bind=True, max_retries=3)
def procesar_actividad_strava(self, object_id, owner_id):
    from .services import obtener_cliente_strava

    print(f"⚙️ [CELERY] Ingesta Strava ID: {object_id}")
    
    try:
        try:
            alumno = Alumno.objects.get(strava_athlete_id=str(owner_id))
        except Alumno.DoesNotExist:
            print(f"⚠️ [SKIP] Atleta {owner_id} desconocido.")
            return "SKIP: Unknown Athlete"

        client = obtener_cliente_strava(alumno.entrenador)
        if not client: return "FAIL: Auth"

        # Descarga con manejo de Rate Limits
        try:
            activity = client.get_activity(object_id)
        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str: return "SKIP: 404"
            if "429" in error_str: raise self.retry(countdown=900)
            raise e

        # --- EXTRACCIÓN SEGURA ---
        tipo_act = map_strava_type_internal(activity.type)
        tiempo_min = safe_duration_minutes(activity.moving_time)
        dist_km = round(safe_float_value(activity.distance) / 1000, 2)
        desnivel_m = int(safe_float_value(activity.total_elevation_gain))
        hr_avg = int(activity.average_heartrate) if hasattr(activity, 'average_heartrate') and activity.average_heartrate else 0
        watts_avg = int(activity.average_watts) if hasattr(activity, 'average_watts') and activity.average_watts else 0
        fecha = activity.start_date_local.date()

        # --- SMART MATCHING (EL JUEZ) ---
        entreno = Entrenamiento.objects.filter(strava_id=str(object_id)).first()
        accion = "ACTUALIZADO"

        if not entreno:
            # Buscamos si había algo planificado para hoy que coincida
            entreno = Entrenamiento.objects.filter(alumno=alumno, fecha_asignada=fecha, completado=False).first()
            if entreno: accion = "VINCULADO (MATCH)"

        if not entreno:
            # LÓGICA DE "NO PLANIFICADO" (N/A)
            print(f"✨ [NUEVO] Actividad no planificada detectada.")
            entreno = Entrenamiento(alumno=alumno, fecha_asignada=fecha, titulo=activity.name)
            accion = "CREADO (No Planificado)"

        # --- GUARDAR DATOS REALES ---
        entreno.strava_id = str(object_id)
        entreno.completado = True
        entreno.tipo_actividad = tipo_act
        entreno.distancia_real_km = dist_km
        entreno.tiempo_real_min = tiempo_min
        entreno.desnivel_real_m = desnivel_m
        entreno.frecuencia_cardiaca_promedio = hr_avg
        entreno.potencia_promedio = watts_avg
        
        # Si es nuevo o no tenía título, usamos el de Strava
        if accion.startswith("CREADO") or entreno.titulo == "Entrenamiento":
            entreno.titulo = activity.name

        entreno.save()
        print(f"💾 [DB] {accion}: {entreno.titulo}")

        # --- DISPARAR CASCADA CIENTÍFICA ---
        # 1. Calcular TSS/GAP/TRIMP
        procesar_metricas_entrenamiento.delay(entreno.id)
        # 2. Generar Feedback IA
        generar_feedback_ia.delay(entreno.id)
        
        return f"SUCCESS: {accion}"

    except Exception as e:
        print(f"❌ [CRITICAL TASK ERROR]: {str(e)}")
        # No relanzamos para no matar al worker, pero logueamos fuerte
        return f"FAIL: {str(e)}"