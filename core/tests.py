from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.models import HistorialFitness, InjuryRiskSnapshot
from core.models import Alumno


User = get_user_model()


class InjuryRiskAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coach1 = User.objects.create_user(username="coach1", password="x")
        self.coach2 = User.objects.create_user(username="coach2", password="x")

        self.alumno1 = Alumno.objects.create(entrenador=self.coach1, nombre="Ana", apellido="Test", email="ana@test.com")
        self.alumno2 = Alumno.objects.create(entrenador=self.coach2, nombre="Beto", apellido="Other", email="beto@test.com")

        self.today = timezone.localdate()

        # PMC mínimo para alumno1 (hoy y 7d)
        HistorialFitness.objects.create(alumno=self.alumno1, fecha=self.today - timedelta(days=7), tss_diario=50, ctl=40, atl=40, tsb=0)
        HistorialFitness.objects.create(alumno=self.alumno1, fecha=self.today, tss_diario=120, ctl=50, atl=80, tsb=-30)

        # Snapshot existente para el list include
        InjuryRiskSnapshot.objects.create(
            entrenador=self.coach1,
            alumno=self.alumno1,
            fecha=self.today,
            risk_level="MEDIUM",
            risk_score=60,
            risk_reasons=["seed"],
            ctl=50,
            atl=80,
            tsb=-30,
        )

    def test_multi_tenant_denies_cross_athlete(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno2.id}/injury-risk/")
        # get_object() usa queryset scopiado -> 404
        self.assertEqual(res.status_code, 404)

    def test_injury_risk_endpoint_returns_latest(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno1.id}/injury-risk/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data_available", res.data)
        self.assertTrue(res.data["data_available"])
        self.assertIn("risk_level", res.data)

    def test_injury_risk_endpoint_date_param(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get(f"/api/alumnos/{self.alumno1.id}/injury-risk/?date={self.today.isoformat()}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["data_available"])
        self.assertEqual(res.data["fecha"], self.today.isoformat())

    def test_include_injury_risk_in_list_no_n_plus_one_contract(self):
        self.client.force_authenticate(user=self.coach1)
        res = self.client.get("/api/alumnos/?include_injury_risk=1")
        self.assertEqual(res.status_code, 200)
        # alumno1 debería traer injury_risk embebido
        item = next(x for x in res.data if x["id"] == self.alumno1.id)
        self.assertIsNotNone(item.get("injury_risk"))
        self.assertEqual(item["injury_risk"]["risk_level"], "MEDIUM")

