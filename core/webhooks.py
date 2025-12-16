import json
import logging
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from core.tasks import procesar_actividad_strava 

logger = logging.getLogger(__name__)

# OBTENEMOS EL TOKEN DE MANERA SEGURA DESDE SETTINGS
# Si no está en settings, usamos un fallback para que no crashee, pero avisamos.
VERIFY_TOKEN = getattr(settings, 'STRAVA_WEBHOOK_VERIFY_TOKEN', "MENDIETA_SECRET_TOKEN_2025")

@csrf_exempt 
@require_http_methods(["GET", "POST"])
def strava_webhook(request):
    """
    Manejador principal de Webhooks de Strava.
    Maneja:
    1. GET: Verificación de suscripción (Handshake).
    2. POST: Recepción de eventos (Actividades nuevas).
    """
    
    # ==============================================================================
    #  1. HANDSHAKE (Verificación de Strava - GET)
    # ==============================================================================
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                print("✅ WEBHOOK: Handshake con Strava exitoso.")
                return JsonResponse({"hub.challenge": challenge})
            else:
                print(f"⛔ Token inválido. Recibido: {token} | Esperado: {VERIFY_TOKEN}")
                return HttpResponse("Token de verificación inválido", status=403)
        
        # Si es GET pero no tiene los params correctos
        return HttpResponse("Faltan parámetros de verificación", status=400)

    # ==============================================================================
    #  2. RECEPCIÓN DE EVENTOS (POST)
    # ==============================================================================
    if request.method == 'POST':
        try:
            # Intentamos parsear el JSON
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return HttpResponse("JSON inválido", status=400)
            
            # Extraemos metadatos
            object_type = data.get('object_type') # 'activity' o 'athlete'
            aspect_type = data.get('aspect_type') # 'create', 'update', 'delete'
            object_id = data.get('object_id')     # ID de la actividad
            owner_id = data.get('owner_id')       # ID del atleta

            print(f"📩 WEBHOOK RECIBIDO: {object_type} | {aspect_type} | ID: {object_id}")

            # LÓGICA DE NEGOCIO: Solo procesamos ACTIVIDADES NUEVAS
            if object_type == 'activity' and aspect_type == 'create':
                print(f"🚀 [ACTION] Nueva actividad detectada ({object_id}). Disparando Celery...")
                
                # Disparar tarea asíncrona
                procesar_actividad_strava.delay(object_id, owner_id)
            else:
                print(f"ℹ️ [IGNORE] Evento ignorado: {object_type} / {aspect_type}")

            # IMPORTANTE: Siempre responder 200 OK a Strava para confirmar recepción
            return HttpResponse(status=200)

        except Exception as e:
            logger.error(f"❌ Error crítico en Webhook: {str(e)}")
            print(f"❌ [WEBHOOK ERROR]: {str(e)}")
            # Aún si falla nuestra lógica interna, respondemos 500 para alertar (o 200 si queremos evitar reintentos infinitos)
            return HttpResponse(status=500)

    # Si por alguna razón milagrosa llega aquí (no debería por el decorador), devolvemos 405
    return HttpResponse(status=405)