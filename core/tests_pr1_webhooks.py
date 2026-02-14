
import json
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

class TestStravaWebhookFailClosed(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 12345,
            "owner_id": 99999,
            "subscription_id": 1001,
            "event_time": 1700000000
        }

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=None)
    def test_missing_config_returns_500(self):
        """
        If settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID is missing/None,
        return 500 and log critical (do not process).
        """
        response = self.client.post(
            "/webhooks/strava/",
            data=json.dumps(self.payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 500)

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=9999)
    def test_subscription_mismatch_returns_403(self):
        """
        If request payload subscription_id (1001) mismatches expected (9999),
        return 403.
        """
        response = self.client.post(
            "/webhooks/strava/",
            data=json.dumps(self.payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1001)
    def test_subscription_match_returns_200(self):
        """
        If request payload subscription_id (1001) matches expected (1001),
        proceed as today (200).
        """
        # Mock processing to avoid side effects (DB, Celery) and just verify it got past the check
        with patch("core.webhooks.process_strava_event.delay") as mock_delay:
            response = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(self.payload),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
            # Ensure it actually tried to process an event
            self.assertTrue(mock_delay.called)
