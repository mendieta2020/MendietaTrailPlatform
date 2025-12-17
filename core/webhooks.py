import json
import logging
import hashlib
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError

from core.models import StravaWebhookEvent
from core.tasks import process_strava_event

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
                logger.info("strava_webhook.handshake_ok")
                return JsonResponse({"hub.challenge": challenge})
            else:
                logger.warning("strava_webhook.handshake_invalid_token", extra={"received_token": token})
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
            
            # Extraemos metadatos (Strava canonical)
            object_type = data.get('object_type')  # 'activity' o 'athlete'
            aspect_type = data.get('aspect_type')  # 'create', 'update', 'delete'
            object_id = data.get('object_id')      # ID de la actividad
            owner_id = data.get('owner_id')        # ID del atleta
            subscription_id = data.get('subscription_id')
            event_time = data.get('event_time')

            # event_uid determinístico para idempotencia total.
            # Incluimos event_time si viene para diferenciar eventos legítimos sobre el mismo object_id.
            uid_payload = {
                "subscription_id": subscription_id,
                "owner_id": owner_id,
                "object_type": object_type,
                "object_id": object_id,
                "aspect_type": aspect_type,
                "event_time": event_time,
            }
            uid_raw = json.dumps(uid_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            event_uid = hashlib.sha256(uid_raw.encode("utf-8")).hexdigest()[:80]

            # Idempotencia (cero duplicados): si ya existe el evento, respondemos OK sin reprocesar.
            try:
                event, created = StravaWebhookEvent.objects.get_or_create(
                    event_uid=event_uid,
                    defaults={
                        "object_type": str(object_type or ""),
                        "object_id": int(object_id or 0),
                        "aspect_type": str(aspect_type or ""),
                        "owner_id": int(owner_id or 0),
                        "subscription_id": int(subscription_id) if subscription_id is not None else None,
                        "payload_raw": data,
                        "status": StravaWebhookEvent.Status.RECEIVED,
                    },
                )
            except IntegrityError:
                created = False
                event = StravaWebhookEvent.objects.filter(event_uid=event_uid).first()

            logger.info(
                "strava_webhook.received",
                extra={
                    "correlation_id": event_uid,
                    "object_type": object_type,
                    "aspect_type": aspect_type,
                    "object_id": object_id,
                    "owner_id": owner_id,
                    "created": created,
                },
            )

            if not created:
                return HttpResponse(status=200)

            # Thin endpoint: encolar y responder 200 ASAP.
            StravaWebhookEvent.objects.filter(pk=event.pk).update(status=StravaWebhookEvent.Status.QUEUED)
            process_strava_event.delay(event.pk)

            # IMPORTANTE: Siempre responder 200 OK a Strava para confirmar recepción
            return HttpResponse(status=200)

        except Exception as e:
            # Responder 200 evita reintentos masivos; el error queda auditado en logs.
            logger.exception("strava_webhook.error", extra={"error": str(e)})
            return HttpResponse(status=200)

    # Si por alguna razón milagrosa llega aquí (no debería por el decorador), devolvemos 405
    return HttpResponse(status=405)