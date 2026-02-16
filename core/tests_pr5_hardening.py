import pytest
from rest_framework.test import APIClient
from core.models import User, Alumno, Entrenamiento
from django.urls import reverse

@pytest.fixture
def coach(db):
    return User.objects.create_user(username='coach_hard', password='password')

@pytest.fixture
def athlete(db):
    return User.objects.create_user(username='athlete_hard', password='password')

@pytest.fixture
def alumno(db, coach, athlete):
    return Alumno.objects.create(
        nombre="Hardy", apellido="Test", entrenador=coach, usuario=athlete, email="hardy@test.com"
    )

@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username='admin_hard', password='password', is_staff=True)

@pytest.mark.django_db
class TestPR5Hardening:
    def setup_method(self):
        self.client = APIClient()

    def test_write_real_fields_blocked_for_coach(self, coach, alumno):
        self.client.force_authenticate(user=coach)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        payload = {
            "fecha_asignada": "2025-12-01",
            "titulo": "Block Test",
            "tipo_actividad": "RUN",
            "distancia_real_km": 10.5 # Forbidden
        }
        res = self.client.post(url, payload, format='json')
        assert res.status_code == 400
        assert "real_fields_read_only" in str(res.content)

    def test_write_real_fields_blocked_for_athlete(self, athlete, alumno):
        self.client.force_authenticate(user=athlete)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        payload = {
            "fecha_asignada": "2025-12-02",
            "titulo": "Block Test Athlete",
            "tipo_actividad": "RUN",
            "tiempo_real_min": 60 # Forbidden
        }
        res = self.client.post(url, payload, format='json')
        assert res.status_code == 400
        assert "real_fields_read_only" in str(res.content)

    def test_write_real_fields_allowed_for_staff(self, staff_user, alumno):
        # Staff bypasses the check (operational requirement just in case, or migration)
        self.client.force_authenticate(user=staff_user)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        payload = {
            "fecha_asignada": "2025-12-03",
            "titulo": "Staff Override",
            "tipo_actividad": "RUN",
            "distancia_real_km": 5.0
        }
        res = self.client.post(url, payload, format='json')
        assert res.status_code == 201
        # It's allowed, ensuring 201 created.
        # Note: Serializer might Ignore it if read_only=True in Meta, but validation pass is what we check.
        # If read_only=True in Meta, it won't be saved, but won't raise 400.
        # This test ensures NO 400 is raised.

    def test_write_plan_fields_allowed(self, coach, alumno):
        self.client.force_authenticate(user=coach)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        payload = {
            "fecha_asignada": "2025-12-04",
            "titulo": "Plan Only",
            "tipo_actividad": "RUN",
            "distancia_planificada_km": 10
        }
        res = self.client.post(url, payload, format='json')
        assert res.status_code == 201

    def test_update_blocked_real_fields(self, coach, alumno):
        # Create valid workout first
        entrenamiento = Entrenamiento.objects.create(
            alumno=alumno, fecha_asignada="2025-12-05", titulo="Update Test", tipo_actividad="RUN"
        )
        self.client.force_authenticate(user=coach)
        url = reverse('alumno-planned-workouts-detail', kwargs={'alumno_id': alumno.id, 'pk': entrenamiento.id})
        
        payload = {
            "rpe": 8 # Forbidden
        }
        res = self.client.patch(url, payload, format='json')
        assert res.status_code == 400
        assert "real_fields_read_only" in str(res.content)
