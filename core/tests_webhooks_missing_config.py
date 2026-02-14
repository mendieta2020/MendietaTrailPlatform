import json
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse

class StravaWebhookMissingConfigTests(TestCase):
    def test_missing_config_returns_200_and_does_not_enqueue(self):
        """
        If STRAVA_WEBHOOK_SUBSCRIPTION_ID is invalid or missing generally,
        we usually want fail-closed (403 or 500).
        BUT the user specifically requested:
        'If required config ... is missing, ... return HTTP 200 ... do not enqueue'
        """
        # Ensure setting is missing/None
        with override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=None):
            payload = {
                "object_type": "activity",
                "aspect_type": "create",
                "object_id": 123,
                "owner_id": 999,
                "subscription_id": 1,
                "event_time": 1700000000,
            }
            
            with patch("core.webhooks.process_strava_event.delay") as delay_mock:
                response = self.client.post(
                    "/webhooks/strava/",
                    data=json.dumps(payload),
                    content_type="application/json"
                )
                
                # Currently fails with 500. Goal: 200.
                self.assertEqual(response.status_code, 200)
                
                # Verify we did NOT enqueue anything
                self.assertEqual(delay_mock.call_count, 0)
