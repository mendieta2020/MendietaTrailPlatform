import json
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Actividad, Alumno, StravaWebhookEvent
from core.tests_strava import _FakeStravaActivity, _FakeStravaClient


@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestsWebhookFiabilidad(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _payload(self):
        return {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 123,
            "owner_id": 999,
            "subscription_id": 1,
            "event_time": 1700000000,
        }

    def test_webhook_valido_crea_evento_y_responde_2xx(self):
        payload = self._payload()
        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(delay_mock.call_count, 1)
        evento = StravaWebhookEvent.objects.get()
        self.assertEqual(evento.status, StravaWebhookEvent.Status.QUEUED)
        self.assertEqual(evento.attempts, 0)

    def test_error_interno_recuperable_marca_failed_y_responde_5xx(self):
        payload = self._payload()
        with patch("core.webhooks.process_strava_event.delay", side_effect=RuntimeError("cola caída")):
            res = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertGreaterEqual(res.status_code, 500)
        evento = StravaWebhookEvent.objects.get()
        self.assertEqual(evento.status, StravaWebhookEvent.Status.FAILED)
        self.assertEqual(evento.attempts, 1)
        self.assertTrue(evento.last_error)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True, STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
class TestsWebhookIdempotencia(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_webhook", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Test",
            email="ana_webhook@test.com",
            strava_athlete_id="999",
        )

    def test_reintento_idempotente_no_duplica_actividades(self):
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 555,
            "owner_id": 999,
            "subscription_id": 1,
            "event_time": 1700001234,
        }
        actividad = _FakeStravaActivity(
            activity_id=555,
            athlete_id=999,
            name="Rodaje",
            type_="Run",
            start=timezone.now(),
            distance_m=5000.0,
            moving_time_s=1500,
            elapsed_time_s=1500,
            elev_m=20.0,
        )

        with patch(
            "core.services.obtener_cliente_strava_para_alumno",
            return_value=_FakeStravaClient(actividad),
        ):
            res1 = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )
            res2 = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(StravaWebhookEvent.objects.count(), 1)
        self.assertEqual(Actividad.objects.count(), 1)


class TestsWebhookEventosColgados(TestCase):
    def test_evento_processing_antiguo_se_detecta_como_stuck(self):
        evento = StravaWebhookEvent.objects.create(
            event_uid="stuck-1",
            object_type="activity",
            object_id=123,
            aspect_type="create",
            owner_id=999,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.PROCESSING,
        )
        viejo = timezone.now() - timezone.timedelta(minutes=10)
        StravaWebhookEvent.objects.filter(pk=evento.pk).update(updated_at=viejo)

        stuck = StravaWebhookEvent.objects.stuck_processing(older_than_minutes=5)
        self.assertEqual(list(stuck.values_list("id", flat=True)), [evento.id])
