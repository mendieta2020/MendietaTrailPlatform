"""
Suunto OAuth 2.0 integration — provider-isolated implementation.

All Suunto-specific URLs, token response parsing, and field normalization
live here and ONLY here (Law 4: provider boundaries).

Key Suunto-specific behavior:
- Authorization host: cloudapi-oauth.suunto.com
- Token response returns `expires_in` (seconds) instead of `expires_at` (unix ts).
  This module normalizes `expires_in` → `expires_at` before returning to the domain layer.
- User identifier is returned as `user` (username string) in the token response.
"""
import logging
import time
from datetime import datetime, timezone as dt_timezone
from typing import Dict
from urllib.parse import urlencode

import requests as http_requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SUUNTO_AUTHORIZE_URL = "https://cloudapi-oauth.suunto.com/oauth/authorize"
_SUUNTO_TOKEN_URL = "https://cloudapi-oauth.suunto.com/oauth/token"
_TOKEN_EXCHANGE_TIMEOUT = 10
_REFRESH_BUFFER_SECONDS = 300  # refresh when < 5 minutes remain


def build_authorize_url(state: str, callback_uri: str) -> str:
    """
    Build Suunto OAuth 2.0 authorization URL.

    Required params: client_id, redirect_uri, response_type=code, scope, state.
    """
    params = {
        "client_id": settings.SUUNTO_CLIENT_ID,
        "redirect_uri": callback_uri,
        "response_type": "code",
        "scope": "workout",
        "state": state,
    }
    return f"{_SUUNTO_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, callback_uri: str) -> Dict:
    """
    Exchange Suunto authorization code for access token.

    Suunto token response uses `expires_in` (seconds from now).
    This function normalizes the response to include `expires_at` (unix timestamp)
    so the domain callback layer can treat all providers uniformly.

    Returns:
        {
            "access_token": str,
            "refresh_token": str,
            "expires_at": int  (unix timestamp — normalized from expires_in),
            "user": str        (Suunto username / external user identifier),
            "token_type": str,
        }

    Raises:
        requests.HTTPError: If exchange fails (4xx/5xx from Suunto).
    """
    data = {
        "client_id": settings.SUUNTO_CLIENT_ID,
        "client_secret": settings.SUUNTO_CLIENT_SECRET,
        "code": code,
        "redirect_uri": callback_uri,
        "grant_type": "authorization_code",
    }

    response = http_requests.post(_SUUNTO_TOKEN_URL, data=data, timeout=_TOKEN_EXCHANGE_TIMEOUT)

    logger.info(
        "suunto.http.request",
        extra={
            "method": "POST",
            "url_path": "/oauth/token",
            "status_code": response.status_code,
        },
    )

    response.raise_for_status()

    token_data = response.json()

    # Normalize: convert expires_in (seconds) → expires_at (unix timestamp)
    # Strava provides expires_at; Suunto provides expires_in.
    # The domain callback layer reads token_data["expires_at"], so we normalize here.
    expires_in = token_data.get("expires_in")
    if expires_in is not None and "expires_at" not in token_data:
        token_data["expires_at"] = int(time.time()) + int(expires_in)

    return token_data


def get_external_user_id(token_data: Dict) -> str:
    """
    Extract Suunto user identifier from token response.

    Suunto returns a `user` field (username string) in the token response.

    Args:
        token_data: Response from exchange_code_for_token()

    Returns:
        Suunto username as string (e.g., "athlete_username")

    Raises:
        ValueError: If user identifier is missing from the response.
    """
    user_id = token_data.get("user")
    if not user_id:
        raise ValueError("Missing 'user' field in Suunto token response")
    return str(user_id)


def refresh_token(refresh_token_value: str) -> Dict:
    """
    Exchange a Suunto refresh token for a new token pair.

    Suunto token response uses `expires_in` (seconds from now).
    This function normalizes to `expires_at` (unix timestamp) for uniform
    treatment across providers in the domain layer.

    Args:
        refresh_token_value: The current refresh_token stored in OAuthCredential.

    Returns:
        {
            "access_token": str,
            "refresh_token": str,
            "expires_at": int  (unix timestamp — normalized from expires_in),
            "token_type": str,
        }

    Raises:
        requests.HTTPError: If refresh fails (4xx/5xx from Suunto).

    Law 6: refresh_token_value is NEVER logged.
    """
    data = {
        "client_id": settings.SUUNTO_CLIENT_ID,
        "client_secret": settings.SUUNTO_CLIENT_SECRET,
        "refresh_token": refresh_token_value,
        "grant_type": "refresh_token",
    }

    response = http_requests.post(_SUUNTO_TOKEN_URL, data=data, timeout=_TOKEN_EXCHANGE_TIMEOUT)

    logger.info(
        "suunto.token_refresh.http",
        extra={
            "event_name": "suunto.token_refresh.http",
            "method": "POST",
            "url_path": "/oauth/token",
            "status_code": response.status_code,
        },
    )

    response.raise_for_status()

    token_data = response.json()

    # Normalize: convert expires_in (seconds) → expires_at (unix timestamp)
    expires_in = token_data.get("expires_in")
    if expires_in is not None and "expires_at" not in token_data:
        token_data["expires_at"] = int(time.time()) + int(expires_in)

    return token_data


def ensure_fresh_token(credential) -> str:
    """
    Return a valid Suunto access token, refreshing via refresh_token() if needed.

    Checks whether the stored token expires within _REFRESH_BUFFER_SECONDS.
    If so, calls refresh_token(), persists the new tokens to OAuthCredential,
    and returns the new access_token.

    Args:
        credential: An OAuthCredential instance with provider=="suunto".

    Returns:
        A valid access_token string.

    Raises:
        requests.HTTPError: If the refresh HTTP call fails (propagated to caller
        so the Celery task can retry).

    Law 6: Tokens are NEVER included in log records.
    """
    expires_at = credential.expires_at  # DateTimeField, may be None
    now_ts = time.time()

    if expires_at is not None:
        remaining = expires_at.timestamp() - now_ts
        needs_refresh = remaining < _REFRESH_BUFFER_SECONDS
    else:
        # No expiry recorded — treat as expired to be safe
        needs_refresh = True

    if not needs_refresh:
        return credential.access_token

    if not credential.refresh_token:
        logger.warning(
            "suunto.token_refresh.no_refresh_token",
            extra={
                "event_name": "suunto.token_refresh.no_refresh_token",
                "alumno_id": credential.alumno_id,
                "outcome": "skipped_no_refresh_token",
            },
        )
        return credential.access_token

    token_data = refresh_token(credential.refresh_token)

    credential.access_token = token_data["access_token"]
    # Suunto may rotate the refresh token; keep the old one if not returned
    if token_data.get("refresh_token"):
        credential.refresh_token = token_data["refresh_token"]
    expires_at_unix = token_data.get("expires_at")
    if expires_at_unix:
        credential.expires_at = datetime.fromtimestamp(
            int(expires_at_unix), tz=dt_timezone.utc
        )
    credential.save(update_fields=["access_token", "refresh_token", "expires_at"])

    logger.info(
        "suunto.token_refresh.success",
        extra={
            "event_name": "suunto.token_refresh.success",
            "alumno_id": credential.alumno_id,
            "outcome": "success",
        },
    )

    return credential.access_token
