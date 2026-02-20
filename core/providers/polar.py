"""
Polar OAuth integration provider — STUB (disabled).

Status: Coming Soon — not yet enabled for production.

Notes:
- Polar uses OAuth 2.0 authorization code flow (Polar Accesslink API).
- Requires POLAR_CLIENT_ID + POLAR_CLIENT_SECRET in settings.
- API docs: https://www.polar.com/accesslink-api/
"""
from typing import Dict

from .base import IntegrationProvider


class PolarProvider(IntegrationProvider):
    """
    Polar integration provider stub.

    enabled=False: Not yet implemented. Provider is registered in the
    catalog so the frontend can show "Coming Soon" state.
    """

    @property
    def provider_id(self) -> str:
        return "polar"

    @property
    def display_name(self) -> str:
        return "Polar"

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
            "PolarProvider is not yet implemented. "
            "Provider must be enabled before use."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict:
        raise NotImplementedError(
            "PolarProvider is not yet implemented. "
            "Provider must be enabled before use."
        )

    def get_external_user_id(self, token_data: Dict) -> str:
        raise NotImplementedError(
            "PolarProvider is not yet implemented. "
            "Provider must be enabled before use."
        )
