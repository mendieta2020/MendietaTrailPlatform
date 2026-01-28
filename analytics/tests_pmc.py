from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from analytics.models import PMCHistory
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
        

    def test_pmc_invariants_tsb_sign_and_reactivity(self):
        """
        Invariantes científicos:
        - ATL (7d) reacciona más rápido que CTL (42d)
        - TSB = CTL - ATL
        - Tras un escalón de carga, ATL > CTL => TSB negativo
        """
        base = timezone.localdate() - timedelta(days=10)
        days = [base + timedelta(days=i) for i in range(10)]

        # 5 días sin carga, 5 días con carga alta constante
        for i, d in enumerate(days):
            load = 0 if i < 5 else 100
            if load > 0:
                Actividad.objects.create(
                    usuario=self.coach,
                    alumno=self.alumno,
                    source="strava",
                    source_object_id=f"inv{i}",
                    source_hash="",
                    strava_id=1000 + i,
                    strava_sport_type="Run",
                    nombre="Run",
                    distancia=10000,
                    tiempo_movimiento=3600,
                    fecha_inicio=timezone.make_aware(datetime.combine(d, datetime.min.time())),
                    tipo_deporte="RUN",
                    desnivel_positivo=100,
                    datos_brutos={"relative_effort": load},
                    validity=Actividad.Validity.VALID,
                )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=days[0])
        recompute_pmc_for_alumno(alumno_id=self.alumno.id, start_date=days[0])

        # Tomamos el primer día del "escalón"
        step_day = days[5]
        row = PMCHistory.objects.get(alumno=self.alumno, fecha=step_day, sport="ALL")

        # Identidad dura
        self.assertAlmostEqual(row.tsb, row.ctl - row.atl, places=6)

        # Reactividad: tras el escalón, ATL debería ir arriba de CTL
        self.assertGreater(row.atl, row.ctl)

        # Signo esperado: si ATL > CTL => TSB negativo
        self.assertLess(row.tsb, 0.0)

    def test_pmc_per_sport_consistency_all_equals_sum(self):
        """
        Consistencia por deporte:
        - Día con BIKE: RUN tss=0, BIKE tss>0, ALL tss==BIKE tss
        - Evita contaminación entre deportes / normalize mal.
        """
        d = timezone.localdate() - timedelta(days=2)

        Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            source="strava",
            source_object_id="bike_only",
            source_hash="",
            strava_id=2001,
            strava_sport_type="Ride",
            nombre="Ride",
            distancia=20000,
            tiempo_movimiento=1800,
            fecha_inicio=timezone.make_aware(datetime.combine(d, datetime.min.time())),
            tipo_deporte="BIKE",
            desnivel_positivo=200,
            datos_brutos={"relative_effort": 70},
            validity=Actividad.Validity.VALID,
        )

        build_daily_aggs_for_alumno(alumno_id=self.alumno.id, start_date=d)
        recompute_pmc_for_alumno(alumno_id=self.alumno.id, start_date=d)

        all_row = PMCHistory.objects.get(alumno=self.alumno, fecha=d, sport="ALL")
        run_row = PMCHistory.objects.get(alumno=self.alumno, fecha=d, sport="RUN")
        bike_row = PMCHistory.objects.get(alumno=self.alumno, fecha=d, sport="BIKE")

        self.assertEqual(run_row.tss_diario, 0.0)
        self.assertGreater(bike_row.tss_diario, 0.0)
        self.assertAlmostEqual(all_row.tss_diario, bike_row.tss_diario, places=6)

        

