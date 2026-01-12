import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from kombu import Connection

from backend.celery import app as celery_app
from core.models import StravaWebhookEvent

logger = logging.getLogger(__name__)


def _json_status(*, ok: bool, checks: dict, http_status: int | None = None) -> JsonResponse:
    status_label = "ok" if ok else "unhealthy"
    return JsonResponse(
        {"status": status_label, "checks": checks},
        status=http_status or (200 if ok else 503),
    )


@require_GET
def healthz(request):
    try:
        get_user_model().objects.exists()
    except Exception:
        logger.exception("healthz.db.error")
        return _json_status(ok=False, checks={"db": "error"})
    return _json_status(ok=True, checks={"db": "ok"})


@require_GET
def healthz_celery(request):
    try:
        responses = celery_app.control.ping(timeout=1.0) or []
        workers = len(responses)
    except Exception:
        logger.exception("healthz.celery.error")
        return _json_status(ok=False, checks={"celery": {"workers_responding": 0}})
    return _json_status(
        ok=workers > 0,
        checks={"celery": {"workers_responding": workers}},
    )


@require_GET
def healthz_redis(request):
    broker_url = getattr(settings, "CELERY_BROKER_URL", None)
    if not broker_url:
        logger.warning("healthz.redis.missing_broker_url")
        return _json_status(ok=False, checks={"redis": "error"})
    try:
        with Connection(broker_url) as connection:
            connection.ensure_connection(max_retries=1)
    except Exception:
        logger.exception("healthz.redis.error")
        return _json_status(ok=False, checks={"redis": "error"})
    return _json_status(ok=True, checks={"redis": "ok"})


@require_GET
def healthz_strava(request):
    failed_threshold = int(getattr(settings, "STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD", 50))
    stuck_threshold_minutes = int(getattr(settings, "STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES", 30))

    failed = StravaWebhookEvent.objects.failed().count()
    stuck_processing = StravaWebhookEvent.objects.stuck_processing(
        older_than_minutes=stuck_threshold_minutes
    ).count()

    stuck_unhealthy_threshold = max(1, failed_threshold)
    if failed > failed_threshold or stuck_processing >= stuck_unhealthy_threshold:
        status = "unhealthy"
    elif failed > 0 or stuck_processing > 0:
        status = "degraded"
    else:
        status = "ok"

    if failed > failed_threshold or stuck_processing > 0:
        logger.warning(
            "strava.healthcheck",
            extra={
                "failed": failed,
                "stuck_processing": stuck_processing,
                "failed_threshold": failed_threshold,
                "stuck_threshold_minutes": stuck_threshold_minutes,
            },
        )

    return JsonResponse(
        {
            "status": status,
            "checks": {
                "strava": {
                    "failed": failed,
                    "stuck_processing": stuck_processing,
                    "failed_threshold": failed_threshold,
                    "stuck_threshold_minutes": stuck_threshold_minutes,
                }
            },
        }
    )
