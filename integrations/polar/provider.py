"""
Polar Accesslink integration adapter — STUB.

Status: Placeholder only. Implementation begins when Polar API access is granted.

Polar-specific notes:
- Authentication uses OAuth 2.0 authorization code flow via Polar Accesslink API.
- Required credentials: POLAR_CLIENT_ID, POLAR_CLIENT_SECRET.
- Polar uses a "transaction" model for activity delivery (pull, not push).
- API reference: https://www.polar.com/accesslink-api/
"""
from __future__ import annotations

from datetime import datetime


class PolarProviderAdapter:
    """
    Placeholder adapter for Polar Accesslink integration.

    Will implement OAuth 2.0 flow, activity ingestion,
    and workout delivery when vendor access is granted.

    Implementation notes for future work:
    - Polar Accesslink uses a transaction-based pull model:
      register_user → list_transactions → commit_transaction.
    - Map raw Polar ExerciseSummary to the normalized business TypedDict
      before passing to the domain ingestion pipeline.
    - Polar supports structured workout push via Training Load Pro API.
    """

    PROVIDER_ID = "polar"

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """Build Polar OAuth 2.0 authorization URL."""
        raise NotImplementedError(
            "PolarProviderAdapter: OAuth flow not yet implemented. "
            "Awaiting Polar Accesslink API developer access."
        )

    def exchange_code_for_token(self, code: str, callback_uri: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns dict with access_token, token_type, x_user_id.
        """
        raise NotImplementedError(
            "PolarProviderAdapter: token exchange not yet implemented."
        )

    def refresh_token(self, refresh_token: str) -> dict:
        """Refresh Polar OAuth 2.0 access token."""
        raise NotImplementedError(
            "PolarProviderAdapter: token refresh not yet implemented."
        )

    def fetch_activities(
        self,
        access_token: str,
        after: datetime,
        before: datetime | None = None,
    ) -> list[dict]:
        """
        Pull activity transactions from Polar Accesslink API.
        Returns list of raw Polar activity dicts for normalization.
        """
        raise NotImplementedError(
            "PolarProviderAdapter: activity fetch not yet implemented."
        )
