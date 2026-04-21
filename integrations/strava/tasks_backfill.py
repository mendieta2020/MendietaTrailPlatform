"""
integrations/strava/tasks_backfill.py — PR-129

Celery task: import historical Strava activities for an athlete.

Secrets discipline:
    OAuth tokens are NEVER passed as task arguments.
    They are fetched from OAuthCredential/SocialToken inside the task body.

Idempotency:
    backfill_strava_activities() calls ingest_strava_activity() per activity,
    which uses get_or_create — safe to rerun with no duplicates (Law 5).

Law 4 compliance:
    All provider-specific logic is confined to integrations/strava/.
    Imports from core/ are lazy and confined to the task body.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="strava.backfill_athlete",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def backfill_strava_athlete(
    self,
    *,
    organization_id: int,
    athlete_id: int | None = None,
    alumno_id: int,
    years: int = 5,
    days: int | None = None,
) -> dict:
    """
    Idempotent Celery task: fetch all Strava activities for an athlete
    and persist as CompletedActivity. Safe to retry and rerun.

    Args:
        organization_id: PK of the Organization (tenancy guard in log).
        athlete_id:      PK of the new-style Athlete (for structured logging).
        alumno_id:       PK of the legacy Alumno (token lookup + ingest).
        years:           How many years back to import (default 5, max 10).
                         Ignored when `days` is provided.
        days:            If set, import exactly this many days back instead of
                         years. Used for onboarding backfill (days=90).
    """
    from core.models import Alumno  # noqa: PLC0415
    from core.services import obtener_cliente_strava_para_alumno  # noqa: PLC0415
    from integrations.strava.services_strava_ingest import backfill_strava_activities  # noqa: PLC0415

    # ── 1. Resolve Alumno ─────────────────────────────────────────────────────
    try:
        alumno = Alumno.objects.get(pk=alumno_id)
    except Alumno.DoesNotExist:
        logger.error(
            "strava.backfill.alumno_not_found",
            extra={
                "event_name": "strava.backfill.alumno_not_found",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "outcome": "error",
                "reason_code": "ALUMNO_NOT_FOUND",
            },
        )
        return {"outcome": "error", "reason": "alumno_not_found"}

    # ── 2. Obtain access token (token never passed as task arg) ───────────────
    client = obtener_cliente_strava_para_alumno(alumno)
    if client is None:
        logger.warning(
            "strava.backfill.no_credential",
            extra={
                "event_name": "strava.backfill.no_credential",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "outcome": "noop_no_credential",
                "reason_code": "NO_STRAVA_CREDENTIAL",
            },
        )
        return {"outcome": "noop_no_credential"}

    access_token = client.access_token

    # ── 3. Run paginated backfill ─────────────────────────────────────────────
    try:
        result = backfill_strava_activities(
            alumno_id=alumno_id,
            access_token=access_token,
            years=years,
            days=days,
        )
    except Exception as exc:
        logger.exception(
            "strava.backfill.error",
            extra={
                "event_name": "strava.backfill.error",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "outcome": "error",
            },
        )
        raise self.retry(exc=exc)

    # ── 4. Structured completion log ──────────────────────────────────────────
    logger.info(
        "strava.backfill.complete",
        extra={
            "event_name": "strava.backfill.complete",
            "organization_id": organization_id,
            "athlete_id": athlete_id,
            "outcome": "success",
            "created_count": result.get("created", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", 0),
        },
    )
    return result
