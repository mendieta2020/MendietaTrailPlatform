from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import HistorialFitness, InjuryRiskSnapshot
from core.models import Actividad, Alumno, Equipo, Entrenamiento


User = get_user_model()

def _api_list_results(res):
    """
    Helper para endpoints list que pueden venir paginados.
    Si hay paginación, DRF devuelve {"count","next","previous","results"}.
    """
    if isinstance(res.data, dict) and "results" in res.data:
        return res.data["results"]
    return res.data


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
        results = _api_list_results(res)
        item = next(x for x in results if x["id"] == self.alumno1.id)
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


class ActividadFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach1 = User.objects.create_user(username="coach_filter_1", password="x")
        self.coach2 = User.objects.create_user(username="coach_filter_2", password="x")

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="Ana", apellido="Filtro", email="ana_filtro@test.com")
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="Beto", apellido="Filtro", email="beto_filtro@test.com")

        self.start = timezone.now()
        self.end = self.start + timedelta(hours=1)

        self.activity_run = Actividad.objects.create(
            usuario=self.coach1,
            alumno=self.alumno1,
            nombre="Run base",
            distancia=5000,
            tiempo_movimiento=1500,
            fecha_inicio=self.start,
            tipo_deporte="RUN",
            source=Actividad.Source.STRAVA,
        )
        self.activity_bike = Actividad.objects.create(
            usuario=self.coach1,
            alumno=self.alumno1,
            nombre="Bike base",
            distancia=20000,
            tiempo_movimiento=3600,
            fecha_inicio=self.end,
            tipo_deporte="BIKE",
            source=Actividad.Source.GARMIN,
        )
        self.activity_other_tenant = Actividad.objects.create(
            usuario=self.coach2,
            alumno=self.alumno2,
            nombre="Other tenant",
            distancia=3000,
            tiempo_movimiento=1000,
            fecha_inicio=self.start,
            tipo_deporte="RUN",
            source=Actividad.Source.STRAVA,
        )

        self.training = Entrenamiento.objects.create(
            alumno=self.alumno1,
            fecha_asignada=timezone.localdate(),
            titulo="Plan",
            tipo_actividad="RUN",
            tiempo_planificado_min=30,
        )
        self.activity_with_training = Actividad.objects.create(
            usuario=self.coach1,
            alumno=self.alumno1,
            entrenamiento=self.training,
            nombre="Run linked",
            distancia=8000,
            tiempo_movimiento=2000,
            fecha_inicio=self.start + timedelta(days=1),
            tipo_deporte="RUN",
            source=Actividad.Source.STRAVA,
        )

    def test_actividad_filters_by_english_params(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(
            "/api/activities/",
            {
                "athlete_id": self.alumno1.id,
                "sport_type": "RUN",
                "start_date": self.start.date().isoformat(),
                "end_date": (self.start.date() + timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(res.status_code, 200)
        results = _api_list_results(res)
        ids = {item["id"] for item in results}
        self.assertIn(self.activity_run.id, ids)
        self.assertNotIn(self.activity_bike.id, ids)

    def test_actividad_filters_enforce_tenant_scope(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get("/api/activities/", {"athlete_id": self.alumno2.id})
        self.assertEqual(res.status_code, 200)
        results = _api_list_results(res)
        self.assertEqual(results, [])

    def test_actividad_filters_has_training(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get("/api/activities/", {"has_training": "true"})
        self.assertEqual(res.status_code, 200)
        results = _api_list_results(res)
        ids = {item["id"] for item in results}
        self.assertIn(self.activity_with_training.id, ids)
        self.assertNotIn(self.activity_run.id, ids)

    def test_pmc_allows_own_tenant(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/analytics/pmc/?alumno_id={self.alumno1.id}")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)
        # Con al menos 1 entrenamiento, debería devolver ventana de datos (no vacía)
        self.assertGreater(len(res.data), 0)


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
        results = _api_list_results(res)
        ids = [t["id"] for t in results]
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
