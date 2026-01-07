from django.test import TestCase
from django.contrib.auth.models import AnonymousUser

from analytics.injury_risk import compute_injury_risk
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APIRequestFactory
from core.models import Alumno
from analytics.models import AlertaRendimiento
from analytics.views import AlertaRendimientoViewSet


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


class AnalyticsAlertsSchemaGuardTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.url = "/api/analytics/alerts/"

    def _obtain_jwt(self, username: str, password: str) -> dict:
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

    def test_alerts_get_queryset_handles_swagger_fake_view(self):
        factory = APIRequestFactory()
        request = factory.get("/api/analytics/alerts/")
        request.user = AnonymousUser()

        view = AlertaRendimientoViewSet()
        view.request = request
        view.swagger_fake_view = True

        queryset = view.get_queryset()
        self.assertEqual(queryset.count(), 0)

    def test_alerts_get_queryset_handles_anonymous_user(self):
        factory = APIRequestFactory()
        request = factory.get("/api/analytics/alerts/")
        request.user = AnonymousUser()

        view = AlertaRendimientoViewSet()
        view.request = request

        queryset = view.get_queryset()
        self.assertEqual(queryset.count(), 0)

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
