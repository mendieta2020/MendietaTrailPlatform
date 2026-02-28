import json
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

class TestStravaDiagnosticsView(TestCase):
    def setUp(self):
        self.client = APIClient()

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=332574)
    def test_with_configured_id(self):
        """
        Verify that configuring the subscription id returns true for subscription_id_configured
        and the correct value.
        """
        response = self.client.get("/api/integrations/strava/diagnostics/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["subscription_id_configured"])
        self.assertEqual(data["subscription_id_value"], 332574)
        
    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=None)
    def test_with_missing_id(self):
        """
        Verify that missing the subscription id returns false for subscription_id_configured.
        """
        response = self.client.get("/api/integrations/strava/diagnostics/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["subscription_id_configured"])
        self.assertIsNone(data["subscription_id_value"])
