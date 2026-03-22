"""
MercadoPago OAuth helpers — PR-134 (Coach MP OAuth connect).

Law 4: this module is ONLY imported via lazy imports from core/ views.
Law 6: tokens and client_secret are NEVER logged.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def mp_get_authorization_url(org_id: int) -> str:
    """
    Build the MercadoPago authorization URL for a coach OAuth connect.

    The `state` parameter carries the organization PK as a minimal anti-CSRF
    measure: the callback validates that the PK maps to a real organization.

    Returns:
        Full authorization URL string (redirect the browser here).
    """
    client_id = settings.MERCADOPAGO_CLIENT_ID
    redirect_uri = settings.MERCADOPAGO_REDIRECT_URI
    return (
        "https://auth.mercadopago.com/authorization"
        f"?client_id={client_id}"
        "&response_type=code"
        "&platform_id=mp"
        f"&redirect_uri={redirect_uri}"
        f"&state={org_id}"
    )


def mp_exchange_code(code: str) -> dict:
    """
    Exchange an authorization code for an MP access token.

    POST https://api.mercadopago.com/oauth/token

    Returns:
        dict with keys: access_token, refresh_token, user_id (at minimum).

    Raises:
        ValueError if the request fails or MP returns a non-2xx status.

    Security (Law 6):
        client_secret and tokens are NEVER logged — only boolean presence flags.
    """
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.MERCADOPAGO_CLIENT_ID,
        "client_secret": settings.MERCADOPAGO_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.MERCADOPAGO_REDIRECT_URI,
    }

    try:
        resp = requests.post(
            "https://api.mercadopago.com/oauth/token",
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.error(
            "mp.oauth.exchange_code.request_error",
            extra={"outcome": "error", "error_type": type(exc).__name__},
        )
        raise ValueError(f"MP request failed: {exc}") from exc

    if not resp.ok:
        logger.error(
            "mp.oauth.exchange_code.bad_status",
            extra={"status_code": resp.status_code, "outcome": "error"},
        )
        raise ValueError(f"MP token exchange failed with status {resp.status_code}")

    data = resp.json()
    logger.info(
        "mp.oauth.exchange_code.success",
        extra={
            "outcome": "success",
            "has_access_token": bool(data.get("access_token")),
            "has_refresh_token": bool(data.get("refresh_token")),
        },
    )
    return data
