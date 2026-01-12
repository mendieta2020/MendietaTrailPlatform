from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import AnalyticsRangeCache, PMCHistory
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


class WeeklySummaryEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_week", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Beto",
            apellido="Week",
            email="beto_week@test.com",
        )
        self.client.force_authenticate(user=self.coach)

        today = date.today()
        year, week, _ = today.isocalendar()
        self.week = f"{year}-{week:02d}"
        monday = date.fromisocalendar(year, week, 1)
        start_dt = timezone.make_aware(datetime.combine(monday, datetime.min.time()))

        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            nombre="Run",
            distancia=5000,
            tiempo_movimiento=1800,
            fecha_inicio=start_dt,
            tipo_deporte="RUN",
            source=Actividad.Source.STRAVA,
        )

    def test_week_summary_returns_payload(self):
        res = self.client.get(
            f"/api/coach/athletes/{self.alumno.id}/week-summary/?week={self.week}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("kpis", res.data)
        self.assertIn("sessions_by_type", res.data)
        self.assertIn("pmc", res.data)
