"""
Garmin Connect integration adapter — STUB.

Status: Placeholder only. Implementation begins when Garmin API access is granted.

Garmin-specific notes:
- Authentication uses OAuth 1.0a (not OAuth 2.0 authorization code flow).
  The base IntegrationProvider contract assumes OAuth 2.0; Garmin requires a
  separate OAuth 1.0a code path using requests-oauthlib.
- Activity sync uses polling; Garmin's public API does not support webhooks.
- Required credentials: GARMIN_CONSUMER_KEY, GARMIN_CONSUMER_SECRET.
- API reference: https://developer.garmin.com/gc-developer-program/overview/
"""
from __future__ import annotations

from datetime import datetime


class GarminProviderAdapter:
    """
    Placeholder adapter for Garmin Connect integration.

    Will implement OAuth 1.0a flow, activity polling/ingestion,
    and workout delivery when vendor access is granted.

    Implementation notes for future work:
    - Use requests-oauthlib.OAuth1Session for the OAuth 1.0a handshake.
    - Polling cadence must respect Garmin rate limits (see API docs).
    - Map raw Garmin activity JSON to NormalizedStravaBusinessActivity-equivalent
      TypedDict before passing to the domain ingestion pipeline.
    """

    PROVIDER_ID = "garmin"

    def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
        """
        Build Garmin OAuth 1.0a authorization URL.
        Requires a temporary request token exchange before redirecting.
        """
        raise NotImplementedError(
            "GarminProviderAdapter: OAuth 1.0a flow not yet implemented. "
            "Awaiting Garmin Connect API developer access."
        )

    def exchange_code_for_token(self, oauth_verifier: str, callback_uri: str) -> dict:
        """
        Exchange OAuth 1.0a verifier for access token.
        Returns dict with access_token, access_token_secret.
        """
        raise NotImplementedError(
            "GarminProviderAdapter: token exchange not yet implemented."
        )

    def refresh_token(self, refresh_token: str) -> dict:
        """
        OAuth 1.0a access tokens do not expire; this method is not applicable.
        Included for interface consistency.
        """
        raise NotImplementedError(
            "GarminProviderAdapter: OAuth 1.0a does not use refresh tokens."
        )

    def fetch_activities(
        self,
        access_token: str,
        after: datetime,
        before: datetime | None = None,
    ) -> list[dict]:
        """
        Poll Garmin Health API for activities in the given date range.
        Returns list of raw Garmin activity dicts for normalization.
        """
        raise NotImplementedError(
            "GarminProviderAdapter: activity fetch not yet implemented."
        )
