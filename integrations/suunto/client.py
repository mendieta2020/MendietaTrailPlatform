"""
Suunto API HTTP client — provider-isolated (Law 4).

Wraps authenticated calls to the Suunto STS / Workout API.
All Suunto-specific URLs and response shapes live here exclusively.

Tokens are NEVER stored here — callers pass them in per-call.
Callers (tasks) fetch tokens from OAuthCredential, never from task args.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_SUUNTO_API_BASE = "https://cloudapi.suunto.com/v2"
_TIMEOUT = 15  # seconds


def list_workouts(
    access_token: str,
    subscription_key: str,
    *,
    days_back: int = 7,
) -> list[dict]:
    """
    Fetch recent workout summaries from the Suunto API.

    Returns a list of workout dicts, each containing at minimum 'workoutKey'.

    Raises:
        requests.HTTPError: on 4xx/5xx responses.
    """
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    response = requests.get(
        f"{_SUUNTO_API_BASE}/workouts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Ocp-Apim-Subscription-Key": subscription_key,
        },
        params={"since": since},
        timeout=_TIMEOUT,
    )
    logger.info(
        "suunto.api.list_workouts",
        extra={
            "event_name": "suunto.api.list_workouts",
            "status_code": response.status_code,
            "days_back": days_back,
        },
    )
    response.raise_for_status()
    return response.json().get("payload", [])


def download_fit_file(
    access_token: str,
    subscription_key: str,
    workout_key: str,
) -> bytes:
    """
    Download the .FIT binary for a single workout.

    Raises:
        requests.HTTPError: on 4xx/5xx responses.
    """
    response = requests.get(
        f"{_SUUNTO_API_BASE}/workout/exportFit/{workout_key}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Ocp-Apim-Subscription-Key": subscription_key,
        },
        timeout=_TIMEOUT,
        stream=True,
    )
    logger.info(
        "suunto.api.download_fit",
        extra={
            "event_name": "suunto.api.download_fit",
            "status_code": response.status_code,
            "workout_key": workout_key,
        },
    )
    response.raise_for_status()
    return response.content


def push_guide(
    access_token: str,
    subscription_key: str,
    *,
    payload: dict,
) -> dict:
    """
    Push a workout guide to SuuntoPlus so it appears on the athlete's watch.

    Returns the API response dict, which includes 'guideId' on success.

    Raises:
        requests.HTTPError: on 4xx/5xx responses.
    """
    response = requests.post(
        f"{_SUUNTO_API_BASE}/guide",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Ocp-Apim-Subscription-Key": subscription_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=_TIMEOUT,
    )
    logger.info(
        "suunto.api.push_guide",
        extra={
            "event_name": "suunto.api.push_guide",
            "status_code": response.status_code,
        },
    )
    response.raise_for_status()
    return response.json()
