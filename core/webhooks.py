import json
import logging
import hashlib
import time
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from core.models import StravaWebhookEvent
from core.tasks import process_strava_event
from core.models import ExternalIdentity

logger = logging.getLogger(__name__)

# Token de verificación para el handshake (GET).
# En prod debe venir desde settings/env; en dev permitimos un fallback para no romper local.
_CONFIGURED_VERIFY_TOKEN = getattr(settings, "STRAVA_WEBHOOK_VERIFY_TOKEN", None)
VERIFY_TOKEN = _CONFIGURED_VERIFY_TOKEN or ("MENDIETA_SECRET_TOKEN_2025" if getattr(settings, "DEBUG", False) else None)

# Validación opcional de subscription_id en POST (hardening sin romper dev):
# si se define `STRAVA_WEBHOOK_SUBSCRIPTION_ID`, solo aceptamos eventos de esa suscripción.
EXPECTED_SUBSCRIPTION_ID = getattr(settings, "STRAVA_WEBHOOK_SUBSCRIPTION_ID", None)


def _truncate_error(message: str, limit: int = 300) -> str:
    return (message or "")[:limit]


def _mark_event_failed(event: StravaWebhookEvent, *, error: Exception | str, attempts_increment: bool = True):
    last_error = _truncate_error(str(error))
    updates = {
        "status": StravaWebhookEvent.Status.FAILED,
        "last_error": last_error,
        "last_attempt_at": timezone.now(),
    }
    if attempts_increment:
        updates["attempts"] = F("attempts") + 1
    StravaWebhookEvent.objects.filter(pk=event.pk).update(**updates)
    logger.warning(
        "strava.webhook.event_failed",
        extra={
            "event_uid": event.event_uid,
            "event_id": event.pk,
            "owner_id": event.owner_id,
            "object_id": event.object_id,
            "status": StravaWebhookEvent.Status.FAILED,
        },
    )
    StravaWebhookEvent.objects.log_failed_threshold(logger=logger)

def _allow_simulation() -> bool:
    """
    Modo simulación local:
    - True si DEBUG=True
    - True si STRAVA_WEBHOOK_ALLOW_SIMULATION=True
    En prod debe habilitarse explícitamente (o dejar DEBUG=False).
    """
    return bool(getattr(settings, "STRAVA_WEBHOOK_ALLOW_SIMULATION", False)) or bool(
        getattr(settings, "DEBUG", False)
    )


def _extract_charset(content_type: str | None) -> str | None:
    """
    Extrae charset=... de Content-Type (si existe).
    Ej: application/json; charset=utf-16
    """
    if not content_type:
        return None
    parts = [p.strip() for p in content_type.split(";") if p.strip()]
    for p in parts[1:]:
        if p.lower().startswith("charset="):
            return p.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _body_preview(raw: bytes, limit: int = 2048) -> str:
    """
    Preview seguro para logs/respuestas: intenta utf-8 (con reemplazo).
    """
    if raw is None:
        return ""
    chunk = raw[:limit]
    try:
        return chunk.decode("utf-8", errors="replace")
    except Exception:
        # Fallback ultra-defensivo
        return repr(chunk)


def parse_strava_payload(request):
    """
    Parseo robusto para payloads JSON de Strava.
    - Soporta charset explícito (PowerShell suele enviar UTF-16)
    - No relaja validaciones de producción (content-type)
    Devuelve: (payload_dict, meta_dict)
    """
    content_type = request.META.get("CONTENT_TYPE") or request.headers.get("Content-Type")
    raw = request.body or b""
    allow_simulation = _allow_simulation()

    meta = {
        "content_type": content_type,
        "raw_len": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
    }

    if not raw:
        raise ValueError("empty_body")

    # En producción solo aceptamos JSON explícito.
    is_json_ct = bool(content_type) and (
        content_type.lower().startswith("application/json")
        or content_type.lower().startswith("application/") and "+json" in content_type.lower()
    )
    if not is_json_ct and not allow_simulation:
        raise ValueError("unsupported_content_type")

    # Probar decodificaciones (priorizando charset del request).
    charset = _extract_charset(content_type)
    preferred = []
    if charset:
        preferred.append(charset)
    if getattr(request, "encoding", None):
        preferred.append(request.encoding)

    # Order matters: utf-8/utf-8-sig primero, luego variantes comunes de PowerShell.
    candidates = []
    for enc in preferred + ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"]:
        if enc and enc not in candidates:
            candidates.append(enc)

    last_decode_error = None
    last_json_error = None
    for enc in candidates:
        try:
            text = raw.decode(enc)
        except Exception as e:
            last_decode_error = (enc, str(e))
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            last_json_error = (enc, str(e))
            continue

        if not isinstance(parsed, dict):
            raise ValueError("json_not_object")

        meta.update({"decoded_as": enc})
        return parsed, meta

    # Si no pudimos parsear, devolvemos razón detallada (para logs / modo simulación).
    reason = "invalid_json"
    details = {
        "reason": reason,
        "charset": charset,
        "decode_error": last_decode_error,
        "json_error": last_json_error,
    }
    raise ValueError(json.dumps(details, ensure_ascii=False))

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
            if VERIFY_TOKEN is None:
                logger.error("strava_webhook.handshake_misconfigured_no_verify_token")
                return HttpResponse("Webhook misconfigured", status=500)
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                logger.info("strava_webhook.handshake_ok")
                return JsonResponse({"hub.challenge": challenge})
            else:
                # No loggear tokens/secretos (seguridad).
                logger.warning("strava_webhook.handshake_invalid_token")
                return HttpResponse("Token de verificación inválido", status=403)
        
        # Si es GET pero no tiene los params correctos
        return HttpResponse("Faltan parámetros de verificación", status=400)

    # ==============================================================================
    #  2. RECEPCIÓN DE EVENTOS (POST)
    # ==============================================================================
    if request.method == 'POST':
        t0 = time.monotonic()
        event = None
        created = False
        try:
            # Intentamos parsear el JSON (robusto: soporta UTF-16 en simulaciones locales).
            try:
                data, parse_meta = parse_strava_payload(request)
            except ValueError as e:
                raw = request.body or b""
                error_reason = str(e)
                allow_simulation = _allow_simulation()
                logger.warning(
                    "strava_webhook.invalid_payload",
                    extra={
                        "error_reason": error_reason,
                        "content_type": request.META.get("CONTENT_TYPE") or request.headers.get("Content-Type"),
                        "raw_len": len(raw),
                        "raw_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
                        "raw_body_preview": _body_preview(raw),
                        "allow_simulation": allow_simulation,
                    },
                )
                # En modo simulación (o DEBUG) devolvemos detalle útil; en prod mantenemos mensaje genérico.
                if allow_simulation:
                    return JsonResponse(
                        {
                            "detail": "Invalid JSON payload",
                            "error_reason": error_reason,
                            "content_type": request.META.get("CONTENT_TYPE") or request.headers.get("Content-Type"),
                            "raw_len": len(raw),
                            "raw_body_preview": _body_preview(raw),
                        },
                        status=400,
                    )
                return HttpResponse("JSON inválido", status=400)

            # Logs útiles (sin exponer full body en prod)
            allow_simulation = _allow_simulation()
            logger.info(
                "strava_webhook.payload_parsed",
                extra={
                    "content_type": parse_meta.get("content_type"),
                    "decoded_as": parse_meta.get("decoded_as"),
                    "raw_len": parse_meta.get("raw_len"),
                    "raw_sha256": parse_meta.get("raw_sha256"),
                    "raw_body_preview": _body_preview(request.body or b"") if allow_simulation else None,
                    "parsed_payload": data if allow_simulation else None,
                },
            )
            
            # Extraemos metadatos (Strava canonical)
            object_type = data.get('object_type')  # 'activity' o 'athlete'
            aspect_type = data.get('aspect_type')  # 'create', 'update', 'delete'
            object_id = data.get('object_id')      # ID de la actividad
            owner_id = data.get('owner_id')        # ID del atleta
            subscription_id = data.get('subscription_id')
            event_time = data.get('event_time')

            if object_type is None or aspect_type is None or object_id is None or owner_id is None:
                return HttpResponse("Payload inválido", status=400)

            try:
                object_id_int = int(object_id)
                owner_id_int = int(owner_id)
            except (TypeError, ValueError):
                return HttpResponse("Payload inválido", status=400)

            # Hardening PR1: Fail-closed verification of subscription_id.
            # We MUST access settings at runtime to support override_settings in tests and hot-reloads.
            configured_sub_id = getattr(settings, "STRAVA_WEBHOOK_SUBSCRIPTION_ID", None)

            if configured_sub_id is None:
                # User requested fail-closed but ACK (200 OK) so Strava doesn't retry forever.
                logger.critical("strava_webhook.fail_closed_missing_config_subscription_id")
                return JsonResponse({"ok": True, "ignored": "missing_subscription_config"})

            # Ensure strict string comparison to avoid type coercion issues
            if str(subscription_id) != str(configured_sub_id):
                logger.warning(
                    "strava_webhook.subscription_mismatch",
                    extra={
                        "status": "discarded",
                        "reason": "subscription_mismatch",
                        "received_subscription_id": subscription_id,
                        "expected_subscription_id": configured_sub_id,
                    },
                )
                return HttpResponse(status=403)

            # event_uid determinístico para idempotencia total.
            # Incluimos event_time si viene para diferenciar eventos legítimos sobre el mismo object_id.
            uid_payload = {
                "subscription_id": subscription_id,
                "owner_id": owner_id_int,
                "object_type": object_type,
                "object_id": object_id_int,
                "aspect_type": aspect_type,
                "event_time": event_time,
            }
            uid_raw = json.dumps(uid_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            event_uid = hashlib.sha256(uid_raw.encode("utf-8")).hexdigest()[:80]

            # Idempotencia (cero duplicados): si ya existe el evento, respondemos OK sin reprocesar.
            try:
                event, created = StravaWebhookEvent.objects.get_or_create(
                    provider="strava",
                    event_uid=event_uid,
                    defaults={
                        "object_type": str(object_type or ""),
                        "object_id": object_id_int,
                        "aspect_type": str(aspect_type or ""),
                        "owner_id": owner_id_int,
                        "subscription_id": int(subscription_id) if subscription_id is not None else None,
                        "event_time": int(event_time) if event_time is not None else None,
                        "payload_raw": data,
                        "status": StravaWebhookEvent.Status.RECEIVED,
                    },
                )
            except IntegrityError:
                created = False
                event = StravaWebhookEvent.objects.filter(provider="strava", event_uid=event_uid).first()
                # Si falló por integridad pero no pudimos recuperar el evento, tratamos como fallo de persistencia
                # y devolvemos 500 para que Strava reintente (hardening Semana 1).
                if event is None:
                    logger.exception(
                        "strava_webhook.event_persist_failed_integrity_no_event",
                        extra={"event_uid": event_uid, "athlete_id": owner_id, "activity_id": object_id},
                    )
                    return HttpResponse(status=500)
            except Exception:
                # Falla de persistencia inicial (DB down/timeout/etc): devolvemos 500 para forzar retry de Strava.
                logger.exception(
                    "strava_webhook.event_persist_failed",
                    extra={"event_uid": event_uid, "athlete_id": owner_id, "activity_id": object_id},
                )
                return HttpResponse(status=500)

            duration_ms = int((time.monotonic() - t0) * 1000)

            if not created:
                # Registrar duplicado (no reprocesar) y responder 200 igual (Strava-friendly).
                if event:
                    StravaWebhookEvent.objects.filter(pk=event.pk).update(
                        duplicate_count=F("duplicate_count") + 1,
                        last_duplicate_at=timezone.now(),
                    )
                    if event.status in {
                        StravaWebhookEvent.Status.RECEIVED,
                        StravaWebhookEvent.Status.FAILED,
                    }:
                        try:
                            StravaWebhookEvent.objects.filter(pk=event.pk).update(
                                status=StravaWebhookEvent.Status.QUEUED,
                                last_error="",
                                error_message="",
                                discard_reason="",
                            )
                            process_strava_event.delay(event.pk)
                            logger.info(
                                "strava_webhook.outcome",
                                extra={
                                    "event_uid": event_uid,
                                    "correlation_id": str(getattr(event, "correlation_id", "") or ""),
                                    "athlete_id": owner_id_int,
                                    "activity_id": object_id_int,
                                    "status": "requeued",
                                    "reason": "event_uid_retry",
                                    "attempt": 0,
                                    "duration_ms": duration_ms,
                                },
                            )
                            return HttpResponse(status=200)
                        except Exception as exc:
                            _mark_event_failed(event, error=exc)
                            return HttpResponse(status=503)
                logger.info(
                    "strava_webhook.outcome",
                    extra={
                        "event_uid": event_uid,
                        "correlation_id": str(getattr(event, "correlation_id", "") or ""),
                        "athlete_id": owner_id_int,
                        "activity_id": object_id_int,
                        "status": "duplicate",
                        "reason": "event_uid_already_seen",
                        "attempt": 0,
                        "duration_ms": duration_ms,
                    },
                )
                return HttpResponse(status=200)

            # Canonical identity seed: siempre creamos/actualizamos la identidad externa,
            # aunque todavía no exista `Alumno` (evita pérdida de eventos y habilita linking posterior).
            try:
                if owner_id is not None:
                    ExternalIdentity.objects.get_or_create(
                        provider="strava",
                        external_user_id=str(int(owner_id)),
                        defaults={"status": ExternalIdentity.Status.UNLINKED},
                    )
            except Exception:
                # No bloquear el webhook endpoint por problemas internos de identidad.
                logger.exception("strava_webhook.external_identity_seed_failed", extra={"owner_id": owner_id})

            # Thin endpoint: validar rápido lo obvio y evitar encolar basura.
            if object_type != "activity":
                StravaWebhookEvent.objects.filter(pk=event.pk).update(
                    status=StravaWebhookEvent.Status.DISCARDED,
                    discard_reason="non_activity_event",
                    processed_at=timezone.now(),
                )
                logger.info(
                    "strava_webhook.outcome",
                    extra={
                        "event_uid": event_uid,
                        "correlation_id": str(event.correlation_id),
                        "athlete_id": owner_id_int,
                        "activity_id": object_id_int,
                        "status": "discarded",
                        "reason": "non_activity_event",
                        "attempt": 0,
                        "duration_ms": duration_ms,
                    },
                )
                return HttpResponse(status=200)

            if aspect_type == "delete":
                StravaWebhookEvent.objects.filter(pk=event.pk).update(
                    status=StravaWebhookEvent.Status.DISCARDED,
                    discard_reason="delete_event_ignored",
                    processed_at=timezone.now(),
                )
                logger.info(
                    "strava_webhook.outcome",
                    extra={
                        "event_uid": event_uid,
                        "correlation_id": str(event.correlation_id),
                        "athlete_id": owner_id_int,
                        "activity_id": object_id_int,
                        "status": "discarded",
                        "reason": "delete_event_ignored",
                        "attempt": 0,
                        "duration_ms": duration_ms,
                    },
                )
                return HttpResponse(status=200)

            # OK: encolar y responder 200 ASAP.
            StravaWebhookEvent.objects.filter(pk=event.pk).update(status=StravaWebhookEvent.Status.QUEUED)
            try:
                process_strava_event.delay(event.pk)
            except Exception as exc:
                _mark_event_failed(event, error=exc)
                return HttpResponse(status=503)
            logger.info(
                "strava_webhook.outcome",
                extra={
                    "event_uid": event_uid,
                    "correlation_id": str(event.correlation_id),
                    "athlete_id": owner_id_int,
                    "activity_id": object_id_int,
                    "status": "enqueued",
                    "reason": "accepted",
                    "attempt": 0,
                    "duration_ms": duration_ms,
                },
            )

            return HttpResponse(status=200)

        except Exception as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.exception(
                "strava_webhook.error",
                extra={"error": str(e), "status": "error", "duration_ms": duration_ms},
            )
            if event is not None:
                _mark_event_failed(event, error=e, attempts_increment=True)
            return HttpResponse(status=500)

    # Si por alguna razón milagrosa llega aquí (no debería por el decorador), devolvemos 405
    return HttpResponse(status=405)


class StravaWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def get(self, request, *args, **kwargs):
        return strava_webhook(request._request)

    def post(self, request, *args, **kwargs):
        return strava_webhook(request._request)
