import json as _json
import logging
import requests as _requests
from django.conf import settings
from .client import mp_get, mp_post, mp_put, MP_API_BASE

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


def create_preapproval_plan(
    access_token: str,
    name: str,
    price_ars,
    back_url: str = "",
) -> dict:
    """
    Creates a MercadoPago preapproval_plan in the coach's account (using their access_token).
    Called lazily the first time an athlete attempts to pay for a plan that has no mp_plan_id.
    Law 6: access_token never logged.
    payment_methods_allowed is intentionally omitted so MP shows all available methods
    (credit_card, debit_card, account_money/saldo) based on the payer's account.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "reason": name,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(price_ars),
            "currency_id": "ARS",
        },
        "back_url": back_url,
        "status": "active",
    }
    response = _requests.post(
        f"{MP_API_BASE}/preapproval_plan",
        json=payload,
        headers=headers,
        timeout=10,
    )
    if not response.ok:
        logger.error(
            "mp.preapproval_plan.error",
            extra={
                "status_code": response.status_code,
                "mp_response_body": response.text,
                "payload_reason": payload.get("reason"),
                "payload_back_url": payload.get("back_url"),
                "outcome": "error",
            },
        )
    response.raise_for_status()
    result = response.json()
    logger.info(
        "mp.preapproval_plan.created",
        extra={
            "plan_id": result.get("id"),
            "outcome": "created",
        },
    )
    return result


def create_coach_athlete_preapproval(
    access_token: str,
    mp_plan_id: str,
    payer_email: str,
    reason: str,
    back_url: str = "",
) -> dict:
    """
    Crea un preapproval en la cuenta MP del coach (usando su access_token).
    Difiere de create_subscription() que usa el token de plataforma.
    Law 6: access_token nunca se loggea.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "preapproval_plan_id": mp_plan_id,
        "reason": reason,
        "payer_email": payer_email,
        "back_url": back_url,
        "status": "pending",
    }
    # [DEBUG PR-167] Log full payload to stdout so it appears in Railway Deploy Logs
    print(
        "[MP DEBUG] create_coach_athlete_preapproval PAYLOAD:",
        _json.dumps(payload),
        flush=True,
    )
    print(
        f"[MP DEBUG] Endpoint: POST {MP_API_BASE}/preapproval  |  "
        f"token_type={'bearer'}  |  token_len={len(access_token)}",
        flush=True,
    )
    response = _requests.post(
        f"{MP_API_BASE}/preapproval",
        json=payload,
        headers=headers,
        timeout=10,
    )
    # Always print status + body to stdout (Railway Deploy Logs)
    print(
        f"[MP DEBUG] Response status: {response.status_code}",
        flush=True,
    )
    print(
        f"[MP DEBUG] Response body: {response.text}",
        flush=True,
    )
    if not response.ok:
        logger.error(
            "mp.coach_preapproval.error",
            extra={
                "status_code": response.status_code,
                "mp_response_body": response.text,
                "mp_plan_id": mp_plan_id,
                "payload_payer_email": payer_email,
                "payload_back_url": back_url,
                "payload_reason": reason,
                "outcome": "error",
            },
        )
    response.raise_for_status()
    result = response.json()
    logger.info(
        "mp.coach_preapproval.created",
        extra={
            "mp_plan_id": mp_plan_id,
            "preapproval_id": result.get("id"),
            "outcome": "created",
        },
    )
    return result


def get_preapproval_plan(access_token: str, plan_id: str) -> dict:
    """
    GET /preapproval_plan/{plan_id} using the coach's access_token.
    Returns the plan object, which includes init_point (checkout URL).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = _requests.get(
        f"{MP_API_BASE}/preapproval_plan/{plan_id}",
        headers=headers,
        timeout=10,
    )
    if not response.ok:
        logger.error(
            "mp.preapproval_plan.get_error",
            extra={
                "plan_id": plan_id,
                "status_code": response.status_code,
                "mp_response_body": response.text,
                "outcome": "error",
            },
        )
    response.raise_for_status()
    return response.json()


def get_subscription(preapproval_id: str) -> dict:
    return mp_get(f"/preapproval/{preapproval_id}")


def cancel_subscription(preapproval_id: str) -> dict:
    result = mp_put(f"/preapproval/{preapproval_id}", json={"status": "cancelled"})
    logger.info(
        "mp.subscription.cancelled",
        extra={"preapproval_id": preapproval_id, "outcome": "cancelled"},
    )
    return result
