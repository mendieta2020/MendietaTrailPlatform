from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Alumno, Entrenamiento, PlantillaEntrenamiento, BloqueEntrenamiento, PasoEntrenamiento
from core.services import asignar_plantilla_a_alumno
from datetime import date

User = get_user_model()

class PR1LegacyCheckTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_pr1", password="x")
        self.alumno = Alumno.objects.create(entrenador=self.coach, nombre="L", apellido="Check", email="l@check.com")
        self.plantilla = PlantillaEntrenamiento.objects.create(
            entrenador=self.coach,
            titulo="Legacy Check Workout",
            deporte="RUN",
            estructura={
                "blocks": [
                    {
                        "type": "WARMUP", 
                        "steps": [{"duration_type": "TIME", "duration_value": 600}]
                    }
                ]
            }
        )
        self.fecha = date(2026, 1, 1)

    def test_assignment_does_not_create_legacy_rows(self):
        # Initial count
        bloques_before = BloqueEntrenamiento.objects.count()
        pasos_before = PasoEntrenamiento.objects.count()
        
        # Action
        entrenamiento, created = asignar_plantilla_a_alumno(self.plantilla, self.alumno, self.fecha)
        
        # Assertions
        self.assertTrue(created)
        self.assertEqual(entrenamiento.estructura_schema_version, "1.0")
        self.assertEqual(entrenamiento.tiempo_planificado_min, 10) # 600s = 10m
        
        # Verify NO new legacy rows
        self.assertEqual(BloqueEntrenamiento.objects.count(), bloques_before)
        self.assertEqual(PasoEntrenamiento.objects.count(), pasos_before)
