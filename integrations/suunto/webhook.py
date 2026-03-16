"""
Suunto webhook helpers — provider-specific parsing and auth (Law 4).

This module lives exclusively in integrations/suunto/ to respect the provider
boundary.  core/webhooks.py delegates to these functions; domain code never
imports from here directly.

LAW 4:  All provider-specific logic stays in integrations/<provider>/.
LAW 5:  Deterministic event_uid makes duplicate events a noop.
LAW 6:  SUUNTO_SUBSCRIPTION_KEY is NEVER logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def validate_suunto_webhook_auth(request) -> bool:
    """
    Validate the Ocp-Apim-Subscription-Key header sent by Suunto.

    Suunto delivers webhooks via Azure API Management (APIM).  The shared
    subscription key is sent in the ``Ocp-Apim-Subscription-Key`` header on
    every POST request.

    Fail-closed: if SUUNTO_SUBSCRIPTION_KEY is unconfigured or empty → False.
    Timing-safe: uses hmac.compare_digest to prevent timing oracle attacks.

    NEVER logs the raw key value (Law 6).
    """
    configured_key = getattr(settings, "SUUNTO_SUBSCRIPTION_KEY", "") or ""
    if not configured_key:
        logger.warning(
            "suunto_webhook.auth_failed",
            extra={
                "event_name": "suunto_webhook.auth_failed",
                "reason_code": "missing_subscription_key_config",
                "outcome": "forbidden",
            },
        )
        return False

    # Django transforms HTTP headers: "Ocp-Apim-Subscription-Key" →
    # META key "HTTP_OCP_APIM_SUBSCRIPTION_KEY"
    received_key = request.META.get("HTTP_OCP_APIM_SUBSCRIPTION_KEY", "") or ""
    if not received_key:
        logger.warning(
            "suunto_webhook.auth_failed",
            extra={
                "event_name": "suunto_webhook.auth_failed",
                "reason_code": "missing_auth_header",
                "outcome": "forbidden",
            },
        )
        return False

    return hmac.compare_digest(
        received_key.encode("utf-8"),
        configured_key.encode("utf-8"),
    )


def parse_suunto_webhook_payload(body: bytes) -> Optional[dict]:
    """
    Parse and validate a Suunto webhook notification body.

    Suunto sends workout-completion notifications.  Required fields:
      - username / userName  : athlete's Suunto username
      - workoutid / workoutKey / workout_id : workout identifier

    Optional fields:
      - event_type / eventType : defaults to "workout_create"

    Returns a normalized dict or None if the payload is invalid or malformed.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    username = data.get("username") or data.get("userName")
    # Support both naming conventions present in Suunto API responses.
    workout_key = (
        data.get("workoutid")
        or data.get("workoutKey")
        or data.get("workout_id")
    )
    event_type = (
        data.get("event_type")
        or data.get("eventType")
        or "workout_create"
    )

    if not username or not workout_key:
        return None

    return {
        "username": str(username),
        "workout_key": str(workout_key),
        "event_type": str(event_type),
    }


def compute_suunto_event_uid(parsed: dict) -> str:
    """
    Compute a deterministic, globally unique event identifier.

    Keyed on (provider, username, workout_key).  event_type is intentionally
    excluded so that a create/update pair for the same workout deduplicates to
    a single StravaWebhookEvent row.

    The "provider" prefix guarantees zero collision with Strava event UIDs,
    which are hashed from entirely different fields.

    Returns an 80-char hex string (SHA-256 truncated to match field max_length).
    """
    uid_payload = {
        "provider": "suunto",
        "username": parsed["username"],
        "workout_key": parsed["workout_key"],
    }
    uid_raw = json.dumps(
        uid_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(uid_raw.encode("utf-8")).hexdigest()[:80]
