from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from allauth.socialaccount.models import SocialToken, SocialApp
from stravalib.client import Client
from .models import Alumno, Entrenamiento, BloqueEntrenamiento, PasoEntrenamiento, Actividad
import json 
import time
import datetime

# ==============================================================================
#  1. CLONADOR UNIVERSAL (EL NÚCLEO DE LA AUTOMATIZACIÓN)
# ==============================================================================

def copiar_estructura_plantilla(entrenamiento, plantilla):
    """
    Toma un entrenamiento (existente o recién creado) y le inyecta 
    una COPIA PROFUNDA (Deep Copy) de los bloques y pasos de la plantilla.
    Adapta la estructura nueva de objetivos flexibles (RPE, Zona VAM, Manual).
    """
    print(f"📋 Copiando estructura de '{plantilla.titulo}' a Entrenamiento ID {entrenamiento.id}")
    
    try:
        # 1. Limpieza previa (Evita duplicados si se edita y cambia la plantilla)
        entrenamiento.bloques_reales.all().delete()
        
        # 2. Clonado de Bloques
        bloques_origen = plantilla.bloques.all().order_by('orden')
        
        for bloque_orig in bloques_origen:
            nuevo_bloque = BloqueEntrenamiento.objects.create(
                entrenamiento=entrenamiento,
                plantilla=None, # Desvinculado para edición libre
                orden=bloque_orig.orden,
                nombre_bloque=bloque_orig.nombre_bloque,
                repeticiones=bloque_orig.repeticiones
            )
            
            # 3. Clonado de Pasos (NUEVA ESTRUCTURA FLEXIBLE)
            pasos_origen = bloque_orig.pasos.all().order_by('orden')
            for paso_orig in pasos_origen:
                PasoEntrenamiento.objects.create(
                    bloque=nuevo_bloque,
                    orden=paso_orig.orden,
                    fase=paso_orig.fase,
                    
                    # Datos de Tiempo/Distancia
                    tipo_duracion=paso_orig.tipo_duracion,
                    valor_duracion=paso_orig.valor_duracion,
                    unidad_duracion=paso_orig.unidad_duracion,
                    
                    # --- NUEVA LÓGICA DE OBJETIVOS (CORRECCIÓN CRÍTICA) ---
                    tipo_objetivo=paso_orig.tipo_objetivo,
                    objetivo_rpe=paso_orig.objetivo_rpe,
                    objetivo_zona_vam=paso_orig.objetivo_zona_vam,
                    objetivo_manual=paso_orig.objetivo_manual,
                    
                    # Textos y Multimedia
                    titulo_paso=paso_orig.titulo_paso,
                    nota_paso=paso_orig.nota_paso,
                    archivo_adjunto=paso_orig.archivo_adjunto, # Copia la referencia
                    enlace_url=paso_orig.enlace_url
                )
                
        # 4. Auto-completar título si no tiene uno
        if not entrenamiento.titulo or entrenamiento.titulo.strip() == "":
            entrenamiento.titulo = plantilla.titulo

        # 5. GUARDADO FINAL (EL GATILLO)
        entrenamiento.save()
        
    except Exception as e:
        print(f"❌ ERROR CRÍTICO EN COPIADO: {e}")
        raise e

# ==============================================================================
#  2. ASIGNACIÓN MASIVA (USA EL CLONADOR ACTUALIZADO)
# ==============================================================================

def asignar_plantilla_a_alumno(plantilla, alumno, fecha):
    """
    Crea la cáscara del entrenamiento y delega el copiado al Clonador Universal.
    Calcula ritmos personalizados al final.
    """
    print(f"🚀 INICIANDO CLONADO: {plantilla.titulo} -> {alumno.nombre} ({fecha})")
    
    try:
        with transaction.atomic():
            # A. Crear la cáscara vacía
            nuevo_entreno = Entrenamiento.objects.create(
                alumno=alumno,
                plantilla_origen=plantilla,
                fecha_asignada=fecha,
                titulo=plantilla.titulo,
                tipo_actividad=plantilla.deporte,
                descripcion_detallada=plantilla.descripcion_global, # Copiamos la descripción
                completado=False
            )
            
            # B. Inyectar contenido (Bloques/Pasos)
            copiar_estructura_plantilla(nuevo_entreno, plantilla)
            
            # C. Calcular Totales y Ritmos Personalizados (MAGIA DE VAM)
            nuevo_entreno.calcular_totales_desde_estructura()
            
            # Si el modelo tiene la función de ritmos personalizados, la ejecutamos
            if hasattr(nuevo_entreno, 'calcular_objetivos_personalizados'):
                nuevo_entreno.calcular_objetivos_personalizados()
                
            nuevo_entreno.save()
            
            return nuevo_entreno

    except Exception as e:
        print(f"❌ ERROR CRÍTICO EN ASIGNACIÓN: {e}")
        raise e

# ==============================================================================
#  3. EL JUEZ: LÓGICA DE CRUCE V2 (INTACTA)
# ==============================================================================

def ejecutar_cruce_inteligente(actividad):
    """
    Algoritmo 'El Juez' V2:
    1. Busca si la actividad YA estaba vinculada (Update).
    2. Si no, busca un plan PENDIENTE (Match).
    3. Califica cumplimiento (%).
    """
    print(f"⚖️  EL JUEZ: Evaluando actividad {actividad.strava_id} ({actividad.nombre})...")

    email_usuario = actividad.usuario.email
    alumno = Alumno.objects.filter(email=email_usuario).first()

    if not alumno:
        return False

    # --- BÚSQUEDA DUAL ---
    # 1. ¿Re-procesar existente? (Prioridad a lo ya vinculado)
    entrenamiento_objetivo = Entrenamiento.objects.filter(strava_id=str(actividad.strava_id)).first()

    if entrenamiento_objetivo:
        print(f"   🔄 Re-procesando: {entrenamiento_objetivo.titulo}")
    else:
        # 2. ¿Nuevo Match? (Buscar por fecha y estado pendiente)
        fecha_actividad = actividad.fecha_inicio.date()
        entrenamiento_objetivo = Entrenamiento.objects.filter(
            alumno=alumno,
            fecha_asignada=fecha_actividad,
            completado=False 
        ).first()

    if not entrenamiento_objetivo:
        return False

    # --- FUSIÓN ---
    try:
        with transaction.atomic():
            if not entrenamiento_objetivo.strava_id:
                print(f"   🔥 ¡NUEVO MATCH! Vinculando con: {entrenamiento_objetivo.titulo}")
            
            # 1. Datos Reales (Normalizados)
            dist_real_km = round(actividad.distancia / 1000, 2)
            tiempo_real_min = int(actividad.tiempo_movimiento / 60)
            
            entrenamiento_objetivo.distancia_real_km = dist_real_km
            entrenamiento_objetivo.tiempo_real_min = tiempo_real_min
            entrenamiento_objetivo.desnivel_real_m = int(actividad.desnivel_positivo)
            entrenamiento_objetivo.strava_id = str(actividad.strava_id)
            # Guardamos fecha real por si difiere de la asignada
            # (No tenemos campo fecha_ejecucion en el modelo actual, usamos la asignada o creamos uno si quieres)
            
            # 2. SCORE DE CUMPLIMIENTO
            cumplimiento = 0
            
            # Prioridad A: Comparar por Distancia
            if entrenamiento_objetivo.distancia_planificada_km and entrenamiento_objetivo.distancia_planificada_km > 0:
                cumplimiento = (dist_real_km / entrenamiento_objetivo.distancia_planificada_km) * 100
            
            # Prioridad B: Comparar por Tiempo
            elif entrenamiento_objetivo.tiempo_planificado_min and entrenamiento_objetivo.tiempo_planificado_min > 0:
                cumplimiento = (tiempo_real_min / entrenamiento_objetivo.tiempo_planificado_min) * 100
            
            # Prioridad C: Entrenamiento libre
            else:
                cumplimiento = 100 
            
            # Límite lógico visual (max 120%)
            if cumplimiento > 120: cumplimiento = 120
            entrenamiento_objetivo.porcentaje_cumplimiento = int(cumplimiento)

            # 3. Sensores (Si existen en el JSON)
            raw = actividad.datos_brutos
            if 'average_watts' in raw:
                entrenamiento_objetivo.potencia_promedio = int(raw['average_watts'])
            if 'average_heartrate' in raw:
                entrenamiento_objetivo.frecuencia_cardiaca_promedio = int(raw['average_heartrate'])

            # 4. Guardar y Calcular Métricas Fisiológicas
            entrenamiento_objetivo.completado = True
            entrenamiento_objetivo.save()

            # Llamada asíncrona (simulada aquí) a la calculadora de TSS/TRIMP
            from .tasks import procesar_metricas_entrenamiento
            procesar_metricas_entrenamiento(entrenamiento_objetivo.id)
            
            print(f"   ✅ Fusión Exitosa. Score: {entrenamiento_objetivo.porcentaje_cumplimiento}%")
            return True

    except Exception as e:
        print(f"   ❌ Error fusión: {e}")
        return False

# ==============================================================================
#  4. SYNC STRAVA (INTACTO)
# ==============================================================================

def obtener_cliente_strava(user):
    try:
        social_token = SocialToken.objects.filter(account__user=user, account__provider='strava').first()
        if not social_token: return None

        client = Client()
        client.access_token = social_token.token
        client.refresh_token = social_token.token_secret
        
        token_expira_en = social_token.expires_at 
        if token_expira_en and timezone.now() > token_expira_en:
            app_config = social_token.app
            if not app_config:
                app_config = SocialApp.objects.filter(provider='strava').first()
                if app_config:
                    social_token.app = app_config
                    social_token.save()
            if not app_config: return None

            try:
                refresh_response = client.refresh_access_token(
                    client_id=app_config.client_id,
                    client_secret=app_config.secret,
                    refresh_token=social_token.token_secret
                )
                social_token.token = refresh_response['access_token']
                social_token.token_secret = refresh_response['refresh_token']
                social_token.expires_at = timezone.make_aware(datetime.datetime.fromtimestamp(refresh_response['expires_at']))
                social_token.save()
                
                client.access_token = social_token.token
                client.refresh_token = social_token.token_secret
            except: return None
        return client
    except: return None

def sincronizar_actividades_strava(user, dias_historial=None):
    client = obtener_cliente_strava(user)
    if not client: return 0, 0, "Token inválido."

    nuevas = 0
    actualizadas = 0

    try:
        print(f"🔄 Sincronizando Strava para: {user.username}...")
        
        if dias_historial:
            start_time = timezone.now() - datetime.timedelta(days=dias_historial)
            print(f"   📅 Modo Historia: Buscando desde {start_time.date()}")
            activities = client.get_activities(after=start_time)
        else:
            activities = client.get_activities(limit=10)

        for activity in activities:
            tiempo_s = 0
            raw_time = activity.moving_time
            if raw_time:
                try: 
                    if hasattr(raw_time, 'total_seconds'): tiempo_s = int(raw_time.total_seconds())
                    elif hasattr(raw_time, 'seconds'): tiempo_s = int(raw_time.seconds)
                    else: tiempo_s = int(raw_time)
                except: tiempo_s = 0
            
            distancia_m = 0.0
            if activity.distance:
                try:
                    if hasattr(activity.distance, 'magnitude'): distancia_m = float(activity.distance.magnitude)
                    else: distancia_m = float(activity.distance)
                except: pass

            elevacion_m = 0.0
            if activity.total_elevation_gain:
                try:
                    if hasattr(activity.total_elevation_gain, 'magnitude'): elevacion_m = float(activity.total_elevation_gain.magnitude)
                    else: elevacion_m = float(activity.total_elevation_gain)
                except: pass
            
            mapa_str = activity.map.summary_polyline if activity.map else None

            datos_backup = {}
            try:
                if hasattr(activity, 'to_dict'): raw_data = activity.to_dict()
                elif hasattr(activity, 'model_dump'): raw_data = activity.model_dump()
                else: raw_data = {"info": str(activity)}
                datos_backup = json.loads(json.dumps(raw_data, cls=DjangoJSONEncoder))
            except: datos_backup = {}

            obj, created = Actividad.objects.update_or_create(
                strava_id=activity.id, 
                defaults={
                    'usuario': user,
                    'nombre': activity.name,
                    'distancia': distancia_m,
                    'tiempo_movimiento': tiempo_s,
                    'fecha_inicio': activity.start_date_local,
                    'tipo_deporte': activity.type,
                    'desnivel_positivo': elevacion_m,
                    'mapa_polilinea': mapa_str,
                    'datos_brutos': datos_backup
                }
            )
            
            ejecutar_cruce_inteligente(obj)

            if created: nuevas += 1
            else: actualizadas += 1
        
        if dias_historial:
             from analytics.utils import recalcular_historial_completo
             alumno = Alumno.objects.filter(email=user.email).first()
             if alumno:
                 recalcular_historial_completo(alumno)

        print(f"✅ Sincronización OK: {nuevas} nuevas, {actualizadas} actualizadas.")     
        return nuevas, actualizadas, "OK"

    except Exception as e:
        error_msg = f"Error técnico: {str(e)}"
        print(f"❌ {error_msg}")
        return nuevas, actualizadas, error_msg