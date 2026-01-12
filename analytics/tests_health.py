import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import StravaWebhookEvent


class HealthzTests(TestCase):
    def _create_event(self, *, status, updated_at=None):
        event = StravaWebhookEvent.objects.create(
            event_uid=f"evt-{uuid.uuid4()}",
            object_type="activity",
            object_id=123,
            aspect_type="create",
            owner_id=456,
            status=status,
        )
        if updated_at is not None:
            StravaWebhookEvent.objects.filter(pk=event.pk).update(updated_at=updated_at)
        return event

    def test_healthz_db_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["db"], "ok")

    def test_healthz_celery_ok(self):
        with patch("analytics.health_views.celery_app.control.ping") as mock_ping:
            mock_ping.return_value = [{"worker-1": "pong"}]
            response = self.client.get("/healthz/celery")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["checks"]["celery"]["workers_responding"], 1)

    @override_settings(CELERY_BROKER_URL="redis://localhost:6379/0")
    def test_healthz_redis_ok(self):
        with patch("analytics.health_views.Connection") as mock_connection:
            mock_connection.return_value.__enter__.return_value.ensure_connection.return_value = None
            response = self.client.get("/healthz/redis")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["redis"], "ok")

    @override_settings(STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD=2, STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES=5)
    def test_healthz_strava_ok(self):
        response = self.client.get("/healthz/strava")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @override_settings(STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD=2, STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES=5)
    def test_healthz_strava_degraded_on_failed(self):
        self._create_event(status=StravaWebhookEvent.Status.FAILED)
        response = self.client.get("/healthz/strava")
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["checks"]["strava"]["failed"], 1)

    @override_settings(STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD=2, STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES=5)
    def test_healthz_strava_degraded_on_stuck(self):
        stuck_time = timezone.now() - timedelta(minutes=10)
        self._create_event(status=StravaWebhookEvent.Status.PROCESSING, updated_at=stuck_time)
        response = self.client.get("/healthz/strava")
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["checks"]["strava"]["stuck_processing"], 1)

    @override_settings(STRAVA_WEBHOOK_FAILED_ALERT_THRESHOLD=2, STRAVA_WEBHOOK_STUCK_THRESHOLD_MINUTES=5)
    def test_healthz_strava_unhealthy(self):
        for _ in range(3):
            self._create_event(status=StravaWebhookEvent.Status.FAILED)
        response = self.client.get("/healthz/strava")
        self.assertEqual(response.json()["status"], "unhealthy")
