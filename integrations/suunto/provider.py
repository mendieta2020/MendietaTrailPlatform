"""
Suunto Sports Tracking Services integration adapter — STUB.

Status: Placeholder only. Implementation begins when Suunto API access is granted.

Suunto-specific notes:
- Authentication uses OAuth 2.0 authorization code flow.
- Required credentials: SUUNTO_CLIENT_ID, SUUNTO_CLIENT_SECRET.
- Suunto STS API supports webhooks for near-real-time activity delivery.
- API reference: https://www.suunto.com/en-gb/sports-tech/suunto-developer-program/
"""
from __future__ import annotations

from datetime import datetime


class SuuntoProviderAdapter:
    """
    Placeholder adapter for Suunto integration.

    Will implement OAuth 2.0 flow, activity ingestion,
    and workout delivery when vendor access is granted.

    Implementation notes for future work:
    - Suunto STS supports webhook subscriptions (similar architecture to Strava).
    - The existing StravaWebhookView pattern in core/webhooks.py can be
      mirrored for Suunto webhook ingestion.
    - Map raw Suunto workoutSummary JSON to the normalized business TypedDict
      before passing to the domain ingestion pipeline.
    """

    PROVIDER_ID = "suunto"

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """Build Suunto OAuth 2.0 authorization URL."""
        raise NotImplementedError(
            "SuuntoProviderAdapter: OAuth flow not yet implemented. "
            "Awaiting Suunto developer program access."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns dict with access_token, refresh_token, expires_in.
        """
        raise NotImplementedError(
            "SuuntoProviderAdapter: token exchange not yet implemented."
        )

    def refresh_token(self, refresh_token: str) -> dict:
        """Refresh Suunto OAuth 2.0 access token."""
        raise NotImplementedError(
            "SuuntoProviderAdapter: token refresh not yet implemented."
        )

    def fetch_activities(
        self,
        access_token: str,
        after: datetime,
        before: datetime | None = None,
    ) -> list[dict]:
        """
        Fetch workout history from Suunto STS API.
        Returns list of raw Suunto workoutSummary dicts for normalization.
        """
        raise NotImplementedError(
            "SuuntoProviderAdapter: activity fetch not yet implemented."
        )
