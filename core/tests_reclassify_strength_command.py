from __future__ import annotations

import io
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from analytics.models import HistorialFitness
from core.models import Actividad, Alumno, Entrenamiento


class ReclassifyStrengthFromOtherCommandTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coach1 = User.objects.create_user(username="coach1", password="x")
        self.coach2 = User.objects.create_user(username="coach2", password="x")

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="A", apellido="One", email="a1@example.com")
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="B", apellido="Two", email="b2@example.com")

        self.start_dt = datetime(2025, 1, 10, 10, 0, tzinfo=dt_timezone.utc)

        # Actividad OTHER pero Strava type=WeightTraining (target)
        self.act1 = Actividad.objects.create(
            usuario=self.coach1,
            alumno=self.alumno1,
            source=Actividad.Source.STRAVA,
            source_object_id="555",
            strava_id=555,
            nombre="Gym",
            distancia=0.0,
            tiempo_movimiento=3600,
            fecha_inicio=self.start_dt,
            tipo_deporte="OTHER",
            desnivel_positivo=0.0,
            datos_brutos={"type": "WeightTraining"},
        )
        self.ent1 = Entrenamiento.objects.create(
            alumno=self.alumno1,
            fecha_asignada=self.start_dt.date(),
            titulo="Gym",
            tipo_actividad="OTHER",
            completado=True,
            strava_id="555",
            tiempo_real_min=60,
            rpe=0,
        )

        # Control cross-tenant: no debe tocarse al correr tenant_id=coach1
        self.act2 = Actividad.objects.create(
            usuario=self.coach2,
            alumno=self.alumno2,
            source=Actividad.Source.STRAVA,
            source_object_id="777",
            strava_id=777,
            nombre="Gym2",
            distancia=0.0,
            tiempo_movimiento=1800,
            fecha_inicio=self.start_dt,
            tipo_deporte="OTHER",
            desnivel_positivo=0.0,
            datos_brutos={"type": "WeightTraining"},
        )
        self.ent2 = Entrenamiento.objects.create(
            alumno=self.alumno2,
            fecha_asignada=self.start_dt.date(),
            titulo="Gym2",
            tipo_actividad="OTHER",
            completado=True,
            strava_id="777",
            tiempo_real_min=30,
            rpe=0,
        )

    def test_dry_run_does_not_modify_data(self):
        before_hf_count = HistorialFitness.objects.filter(alumno=self.alumno1).count()
        out = io.StringIO()
        call_command(
            "reclassify_strength_from_other",
            "--tenant_id",
            str(self.coach1.id),
            "--dry-run",
            stdout=out,
        )

        self.act1.refresh_from_db()
        self.ent1.refresh_from_db()
        self.assertEqual(self.act1.tipo_deporte, "OTHER")
        self.assertEqual(self.ent1.tipo_actividad, "OTHER")
        self.assertEqual(HistorialFitness.objects.filter(alumno=self.alumno1).count(), before_hf_count)

        # Cross-tenant intact
        self.act2.refresh_from_db()
        self.ent2.refresh_from_db()
        self.assertEqual(self.act2.tipo_deporte, "OTHER")
        self.assertEqual(self.ent2.tipo_actividad, "OTHER")

    def test_real_run_reclassifies_and_recomputes_pmc(self):
        out = io.StringIO()
        call_command(
            "reclassify_strength_from_other",
            "--tenant_id",
            str(self.coach1.id),
            stdout=out,
        )

        self.act1.refresh_from_db()
        self.ent1.refresh_from_db()
        self.assertEqual(self.act1.tipo_deporte, "STRENGTH")
        self.assertEqual(self.ent1.tipo_actividad, "STRENGTH")

        # PMC recomputed desde fecha de la actividad: debe existir registro en esa fecha
        hf = HistorialFitness.objects.get(alumno=self.alumno1, fecha=self.start_dt.date())
        # Con defaults del sistema: rpe=0, tss/load_final/training_load no seteados => load = 60 * 1.0 = 60
        self.assertAlmostEqual(float(hf.tss_diario), 60.0, places=4)

        # Cross-tenant intact
        self.act2.refresh_from_db()
        self.ent2.refresh_from_db()
        self.assertEqual(self.act2.tipo_deporte, "OTHER")
        self.assertEqual(self.ent2.tipo_actividad, "OTHER")

