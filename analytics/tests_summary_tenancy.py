from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Alumno

User = get_user_model()


class AnalyticsSummaryTenancyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_summary", password="x")
        self.other_coach = User.objects.create_user(username="coach_summary_other", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Summary",
            email="ana_summary@test.com",
        )
        self.other_alumno = Alumno.objects.create(
            entrenador=self.other_coach,
            nombre="Omar",
            apellido="Other",
            email="omar_other@test.com",
        )
        self.client.force_authenticate(user=self.coach)

    def test_summary_athlete_id_ok_returns_200(self):
        res = self.client.get(f"/api/analytics/summary/?athlete_id={self.alumno.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["alumno_id"], self.alumno.id)

    def test_summary_athlete_id_cross_tenant_returns_404(self):
        res = self.client.get(f"/api/analytics/summary/?athlete_id={self.other_alumno.id}")
        self.assertEqual(res.status_code, 404)

    def test_summary_mismatched_ids_return_404(self):
        res = self.client.get(
            f"/api/analytics/summary/?athlete_id={self.alumno.id}&alumno_id={self.other_alumno.id}"
        )
        self.assertEqual(res.status_code, 404)
