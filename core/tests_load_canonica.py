from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.metrics import (
    LOAD_DEFINITION_VERSION,
    calcular_carga_canonica,
    calcular_load_rpe,
    calcular_trimp,
    calcular_tss_power,
)
from core.models import Alumno
from core.tasks import build_canonical_load_fields


User = get_user_model()


class CanonicalLoadTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_load", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Carga",
            email="ana@load.test",
            fcm=190,
            fcreposo=50,
            ftp_ciclismo=250,
        )

    def test_running_with_hr_uses_trimp(self):
        actividad = SimpleNamespace(
            tipo_deporte="RUN",
            tiempo_real_min=60,
            frecuencia_cardiaca_promedio=150,
            alumno=self.alumno,
        )

        expected = calcular_trimp(60, 150, self.alumno.fcm, self.alumno.fcreposo)
        load, method = calcular_carga_canonica(actividad)
        self.assertAlmostEqual(load, expected, places=6)
        self.assertEqual(method, "trimp")

    def test_cycling_with_power_uses_tss_power(self):
        actividad = SimpleNamespace(
            tipo_deporte="BIKE",
            tiempo_real_min=60,
            potencia_promedio=200,
            alumno=self.alumno,
        )

        expected, _ = calcular_tss_power(60, 200, self.alumno.ftp_ciclismo)
        load, method = calcular_carga_canonica(actividad)
        self.assertAlmostEqual(load, expected, places=6)
        self.assertEqual(method, "tss_power")

    def test_rpe_fallback_uses_load_rpe(self):
        actividad = SimpleNamespace(
            tipo_deporte="RUN",
            tiempo_real_min=45,
            rpe=6,
        )

        expected = calcular_load_rpe(45, 6)
        load, method = calcular_carga_canonica(actividad)
        self.assertAlmostEqual(load, expected, places=6)
        self.assertEqual(method, "rpe")

    def test_strava_ingest_fields_use_version(self):
        activity = {
            "moving_time_s": 3600,
            "avg_watts": 200,
        }
        load_fields = build_canonical_load_fields(activity=activity, alumno=self.alumno, sport_type="BIKE")
        expected, _ = calcular_tss_power(60, 200, self.alumno.ftp_ciclismo)
        self.assertAlmostEqual(load_fields["canonical_load"], expected, places=6)
        self.assertEqual(load_fields["canonical_load_method"], "tss_power")
        self.assertEqual(load_fields["load_version"], LOAD_DEFINITION_VERSION)
