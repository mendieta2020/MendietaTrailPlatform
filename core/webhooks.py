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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from core.models import StravaWebhookEvent
from core.tasks import process_strava_event
from core.models import ExternalIdentity

logger = logging.getLogger(__name__)

# Token de verificación para el handshake (GET).
# Resolvemos at runtime para que override_settings en tests funcione correctamente.
# En prod debe venir desde settings/env; en dev permitimos un fallback para no romper local.
# VERIFY_TOKEN NO se cachea a nivel de módulo — se lee en cada request.

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

        # Resolve at request time — no module-level caching, no hardcoded fallback.
        # Fail-closed: if STRAVA_WEBHOOK_VERIFY_TOKEN is unset, return 403.
        verify_token = getattr(settings, "STRAVA_WEBHOOK_VERIFY_TOKEN", None)

        if mode and token:
            if verify_token is None:
                logger.warning(
                    "strava_webhook_verify",
                    extra={"event_name": "strava_webhook_verify", "outcome": "forbidden", "reason_code": "missing_verify_token"},
                )
                return HttpResponse(status=403)
            if mode == 'subscribe' and token == verify_token:
                logger.info(
                    "strava_webhook_verify",
                    extra={"event_name": "strava_webhook_verify", "outcome": "success", "reason_code": "token_match"},
                )
                return JsonResponse({"hub.challenge": challenge})
            else:
                # No loggear tokens/secretos (seguridad).
                logger.warning(
                    "strava_webhook_verify",
                    extra={"event_name": "strava_webhook_verify", "outcome": "forbidden", "reason_code": "token_mismatch"},
                )
                return HttpResponse(status=403)

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

            if str(subscription_id) != str(configured_sub_id):
                logger.warning(
                    "strava_webhook.subscription_id_mismatch",
                    extra={
                        "status": "discarded",
                        "reason": "subscription_id_mismatch",
                        "received_subscription_id": subscription_id,
                        "expected_subscription_id": configured_sub_id,
                    },
                )
                return JsonResponse({"ok": True, "ignored": "subscription_id_mismatch"})

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


# ==============================================================================
#  SUUNTO WEBHOOK
# ==============================================================================

def suunto_webhook(request):
    """
    Suunto webhook endpoint — real-time workout delivery.

    Accepts POST only (Suunto does not require a GET handshake challenge).
    Flow:
      1. Validate Ocp-Apim-Subscription-Key header (fail-closed 403).
      2. Parse JSON body and extract username + workout_key (400 on bad payload).
      3. Compute deterministic event_uid; StravaWebhookEvent.get_or_create.
      4. If duplicate → noop 200.
      5. If new + unlinked identity → LINK_REQUIRED, 200 (will retry on link).
      6. If new + linked → enqueue suunto.ingest_workout, 200.

    Law 4: Provider-specific logic delegated to integrations/suunto/webhook.py.
    Law 5: Idempotency guaranteed by event_uid UniqueConstraint.
    Law 6: No tokens or keys are ever logged.
    """
    from integrations.suunto.webhook import (
        validate_suunto_webhook_auth,
        parse_suunto_webhook_payload,
        compute_suunto_event_uid,
    )
    from integrations.suunto.tasks import ingest_workout as suunto_ingest_workout

    if request.method != "POST":
        return HttpResponse(status=405)

    t0 = time.monotonic()
    event = None
    created = False

    try:
        # ------------------------------------------------------------------ #
        # 1. Auth — validate subscription key (fail-closed)
        # ------------------------------------------------------------------ #
        if not validate_suunto_webhook_auth(request):
            return HttpResponse(status=403)

        # ------------------------------------------------------------------ #
        # 2. Parse payload
        # ------------------------------------------------------------------ #
        parsed = parse_suunto_webhook_payload(request.body)
        if parsed is None:
            return HttpResponse("Payload inválido", status=400)

        username = parsed["username"]
        workout_key = parsed["workout_key"]
        event_type = parsed["event_type"]

        # ------------------------------------------------------------------ #
        # 3. Deterministic event_uid + idempotent persist
        # ------------------------------------------------------------------ #
        event_uid = compute_suunto_event_uid(parsed)

        try:
            event, created = StravaWebhookEvent.objects.get_or_create(
                event_uid=event_uid,
                defaults={
                    "provider": "suunto",
                    # object_id and owner_id are BigIntegerField; Suunto uses
                    # string identifiers so we store 0 as placeholder — the
                    # real IDs live in payload_raw.
                    "object_type": "workout",
                    "object_id": 0,
                    "aspect_type": event_type,
                    "owner_id": 0,
                    "payload_raw": parsed,
                    "status": StravaWebhookEvent.Status.RECEIVED,
                },
            )
        except IntegrityError:
            created = False
            event = StravaWebhookEvent.objects.filter(event_uid=event_uid).first()
            if event is None:
                logger.exception(
                    "suunto_webhook.event_persist_failed_integrity_no_event",
                    extra={"event_uid": event_uid, "username": username, "workout_key": workout_key},
                )
                return HttpResponse(status=500)
        except Exception:
            logger.exception(
                "suunto_webhook.event_persist_failed",
                extra={"event_uid": event_uid, "username": username, "workout_key": workout_key},
            )
            return HttpResponse(status=500)

        duration_ms = int((time.monotonic() - t0) * 1000)

        # ------------------------------------------------------------------ #
        # 4. Duplicate handling
        # ------------------------------------------------------------------ #
        if not created:
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
                        suunto_ingest_workout.delay(
                            alumno_id=event.payload_raw.get("_resolved_alumno_id", 0),
                            external_workout_id=workout_key,
                        )
                        logger.info(
                            "suunto_webhook.outcome",
                            extra={
                                "event_name": "suunto_webhook.outcome",
                                "event_uid": event_uid,
                                "username": username,
                                "workout_key": workout_key,
                                "status": "requeued",
                                "duration_ms": duration_ms,
                            },
                        )
                        return HttpResponse(status=200)
                    except Exception as exc:
                        _mark_event_failed(event, error=exc)
                        return HttpResponse(status=503)

            logger.info(
                "suunto_webhook.outcome",
                extra={
                    "event_name": "suunto_webhook.outcome",
                    "event_uid": event_uid,
                    "username": username,
                    "workout_key": workout_key,
                    "status": "duplicate",
                    "duration_ms": duration_ms,
                },
            )
            return HttpResponse(status=200)

        # ------------------------------------------------------------------ #
        # 5. Seed canonical identity (UNLINKED if not seen before)
        # ------------------------------------------------------------------ #
        try:
            ExternalIdentity.objects.get_or_create(
                provider="suunto",
                external_user_id=username,
                defaults={"status": ExternalIdentity.Status.UNLINKED},
            )
        except Exception:
            logger.exception(
                "suunto_webhook.external_identity_seed_failed",
                extra={"username": username},
            )

        # ------------------------------------------------------------------ #
        # 6. Resolve Alumno via linked ExternalIdentity
        # ------------------------------------------------------------------ #
        linked_identity = (
            ExternalIdentity.objects.filter(
                provider="suunto",
                external_user_id=username,
                status=ExternalIdentity.Status.LINKED,
                alumno__isnull=False,
            )
            .select_related("alumno")
            .first()
        )

        if linked_identity is None:
            StravaWebhookEvent.objects.filter(pk=event.pk).update(
                status=StravaWebhookEvent.Status.LINK_REQUIRED,
                discard_reason="no_linked_alumno",
            )
            logger.warning(
                "suunto_webhook.outcome",
                extra={
                    "event_name": "suunto_webhook.outcome",
                    "event_uid": event_uid,
                    "username": username,
                    "workout_key": workout_key,
                    "status": "link_required",
                    "duration_ms": duration_ms,
                },
            )
            return HttpResponse(status=200)

        alumno_id = linked_identity.alumno.pk

        # Stash resolved alumno_id in payload_raw so requeue can use it.
        StravaWebhookEvent.objects.filter(pk=event.pk).update(
            status=StravaWebhookEvent.Status.QUEUED,
            payload_raw={**parsed, "_resolved_alumno_id": alumno_id},
        )

        # ------------------------------------------------------------------ #
        # 7. Enqueue ingestion task — respond 200 ASAP
        # ------------------------------------------------------------------ #
        try:
            suunto_ingest_workout.delay(
                alumno_id=alumno_id,
                external_workout_id=workout_key,
            )
        except Exception as exc:
            _mark_event_failed(event, error=exc)
            return HttpResponse(status=503)

        logger.info(
            "suunto_webhook.outcome",
            extra={
                "event_name": "suunto_webhook.outcome",
                "event_uid": event_uid,
                "username": username,
                "workout_key": workout_key,
                "alumno_id": alumno_id,
                "status": "enqueued",
                "duration_ms": duration_ms,
            },
        )
        return HttpResponse(status=200)

    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.exception(
            "suunto_webhook.error",
            extra={
                "event_name": "suunto_webhook.error",
                "error": str(exc),
                "status": "error",
                "duration_ms": duration_ms,
            },
        )
        if event is not None:
            _mark_event_failed(event, error=exc, attempts_increment=True)
        return HttpResponse(status=500)


class SuuntoWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def post(self, request, *args, **kwargs):
        return suunto_webhook(request._request)


class StravaDiagnosticsView(APIView):
    """
    Runtime diagnostics endpoint to verify webhook config.
    Requires authentication. Returns only boolean readiness signals — never raw config values.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES

    def get(self, request, *args, **kwargs):
        sub_id = getattr(settings, "STRAVA_WEBHOOK_SUBSCRIPTION_ID", None)
        callback_url = getattr(settings, "PUBLIC_BASE_URL", None)
        return JsonResponse({
            "subscription_id_configured": sub_id is not None,
            "callback_url_configured": callback_url is not None,
            "environment": "production" if not settings.DEBUG else "staging/dev"
        })
