from django.db import transaction
from django.utils import timezone
from allauth.socialaccount.models import SocialToken
from stravalib.client import Client
from .models import Entrenamiento, BloqueEntrenamiento, PasoEntrenamiento, Actividad
import sys
import datetime 
import time # Necesario para manejar timestamps de Strava

# ==============================================================================
#  1. LÓGICA DE CLONADO (INTACTA - CORE DEL NEGOCIO)
# ==============================================================================

def asignar_plantilla_a_alumno(plantilla, alumno, fecha):
    """
    Realiza una COPIA PROFUNDA (Deep Copy) de una plantilla de librería
    hacia el calendario de un alumno.
    """
    print(f"🚀 INICIANDO CLONADO: {plantilla.titulo} -> {alumno.nombre} ({fecha})")
    
    try:
        # Inicia una transacción segura
        with transaction.atomic():
            
            # A. Crear la "Cáscara" del Entrenamiento
            nuevo_entreno = Entrenamiento.objects.create(
                alumno=alumno,
                plantilla_origen=plantilla,
                fecha_asignada=fecha,
                titulo=plantilla.titulo,
                completado=False
            )
            print(f"   ✅ Entrenamiento creado ID: {nuevo_entreno.id}")
            
            # B. Clonar los Bloques
            bloques_origen = plantilla.bloques.all().order_by('orden')
            print(f"   ℹ️ Encontrados {bloques_origen.count()} bloques para copiar.")
            
            if bloques_origen.count() == 0:
                print("   ⚠️ ALERTA: La plantilla no tiene bloques. Se creó el entrenamiento vacío.")

            for bloque_orig in bloques_origen:
                nuevo_bloque = BloqueEntrenamiento.objects.create(
                    entrenamiento=nuevo_entreno,
                    plantilla=None, # Ya no es de librería
                    orden=bloque_orig.orden,
                    nombre_bloque=bloque_orig.nombre_bloque,
                    repeticiones=bloque_orig.repeticiones
                )
                
                # C. Clonar los Pasos
                pasos_origen = bloque_orig.pasos.all().order_by('orden')
                print(f"      ↳ Bloque '{bloque_orig.nombre_bloque}': Copiando {pasos_origen.count()} pasos.")
                
                for paso_orig in pasos_origen:
                    PasoEntrenamiento.objects.create(
                        bloque=nuevo_bloque,
                        orden=paso_orig.orden,
                        fase=paso_orig.fase,
                        titulo_paso=paso_orig.titulo_paso,
                        tipo_duracion=paso_orig.tipo_duracion,
                        valor_duracion=paso_orig.valor_duracion,
                        unidad_duracion=paso_orig.unidad_duracion,
                        objetivo=paso_orig.objetivo,
                        nota_paso=paso_orig.nota_paso
                    )
            
            print("✨ CLONADO FINALIZADO CON ÉXITO")
            return nuevo_entreno

    except Exception as e:
        print(f"❌ ERROR CRÍTICO EN CLONADO: {e}")
        raise e

# ==============================================================================
#  2. LÓGICA DE SINCRONIZACIÓN CON STRAVA (FIX TOKEN EXPIRADO)
# ==============================================================================

def obtener_cliente_strava(user):
    """
    Obtiene el cliente de Strava.
    MAGIA: Si el token está vencido, usa el refresh_token para pedir uno nuevo
    y actualiza la base de datos automáticamente.
    """
    try:
        # 1. Buscamos el token del usuario en la tabla de Allauth
        social_token = SocialToken.objects.filter(account__user=user, account__provider='strava').first()
        
        if not social_token:
            print(f"❌ No se encontró token de Strava para {user.username}")
            return None

        client = Client()
        
        # 2. Configuración inicial con lo que tenemos
        client.access_token = social_token.token
        client.refresh_token = social_token.token_secret
        
        # 3. VERIFICACIÓN DE CADUCIDAD (La parte clave)
        # Convertimos expires_at a timestamp o comparamos fechas
        token_expira_en = social_token.expires_at # Esto es un datetime timezone aware
        
        # Si existe fecha de expiración y HOY es mayor que la fecha de expiración...
        if token_expira_en and timezone.now() > token_expira_en:
            print(f"🔄 Token de {user.username} expirado. Renovando con Strava...")
            
            try:
                # Llamada a Strava para renovar
                refresh_response = client.refresh_access_token(
                    client_id=social_token.app.client_id,
                    client_secret=social_token.app.secret,
                    refresh_token=social_token.token_secret
                )
                
                # 4. ACTUALIZAMOS LA BASE DE DATOS
                social_token.token = refresh_response['access_token']
                social_token.token_secret = refresh_response['refresh_token']
                # Strava devuelve expires_at en timestamp (segundos epoch), convertimos a datetime
                social_token.expires_at = timezone.make_aware(
                    datetime.datetime.fromtimestamp(refresh_response['expires_at'])
                )
                social_token.save()
                
                # Actualizamos el cliente en memoria para usarlo YA
                client.access_token = social_token.token
                client.refresh_token = social_token.token_secret
                
                print("✅ Token renovado y guardado correctamente.")
                
            except Exception as e:
                print(f"❌ Error al intentar renovar el token: {e}")
                # Si falla la renovación, probablemente revocaron el permiso. Retornamos None.
                return None

        return client

    except Exception as e:
        print(f"Error general obteniendo token Strava: {e}")
    return None

def sincronizar_actividades_strava(user, limite=10):
    """
    Descarga las últimas actividades de Strava y las guarda en la Base de Datos local.
    Devuelve: (creadas, actualizadas, mensaje_estado)
    """
    # Usamos la función inteligente de arriba
    client = obtener_cliente_strava(user)
    
    if not client:
        return 0, 0, "Token inválido o expirado. Por favor, desconecta y vuelve a conectar Strava."

    nuevas = 0
    actualizadas = 0

    try:
        print(f"🔄 Sincronizando Strava para: {user.username}...")
        
        # Pedimos las actividades a la API de Strava
        # Nota: stravalib maneja la paginación, aquí pedimos las últimas 'limite'
        activities = client.get_activities(limit=limite)
        
        for activity in activities:
            
            # --- 1. SANEAMIENTO DE TIEMPO (Solución Robusta) ---
            tiempo_s = 0
            raw_time = activity.moving_time
            if raw_time:
                # Caso A: Objeto estándar con total_seconds (ej: timedelta)
                if hasattr(raw_time, 'total_seconds'):
                    tiempo_s = int(raw_time.total_seconds())
                # Caso B: Objeto raro de Strava/Pint con .seconds
                elif hasattr(raw_time, 'seconds'):
                    tiempo_s = int(raw_time.seconds)
                # Caso C: Ya es un número
                else:
                    try:
                        tiempo_s = int(raw_time)
                    except:
                        tiempo_s = 0
            
            # --- 2. SANEAMIENTO DE DISTANCIA ---
            distancia_m = 0.0
            if activity.distance:
                # Si tiene magnitud (es un objeto Pint), extraemos el valor
                if hasattr(activity.distance, 'magnitude'):
                    distancia_m = float(activity.distance.magnitude)
                else:
                    try:
                        distancia_m = float(activity.distance)
                    except:
                        pass

            # --- 3. SANEAMIENTO DE ELEVACIÓN ---
            elevacion_m = 0.0
            if activity.total_elevation_gain:
                if hasattr(activity.total_elevation_gain, 'magnitude'):
                    elevacion_m = float(activity.total_elevation_gain.magnitude)
                else:
                    try:
                        elevacion_m = float(activity.total_elevation_gain)
                    except:
                        pass
            
            # --- 4. MAPA (Polyline) ---
            mapa_str = None
            if activity.map and activity.map.summary_polyline:
                mapa_str = activity.map.summary_polyline

            # --- 5. BACKUP DE DATOS (Solución al error 'to_dict') ---
            datos_backup = {}
            try:
                # Intentamos diferentes métodos de serialización según la versión de la librería
                if hasattr(activity, 'model_dump'):
                    datos_backup = activity.model_dump()
                elif hasattr(activity, 'to_dict'):
                    datos_backup = activity.to_dict()
                else:
                    # Si todo falla, guardamos una representación string para no perder datos
                    datos_backup = {"info": str(activity)}
            except Exception:
                datos_backup = {"error": "No se pudo serializar el objeto"}

            # --- GUARDADO EN BASE DE DATOS ---
            # Usamos update_or_create para no duplicar si ya existe ese ID de Strava
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
                    'datos_brutos': datos_backup # JSON Crudo
                }
            )
            
            if created:
                nuevas += 1
            else:
                actualizadas += 1
        
        print(f"✅ Sincronización OK: {nuevas} nuevas, {actualizadas} actualizadas.")     
        return nuevas, actualizadas, "OK"

    except Exception as e:
        error_msg = f"Error técnico en sincronización: {str(e)}"
        print(f"❌ {error_msg}")
        # Si el error es de autorización (401), es probable que el refresh token fallara
        # o el usuario revocara acceso.
        return nuevas, actualizadas, error_msg