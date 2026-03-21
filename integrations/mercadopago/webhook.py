import logging
from core.models import OrganizationSubscription
from .client import mp_get

logger = logging.getLogger(__name__)

MP_STATUS_TO_ACTIVE = {
    "authorized": True,
    "paused": False,
    "cancelled": False,
    "pending": False,
}


def process_subscription_webhook(payload: dict) -> None:
    """
    Procesa webhook de MercadoPago tipo subscription_preapproval.
    Actualiza OrganizationSubscription.is_active segun el estado de MP.
    Es idempotente: procesar el mismo webhook dos veces no crea duplicados.
    """
    if payload.get("type") != "subscription_preapproval":
        return

    preapproval_id = payload.get("data", {}).get("id")
    if not preapproval_id:
        logger.warning("mp.webhook.missing_id", extra={"payload_keys": list(payload.keys())})
        return

    try:
        mp_data = mp_get(f"/preapproval/{preapproval_id}")
    except Exception as exc:
        logger.error(
            "mp.webhook.fetch_failed",
            extra={"preapproval_id": preapproval_id, "error": str(exc), "outcome": "error"},
        )
        return

    mp_status = mp_data.get("status")
    is_active = MP_STATUS_TO_ACTIVE.get(mp_status, False)

    try:
        sub = OrganizationSubscription.objects.get(mp_preapproval_id=preapproval_id)
        sub.is_active = is_active
        sub.save(update_fields=["is_active", "updated_at"])
        logger.info(
            "mp.webhook.subscription_updated",
            extra={
                "organization_id": sub.organization_id,
                "preapproval_id": preapproval_id,
                "mp_status": mp_status,
                "is_active": is_active,
                "outcome": "updated",
            },
        )
    except OrganizationSubscription.DoesNotExist:
        logger.warning(
            "mp.webhook.subscription_not_found",
            extra={"preapproval_id": preapproval_id, "outcome": "not_found"},
        )
