"""
Wahoo Cloud API integration adapter — STUB.

Status: Placeholder only. Implementation begins when Wahoo API access is granted.

Wahoo-specific notes:
- Authentication uses OAuth 2.0 authorization code flow via Wahoo Cloud API.
- Required credentials: WAHOO_CLIENT_ID, WAHOO_CLIENT_SECRET.
- Supports structured workout push to Wahoo ELEMNT cycling computers.
- API reference: https://developer.wahooligan.com/
"""
from __future__ import annotations

from datetime import datetime


class WahooProviderAdapter:
    """
    Placeholder adapter for Wahoo integration.

    Will implement OAuth 2.0 flow, activity ingestion,
    and workout delivery when vendor access is granted.

    Implementation notes for future work:
    - Wahoo Cloud API supports both activity pull and workout push.
    - Workout push is a key differentiator for Quantoryn: structured sessions
      can be sent directly to ELEMNT devices for guided execution.
    - Map raw Wahoo workout JSON to the normalized business TypedDict
      before passing to the domain ingestion pipeline.
    """

    PROVIDER_ID = "wahoo"

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """Build Wahoo OAuth 2.0 authorization URL."""
        raise NotImplementedError(
            "WahooProviderAdapter: OAuth flow not yet implemented. "
            "Awaiting Wahoo developer program access."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns dict with access_token, refresh_token, expires_in, user_id.
        """
        raise NotImplementedError(
            "WahooProviderAdapter: token exchange not yet implemented."
        )

    def refresh_token(self, refresh_token: str) -> dict:
        """Refresh Wahoo OAuth 2.0 access token."""
        raise NotImplementedError(
            "WahooProviderAdapter: token refresh not yet implemented."
        )

    def fetch_activities(
        self,
        access_token: str,
        after: datetime,
        before: datetime | None = None,
    ) -> list[dict]:
        """
        Fetch workouts from Wahoo Cloud API.
        Returns list of raw Wahoo workout dicts for normalization.
        """
        raise NotImplementedError(
            "WahooProviderAdapter: activity fetch not yet implemented."
        )

    def push_workout(self, access_token: str, workout: dict) -> dict:
        """
        Push a structured workout to the athlete's Wahoo ELEMNT device.
        This capability differentiates Wahoo from other providers.
        """
        raise NotImplementedError(
            "WahooProviderAdapter: workout push not yet implemented."
        )
