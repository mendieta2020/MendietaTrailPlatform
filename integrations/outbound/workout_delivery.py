import logging
import datetime
from typing import TypedDict, Literal

from django.utils import timezone
from core.providers import SUPPORTED_PROVIDERS
from core.provider_capabilities import provider_supports, CAP_OUTBOUND_WORKOUTS

logger = logging.getLogger(__name__)

class WorkoutDeliveryEnvelope(TypedDict):
    organization_id: int
    athlete_id: int
    provider: str
    planned_workout_id: int
    payload: dict
    created_at: datetime.datetime

class DeliveryResult(TypedDict):
    status: Literal["queued", "skipped", "error"]
    reason_code: str
    provider: str

def queue_workout_delivery(
    *, 
    organization_id: int, 
    athlete_id: int, 
    provider: str, 
    planned_workout_id: int, 
    payload: dict
) -> DeliveryResult:
    """
    Creates an internal envelope representing an attempt to deliver a planned workout
    to a provider. Does not execute external HTTP requests yet.
    """
    if not provider or provider not in SUPPORTED_PROVIDERS:
        logger.info(
            "workout_delivery_skipped",
            extra={
                "event_name": "workout_delivery_skipped",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "provider": provider,
                "planned_workout_id": planned_workout_id,
                "reason_code": "provider_unknown"
            }
        )
        return DeliveryResult(status="skipped", reason_code="provider_unknown", provider=provider or "unknown")

    if not provider_supports(provider, CAP_OUTBOUND_WORKOUTS):
        logger.info(
            "workout_delivery_skipped",
            extra={
                "event_name": "workout_delivery_skipped",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "provider": provider,
                "planned_workout_id": planned_workout_id,
                "reason_code": "provider_no_outbound"
            }
        )
        return DeliveryResult(status="skipped", reason_code="provider_no_outbound", provider=provider)

    if not organization_id or not athlete_id or not planned_workout_id or not payload:
        logger.error(
            "workout_delivery_error",
            extra={
                "event_name": "workout_delivery_error",
                "organization_id": organization_id,
                "athlete_id": athlete_id,
                "provider": provider,
                "planned_workout_id": planned_workout_id,
                "reason_code": "missing_required"
            }
        )
        return DeliveryResult(status="error", reason_code="missing_required", provider=provider)

    envelope = WorkoutDeliveryEnvelope(
        organization_id=organization_id,
        athlete_id=athlete_id,
        provider=provider,
        planned_workout_id=planned_workout_id,
        payload=payload,
        created_at=timezone.now()
    )

    logger.info(
        "workout_delivery_queued",
        extra={
            "event_name": "workout_delivery_queued",
            "organization_id": organization_id,
            "athlete_id": athlete_id,
            "provider": provider,
            "planned_workout_id": planned_workout_id,
            "reason_code": "queued"
        }
    )

    return DeliveryResult(status="queued", reason_code="queued", provider=provider)
