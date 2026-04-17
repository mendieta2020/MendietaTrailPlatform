"""
MP webhook signature verification — PR-169 Feature 2.

MercadoPago signs webhook requests with HMAC-SHA256.
Header format:
    x-signature: ts=TIMESTAMP,v1=HASH
    x-request-id: REQUEST_ID

The signed string is reconstructed as:
    "id:{data_id};request-id:{request_id};ts:{timestamp};"

where data_id comes from the `data.id` query param (or request body).

Law 6: MERCADOPAGO_WEBHOOK_SECRET is NEVER logged.
"""

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_mp_signature(request) -> bool:
    """
    Verify the MercadoPago webhook HMAC-SHA256 signature.

    Returns True  — signature valid (or secret not configured → dev passthrough).
    Returns False — signature present but invalid (should return 401).

    If MERCADOPAGO_WEBHOOK_SECRET is empty, logs a warning and returns True
    to preserve backward compatibility for developers without the secret set.
    Law 6: secret is never logged.
    """
    from django.conf import settings

    secret = getattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning(
            "mp.webhook.signature_check_skipped",
            extra={
                "event_name": "mp.webhook.signature_check_skipped",
                "reason": "MERCADOPAGO_WEBHOOK_SECRET not configured",
                "outcome": "passthrough",
            },
        )
        return True

    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")

    if not x_signature:
        logger.warning(
            "mp.webhook.signature_missing",
            extra={
                "event_name": "mp.webhook.signature_missing",
                "outcome": "rejected",
            },
        )
        return False

    # Parse ts and v1 from "ts=TIMESTAMP,v1=HASH"
    ts = ""
    v1 = ""
    for part in x_signature.split(","):
        part = part.strip()
        if part.startswith("ts="):
            ts = part[3:]
        elif part.startswith("v1="):
            v1 = part[3:]

    if not ts or not v1:
        logger.warning(
            "mp.webhook.signature_malformed",
            extra={
                "event_name": "mp.webhook.signature_malformed",
                "outcome": "rejected",
            },
        )
        return False

    # data.id comes from query params (MP sends it as ?data.id=XXX)
    data_id = request.GET.get("data.id", "")

    # Reconstruct the signed manifest
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"

    # Compute HMAC-SHA256
    expected = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, v1):
        logger.warning(
            "mp.webhook.signature_invalid",
            extra={
                "event_name": "mp.webhook.signature_invalid",
                "x_request_id": x_request_id,
                "outcome": "rejected",
                # Law 6: never log secret, ts, or hash values
            },
        )
        return False

    return True
