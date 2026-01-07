from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Actividad, Alumno, Carrera, Entrenamiento


User = get_user_model()


def _api_list_results(res):
    if isinstance(res.data, dict) and "results" in res.data:
        return res.data["results"]
    return res.data


class TenantSecurityAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach_a = User.objects.create_user(username="coach_a", password="x")
        self.coach_b = User.objects.create_user(username="coach_b", password="x")

        self.alumno_a = Alumno.objects.create(
            entrenador=self.coach_a,
            nombre="Ana",
            apellido="CoachA",
            email="ana_coacha@test.com",
        )
        self.alumno_b = Alumno.objects.create(
            entrenador=self.coach_b,
            nombre="Beto",
            apellido="CoachB",
            email="beto_coachb@test.com",
        )

        today = timezone.localdate()
        self.entreno_a = Entrenamiento.objects.create(
            alumno=self.alumno_a,
            fecha_asignada=today,
            titulo="Plan A",
            tipo_actividad="RUN",
        )
        self.entreno_b = Entrenamiento.objects.create(
            alumno=self.alumno_b,
            fecha_asignada=today,
            titulo="Plan B",
            tipo_actividad="RUN",
        )

        self.actividad_b = Actividad.objects.create(
            usuario=self.coach_b,
            alumno=self.alumno_b,
            nombre="Run B",
            distancia=5000,
            tiempo_movimiento=1500,
            fecha_inicio=timezone.now(),
            tipo_deporte="RUN",
        )

        self.carrera = Carrera.objects.create(
            nombre="Carrera Global",
            fecha=today,
            distancia_km=10.0,
            desnivel_positivo_m=100,
        )

    def test_list_is_scoped_to_coach(self):
        self.client.force_authenticate(user=self.coach_a)
        res = self.client.get("/api/entrenamientos/")
        self.assertEqual(res.status_code, 200)
        results = _api_list_results(res)
        ids = [row["id"] for row in results]
        self.assertIn(self.entreno_a.id, ids)
        self.assertNotIn(self.entreno_b.id, ids)

    def test_retrieve_cross_tenant_is_denied(self):
        self.client.force_authenticate(user=self.coach_a)
        res = self.client.get(f"/api/entrenamientos/{self.entreno_b.id}/")
        self.assertEqual(res.status_code, 404)

    def test_nested_endpoint_denies_cross_tenant(self):
        self.client.force_authenticate(user=self.coach_a)
        res = self.client.get(f"/api/alumnos/{self.alumno_b.id}/actividades/")
        self.assertEqual(res.status_code, 404)

    def test_fail_closed_when_model_has_no_tenant_field(self):
        self.client.force_authenticate(user=self.coach_a)
        res = self.client.get("/api/carreras/")
        self.assertEqual(res.status_code, 403)
