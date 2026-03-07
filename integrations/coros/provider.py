"""
COROS Open Platform integration adapter — STUB.

Status: Placeholder only. Implementation begins when COROS API access is granted.

COROS-specific notes:
- Authentication uses OAuth 2.0 authorization code flow.
- Required credentials: COROS_CLIENT_ID, COROS_CLIENT_SECRET.
- API reference: https://open.coros.com/
"""
from __future__ import annotations

from datetime import datetime


class CorosProviderAdapter:
    """
    Placeholder adapter for COROS integration.

    Will implement OAuth 2.0 flow, activity ingestion,
    and workout delivery when vendor access is granted.

    Implementation notes for future work:
    - COROS Open Platform API provides activity list and detail endpoints.
    - Map raw COROS activity JSON to the normalized business TypedDict
      before passing to the domain ingestion pipeline.
    - COROS supports structured workout push for training plan delivery.
    """

    PROVIDER_ID = "coros"

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """Build COROS OAuth 2.0 authorization URL."""
        raise NotImplementedError(
            "CorosProviderAdapter: OAuth flow not yet implemented. "
            "Awaiting COROS Open Platform developer access."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns dict with access_token, refresh_token, expires_in.
        """
        raise NotImplementedError(
            "CorosProviderAdapter: token exchange not yet implemented."
        )

    def refresh_token(self, refresh_token: str) -> dict:
        """Refresh COROS OAuth 2.0 access token."""
        raise NotImplementedError(
            "CorosProviderAdapter: token refresh not yet implemented."
        )

    def fetch_activities(
        self,
        access_token: str,
        after: datetime,
        before: datetime | None = None,
    ) -> list[dict]:
        """
        Fetch activity list from COROS Open Platform API.
        Returns list of raw COROS activity dicts for normalization.
        """
        raise NotImplementedError(
            "CorosProviderAdapter: activity fetch not yet implemented."
        )
