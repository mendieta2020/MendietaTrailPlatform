"""
Garmin Connect OAuth integration provider — STUB (disabled).

Status: Coming Soon — not yet enabled for production.

Notes:
- Garmin uses OAuth 1.0a (not 2.0).
- Requires GARMIN_CONSUMER_KEY + GARMIN_CONSUMER_SECRET in settings.
- Activity sync uses polling (no webhook support in Garmin public API).
"""
from typing import Dict, List
from datetime import datetime

from .base import IntegrationProvider


class GarminProvider(IntegrationProvider):
    """
    Garmin Connect integration provider stub.

    enabled=False: Not yet implemented. Provider is registered in the
    catalog so the frontend can show "Coming Soon" state.

    OAuth mechanics differ from Strava: Garmin uses OAuth 1.0a.
    Implementation requires: requests-oauthlib + Garmin Connect API credentials.
    """

    @property
    def provider_id(self) -> str:
        return "garmin"

    @property
    def display_name(self) -> str:
        return "Garmin Connect"

    @property
    def enabled(self) -> bool:
        return False

    def capabilities(self) -> Dict[str, bool]:
        return {
            "supports_refresh": False,
            "supports_activity_fetch": False,
            "supports_webhooks": False,
            "supports_workout_push": False,
        }

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        raise NotImplementedError(
            "GarminProvider is not yet implemented. "
            "Provider must be enabled before use."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict:
        raise NotImplementedError(
            "GarminProvider is not yet implemented. "
            "Provider must be enabled before use."
        )

    def get_external_user_id(self, token_data: Dict) -> str:
        raise NotImplementedError(
            "GarminProvider is not yet implemented. "
            "Provider must be enabled before use."
        )
