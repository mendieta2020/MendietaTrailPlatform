import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from core.tasks import procesar_actividad_strava

VERIFY_TOKEN = "MENDIETA_SECRET_TOKEN_2025"

@csrf_exempt
@require_http_methods(["GET", "POST"])
def strava_webhook(request):
    # 1. HANDSHAKE
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return JsonResponse({"hub.challenge": challenge})
        return HttpResponse("Token inválido", status=403)
    
    # 2. EVENTOS
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print(f"📨 [WEBHOOK] Payload crudo: {data}") # Debug visual
            
            if data.get('object_type') == 'activity' and data.get('aspect_type') == 'create':
                obj_id = data.get('object_id')
                owner_id = data.get('owner_id')
                print(f"🚀 [WEBHOOK] Disparando tarea Celery para ID: {obj_id}")
                # Llamada al Worker
                procesar_actividad_strava.delay(obj_id, owner_id)
            
            return HttpResponse(status=200)
        except Exception as e:
            print(f"❌ [WEBHOOK ERROR] {e}")
            return HttpResponse(status=500)
            
    return HttpResponse(status=404)