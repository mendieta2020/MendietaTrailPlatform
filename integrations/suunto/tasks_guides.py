"""
integrations/suunto/tasks_guides.py

Celery task: push a PlannedWorkout as a SuuntoPlus Guide to an athlete's watch.

Secrets discipline:
    OAuth tokens are NEVER passed as task arguments.
    They are fetched from OAuthCredential inside the task body.

Idempotency:
    If WorkoutDeliveryRecord.status == "sent", the task returns noop
    without making any HTTP call.

Law 4 compliance:
    All provider-specific imports (client, guides builder) are lazy
    and confined to this module inside integrations/.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="suunto.push_guide", bind=True, max_retries=3, default_retry_delay=60)
def push_guide(self, *, assignment_id: int, organization_id: int, alumno_id: int) -> None:
    """
    Push a PlannedWorkout as a SuuntoPlus Guide to the athlete's Suunto watch.

    Args:
        assignment_id:    PK of the WorkoutAssignment to push.
        organization_id:  Organization PK (tenancy guard inside task).
        alumno_id:        PK of the legacy Alumno whose OAuthCredential to use.
    """
    from django.conf import settings

    from core.models import OAuthCredential, WorkoutAssignment, WorkoutDeliveryRecord
    from integrations.suunto.client import push_guide as client_push_guide
    from integrations.suunto.guides import build_guide_payload
    from integrations.suunto.oauth import ensure_fresh_token

    # ── 1. Idempotency guard ─────────────────────────────────────────────────
    try:
        record = WorkoutDeliveryRecord.objects.get(
            assignment_id=assignment_id, provider="suunto"
        )
        if record.status == WorkoutDeliveryRecord.Status.SENT:
            logger.info(
                "suunto_guide_push",
                extra={
                    "event_name": "suunto_guide_push",
                    "assignment_id": assignment_id,
                    "organization_id": organization_id,
                    "provider": "suunto",
                    "outcome": "noop_already_sent",
                },
            )
            return
    except WorkoutDeliveryRecord.DoesNotExist:
        record = None

    # ── 2. Fetch credential (token never passed as arg) ───────────────────────
    try:
        credential = OAuthCredential.objects.get(alumno_id=alumno_id, provider="suunto")
    except OAuthCredential.DoesNotExist:
        logger.warning(
            "suunto_guide_push",
            extra={
                "event_name": "suunto_guide_push",
                "assignment_id": assignment_id,
                "organization_id": organization_id,
                "provider": "suunto",
                "outcome": "no_credential",
            },
        )
        return

    # ── 3. Load assignment (org-scoped tenancy re-check) ─────────────────────
    try:
        assignment = (
            WorkoutAssignment.objects.select_related("planned_workout")
            .prefetch_related("planned_workout__blocks__intervals")
            .get(pk=assignment_id, organization_id=organization_id)
        )
    except WorkoutAssignment.DoesNotExist:
        logger.error(
            "suunto_guide_push",
            extra={
                "event_name": "suunto_guide_push",
                "assignment_id": assignment_id,
                "organization_id": organization_id,
                "provider": "suunto",
                "outcome": "assignment_not_found",
            },
        )
        return

    # ── 4. Build payload and push ─────────────────────────────────────────────
    payload = build_guide_payload(assignment.planned_workout)
    subscription_key = getattr(settings, "SUUNTO_SUBSCRIPTION_KEY", "")
    access_token = ensure_fresh_token(credential)

    try:
        response = client_push_guide(
            access_token,
            subscription_key,
            payload=payload,
        )
        external_guide_id = response.get("guideId", "")
        WorkoutDeliveryRecord.objects.update_or_create(
            assignment_id=assignment_id,
            provider="suunto",
            defaults={
                "organization_id": organization_id,
                "external_guide_id": external_guide_id,
                "status": WorkoutDeliveryRecord.Status.SENT,
                "snapshot_version": assignment.snapshot_version,
            },
        )
        logger.info(
            "suunto_guide_push",
            extra={
                "event_name": "suunto_guide_push",
                "assignment_id": assignment_id,
                "organization_id": organization_id,
                "provider": "suunto",
                "outcome": "success",
                "external_guide_id": external_guide_id,
            },
        )
    except Exception as exc:
        WorkoutDeliveryRecord.objects.update_or_create(
            assignment_id=assignment_id,
            provider="suunto",
            defaults={
                "organization_id": organization_id,
                "status": WorkoutDeliveryRecord.Status.FAILED,
                "snapshot_version": assignment.snapshot_version,
            },
        )
        logger.warning(
            "suunto_guide_push",
            extra={
                "event_name": "suunto_guide_push",
                "assignment_id": assignment_id,
                "organization_id": organization_id,
                "provider": "suunto",
                "outcome": "error",
                "exc": str(exc),
            },
        )
        raise self.retry(exc=exc)
