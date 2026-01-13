from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from analytics.models import DailyActivityAgg
from analytics.pmc_engine import build_daily_aggs_for_alumno
from core.models import Actividad, Alumno


User = get_user_model()


class DailyAggCaloriesTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_kcal", password="x")
        self.alumno = Alumno.objects.create(entrenador=self.coach, nombre="Leo", apellido="Kcal", email="leo@kcal.test", peso=70.0)

    def test_daily_agg_never_nulls_calories(self):
        day = timezone.localdate() - timedelta(days=1)
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="agg-kcal-1",
            source_hash="",
            strava_id=321,
            strava_sport_type="Run",
            nombre="Run",
            distancia=5000,
            tiempo_movimiento=1500,
            fecha_inicio=timezone.make_aware(datetime.combine(day, datetime.min.time())),
            tipo_deporte="RUN",
            desnivel_positivo=50,
            calories_kcal=None,
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=day)
        agg = DailyActivityAgg.objects.get(alumno=self.alumno, fecha=day, sport="RUN")
        self.assertIsNotNone(agg.calories_kcal)
        self.assertGreater(agg.calories_kcal, 0)
