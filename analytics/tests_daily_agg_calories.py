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

    def test_daily_agg_sums_elevation_metrics(self):
        day = timezone.localdate() - timedelta(days=2)
        start_dt = timezone.make_aware(datetime.combine(day, datetime.min.time()))
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="agg-elev-1",
            source_hash="",
            strava_id=501,
            strava_sport_type="Run",
            nombre="Run 1",
            distancia=8000,
            tiempo_movimiento=2400,
            fecha_inicio=start_dt,
            tipo_deporte="RUN",
            desnivel_positivo=120,
            elev_gain_m=120,
            elev_loss_m=80,
            elev_total_m=200,
            calories_kcal=600,
            validity=Actividad.Validity.VALID,
        )
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="agg-elev-2",
            source_hash="",
            strava_id=502,
            strava_sport_type="Run",
            nombre="Run 2",
            distancia=4000,
            tiempo_movimiento=1200,
            fecha_inicio=start_dt + timedelta(hours=2),
            tipo_deporte="RUN",
            desnivel_positivo=60,
            elev_gain_m=60,
            elev_loss_m=40,
            elev_total_m=100,
            calories_kcal=300,
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=day)
        agg = DailyActivityAgg.objects.get(alumno=self.alumno, fecha=day, sport="RUN")
        self.assertAlmostEqual(agg.distance_m, 12000.0, places=1)
        self.assertEqual(agg.duration_s, 3600)
        self.assertAlmostEqual(agg.elev_gain_m, 180.0, places=1)
        self.assertAlmostEqual(agg.elev_loss_m, 120.0, places=1)
        self.assertAlmostEqual(agg.elev_total_m, 300.0, places=1)
        self.assertAlmostEqual(agg.calories_kcal, 900.0, places=1)
