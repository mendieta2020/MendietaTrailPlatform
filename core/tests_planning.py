from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Alumno, Entrenamiento, PlantillaEntrenamiento


User = get_user_model()


class AsignarPlantillaAlumnoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_plan", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Plan",
            email="ana_plan@test.com",
        )
        self.plantilla = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach,
            titulo="Base Run",
            deporte="RUN",
            descripcion_global="Base semanal",
            estructura={"bloques": [{"tipo": "WARMUP", "duracion": 600}]},
        )
        self.client.force_authenticate(user=self.coach)
        self.fecha = date(2025, 12, 15)

    def _assign(self, plantilla_id=None, alumno_id=None, fecha=None):
        return self.client.post(
            f"/api/plantillas/{plantilla_id or self.plantilla.id}/asignar_a_alumno/",
            {
                "alumno_id": alumno_id or self.alumno.id,
                "fecha": (fecha or self.fecha).isoformat() if fecha else self.fecha.isoformat(),
            },
            format="json",
        )

    def test_asignar_crea_entrenamiento(self):
        res = self._assign()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Entrenamiento.objects.count(), 1)
        entrenamiento = Entrenamiento.objects.get()
        self.assertEqual(entrenamiento.plantilla_origen_id, self.plantilla.id)
        self.assertEqual(entrenamiento.estructura, self.plantilla.estructura)
        self.assertIsNotNone(entrenamiento.plantilla_version_id)

    def test_asignar_es_idempotente(self):
        first = self._assign()
        self.assertEqual(first.status_code, 201)
        second = self._assign()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Entrenamiento.objects.count(), 1)

    def test_asignar_deniega_cross_tenant(self):
        other_coach = User.objects.create_user(username="coach_other", password="x")
        other_alumno = Alumno.objects.create(
            entrenador=other_coach,
            nombre="Beto",
            apellido="Other",
            email="beto_other@test.com",
        )
        res = self._assign(alumno_id=other_alumno.id)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Entrenamiento.objects.count(), 0)

    def test_asignar_fecha_invalida(self):
        res = self.client.post(
            f"/api/plantillas/{self.plantilla.id}/asignar_a_alumno/",
            {"alumno_id": self.alumno.id, "fecha": "15-12-2025"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_asignar_plantilla_inexistente(self):
        res = self.client.post(
            "/api/plantillas/999999/asignar_a_alumno/",
            {"alumno_id": self.alumno.id, "fecha": self.fecha.isoformat()},
            format="json",
        )
        self.assertEqual(res.status_code, 404)
