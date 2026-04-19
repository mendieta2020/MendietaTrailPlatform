import logging
import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from celery import Celery
from celery.signals import task_failure
from kombu import Queue
from celery.schedules import crontab
from core.utils.logging import sanitize_secrets

# 1. Establecemos el módulo de configuración de Django por defecto
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# Sentry: initialize for the Celery worker process.
# The WSGI process (wsgi.py) and the Celery worker are separate OS processes;
# each needs its own sentry_sdk.init() call. No-op if SENTRY_DSN is absent.
def _scrub_sensitive(event, hint):
    """Remove tokens, secrets, and PII from Sentry events before sending."""
    sensitive_keys = {"access_token", "refresh_token", "password", "secret", "authorization"}
    request = event.get("request", {})
    headers = request.get("headers", {})
    for key in list(headers.keys()):
        if key.lower() in sensitive_keys:
            headers[key] = "[Filtered]"
    return event

_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=_scrub_sensitive,
        environment=os.environ.get("DJANGO_ENV", "production"),
    )

# 2. Creamos la instancia de la aplicación Celery
# IMPORTANTE: Aquí definimos la variable 'app'. Por eso el comando debe terminar en ':app'
app = Celery('backend')

# 3. Le decimos que lea la configuración desde el archivo settings.py de Django
#    (Busca variables que empiecen con 'CELERY_')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.task_queues = (
    Queue("default"),
    Queue("strava_ingest"),
    Queue("suunto_ingest"),
    Queue("analytics_recompute"),
    Queue("notifications"),
)

# 3.1. Schedule diario (Celery Beat)
# Nota: requiere ejecutar celery beat en el entorno. Idempotente por diseño (UPSERT).
app.conf.beat_schedule = {
    "injury-risk-daily-recompute": {
        "task": "analytics.recompute_injury_risk_daily",
        "schedule": crontab(hour=2, minute=10),  # 02:10 UTC
        "args": (None,),
    },
}

# 4. Auto-descubrir tareas en todas las apps instaladas (core, etc.)
app.autodiscover_tasks()

# tasks_backfill.py lives outside INSTALLED_APPS so autodiscover misses it;
# this import forces strava.backfill_athlete to register at worker startup.
import integrations.strava.tasks_backfill  # noqa: E402, F401

logger = logging.getLogger(__name__)

@app.task(bind=True)
def debug_task(self):
    logger.debug(
        "celery.debug_task.request",
        extra={"task_id": getattr(self.request, "id", None), "task": self.name},
    )


@task_failure.connect
def log_critical_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **extras):
    task_name = getattr(sender, "name", "") or ""
    if not (task_name.startswith("strava.") or task_name.startswith("analytics.")):
        return
    logger.exception(
        "celery.task.failed",
        extra={
            "task_name": task_name,
            "task_id": task_id,
            "task_args": args,
            "task_kwargs": sanitize_secrets(kwargs),
            "exc_msg": str(exception),
            "exc_type": type(exception).__name__ if exception else "",
        },
    )
