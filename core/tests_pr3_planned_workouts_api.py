from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from core.models import Alumno, Entrenamiento, PlantillaEntrenamiento
from datetime import date, timedelta

User = get_user_model()

class PlannedWorkoutsPR3Tests(APITestCase):
    def setUp(self):
        # 1. Setup Users
        # Coach 1 (Staff/Admin based on user context hint, but we'll genericize as just a coach for strictness, 
        # or make is_staff=True if that's the only way they are a coach in this system. 
        # System says "admin is staff/superuser". Let's stick to RBAC: is_staff=True or has permission.)
        self.coach_user = User.objects.create_user(username="admin_coach", password="password", is_staff=True)
        
        # Coach 2 (Intruder)
        self.intruder_coach = User.objects.create_user(username="intruder", password="password")
        
        # Athlete 1 User (owns Alumno 1)
        self.athlete_user_1 = User.objects.create_user(username="athlete_1", password="password")
        
        # Athlete 2 User (owns Alumno 2)
        self.athlete_user_2 = User.objects.create_user(username="athlete_2", password="password")

        # 2. Setup Alumnos
        # Alumno 1 -> Coach 1
        self.alumno_1 = Alumno.objects.create(
            entrenador=self.coach_user,
            usuario=self.athlete_user_1,
            nombre="Alumno1",
            apellido="Test"
        )
        
        # Alumno 2 -> Coach 1 (Same coach, different athlete)
        self.alumno_2 = Alumno.objects.create(
            entrenador=self.coach_user,
            usuario=self.athlete_user_2,
            nombre="Alumno2",
            apellido="Test"
        )

        # Alumno 3 -> Coach 2 (Different coach)
        self.alumno_3 = Alumno.objects.create(
            entrenador=self.intruder_coach,
            nombre="Alumno3",
            apellido="Test"
        )

        # 3. Setup Workouts
        # Workout for Alumno 1
        self.wkt_a1 = Entrenamiento.objects.create(
            alumno=self.alumno_1,
            fecha_asignada=date(2026, 2, 15),
            titulo="Workout A1",
            tipo_actividad="RUN",
            estructura={"blocks": []}
        )
        
        # Workout for Alumno 2
        self.wkt_a2 = Entrenamiento.objects.create(
            alumno=self.alumno_2,
            fecha_asignada=date(2026, 2, 16),
            titulo="Workout A2",
            tipo_actividad="RUN",
            estructura={}
        )

    def test_coach_access_own_alumno_workouts_ok(self):
        """1) Coach can GET workouts for their own athlete."""
        self.client.force_authenticate(user=self.coach_user)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.data['results']) >= 1)
        self.assertEqual(res.data['results'][0]['id'], self.wkt_a1.id)

    def test_coach_access_other_alumno_404(self):
        """2) Coach CANNOT access workouts of another coach's athlete (Fail-closed 404)."""
        # We use intruder_coach (non-staff) trying to access alumno_1 (belongs to coach_user)
        self.client.force_authenticate(user=self.intruder_coach)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_athlete_access_own_workouts_ok(self):
        """3) Athlete can GET their own workouts."""
        self.client.force_authenticate(user=self.athlete_user_1)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['results'][0]['id'], self.wkt_a1.id)

    def test_athlete_access_other_alumno_404(self):
        """4) Athlete CANNOT access workouts of another athlete (even same coach)."""
        self.client.force_authenticate(user=self.athlete_user_1)
        # Try to access Alumno 2 (also owned by coach_user, but different athlete user)
        url = f"/api/alumnos/{self.alumno_2.id}/planned-workouts/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_invalid_date_format_400(self):
        """5) Invalid date format returns 400."""
        self.client.force_authenticate(user=self.coach_user)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/?from=not-a-date"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_from_to_inclusive(self):
        """6) Filter respects from/to inclusive boundaries."""
        self.client.force_authenticate(user=self.coach_user)
        
        # Create extra workouts
        wkt_early = Entrenamiento.objects.create(alumno=self.alumno_1, fecha_asignada=date(2026, 2, 10), titulo="Early")
        wkt_mid = Entrenamiento.objects.create(alumno=self.alumno_1, fecha_asignada=date(2026, 2, 15), titulo="Mid")
        wkt_late = Entrenamiento.objects.create(alumno=self.alumno_1, fecha_asignada=date(2026, 2, 20), titulo="Late")
        
        # Filter range covering only Mid (and existing wkt_a1 which is also 15th)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/?from=2026-02-12&to=2026-02-18"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in res.data['results']]
        
        self.assertIn(wkt_mid.id, ids)
        self.assertIn(self.wkt_a1.id, ids)
        self.assertNotIn(wkt_early.id, ids)
        self.assertNotIn(wkt_late.id, ids)

    def test_cross_workout_injection_404(self):
        """7) URL alumno A with pk belonging to alumno B => 404."""
        self.client.force_authenticate(user=self.coach_user)
        # Url says Alumno 1, but ID is from Alumno 2's workout
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/{self.wkt_a2.id}/"
        res = self.client.patch(url, {"completado": True})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_forces_alumno_from_url(self):
        """8) Payload tries other alumno; saved alumno is URL one."""
        self.client.force_authenticate(user=self.coach_user)
        url = f"/api/alumnos/{self.alumno_1.id}/planned-workouts/"
        
        payload = {
            "alumno": self.alumno_2.id, # Try to inject Alumno 2
            "titulo": "Hacked Workout",
            "fecha_asignada": "2026-03-01",
            "tipo_actividad": "RUN"
        }
        res = self.client.post(url, payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        
        created_id = res.data['id']
        wkt = Entrenamiento.objects.get(pk=created_id)
        # Should be assigned to Alumno 1 (from URL), NOT Alumno 2
        self.assertEqual(wkt.alumno.id, self.alumno_1.id)
        self.assertNotEqual(wkt.alumno.id, self.alumno_2.id)

    def test_compat_alias_urls(self):
        """Verify /athletes/ alias works same as /alumnos/"""
        self.client.force_authenticate(user=self.coach_user)
        url = f"/api/athletes/{self.alumno_1.id}/planned-workouts/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
