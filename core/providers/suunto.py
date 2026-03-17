"""
Suunto OAuth integration provider.

Delegates all provider-specific logic to integrations/suunto/oauth.py (Law 4).
"""
from typing import Dict

from .base import IntegrationProvider


class SuuntoProvider(IntegrationProvider):
    """
    Suunto integration provider — OAuth 2.0 authorization code flow.

    All Suunto-specific URLs and response parsing are isolated in
    integrations/suunto/oauth.py. This provider class is the domain-layer
    entry point and MUST NOT contain any Suunto-specific HTTP logic.
    """

    @property
    def provider_id(self) -> str:
        return "suunto"

    @property
    def display_name(self) -> str:
        return "Suunto"

    @property
    def enabled(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {
            "supports_refresh": True,
            "supports_activity_fetch": False,  # Phase 2
            "supports_webhooks": True,
            "supports_workout_push": True,
        }

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        from integrations.suunto.oauth import build_authorize_url
        return build_authorize_url(state, callback_uri)

    def exchange_code_for_token(self, code: str, callback_uri: str) -> Dict:
        from integrations.suunto.oauth import exchange_code_for_token
        return exchange_code_for_token(code, callback_uri)

    def get_external_user_id(self, token_data: Dict) -> str:
        from integrations.suunto.oauth import get_external_user_id
        return get_external_user_id(token_data)
