import logging
from django.conf import settings
from .client import mp_get, mp_post, mp_put

logger = logging.getLogger(__name__)


def create_subscription(mp_plan_id: str, payer_email: str, reason: str) -> dict:
    """
    Crea un preapproval en MP para un plan dado.
    Retorna el objeto preapproval con init_point (URL de checkout MP).
    """
    payload = {
        "preapproval_plan_id": mp_plan_id,
        "reason": reason,
        "payer_email": payer_email,
        "back_url": getattr(settings, "FRONTEND_URL", "") + "/billing/callback",
        "status": "pending",
    }
    result = mp_post("/preapproval", json=payload)
    logger.info(
        "mp.subscription.created",
        extra={
            "mp_plan_id": mp_plan_id,
            "preapproval_id": result.get("id"),
            "outcome": "created",
        },
    )
    return result


def get_subscription(preapproval_id: str) -> dict:
    return mp_get(f"/preapproval/{preapproval_id}")


def cancel_subscription(preapproval_id: str) -> dict:
    result = mp_put(f"/preapproval/{preapproval_id}", json={"status": "cancelled"})
    logger.info(
        "mp.subscription.cancelled",
        extra={"preapproval_id": preapproval_id, "outcome": "cancelled"},
    )
    return result
