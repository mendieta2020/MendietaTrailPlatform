from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import HistorialFitness, InjuryRiskSnapshot
from core.models import Alumno, Equipo, Entrenamiento


User = get_user_model()


class InjuryRiskAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach1 = User.objects.create_user(username="coach1", password="x")
        self.coach2 = User.objects.create_user(username="coach2", password="x")

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="Ana", apellido="Test", email="ana@test.com")
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="Beto", apellido="Other", email="beto@test.com")

        self.today = timezone.localdate()

        # PMC mínimo para alumno1 (hoy y 7d)
        HistorialFitness.objects.create(alumno=self.alumno1, fecha=self.today - timedelta(days=7), tss_diario=50, ctl=40, atl=40, tsb=0)
        HistorialFitness.objects.create(alumno=self.alumno1, fecha=self.today, tss_diario=120, ctl=50, atl=80, tsb=-30)

        # Snapshot existente para el list include
        InjuryRiskSnapshot.objects.create(
            entrenador=self.coach1,
            alumno=self.alumno1,
            fecha=self.today,
            risk_level="MEDIUM",
            risk_score=60,
            risk_reasons=["seed"],
            ctl=50,
            atl=80,
            tsb=-30,
        )

    def test_multi_tenant_denies_cross_athlete(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno2.id}/injury-risk/")
        # get_object() usa queryset scopiado -> 404
        self.assertEqual(res.status_code, 404)

    def test_injury_risk_endpoint_returns_latest(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno1.id}/injury-risk/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data_available", res.data)
        self.assertTrue(res.data["data_available"])
        self.assertIn("risk_level", res.data)

    def test_injury_risk_endpoint_date_param(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno1.id}/injury-risk/?date={self.today.isoformat()}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["data_available"])
        self.assertEqual(res.data["fecha"], self.today.isoformat())

    def test_include_injury_risk_in_list_no_n_plus_one_contract(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get("/api/alumnos/?include_injury_risk=1")
        self.assertEqual(res.status_code, 200)
        # alumno1 debería traer injury_risk embebido
        item = next(x for x in res.data if x["id"] == self.alumno1.id)
        self.assertIsNotNone(item.get("injury_risk"))
        self.assertEqual(item["injury_risk"]["risk_level"], "MEDIUM")


class TenantIsolationPMCTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach1 = User.objects.create_user(username="coach1_pmc", password="x")
        self.coach2 = User.objects.create_user(username="coach2_pmc", password="x")

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="Ana", apellido="PMC", email="ana_pmc@test.com")
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="Beto", apellido="PMC", email="beto_pmc@test.com")

        today = timezone.localdate()
        Entrenamiento.objects.create(
            alumno=self.alumno1,
            fecha_asignada=today,
            titulo="Plan A",
            tipo_actividad="RUN",
            tiempo_planificado_min=30,
            completado=False,
        )
        Entrenamiento.objects.create(
            alumno=self.alumno2,
            fecha_asignada=today,
            titulo="Plan B",
            tipo_actividad="RUN",
            tiempo_planificado_min=40,
            completado=False,
        )

    def test_pmc_denies_cross_tenant_alumno_id(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/analytics/pmc/?alumno_id={self.alumno2.id}")
        self.assertEqual(res.status_code, 200)
        # anti-fuga: debe ocultar (respuesta vacía, sin 403 para no romper frontend)
        self.assertEqual(res.data, [])

    def test_pmc_allows_own_tenant(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/analytics/pmc/?alumno_id={self.alumno1.id}")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)
        # Con al menos 1 entrenamiento, debería devolver ventana de datos (no vacía)
        self.assertGreater(len(res.data), 0)

    def test_pmc_all_includes_strength_in_load_calculation(self):
        """
        Requerimiento: STRENGTH suma carga fisiológica aunque no tenga distancia,
        y el PMC (sport=ALL) debe incluirla.
        """
        from django.test import override_settings

        today = timezone.localdate()

        # Endurance (usa RPE)
        Entrenamiento.objects.create(
            alumno=self.alumno1,
            fecha_asignada=today,
            titulo="Run",
            tipo_actividad="RUN",
            completado=True,
            tiempo_real_min=30,
            rpe=5,
        )

        # Strength (usa factor, no RPE)
        Entrenamiento.objects.create(
            alumno=self.alumno1,
            fecha_asignada=today,
            titulo="Gym",
            tipo_actividad="STRENGTH",
            completado=True,
            tiempo_real_min=30,
            rpe=9,  # debe ignorarse en carga de fuerza
            distancia_real_km=0,
        )

        with override_settings(STRENGTH_LOAD_FACTOR=3.0):
            self.client.force_authenticate(user=self.coach1)
            res = self.client.get(f"/api/analytics/pmc/?alumno_id={self.alumno1.id}&sport=ALL")
            self.assertEqual(res.status_code, 200)
            self.assertIsInstance(res.data, list)

            row = next((x for x in res.data if x.get("fecha") == today.isoformat()), None)
            self.assertIsNotNone(row, "Debe existir fila para el día de los entrenamientos")

            expected = int(30 * 5 + 30 * 3.0)
            self.assertEqual(row["load"], expected)


class TenantIsolationEquipoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach1 = User.objects.create_user(username="coach1_team", password="x")
        self.coach2 = User.objects.create_user(username="coach2_team", password="x")

        self.team1 = Equipo.objects.create(nombre="Equipo A", entrenador=self.coach1)
        self.team2 = Equipo.objects.create(nombre="Equipo B", entrenador=self.coach2)

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="Ana", apellido="Team", email="ana_team@test.com", equipo=self.team1)
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="Beto", apellido="Team", email="beto_team@test.com", equipo=self.team2)

    def test_coach_cannot_get_other_team_detail(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/equipos/{self.team2.id}/")
        self.assertEqual(res.status_code, 404)

    def test_coach_list_teams_is_scoped(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get("/api/equipos/")
        self.assertEqual(res.status_code, 200)
        ids = [t["id"] for t in res.data]
        self.assertIn(self.team1.id, ids)
        self.assertNotIn(self.team2.id, ids)

    def test_coach_cannot_assign_athlete_to_other_team(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.patch(f"/api/alumnos/{self.alumno1.id}/", {"equipo": self.team2.id}, format="json")
        self.assertEqual(res.status_code, 400)


class StravaOAuthLoggingTests(TestCase):
    def test_strava_oauth_urls_are_overridden(self):
        # Asegura que nuestras URLs (con logging enriquecido) estén primero que allauth.urls
        from django.urls import resolve

        # Nota: allauth construye una función wrapper (module=allauth...), así que validamos
        # que el adapter capturado en el closure sea el nuestro.
        match = resolve("/accounts/strava/login/")
        self.assertEqual(match.url_name, "strava_login")
        freevars = getattr(match.func, "__code__").co_freevars
        closure = match.func.__closure__ or ()
        self.assertIn("adapter", freevars)
        adapter_cell = dict(zip(freevars, closure))["adapter"].cell_contents
        self.assertEqual(adapter_cell.__module__, "core.strava_oauth_views")
        self.assertEqual(adapter_cell.__name__, "LoggedStravaOAuth2Adapter")

        match = resolve("/accounts/strava/login/callback/")
        self.assertEqual(match.url_name, "strava_callback")
        freevars = getattr(match.func, "__code__").co_freevars
        closure = match.func.__closure__ or ()
        self.assertIn("adapter", freevars)
        adapter_cell = dict(zip(freevars, closure))["adapter"].cell_contents
        self.assertEqual(adapter_cell.__module__, "core.strava_oauth_views")
        self.assertEqual(adapter_cell.__name__, "LoggedStravaOAuth2Adapter")

    def test_sanitize_oauth_payload_redacts_tokens(self):
        from core.strava_oauth_views import sanitize_oauth_payload

        raw = {
            "access_token": "secret-access",
            "refresh_token": "secret-refresh",
            "expires_at": 123,
            "athlete": {"id": 1, "username": "x"},
        }
        sanitized = sanitize_oauth_payload(raw)
        self.assertEqual(sanitized["access_token"], "<redacted>")
        self.assertEqual(sanitized["refresh_token"], "<redacted>")
        self.assertEqual(sanitized["expires_at"], "<redacted>")
        self.assertEqual(sanitized["athlete"]["id"], 1)

