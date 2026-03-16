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
from typing import Dict
from urllib.parse import urlencode

import requests as http_requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SUUNTO_AUTHORIZE_URL = "https://cloudapi-oauth.suunto.com/oauth/authorize"
_SUUNTO_TOKEN_URL = "https://cloudapi-oauth.suunto.com/oauth/token"
_TOKEN_EXCHANGE_TIMEOUT = 10


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
