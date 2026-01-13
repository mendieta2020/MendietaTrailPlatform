from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import DailyActivityAgg
from core.models import Actividad, Alumno


User = get_user_model()


class WeekSummaryPerSportTotalsTests(TestCase):
    def setUp(self):
        self.password = "pass123"
        self.coach = User.objects.create_user(username="coach_week_sport", password=self.password)
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Vale",
            apellido="Week",
            email="vale_week@test.com",
        )
        self.client = APIClient()

        self.week_start = date(2026, 1, 12)
        self.week = f"{self.week_start.isocalendar()[0]}-W{self.week_start.isocalendar()[1]:02d}"

    def _login(self):
        response = self.client.post(
            "/api/token/",
            {"username": self.coach.username, "password": self.password},
            format="json",
        )
        access_cookie = response.cookies.get(settings.COOKIE_AUTH_ACCESS_NAME)
        if access_cookie:
            self.client.cookies[settings.COOKIE_AUTH_ACCESS_NAME] = access_cookie.value
        else:
            access = response.data.get("access")
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _create_activity(self, *, start_dt, sport, distancia, tiempo_movimiento, elev_gain, elev_loss, calories):
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id=f"week-{sport}-{start_dt.date()}",
            source_hash="",
            strava_id=int(start_dt.timestamp()),
            strava_sport_type=sport.title(),
            nombre=f"Week {sport}",
            distancia=distancia,
            tiempo_movimiento=tiempo_movimiento,
            fecha_inicio=start_dt,
            tipo_deporte=sport,
            desnivel_positivo=elev_gain,
            elev_gain_m=elev_gain,
            elev_loss_m=elev_loss,
            elev_total_m=elev_gain + elev_loss,
            calories_kcal=calories,
            validity=Actividad.Validity.VALID,
        )

    def test_week_summary_per_sport_totals(self):
        start_dt = timezone.make_aware(datetime.combine(self.week_start, datetime.min.time()))
        self._create_activity(
            start_dt=start_dt,
            sport="RUN",
            distancia=10000,
            tiempo_movimiento=3600,
            elev_gain=200,
            elev_loss=150,
            calories=800,
        )
        self._create_activity(
            start_dt=start_dt + timedelta(days=2),
            sport="RUN",
            distancia=5000,
            tiempo_movimiento=1800,
            elev_gain=100,
            elev_loss=80,
            calories=400,
        )
        self._create_activity(
            start_dt=start_dt + timedelta(days=3),
            sport="STRENGTH",
            distancia=0,
            tiempo_movimiento=2700,
            elev_gain=0,
            elev_loss=0,
            calories=500,
        )

        DailyActivityAgg.objects.create(
            alumno=self.alumno,
            fecha=self.week_start,
            sport="RUN",
            load=120.0,
            distance_m=10000,
            elev_gain_m=200,
            elev_loss_m=150,
            elev_total_m=350,
            duration_s=3600,
            calories_kcal=800,
        )
        DailyActivityAgg.objects.create(
            alumno=self.alumno,
            fecha=self.week_start + timedelta(days=2),
            sport="RUN",
            load=60.0,
            distance_m=5000,
            elev_gain_m=100,
            elev_loss_m=80,
            elev_total_m=180,
            duration_s=1800,
            calories_kcal=400,
        )
        DailyActivityAgg.objects.create(
            alumno=self.alumno,
            fecha=self.week_start + timedelta(days=3),
            sport="STRENGTH",
            load=90.0,
            distance_m=0,
            elev_gain_m=0,
            elev_loss_m=0,
            elev_total_m=0,
            duration_s=2700,
            calories_kcal=500,
        )

        self._login()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_distance_km"], 15.0)
        self.assertEqual(res.data["total_duration_minutes"], 135)
        self.assertEqual(res.data["total_calories_kcal"], 1700)
        self.assertEqual(res.data["total_elevation_gain_m"], 300)
        self.assertEqual(res.data["total_elevation_loss_m"], 230)
        self.assertEqual(res.data["total_elevation_total_m"], 530)

        per_sport = res.data["per_sport_totals"]
        self.assertEqual(per_sport["RUN"]["distance_km"], 15.0)
        self.assertEqual(per_sport["RUN"]["duration_minutes"], 90)
        self.assertEqual(per_sport["RUN"]["calories_kcal"], 1200)
        self.assertEqual(per_sport["RUN"]["load"], 180.0)

        self.assertEqual(per_sport["STRENGTH"]["duration_minutes"], 45)
        self.assertEqual(per_sport["STRENGTH"]["calories_kcal"], 500)
        self.assertEqual(per_sport["STRENGTH"]["load"], 90.0)
        self.assertNotIn("distance_km", per_sport["STRENGTH"])
        self.assertNotIn("elevation_gain_m", per_sport["STRENGTH"])
        self.assertNotIn("elevation_loss_m", per_sport["STRENGTH"])
        self.assertNotIn("elevation_total_m", per_sport["STRENGTH"])

    def test_week_summary_without_daily_aggs_has_no_per_sport_totals(self):
        empty_athlete = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Lia",
            apellido="NoData",
            email="lia_nodata@test.com",
        )

        self._login()
        res = self.client.get(
            f"/api/coach/athletes/{empty_athlete.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 404)
        self.assertNotIn("per_sport_totals", res.data)
