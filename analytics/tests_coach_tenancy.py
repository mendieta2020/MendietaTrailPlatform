from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from analytics.models import AlertaRendimiento, Alert
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
        self.perf_alert = AlertaRendimiento.objects.create(
            alumno=self.alumno,
            tipo="FTP_UP",
            valor_detectado=320.0,
            valor_anterior=300.0,
            mensaje="Alert performance own coach",
        )
        self.other_alert = Alert.objects.create(
            entrenador=self.other_coach,
            alumno=self.other_alumno,
            type=Alert.Type.OVERTRAINING_RISK,
            severity=Alert.Severity.WARN,
            message="Alert other coach",
        )
        self.other_perf_alert = AlertaRendimiento.objects.create(
            alumno=self.other_alumno,
            tipo="HR_MAX",
            valor_detectado=190.0,
            valor_anterior=180.0,
            mensaje="Alert performance other coach",
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
        self.assertGreaterEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["id"], self.perf_alert.id)

    def test_alerts_list_cross_tenant_returns_404(self):
        res = self.client.get(f"/api/coach/athletes/{self.other_alumno.id}/alerts/")
        self.assertEqual(res.status_code, 404)

    def test_analytics_alerts_list_includes_own_alert(self):
        res = self.client.get(f"/api/analytics/alerts/?alumno_id={self.alumno.id}")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.data), 1)
        ids = [item["id"] for item in res.data]
        self.assertIn(self.perf_alert.id, ids)

    def test_alert_patch_own_tenant_returns_200(self):
        res = self.client.patch(
            f"/api/coach/alerts/{self.alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.alert.id)
        self.assertTrue(res.data["visto_por_coach"])
        self.alert.refresh_from_db()
        self.assertTrue(self.alert.visto_por_coach)

        perf_res = self.client.patch(
            f"/api/coach/alerts/{self.perf_alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(perf_res.status_code, 200)
        self.assertEqual(perf_res.data["id"], self.perf_alert.id)
        self.assertTrue(perf_res.data["visto_por_coach"])
        self.perf_alert.refresh_from_db()
        self.assertTrue(self.perf_alert.visto_por_coach)

    def test_alert_patch_cross_tenant_returns_404(self):
        res = self.client.patch(
            f"/api/coach/alerts/{self.other_alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

        perf_res = self.client.patch(
            f"/api/coach/alerts/{self.other_perf_alert.id}/",
            {"visto_por_coach": True},
            format="json",
        )
        self.assertEqual(perf_res.status_code, 404)
