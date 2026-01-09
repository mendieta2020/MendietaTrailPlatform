from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Actividad, Alumno


User = get_user_model()


def _api_list_results(res):
    if isinstance(res.data, dict) and "results" in res.data:
        return res.data["results"]
    return res.data


class ActividadPrivacyAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_privacy", password="x")
        self.staff = User.objects.create_user(username="staff_privacy", password="x", is_staff=True)

        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Privacy",
            email="ana_privacy@test.com",
        )
        self.actividad = Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            nombre="Actividad privada",
            distancia=5000,
            tiempo_movimiento=1500,
            fecha_inicio=timezone.now(),
            tipo_deporte="RUN",
            datos_brutos={"raw": "secret"},
        )

    def test_actividad_list_hides_raw_payload(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.get("/api/activities/")
        self.assertEqual(res.status_code, 200)
        results = _api_list_results(res)
        self.assertTrue(results)
        self.assertNotIn("datos_brutos", results[0])

    def test_actividad_detail_hides_raw_payload(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.get(f"/api/activities/{self.actividad.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("datos_brutos", res.data)

    def test_actividad_list_is_paginated(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.get("/api/activities/")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, dict)
        self.assertIn("count", res.data)
        self.assertIn("next", res.data)
        self.assertIn("previous", res.data)
        self.assertIn("results", res.data)

    def test_raw_payload_endpoint_denied_for_coach(self):
        self.client.force_authenticate(user=self.coach)
        res = self.client.get("/api/activities/raw/")
        self.assertEqual(res.status_code, 403)
