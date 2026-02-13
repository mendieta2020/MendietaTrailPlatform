"""
Tests for canonical user identity endpoint GET /api/me/
"""
import pytest
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

from core.models import Alumno

User = get_user_model()


@pytest.mark.django_db
class TestUserIdentityEndpoint:
    """Test suite for GET /api/me/ canonical identity endpoint"""
    
    def test_me_endpoint_with_valid_jwt_returns_200(self, client):
        """
        GIVEN: Authenticated user with valid JWT
        WHEN: GET /api/me/
        THEN: Returns 200 with user identity
        """
        # Create user + athlete
        user = User.objects.create_user(username="test_athlete", password="testpass")
        coach_user = User.objects.create_user(username="test_coach", password="testpass")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach_user,
            nombre="Test",
            apellido="Athlete"
        )
        
        # Get JWT
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        # Request
        response = client.get(
            "/api/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Assert
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data
        assert data["id"] == user.id
        assert data["username"] == "test_athlete"
        assert data["role"] == "athlete"
        assert data["coach_id"] == coach_user.id
        assert data["athlete_id"] == alumno.id
    
    def test_me_endpoint_missing_jwt_returns_401(self, client):
        """
        GIVEN: No authentication
        WHEN: GET /api/me/
        THEN: Returns 401 Unauthorized
        """
        response = client.get("/api/me")
        
        assert response.status_code == 401
        assert "detail" in response.json() or "error" in response.json()
    
    def test_me_endpoint_invalid_jwt_returns_401(self, client):
        """
        GIVEN: Invalid JWT token
        WHEN: GET /api/me/
        THEN: Returns 401 Unauthorized
        """
        response = client.get(
            "/api/me",
            HTTP_AUTHORIZATION="Bearer invalid_token_here",
        )
        
        assert response.status_code == 401
    
    def test_me_endpoint_athlete_includes_coach_id(self, client):
        """
        GIVEN: Authenticated athlete with coach
        WHEN: GET /api/me/
        THEN: Returns identity with coach_id
        """
        user = User.objects.create_user(username="athlete_with_coach", password="testpass")
        coach_user = User.objects.create_user(username="coach_user", password="testpass")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach_user,
            nombre="Athlete",
            apellido="WithCoach"
        )
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "athlete"
        assert data["coach_id"] == coach_user.id
        assert data["athlete_id"] == alumno.id
    
    def test_me_endpoint_coach_excludes_athlete_fields(self, client):
        """
        GIVEN: Authenticated coach (user without Alumno profile)
        WHEN: GET /api/me/
        THEN: Returns identity with role=coach, no athlete_id/coach_id
        """
        coach_user = User.objects.create_user(username="pure_coach", password="testpass")
        
        refresh = RefreshToken.for_user(coach_user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == coach_user.id
        assert data["username"] == "pure_coach"
        assert data["role"] == "coach"
        assert "athlete_id" not in data
        assert "coach_id" not in data
    
    def test_me_endpoint_athlete_without_coach(self, client):
        """
        GIVEN: Athlete without assigned coach
        WHEN: GET /api/me/
        THEN: Returns identity with role=athlete but no coach_id
        """
        user = User.objects.create_user(username="solo_athlete", password="testpass")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=None,  # No coach assigned
            nombre="Solo",
            apellido="Athlete"
        )
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "athlete"
        assert data["athlete_id"] == alumno.id
        assert "coach_id" not in data  # No coach assigned
