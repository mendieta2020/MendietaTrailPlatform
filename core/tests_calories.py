from django.test import TestCase

from core.calories import compute_calories_kcal
from core.models import Actividad, Alumno


class CaloriesComputationTests(TestCase):
    def setUp(self):
        self.alumno = Alumno.objects.create(nombre="Ana", apellido="Kcal", email="ana@kcal.test", peso=70.0)

    def test_strava_calories_take_priority(self):
        act = Actividad(
            alumno=self.alumno,
            nombre="Run",
            distancia=10000,
            tiempo_movimiento=3600,
            tipo_deporte="RUN",
            calories_kcal=555.0,
        )
        kcal = compute_calories_kcal(act)
        self.assertEqual(kcal, 555.0)

    def test_running_calories_estimated_from_distance(self):
        act = Actividad(
            alumno=self.alumno,
            nombre="Run",
            distancia=10000,
            tiempo_movimiento=3600,
            tipo_deporte="RUN",
            calories_kcal=None,
        )
        kcal = compute_calories_kcal(act)
        self.assertAlmostEqual(kcal, 700.0, places=1)

    def test_bike_calories_estimated_from_duration(self):
        act = Actividad(
            alumno=self.alumno,
            nombre="Ride",
            distancia=20000,
            tiempo_movimiento=3600,
            tipo_deporte="BIKE",
            calories_kcal=None,
        )
        kcal = compute_calories_kcal(act)
        self.assertAlmostEqual(kcal, 476.0, places=1)
