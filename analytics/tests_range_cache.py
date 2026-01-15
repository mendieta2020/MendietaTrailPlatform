from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import AnalyticsRangeCache, DailyActivityAgg, PMCHistory
from core.models import Actividad, Alumno

User = get_user_model()


class PMCRangeCacheTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_range", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Range",
            email="ana_range@test.com",
        )
        self.other_coach = User.objects.create_user(username="coach_range_other", password="x")
        self.other_alumno = Alumno.objects.create(
            entrenador=self.other_coach,
            nombre="Otto",
            apellido="Other",
            email="otto_other@test.com",
        )
        self.client.force_authenticate(user=self.coach)
        self.today = timezone.localdate()

        PMCHistory.objects.create(
            alumno=self.alumno,
            fecha=self.today - timedelta(days=1),
            sport="ALL",
            tss_diario=50,
            ctl=10,
            atl=12,
            tsb=-2,
        )
        PMCHistory.objects.create(
            alumno=self.alumno,
            fecha=self.today,
            sport="ALL",
            tss_diario=60,
            ctl=11,
            atl=13,
            tsb=-2,
        )

    def test_pmc_range_default(self):
        res = self.client.get(f"/api/analytics/pmc/?alumno_id={self.alumno.id}")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.data), 1)

    def test_pmc_range_custom(self):
        start = (self.today - timedelta(days=1)).isoformat()
        end = (self.today - timedelta(days=1)).isoformat()
        res = self.client.get(
            f"/api/analytics/pmc/?alumno_id={self.alumno.id}&start_date={start}&end_date={end}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["fecha"], start)

    def test_pmc_range_too_large(self):
        start = (self.today - timedelta(days=400)).isoformat()
        end = self.today.isoformat()
        res = self.client.get(
            f"/api/analytics/pmc/?alumno_id={self.alumno.id}&start_date={start}&end_date={end}"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("detail", res.data)

    def test_pmc_cache_hit_and_stale_refresh(self):
        start = self.today.isoformat()
        end = self.today.isoformat()
        res1 = self.client.get(
            f"/api/analytics/pmc/?alumno_id={self.alumno.id}&start_date={start}&end_date={end}"
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.data[0]["ctl"], 11.0)

        PMCHistory.objects.filter(alumno=self.alumno, fecha=self.today).update(ctl=99)

        res2 = self.client.get(
            f"/api/analytics/pmc/?alumno_id={self.alumno.id}&start_date={start}&end_date={end}"
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.data[0]["ctl"], 11.0)

        cache = AnalyticsRangeCache.objects.get(
            alumno=self.alumno,
            cache_type=AnalyticsRangeCache.CacheType.PMC,
            sport="ALL",
            start_date=self.today,
            end_date=self.today,
        )
        cache.last_computed_at = timezone.now() - timedelta(hours=10)
        cache.save(update_fields=["last_computed_at"])

        res3 = self.client.get(
            f"/api/analytics/pmc/?alumno_id={self.alumno.id}&start_date={start}&end_date={end}"
        )
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.data[0]["ctl"], 99.0)

    def test_pmc_athlete_id_valid_returns_200(self):
        res = self.client.get(f"/api/analytics/pmc/?athlete_id={self.alumno.id}")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.data), 1)

    def test_pmc_athlete_id_cross_tenant_returns_404(self):
        res = self.client.get(f"/api/analytics/pmc/?athlete_id={self.other_alumno.id}")
        self.assertEqual(res.status_code, 404)

    def test_pmc_mismatched_ids_return_404(self):
        res = self.client.get(
            f"/api/analytics/pmc/?athlete_id={self.alumno.id}&alumno_id={self.other_alumno.id}"
        )
        self.assertEqual(res.status_code, 404)


@override_settings(
    USE_COOKIE_AUTH=True,
    COOKIE_AUTH_ACCESS_NAME="mt_access",
    COOKIE_AUTH_REFRESH_NAME="mt_refresh",
    COOKIE_AUTH_SECURE=False,
    COOKIE_AUTH_SAMESITE="Lax",
    COOKIE_AUTH_DOMAIN=None,
)
class WeeklySummaryEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "pass-123"
        self.coach = User.objects.create_user(username="coach_week", password=self.password)
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Beto",
            apellido="Week",
            email="beto_week@test.com",
        )

        today = date.today()
        year, week, _ = today.isocalendar()
        self.week = f"{year}-{week:02d}"
        monday = date.fromisocalendar(year, week, 1)
        self.monday = monday
        start_dt = timezone.make_aware(datetime.combine(monday, datetime.min.time()))

        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            nombre="Run",
            distancia=5000,
            tiempo_movimiento=1800,
            fecha_inicio=start_dt,
            tipo_deporte="RUN",
            elev_gain_m=140,
            elev_loss_m=120,
            elev_total_m=260,
            calories_kcal=450,
            source=Actividad.Source.STRAVA,
        )
        DailyActivityAgg.objects.create(
            alumno=self.alumno,
            fecha=self.monday,
            sport=DailyActivityAgg.Sport.RUN,
            load=45,
            distance_m=5000,
            elev_gain_m=140,
            elev_loss_m=120,
            elev_total_m=260,
            duration_s=1800,
            calories_kcal=450,
        )

    def _login_with_cookie(self):
        response = self.client.post(
            "/api/token/",
            {"username": self.coach.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        access_cookie = response.cookies.get(settings.COOKIE_AUTH_ACCESS_NAME)
        self.assertIsNotNone(access_cookie)
        self.client.cookies[settings.COOKIE_AUTH_ACCESS_NAME] = access_cookie.value

    def _login_with_jwt(self, client=None):
        api_client = client or self.client
        response = api_client.post(
            "/api/token/",
            {"username": self.coach.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        access = response.data.get("access")
        self.assertIsNotNone(access)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_week_summary_requires_auth(self):
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 401)

    def test_week_summary_returns_payload(self):
        self._login_with_cookie()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("distance_km", res.data)
        self.assertIn("duration_minutes", res.data)
        self.assertIn("kcal", res.data)
        self.assertIn("elevation_gain_m", res.data)
        self.assertIn("elevation_loss_m", res.data)
        self.assertIn("elevation_total_m", res.data)
        self.assertIn("total_distance_km", res.data)
        self.assertIn("sessions_by_type", res.data)
        self.assertIn("totals_by_type", res.data)
        self.assertIn("pmc", res.data)
        self.assertEqual(res.data["sessions_by_type"].get("RUN"), 1)
        self.assertGreater(res.data["total_duration_minutes"], 0)

    def test_week_summary_custom_range_returns_payload(self):
        self._login_with_cookie()
        start = self.monday.isoformat()
        end = (self.monday + timedelta(days=6)).isoformat()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?start_date={start}&end_date={end}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("total_distance_km", res.data)
        self.assertIn("sessions_by_type", res.data)
        self.assertIn("pmc", res.data)
        self.assertEqual(res.data["distance_km"], res.data["total_distance_km"])

    def test_week_summary_custom_range_too_large(self):
        self._login_with_cookie()
        end = self.monday.isoformat()
        start = (self.monday - timedelta(days=settings.ANALYTICS_MAX_RANGE_DAYS)).isoformat()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?start_date={start}&end_date={end}"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("detail", res.data)

    def test_week_summary_no_activity_returns_zeroes(self):
        empty_athlete = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Lia",
            apellido="Empty",
            email="lia_empty@test.com",
        )
        self._login_with_cookie()
        res = self.client.get(
            f"/api/coach/athletes/{empty_athlete.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sessions_count"], 0)
        self.assertEqual(res.data["total_distance_km"], 0)
        self.assertEqual(res.data["sessions_by_type"], {})
        self.assertEqual(res.data["totals_by_type"], {})

    def test_week_summary_other_coach_returns_404(self):
        other_coach = User.objects.create_user(username="coach_other", password="pass")
        other_client = APIClient()
        response = other_client.post(
            "/api/token/",
            {"username": other_coach.username, "password": "pass"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        access_cookie = response.cookies.get(settings.COOKIE_AUTH_ACCESS_NAME)
        other_client.cookies[settings.COOKIE_AUTH_ACCESS_NAME] = access_cookie.value

        res = other_client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 404)

    def test_week_summary_jwt_allows_access(self):
        self._login_with_jwt()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("distance_km", res.data)

    def test_week_summary_jwt_custom_range_allows_access(self):
        self._login_with_jwt()
        start = self.monday.isoformat()
        end = (self.monday + timedelta(days=6)).isoformat()
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?start_date={start}&end_date={end}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("distance_km", res.data)
