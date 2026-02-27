"""
Protective tests for PR-WebhookRoute:
GET /api/integrations/strava/webhook/ — Strava push_subscription verification.

Coverage:
  1. Correct token → 200, hub.challenge echoed.
  2. Wrong token → 403.
  3. POST → 200 (event ingestion path, no crash).
"""

import json

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

WEBHOOK_URL = "/api/integrations/strava/webhook/"
GOOD_TOKEN = "test_verify_token_abc"
CHALLENGE = "strava_challenge_xyz"


class StravaWebhookVerifyEndpointTests(TestCase):
    """Tests exercising the new /api/integrations/strava/webhook/ route."""

    def setUp(self):
        self.client = APIClient()

    # ------------------------------------------------------------------
    # GET — subscription verification handshake
    # ------------------------------------------------------------------

    @override_settings(
        STRAVA_WEBHOOK_VERIFY_TOKEN=GOOD_TOKEN,
        DEBUG=False,
    )
    def test_get_correct_token_returns_200_and_echoes_challenge(self):
        """
        GET with matching hub.verify_token must return HTTP 200
        and body: {"hub.challenge": "<challenge>"}
        """
        response = self.client.get(
            WEBHOOK_URL,
            {
                "hub.mode": "subscribe",
                "hub.verify_token": GOOD_TOKEN,
                "hub.challenge": CHALLENGE,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data.get("hub.challenge"), CHALLENGE)

    @override_settings(
        STRAVA_WEBHOOK_VERIFY_TOKEN=GOOD_TOKEN,
        DEBUG=False,
    )
    def test_get_wrong_token_returns_403(self):
        """
        GET with a mismatched hub.verify_token must return HTTP 403.
        """
        response = self.client.get(
            WEBHOOK_URL,
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG_TOKEN",
                "hub.challenge": CHALLENGE,
            },
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # POST — event ingestion (smoke test, fail-closed config path)
    # ------------------------------------------------------------------

    @override_settings(
        STRAVA_WEBHOOK_VERIFY_TOKEN=GOOD_TOKEN,
        STRAVA_WEBHOOK_SUBSCRIPTION_ID=None,  # fail-closed: no sub id → ACK only
        DEBUG=False,
    )
    def test_post_returns_200(self):
        """
        POST to the webhook endpoint must always return HTTP 200
        (ACK so Strava does not retry). With no subscription id configured,
        the event is acknowledged but not processed.
        """
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 99001,
            "owner_id": 88001,
            "subscription_id": 12345,
            "event_time": 1700000000,
        }
        response = self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
