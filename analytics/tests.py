from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from analytics.injury_risk import compute_injury_risk
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from core.models import Actividad, Alumno
from analytics.models import AlertaRendimiento


class ComputeInjuryRiskTests(TestCase):
    def test_base_risk_by_tsb(self):
        r1 = compute_injury_risk(ctl=50, atl=80, tsb=-40)
        self.assertEqual(r1.risk_level, "HIGH")
        self.assertGreaterEqual(r1.risk_score, 80)

        r2 = compute_injury_risk(ctl=50, atl=70, tsb=-20)
        self.assertEqual(r2.risk_level, "MEDIUM")

        r3 = compute_injury_risk(ctl=50, atl=55, tsb=-5)
        self.assertEqual(r3.risk_level, "LOW")

    def test_atl_growth_escalates_one_level(self):
        # Base LOW -> escalates to MEDIUM
        r = compute_injury_risk(ctl=50, atl=60, tsb=-5, atl_7d_ago=40)
        self.assertEqual(r.risk_level, "MEDIUM")
        self.assertIn("ATL creció >20% en 7 días", r.risk_reasons)

    def test_consecutive_high_load_escalates_one_level(self):
        # Base MEDIUM -> escalates to HIGH
        r = compute_injury_risk(
            ctl=50,
            atl=70,
            tsb=-20,
            last_3_days_tss=[120, 130, 125],
            high_tss_threshold=100,
            high_load_relative_to_ctl=1.5,
        )
        self.assertEqual(r.risk_level, "HIGH")
        self.assertTrue(any("3+ días consecutivos" in s for s in r.risk_reasons))


class AnalyticsAlertsEndpointTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.url = "/api/analytics/alerts/"

    def _obtain_jwt(self, username: str, password: str) -> dict:
        """
        Helper real (end-to-end) usando los endpoints JWT del proyecto.
        Retorna {"access": "...", "refresh": "..."}.
        """
        # Asegurar que no quede Authorization de otros tests
        self.api_client.credentials()
        resp = self.api_client.post(
            "/api/token/",
            {"username": username, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        return {"access": resp.data["access"], "refresh": resp.data["refresh"]}

    def test_alerts_requires_auth(self):
        resp = self.api_client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def test_alerts_with_jwt_gets_200(self):
        User = get_user_model()
        coach = User.objects.create_user(
            username="coach_jwt",
            email="coach_jwt@example.com",
            password="pass12345",
        )
        tokens = self._obtain_jwt("coach_jwt", "pass12345")
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.api_client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_alerts_legacy_without_page_returns_list(self):
        User = get_user_model()
        coach = User.objects.create_user(
            username="coach",
            email="coach@example.com",
            password="pass12345",
        )
        alumno = Alumno.objects.create(
            entrenador=coach,
            nombre="A",
            apellido="B",
            email="alumno1@example.com",
        )

        for i in range(30):
            AlertaRendimiento.objects.create(
                alumno=alumno,
                tipo="FTP_UP",
                valor_detectado=260 + i,
                valor_anterior=250,
                mensaje=f"alert {i}",
                visto_por_coach=False,
            )

        tokens = self._obtain_jwt("coach", "pass12345")
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.api_client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)
        # Compat: no envelope paginado
        if resp.data:
            self.assertNotIn("results", resp.data)

    def test_alerts_with_page_and_page_size_returns_paginated_envelope(self):
        User = get_user_model()
        coach = User.objects.create_user(
            username="coach2",
            email="coach2@example.com",
            password="pass12345",
        )
        alumno = Alumno.objects.create(
            entrenador=coach,
            nombre="C",
            apellido="D",
            email="alumno2@example.com",
        )

        for i in range(30):
            AlertaRendimiento.objects.create(
                alumno=alumno,
                tipo="HR_MAX",
                valor_detectado=190 + i,
                valor_anterior=185,
                mensaje=f"alert {i}",
                visto_por_coach=False,
            )

        tokens = self._obtain_jwt("coach2", "pass12345")
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.api_client.get(f"{self.url}?page=1&page_size=20")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, dict)
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 30)
        self.assertLessEqual(len(resp.data["results"]), 20)

    def test_alerts_are_scoped_to_authenticated_user(self):
        """
        Multi-tenant: un coach no debe ver alertas de otro coach.
        """
        User = get_user_model()
        coach1 = User.objects.create_user(username="coach_a", email="a@example.com", password="pass12345")
        coach2 = User.objects.create_user(username="coach_b", email="b@example.com", password="pass12345")

        alumno1 = Alumno.objects.create(entrenador=coach1, nombre="A", apellido="A", email="a1@example.com")
        alumno2 = Alumno.objects.create(entrenador=coach2, nombre="B", apellido="B", email="b1@example.com")

        for i in range(5):
            AlertaRendimiento.objects.create(
                alumno=alumno1,
                tipo="FTP_UP",
                valor_detectado=260 + i,
                valor_anterior=250,
                mensaje=f"coach1 alert {i}",
                visto_por_coach=False,
            )
        for i in range(7):
            AlertaRendimiento.objects.create(
                alumno=alumno2,
                tipo="HR_MAX",
                valor_detectado=190 + i,
                valor_anterior=185,
                mensaje=f"coach2 alert {i}",
                visto_por_coach=False,
            )

        tokens = self._obtain_jwt("coach_a", "pass12345")
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        # Legacy list (sin paginación)
        resp_legacy = self.api_client.get(self.url)
        self.assertEqual(resp_legacy.status_code, 200)
        self.assertIsInstance(resp_legacy.data, list)
        self.assertEqual(len(resp_legacy.data), 5)
        self.assertTrue(all("coach1 alert" in a["mensaje"] for a in resp_legacy.data))

        # Paginado opt-in
        resp_pag = self.api_client.get(f"{self.url}?page=1&page_size=20")
        self.assertEqual(resp_pag.status_code, 200)
        self.assertEqual(resp_pag.data["count"], 5)
        self.assertTrue(all("coach1 alert" in a["mensaje"] for a in resp_pag.data["results"]))


class AnalyticsMaterializationTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.user_model = get_user_model()

    def _auth_client(self, username: str, password: str):
        self.api_client.credentials()
        resp = self.api_client.post("/api/token/", {"username": username, "password": password}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def _create_activity(self, alumno: Alumno):
        return Actividad.objects.create(
            usuario=alumno.entrenador,
            alumno=alumno,
            source=Actividad.Source.STRAVA,
            source_object_id="test-activity-1",
            nombre="Test Run",
            distancia=5000.0,
            tiempo_movimiento=1800,
            fecha_inicio=timezone.now() - timedelta(days=1),
            tipo_deporte="RUN",
        )

    def test_pmc_returns_pending_when_materialization_missing(self):
        coach = self.user_model.objects.create_user(username="coach_pmc", email="pmc@example.com", password="pass12345")
        alumno = Alumno.objects.create(entrenador=coach, nombre="A", apellido="B", email="pmc_alumno@example.com")
        self._create_activity(alumno)
        self._auth_client("coach_pmc", "pass12345")

        with mock.patch("analytics.views.recompute_pmc_from_activities.delay") as mocked_delay:
            resp = self.api_client.get(f"/api/analytics/pmc/?alumno_id={alumno.id}")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertEqual(resp.data["status"], "PENDING")
        mocked_delay.assert_called()

    def test_summary_returns_pending_when_materialization_missing(self):
        coach = self.user_model.objects.create_user(username="coach_summary", email="sum@example.com", password="pass12345")
        alumno = Alumno.objects.create(entrenador=coach, nombre="C", apellido="D", email="sum_alumno@example.com")
        self._create_activity(alumno)
        self._auth_client("coach_summary", "pass12345")

        with mock.patch("analytics.views.recompute_pmc_from_activities.delay") as mocked_delay:
            resp = self.api_client.get(f"/api/analytics/summary/?alumno_id={alumno.id}")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertEqual(resp.data["status"], "PENDING")
        mocked_delay.assert_called()

    def test_materialization_status_requires_alumno_id_for_coach(self):
        coach = self.user_model.objects.create_user(username="coach_status", email="status@example.com", password="pass12345")
        self._auth_client("coach_status", "pass12345")
        resp = self.api_client.get("/api/analytics/materialization-status/")
        self.assertEqual(resp.status_code, 400)
