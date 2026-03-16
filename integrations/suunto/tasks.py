"""
Suunto ingestion Celery tasks — fan-out design (Law 5 idempotency).

Task 1 — suunto.sync_athlete_workouts:
    Fetches the workout list for an athlete and fans out to Task 2.

Task 2 — suunto.ingest_workout:
    Downloads the FIT file, parses it, and persists idempotently.

Secrets discipline: OAuth tokens are NEVER passed as task arguments.
They are fetched from OAuthCredential inside the task body.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(name="suunto.sync_athlete_workouts", bind=True, max_retries=3, default_retry_delay=60)
def sync_athlete_workouts(self, *, alumno_id: int, days_back: int = 7) -> None:
    """
    Task 1 — fetch Suunto workout list and fan out to ingest_workout per workout.

    Args:
        alumno_id: pk of the Alumno whose Suunto workouts to sync.
        days_back: history window to retrieve (default: 7).
    """
    from core.models import OAuthCredential
    from integrations.suunto.client import list_workouts

    try:
        credential = OAuthCredential.objects.get(alumno_id=alumno_id, provider="suunto")
    except OAuthCredential.DoesNotExist:
        logger.warning(
            "suunto.sync.no_credential",
            extra={
                "event_name": "suunto.sync.no_credential",
                "alumno_id": alumno_id,
                "outcome": "skipped",
            },
        )
        return

    subscription_key = getattr(settings, "SUUNTO_SUBSCRIPTION_KEY", "")
    try:
        workouts = list_workouts(credential.access_token, subscription_key, days_back=days_back)
    except Exception as exc:
        logger.warning(
            "suunto.sync.list_failed",
            extra={"event_name": "suunto.sync.list_failed", "alumno_id": alumno_id, "exc": str(exc)},
        )
        raise self.retry(exc=exc)

    logger.info(
        "suunto.sync.fanning_out",
        extra={
            "event_name": "suunto.sync.fanning_out",
            "alumno_id": alumno_id,
            "workout_count": len(workouts),
        },
    )
    for workout in workouts:
        workout_key = workout.get("workoutKey") or workout.get("id")
        if workout_key:
            ingest_workout.delay(alumno_id=alumno_id, external_workout_id=str(workout_key))


@shared_task(name="suunto.ingest_workout", bind=True, max_retries=3, default_retry_delay=60)
def ingest_workout(self, *, alumno_id: int, external_workout_id: str) -> None:
    """
    Task 2 — download FIT, parse, persist as CompletedActivity (idempotent).

    Args:
        alumno_id: pk of the Alumno.
        external_workout_id: Suunto workoutKey.
    """
    from core.models import OAuthCredential
    from integrations.suunto.client import download_fit_file
    from integrations.suunto.parser import parse_fit_bytes
    from integrations.suunto.services_suunto_ingest import ingest_suunto_workout

    try:
        credential = OAuthCredential.objects.get(alumno_id=alumno_id, provider="suunto")
    except OAuthCredential.DoesNotExist:
        logger.warning(
            "suunto.ingest.no_credential",
            extra={
                "event_name": "suunto.ingest.no_credential",
                "alumno_id": alumno_id,
                "external_workout_id": external_workout_id,
                "outcome": "skipped",
            },
        )
        return

    subscription_key = getattr(settings, "SUUNTO_SUBSCRIPTION_KEY", "")
    try:
        fit_bytes = download_fit_file(credential.access_token, subscription_key, external_workout_id)
        fit_data = parse_fit_bytes(fit_bytes)
        ingest_suunto_workout(alumno_id=alumno_id, external_workout_id=external_workout_id, fit_data=fit_data)
    except Exception as exc:
        logger.warning(
            "suunto.ingest.retry",
            extra={
                "event_name": "suunto.ingest.retry",
                "alumno_id": alumno_id,
                "external_workout_id": external_workout_id,
                "exc": str(exc),
            },
        )
        raise self.retry(exc=exc)
