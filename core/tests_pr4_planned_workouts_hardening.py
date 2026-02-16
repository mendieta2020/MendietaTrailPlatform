import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from core.models import User, Alumno, Entrenamiento
from django.contrib.auth.models import Group

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def coach_user(db):
    user = User.objects.create_user(username='coach', password='password123')
    # Add to coach group or ensure logic treats as coach
    return user

@pytest.fixture
def athlete_user(db):
    return User.objects.create_user(username='athlete', password='password123')

@pytest.fixture
def other_coach(db):
    return User.objects.create_user(username='other_coach', password='password123')

@pytest.fixture
def alumno(db, coach_user, athlete_user):
    return Alumno.objects.create(
        nombre="Juan", 
        apellido="Perez", 
        entrenador=coach_user,
        usuario=athlete_user,
        email="juan@test.com"
    )

@pytest.fixture
def other_alumno(db, other_coach):
    return Alumno.objects.create(
        nombre="Pedro", 
        apellido="Lopez", 
        entrenador=other_coach,
        email="pedro@test.com"
    )

@pytest.mark.django_db
class TestPlannedWorkoutHardening:
    
    def test_create_success_without_alumno_in_body(self, api_client, coach_user, alumno):
        """
        Rule: Derive target alumno strictly from URL. Body 'alumno' can be omitted.
        """
        api_client.force_authenticate(user=coach_user)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        payload = {
            "fecha_asignada": "2025-10-20",
            "titulo": "Entrenamiento Test",
            "tipo_actividad": "RUN",
            "distancia_planificada_km": 10.5
        }
        
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 201, f"Should succeed without alumno in body. Resp: {response.content}"
        assert response.data['alumno'] == alumno.id

    def test_create_fail_mismatch_alumno_in_body(self, api_client, coach_user, alumno, other_alumno):
        """
        Rule: If request body includes 'alumno', and it mismatches URL -> 400.
        """
        api_client.force_authenticate(user=coach_user)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        # Sending other_alumno (or even 0) in body should fail if it doesn't match URL
        payload = {
            "alumno": other_alumno.id, 
            "fecha_asignada": "2025-10-21",
            "titulo": "Mismatch Test",
            "tipo_actividad": "RUN"
        }
        
        response = api_client.post(url, payload, format='json')
        if response.status_code == 201:
            pytest.fail("Should have failed with 400 Mismatch, but got 201 Created (Silent override?)")
        
        assert response.status_code == 400
        # error message check optional but good
        assert "does not match" in str(response.content).lower() or "no coincide" in str(response.content).lower()

    def test_create_fail_closed_access_other_coach_athlete(self, api_client, coach_user, other_alumno):
        """
        Rule: If alumno not accessible to authenticated user -> 404.
        """
        api_client.force_authenticate(user=coach_user)
        # Try to access other_alumno (belongs to other_coach)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': other_alumno.id})
        
        payload = {
            "fecha_asignada": "2025-10-22",
            "titulo": "Hacker Test",
            "tipo_actividad": "RUN"
        }
        
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 404, "Should return 404 for inaccessible alumno"

    def test_numeric_validation_garbage(self, api_client, coach_user, alumno):
        """
        Rule: Numeric fields must be numbers. Garbage strings returns 400.
        """
        api_client.force_authenticate(user=coach_user)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        
        payload = {
            "fecha_asignada": "2025-10-23",
            "titulo": "Numeric Test",
            "tipo_actividad": "RUN",
            "distancia_planificada_km": "diez kilometros" # Invalid
        }
        
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 400
        assert "number" in str(response.content).lower() or "valid" in str(response.content).lower()

    def test_numeric_validation_valid_string(self, api_client, coach_user, alumno):
        """
        Rule: Numeric strings that are valid numbers should be accepted (DRF DecimalField default).
        """
        api_client.force_authenticate(user=coach_user)
        url = reverse('alumno-planned-workouts-list', kwargs={'alumno_id': alumno.id})
        
        payload = {
            "fecha_asignada": "2025-10-24",
            "titulo": "Numeric String Test",
            "tipo_actividad": "RUN",
            "distancia_planificada_km": "12.5" # Valid string
        }
        
        response = api_client.post(url, payload, format='json')
        assert response.status_code == 201
        assert float(response.data['distancia_planificada_km']) == 12.5
