import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from core.tasks import procesar_actividad_strava 

logger = logging.getLogger(__name__)

# Token secreto de verificación (Scalable: Idealmente esto iría en settings.py/Variables de entorno en el futuro)
VERIFY_TOKEN = "MENDIETA_SECRET_TOKEN_2025"

@csrf_exempt 
@require_http_methods(["GET", "POST"])
def strava_webhook(request):
    
    # ==============================================================================
    #  1. HANDSHAKE (Verificación de Strava)
    #  Strava llama aquí primero para confirmar que el servidor es nuestro.
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
                return HttpResponse("Token de verificación inválido", status=403)
    
    # ==============================================================================
    #  2. RECEPCIÓN DE EVENTOS (POST) - El Motor de Ingesta
    # ==============================================================================
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extraemos metadatos clave
            object_type = data.get('object_type') # 'activity' o 'athlete'
            aspect_type = data.get('aspect_type') # 'create', 'update', 'delete'
            object_id = data.get('object_id')     # ID de la actividad en Strava (BigInt)
            owner_id = data.get('owner_id')       # ID del atleta en Strava

            print(f"📩 WEBHOOK RECIBIDO: {object_type} | {aspect_type} | ID: {object_id}")

            # FILTRO DE NEGOCIO:
            # Solo nos interesa importar actividades NUEVAS ('create').
            # Las actualizaciones ('update') se pueden manejar en una Fase 4 si se desea sincronizar ediciones.
            if object_type == 'activity' and aspect_type == 'create':
                print(f"🚀 Disparando tarea asíncrona para importar actividad {object_id}...")
                
                # --- [CORRECCIÓN CRÍTICA APLICADA] ---
                # Enviamos la tarea a la cola de Redis. Celery la tomará inmediatamente.
                procesar_actividad_strava.delay(object_id, owner_id) 

            # SIEMPRE responder 200 OK rápido a Strava (menos de 2s) o reintentarán enviarlo.
            return HttpResponse(status=200) 

        except Exception as e:
            # Logueamos el error real para auditoría, pero no crasheamos la respuesta HTTP
            logger.error(f"❌ Error crítico en Webhook: {str(e)}")
            print(f"❌ [WEBHOOK ERROR]: {str(e)}")
            return HttpResponse(status=500)

    return HttpResponse(status=404)