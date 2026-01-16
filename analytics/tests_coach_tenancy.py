from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from analytics.models import Alert
from core.models import Alumno

User = get_user_model()


class CoachTenancyEndpointsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_tenancy", password="pass")
        self.other_coach = User.objects.create_user(username="coach_tenancy_other", password="pass")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Coach",
            email="ana_coach@test.com",
        )
        self.other_alumno = Alumno.objects.create(
            entrenador=self.other_coach,
            nombre="Omar",
            apellido="Other",
            email="omar_other@test.com",
        )
        self.alert = Alert.objects.create(
            entrenador=self.coach,
            alumno=self.alumno,
            type=Alert.Type.ANOMALY,
            severity=Alert.Severity.INFO,
            message="Alert own coach",
        )
        self.other_alert = Alert.objects.create(
            entrenador=self.other_coach,
            alumno=self.other_alumno,
            type=Alert.Type.OVERTRAINING_RISK,
            severity=Alert.Severity.WARN,
            message="Alert other coach",
        )
        self.client.force_authenticate(user=self.coach)

        today = date.today()
        year, week, _ = today.isocalendar()
        self.week = f"{year}-{week:02d}"

    def test_week_summary_own_tenant_returns_200(self):
        res = self.client.get(f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["athlete_id"], self.alumno.id)

    def test_week_summary_cross_tenant_returns_404(self):
        res = self.client.get(f"/api/coach/athletes/{self.other_alumno.id}/week-summary/?week={self.week}")
        self.assertEqual(res.status_code, 404)

    def test_alerts_list_own_tenant_returns_200(self):
        res = self.client.get(f"/api/coach/athletes/{self.alumno.id}/alerts/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["athlete_id"], self.alumno.id)

    def test_alerts_list_cross_tenant_returns_404(self):
        res = self.client.get(f"/api/coach/athletes/{self.other_alumno.id}/alerts/")
        self.assertEqual(res.status_code, 404)

    def test_alert_patch_own_tenant_returns_200(self):
        res = self.client.patch(
            f"/api/coach/alerts/{self.alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.alert.id)
        self.assertTrue(res.data["visto_por_coach"])

    def test_alert_patch_cross_tenant_returns_404(self):
        res = self.client.patch(
            f"/api/coach/alerts/{self.other_alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(res.status_code, 404)
