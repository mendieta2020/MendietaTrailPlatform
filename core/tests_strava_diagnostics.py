from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

User = get_user_model()

DIAGNOSTICS_URL = "/api/integrations/strava/diagnostics/"


class TestStravaDiagnosticsView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="coach_test",
            email="coach@example.com",
            password="testpass123",
        )

    # ------------------------------------------------------------------
    # Auth enforcement
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        """Unauthenticated callers must be rejected — Law 7 (no AllowAny on sensitive endpoints)."""
        response = self.client.get(DIAGNOSTICS_URL)
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # Authenticated — payload contract
    # ------------------------------------------------------------------

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=332574)
    def test_authenticated_with_configured_id_returns_200(self):
        """Authenticated user receives 200 and subscription_id_configured=True."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(DIAGNOSTICS_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["subscription_id_configured"])

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=None)
    def test_authenticated_with_missing_id_returns_200(self):
        """Authenticated user receives 200 and subscription_id_configured=False when not set."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(DIAGNOSTICS_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["subscription_id_configured"])

    @override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=332574)
    def test_response_never_exposes_raw_subscription_id(self):
        """The raw subscription ID value must never appear in the response body — Law 6."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(DIAGNOSTICS_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("subscription_id_value", data)
        # Confirm the numeric value is not present anywhere in the response
        self.assertNotIn("332574", response.content.decode())
