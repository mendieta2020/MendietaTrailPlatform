from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import AnalyticsRangeCache
from core.models import Actividad, Alumno


User = get_user_model()


class WeekSummaryElevationTests(TestCase):
    def setUp(self):
        self.password = "pass123"
        self.coach = User.objects.create_user(username="coach_week_elev", password=self.password)
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Lia",
            apellido="Week",
            email="lia_week@test.com",
        )
        self.client = APIClient()

        self.week_start = date(2026, 1, 12)
        self.week = f"{self.week_start.isocalendar()[0]}-W{self.week_start.isocalendar()[1]:02d}"

        start_dt = timezone.make_aware(datetime.combine(self.week_start, datetime.min.time()))
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="week-1",
            source_hash="",
            strava_id=9001,
            strava_sport_type="Run",
            nombre="Week Run 1",
            distancia=10000,
            tiempo_movimiento=3600,
            fecha_inicio=start_dt,
            tipo_deporte="RUN",
            desnivel_positivo=200,
            elev_gain_m=200,
            elev_loss_m=150,
            elev_total_m=350,
            calories_kcal=800,
            validity=Actividad.Validity.VALID,
        )
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="week-2",
            source_hash="",
            strava_id=9002,
            strava_sport_type="Ride",
            nombre="Week Ride",
            distancia=20000,
            tiempo_movimiento=5400,
            fecha_inicio=start_dt + timedelta(days=2),
            tipo_deporte="BIKE",
            desnivel_positivo=300,
            elev_gain_m=300,
            elev_loss_m=280,
            elev_total_m=580,
            calories_kcal=1200,
            validity=Actividad.Validity.VALID,
        )

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

    def test_week_summary_includes_elevation_and_calories(self):
        call_command(
            "recompute_daily_analytics",
            "--alumno-id",
            str(self.alumno.id),
            "--entrenador-id",
            str(self.coach.id),
            "--start-date",
            self.week_start.isoformat(),
        )

        self._login()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sessions_count"], 2)
        self.assertEqual(res.data["distance_km"], 30.0)
        self.assertEqual(res.data["duration_minutes"], 150)
        self.assertEqual(res.data["elevation_gain_m"], 500)
        self.assertEqual(res.data["elevation_loss_m"], 430)
        self.assertEqual(res.data["elevation_total_m"], 930)
        self.assertEqual(res.data["kcal"], 2000)
        self.assertEqual(res.data["total_distance_km"], 30.0)
        self.assertEqual(res.data["total_duration_minutes"], 150)
        self.assertEqual(res.data["total_elevation_gain_m"], 500)
        self.assertEqual(res.data["total_elevation_loss_m"], 430)
        self.assertEqual(res.data["total_elevation_total_m"], 930)
        self.assertEqual(res.data["total_calories_kcal"], 2000)

    def test_week_summary_ignores_stale_cache_when_daily_aggs_updated(self):
        call_command(
            "recompute_daily_analytics",
            "--alumno-id",
            str(self.alumno.id),
            "--entrenador-id",
            str(self.coach.id),
            "--start-date",
            self.week_start.isoformat(),
        )

        AnalyticsRangeCache.objects.create(
            alumno=self.alumno,
            cache_type=AnalyticsRangeCache.CacheType.WEEK_SUMMARY,
            sport="ALL",
            start_date=self.week_start,
            end_date=self.week_start + timedelta(days=6),
            payload={
                "distance_km": 0,
                "duration_minutes": 0,
                "kcal": 0,
                "elevation_gain_m": 0,
                "elevation_loss_m": 0,
                "elevation_total_m": 0,
                "total_distance_km": 0,
                "total_duration_minutes": 0,
                "total_elevation_gain_m": 0,
                "total_elevation_loss_m": 0,
                "total_elevation_total_m": 0,
                "total_calories": 0,
                "total_calories_kcal": 0,
                "sessions_count": 0,
                "sessions_by_type": {},
                "totals_by_type": {},
                "pmc": {},
                "compliance": {},
            },
            last_computed_at=timezone.now() - timedelta(hours=1),
        )

        self._login()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_distance_km"], 30.0)
        self.assertEqual(res.data["total_duration_minutes"], 150)
        self.assertEqual(res.data["total_elevation_gain_m"], 500)
        self.assertEqual(res.data["total_elevation_loss_m"], 430)
        self.assertEqual(res.data["total_elevation_total_m"], 930)
        self.assertEqual(res.data["total_calories_kcal"], 2000)
        self.assertEqual(res.data["sessions_count"], 2)

    def test_week_summary_returns_404_when_no_daily_aggs(self):
        empty_athlete = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Nico",
            apellido="Empty",
            email="nico_empty@test.com",
        )

        self._login()
        res = self.client.get(
            f"/api/coach/athletes/{empty_athlete.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 404)
