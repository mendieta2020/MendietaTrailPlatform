from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from core.models import Alumno, Entrenamiento, PlantillaEntrenamiento, Equipo

User = get_user_model()

class RBAC_PR2_Tests(APITestCase):
    def setUp(self):
        # 1. Staff
        self.staff_user = User.objects.create_user(username="staff", password="p", is_staff=True)
        
        # 2. Coach A
        self.coach_a = User.objects.create_user(username="coach_a", password="p")
        self.athlete_a = Alumno.objects.create(entrenador=self.coach_a, nombre="Ath A", usuario=User.objects.create_user(username="ath_a", password="p"))
        
        # 3. Coach B
        self.coach_b = User.objects.create_user(username="coach_b", password="p")
        self.athlete_b = Alumno.objects.create(entrenador=self.coach_b, nombre="Ath B", usuario=User.objects.create_user(username="ath_b", password="p"))
        
        # 4. Athlete Separate User (Simulating login)
        self.athlete_user_a = self.athlete_a.usuario
        self.athlete_user_b = self.athlete_b.usuario

        # Data
        self.template_a = PlantillaEntrenamiento.objects.create(entrenador=self.coach_a, titulo="Tpl A", deporte="RUN", estructura={"blocks": []})
        self.workout_a = Entrenamiento.objects.create(
            alumno=self.athlete_a, 
            fecha_asignada="2026-01-01", 
            titulo="Wkt A", 
            # entrenador implied via alumno
            estructura={"blocks": []},
            estructura_schema_version="1.0"
        )
        
    # --- TEMPLATES RESTRICTIONS ---
    
    def test_athlete_cannot_access_templates(self):
        self.client.force_authenticate(user=self.athlete_user_a)
        res = self.client.get("/api/plantillas/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
        res = self.client.get(f"/api/plantillas/{self.template_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_coach_can_crud_own_templates(self):
        self.client.force_authenticate(user=self.coach_a)
        
        # List
        res = self.client.get("/api/plantillas/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)
        
        # Create
        res = self.client.post("/api/plantillas/", {
            "titulo": "New Tpl", "deporte": "RUN", "descripcion_global": "Desc", "estructura": {}
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        
    def test_coach_cannot_access_other_coach_templates(self):
        self.client.force_authenticate(user=self.coach_b)
        res = self.client.get("/api/plantillas/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 0) # Filtered out
        
        res = self.client.get(f"/api/plantillas/{self.template_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND) # Fail closed
        
    # --- PLANNED WORKOUTS RESTRICTIONS ---
    
    def test_coach_can_crud_own_athlete_workouts(self):
        self.client.force_authenticate(user=self.coach_a)
        
        # List
        res = self.client.get("/api/entrenamientos/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in res.data['results']]
        self.assertIn(self.workout_a.id, ids)
        
        # Create (Standard)
        res = self.client.post("/api/entrenamientos/", {
            "alumno": self.athlete_a.id,
            "titulo": "New Workout",
            "fecha_asignada": "2026-02-01",
            "tipo_actividad": "RUN",
            "estructura": {"blocks": []}
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        
    def test_coach_cannot_create_workout_for_other_athlete(self):
        self.client.force_authenticate(user=self.coach_a)
        res = self.client.post("/api/entrenamientos/", {
            "alumno": self.athlete_b.id, # Belongs to Coach B
            "titulo": "Malicious Workout",
            "fecha_asignada": "2026-02-01",
            "estructura": {}
        }, format='json')
        # Should be 403 or 400 validation error depending on implementation
        # Ideally 403 or Validation Error "Invalid athlete"
        self.assertTrue(res.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_athlete_can_read_own_workouts(self):
        self.client.force_authenticate(user=self.athlete_user_a)
        res = self.client.get("/api/entrenamientos/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)
        
    def test_athlete_cannot_create_workouts(self):
        self.client.force_authenticate(user=self.athlete_user_a)
        res = self.client.post("/api/entrenamientos/", {
            "alumno": self.athlete_a.id,
            "titulo": "Self Assigned",
            "fecha_asignada": "2026-03-01"
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_athlete_cannot_access_other_athlete_workouts(self):
        # Create workout for B
        workout_b = Entrenamiento.objects.create(alumno=self.athlete_b, fecha_asignada="2026-01-01", titulo="Wkt B")
        
        self.client.force_authenticate(user=self.athlete_user_a)
        res = self.client.get(f"/api/entrenamientos/{workout_b.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND) # Fail closed

    def test_athlete_can_patch_status_notes(self):
        self.client.force_authenticate(user=self.athlete_user_a)
        res = self.client.patch(f"/api/entrenamientos/{self.workout_a.id}/", {
            "feedback_alumno": "Hard!",
            "rpe": 8,
            "completado": True
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.workout_a.refresh_from_db()
        self.assertEqual(self.workout_a.rpe, 8)
        self.assertTrue(self.workout_a.completado)

    def test_athlete_cannot_patch_structure(self):
        self.client.force_authenticate(user=self.athlete_user_a)
        original_struct = self.workout_a.estructura
        res = self.client.patch(f"/api/entrenamientos/{self.workout_a.id}/", {
            "estructura": {"blocks": [{"type": "HACKED"}]}
        }, format='json')
        
        # Depending on strictness, this might be 403 or ignored.
        # Ideally ignored or 403. If 200, check it wasn't updated.
        self.workout_a.refresh_from_db()
        self.assertEqual(self.workout_a.estructura, original_struct)
