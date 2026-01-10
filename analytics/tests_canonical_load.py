from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from analytics.models import DailyActivityAgg
from analytics.pmc_engine import build_daily_aggs_for_alumno
from core.metrics import LOAD_DEFINITION_VERSION
from core.models import Actividad, Alumno


User = get_user_model()


class CanonicalLoadAnalyticsTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_load_agg", password="x")
        self.alumno = Alumno.objects.create(entrenador=self.coach, nombre="Lia", apellido="Agg", email="lia@agg.test")

    def test_daily_agg_prefers_canonical_load(self):
        day = timezone.localdate() - timedelta(days=1)
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="agg-1",
            source_hash="",
            strava_id=123,
            strava_sport_type="Run",
            nombre="Run",
            distancia=10000,
            tiempo_movimiento=3600,
            fecha_inicio=timezone.make_aware(datetime.combine(day, datetime.min.time())),
            tipo_deporte="RUN",
            desnivel_positivo=100,
            datos_brutos={"relative_effort": 120},
            canonical_load=80,
            canonical_load_method="relative_effort",
            load_version=LOAD_DEFINITION_VERSION,
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=day)
        agg = DailyActivityAgg.objects.get(alumno=self.alumno, fecha=day, sport="RUN")
        self.assertEqual(agg.load, 80)
