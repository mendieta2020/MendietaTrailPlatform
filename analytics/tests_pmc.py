from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import DailyActivityAgg, PMCHistory
from analytics.pmc_engine import build_daily_aggs_for_alumno, recompute_pmc_for_alumno
from core.models import Actividad, Alumno


User = get_user_model()


class PMCIncrementalRecomputeTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_pmc", password="x")
        self.alumno = Alumno.objects.create(entrenador=self.coach, nombre="Ana", apellido="PMC", email="ana@pmc.test")

    def test_pmc_incremental_recompute_from_affected_date(self):
        d1 = timezone.localdate() - timedelta(days=2)
        d2 = timezone.localdate() - timedelta(days=1)

        # Día 1: 100 de carga
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="a1",
            source_hash="",
            strava_id=1,
            strava_sport_type="Run",
            nombre="Run",
            distancia=10000,
            tiempo_movimiento=3600,
            fecha_inicio=timezone.make_aware(datetime.combine(d1, datetime.min.time())),
            tipo_deporte="RUN",
            desnivel_positivo=100,
            datos_brutos={"relative_effort": 100},
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=d1)
        recompute_pmc_for_alumno(alumno_id=self.alumno.id, start_date=d1)

        p1 = PMCHistory.objects.get(alumno=self.alumno, fecha=d1, sport="ALL")
        expected_ctl1 = 100.0 / 42.0
        expected_atl1 = 100.0 / 7.0
        self.assertAlmostEqual(p1.ctl, expected_ctl1, places=6)
        self.assertAlmostEqual(p1.atl, expected_atl1, places=6)
        self.assertAlmostEqual(p1.tsb, expected_ctl1 - expected_atl1, places=6)

        # Día 2 inicialmente sin carga => decae desde día 1
        p2 = PMCHistory.objects.get(alumno=self.alumno, fecha=d2, sport="ALL")
        expected_ctl2 = expected_ctl1 + (0.0 - expected_ctl1) / 42.0
        expected_atl2 = expected_atl1 + (0.0 - expected_atl1) / 7.0
        self.assertAlmostEqual(p2.ctl, expected_ctl2, places=6)
        self.assertAlmostEqual(p2.atl, expected_atl2, places=6)

        # Agregamos actividad en día 2 (70 carga). Recompute desde día 2.
        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="a2",
            source_hash="",
            strava_id=2,
            strava_sport_type="Ride",
            nombre="Ride",
            distancia=20000,
            tiempo_movimiento=1800,
            fecha_inicio=timezone.make_aware(datetime.combine(d2, datetime.min.time())),
            tipo_deporte="BIKE",
            desnivel_positivo=200,
            datos_brutos={"relative_effort": 70},
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=d2)
        recompute_pmc_for_alumno(alumno_id=self.alumno.id, start_date=d2)

        # Día 1 no debe cambiar.
        p1b = PMCHistory.objects.get(alumno=self.alumno, fecha=d1, sport="ALL")
        self.assertAlmostEqual(p1b.ctl, expected_ctl1, places=6)
        self.assertAlmostEqual(p1b.atl, expected_atl1, places=6)

        # Día 2 ahora usa seed de día 1 y tss=70.
        p2b = PMCHistory.objects.get(alumno=self.alumno, fecha=d2, sport="ALL")
        expected_ctl2b = expected_ctl1 + (70.0 - expected_ctl1) / 42.0
        expected_atl2b = expected_atl1 + (70.0 - expected_atl1) / 7.0
        self.assertAlmostEqual(p2b.ctl, expected_ctl2b, places=6)
        self.assertAlmostEqual(p2b.atl, expected_atl2b, places=6)


class PMCContractEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach = User.objects.create_user(username="coach_pmc_contract", password="x")
        self.other_coach = User.objects.create_user(username="coach_pmc_other", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="PMC",
            email="ana_pmc_contract@test.com",
        )
        self.other_alumno = Alumno.objects.create(
            entrenador=self.other_coach,
            nombre="Beto",
            apellido="PMC",
            email="beto_pmc_contract@test.com",
        )
        self.client.force_authenticate(user=self.coach)
        self.start = date(2026, 1, 1)
        self.end = date(2026, 1, 3)

        for offset, (tss, ctl, atl, tsb) in enumerate(
            [
                (50, 10.123, 12.987, -2.5),
                (40, 11.5, 13.2, -1.7),
                (20, 12.0, 12.0, 0.0),
            ]
        ):
            d = self.start + timedelta(days=offset)
            PMCHistory.objects.create(
                alumno=self.alumno,
                fecha=d,
                sport="ALL",
                tss_diario=tss,
                ctl=ctl,
                atl=atl,
                tsb=tsb,
            )
            DailyActivityAgg.objects.create(
                alumno=self.alumno,
                fecha=d,
                sport=DailyActivityAgg.Sport.RUN,
                load=tss,
                distance_m=10000 + (offset * 1000),
                elev_gain_m=150 + (offset * 10),
                elev_loss_m=120 + (offset * 5),
                elev_total_m=270 + (offset * 15),
                duration_s=3600 + (offset * 300),
                calories_kcal=500 + (offset * 50),
            )

        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="effort-1",
            source_hash="",
            strava_id=101,
            strava_sport_type="Run",
            nombre="Run effort",
            distancia=10000,
            tiempo_movimiento=3600,
            fecha_inicio=timezone.make_aware(datetime.combine(self.start, datetime.min.time())),
            tipo_deporte="RUN",
            desnivel_positivo=120,
            effort=45.5,
            validity=Actividad.Validity.VALID,
        )

        PMCHistory.objects.create(
            alumno=self.other_alumno,
            fecha=self.start,
            sport="ALL",
            tss_diario=80,
            ctl=20.0,
            atl=25.0,
            tsb=-5.0,
        )

    def _get_pmc(self, alumno_id: int):
        return self.client.get(
            f"/api/analytics/pmc/?alumno_id={alumno_id}&start_date={self.start}&end_date={self.end}"
        )

    def test_pmc_contract_shape_types_and_order(self):
        res = self._get_pmc(self.alumno.id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 3)

        expected_keys = {
            "fecha",
            "is_future",
            "ctl",
            "atl",
            "tsb",
            "dist",
            "load",
            "time",
            "elev_gain",
            "elev_loss",
            "calories",
            "effort",
            "race",
        }
        fechas = []
        for item in res.data:
            self.assertEqual(set(item.keys()), expected_keys)
            fechas.append(item["fecha"])
            datetime.strptime(item["fecha"], "%Y-%m-%d")

            self.assertIsInstance(item["is_future"], bool)
            self.assertIsInstance(item["ctl"], float)
            self.assertIsInstance(item["atl"], float)
            self.assertIsInstance(item["tsb"], float)
            self.assertIsInstance(item["dist"], float)
            self.assertIsInstance(item["load"], int)
            self.assertIsInstance(item["time"], int)
            self.assertIsInstance(item["elev_gain"], int)
            self.assertTrue(item["elev_loss"] is None or isinstance(item["elev_loss"], int))
            self.assertTrue(item["calories"] is None or isinstance(item["calories"], int))
            self.assertTrue(item["effort"] is None or isinstance(item["effort"], float))
            self.assertTrue(item["race"] is None or isinstance(item["race"], dict))

            for forbidden in {"raw_payload", "datos_brutos", "headers", "token", "access", "refresh"}:
                self.assertNotIn(forbidden, item)

        self.assertEqual(fechas, sorted(fechas))

    def test_pmc_tenant_isolation_returns_only_own_rows(self):
        res = self._get_pmc(self.alumno.id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual({row["fecha"] for row in res.data}, {"2026-01-01", "2026-01-02", "2026-01-03"})

        other_client = APIClient()
        other_client.force_authenticate(user=self.other_coach)
        other_res = other_client.get(
            f"/api/analytics/pmc/?alumno_id={self.other_alumno.id}&start_date={self.start}&end_date={self.end}"
        )
        self.assertEqual(other_res.status_code, 200)
        self.assertEqual(len(other_res.data), 1)
        self.assertEqual(other_res.data[0]["fecha"], "2026-01-01")

    def test_pmc_snapshot_regression(self):
        res = self._get_pmc(self.alumno.id)
        self.assertEqual(res.status_code, 200)
        expected = [
            {
                "fecha": "2026-01-01",
                "is_future": False,
                "ctl": 10.1,
                "atl": 13.0,
                "tsb": -2.5,
                "load": 50,
                "dist": 10.0,
                "time": 60,
                "elev_gain": 150,
                "elev_loss": 120,
                "calories": 500,
                "effort": 45.5,
                "race": None,
            },
            {
                "fecha": "2026-01-02",
                "is_future": False,
                "ctl": 11.5,
                "atl": 13.2,
                "tsb": -1.7,
                "load": 40,
                "dist": 11.0,
                "time": 65,
                "elev_gain": 160,
                "elev_loss": 125,
                "calories": 550,
                "effort": None,
                "race": None,
            },
            {
                "fecha": "2026-01-03",
                "is_future": False,
                "ctl": 12.0,
                "atl": 12.0,
                "tsb": 0.0,
                "load": 20,
                "dist": 12.0,
                "time": 70,
                "elev_gain": 170,
                "elev_loss": 130,
                "calories": 600,
                "effort": None,
                "race": None,
            },
        ]
        self.assertEqual(res.data, expected)
