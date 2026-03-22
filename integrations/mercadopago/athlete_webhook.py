import logging

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "authorized": "active",
    "paused": "overdue",
    "cancelled": "cancelled",
    "pending": None,  # no-op
}


def process_athlete_subscription_webhook(payload: dict) -> dict:
    """
    Procesa eventos de MP para AthleteSubscription.
    Idempotente — safe to rerun multiple times.

    Eventos que maneja:
    - authorized  → status = "active", last_payment_at = now()
    - paused      → status = "overdue"
    - cancelled   → status = "cancelled"
    - pending     → no-op (ya está en pending)

    Returns: {"outcome": "updated"|"noop"|"not_found",
              "preapproval_id": str}
    """
    preapproval_id = payload.get("id") or payload.get("data", {}).get("id")
    if not preapproval_id:
        return {"outcome": "noop", "preapproval_id": None}

    # Lazy import (Law 4)
    from core.models import AthleteSubscription
    from django.utils import timezone

    try:
        sub = AthleteSubscription.objects.get(mp_preapproval_id=preapproval_id)
    except AthleteSubscription.DoesNotExist:
        logger.warning(
            "mp.athlete_webhook.not_found",
            extra={"preapproval_id": preapproval_id, "outcome": "not_found"},
        )
        return {"outcome": "not_found", "preapproval_id": preapproval_id}

    mp_status = payload.get("status")
    new_status = STATUS_MAP.get(mp_status)

    if new_status is None:
        return {"outcome": "noop", "preapproval_id": preapproval_id}

    if sub.status == new_status:
        return {"outcome": "noop", "preapproval_id": preapproval_id}

    sub.status = new_status
    if new_status == "active":
        sub.last_payment_at = timezone.now()
    sub.save(update_fields=["status", "last_payment_at"])

    logger.info(
        "athlete_subscription_updated",
        extra={
            "event": "athlete_subscription_updated",
            "preapproval_id": preapproval_id,
            "new_status": new_status,
            "subscription_id": sub.id,
        },
    )

    return {"outcome": "updated", "preapproval_id": preapproval_id}
