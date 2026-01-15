import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase


class SwaggerSecurityTests(APITestCase):
    def test_swagger_denies_non_staff_when_enabled(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="viewer",
            password="test-pass-123",
        )
        staff_user = user_model.objects.create_user(
            username="admin",
            password="test-pass-123",
            is_staff=True,
        )

        with override_settings(SWAGGER_ENABLED=True):
            response_anonymous = self.client.get("/swagger/")
            self.client.force_authenticate(user=user)
            response_non_staff = self.client.get("/swagger/")
            self.client.force_authenticate(user=staff_user)
            response_staff = self.client.get("/swagger/")
            self.client.force_authenticate(user=None)

        self.assertEqual(response_anonymous.status_code, 401)
        self.assertEqual(response_non_staff.status_code, 403)
        self.assertEqual(response_staff.status_code, 200)


class ThrottlingSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="coach",
            password="test-pass-123",
        )
        self.client.defaults["REMOTE_ADDR"] = "203.0.113.10"

    def tearDown(self):
        cache.clear()

    def _rest_framework_with_rates(self, rates):
        rest_framework = settings.REST_FRAMEWORK.copy()
        rest_framework["DEFAULT_THROTTLE_RATES"] = rates
        return rest_framework

    def test_token_endpoint_is_throttled(self):
        rest_framework = self._rest_framework_with_rates(
            {
                "token": "1/min",
                "strava_webhook": "1000/min",
                "coach": "1000/min",
                "analytics": "1000/min",
            }
        )

        with override_settings(REST_FRAMEWORK=rest_framework):
            response_ok = self.client.post(
                "/api/token/",
                {"username": "coach", "password": "test-pass-123"},
                format="json",
            )
            response_limited = self.client.post(
                "/api/token/",
                {"username": "coach", "password": "test-pass-123"},
                format="json",
            )

        self.assertEqual(response_ok.status_code, 200)
        self.assertEqual(response_limited.status_code, 429)

    def test_strava_webhook_is_throttled(self):
        rest_framework = self._rest_framework_with_rates(
            {
                "token": "1000/min",
                "strava_webhook": "1/min",
                "coach": "1000/min",
                "analytics": "1000/min",
            }
        )
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 123,
            "owner_id": 999,
            "subscription_id": 1,
            "event_time": 1700000000,
        }

        with override_settings(REST_FRAMEWORK=rest_framework):
            with patch("core.webhooks.process_strava_event.delay") as delay_mock:
                response_ok = self.client.post(
                    "/webhooks/strava/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                response_limited = self.client.post(
                    "/webhooks/strava/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )

        self.assertEqual(response_ok.status_code, 200)
        self.assertEqual(response_limited.status_code, 429)
        self.assertEqual(delay_mock.call_count, 1)
