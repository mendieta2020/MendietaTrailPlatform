"""
Tests for IntegrationStartView (POST /api/integrations/{provider}/start)

Verifies:
- Authenticated athletes can initiate OAuth flow
- Unauthenticated users are rejected (401/403)
- Invalid providers are rejected (400)
- Coaches without Alumno profile are rejected (404)
- Response includes both authorization_url and oauth_url (backward compat)
"""
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from unittest.mock import patch

from core.models import Alumno

User = get_user_model()


@pytest.fixture
def api_client():
    """API client for testing"""
    return APIClient()


@pytest.fixture
def athlete_user(db):
    """Create athlete user with Alumno profile"""
    user = User.objects.create_user(
        username="athlete_test",
        email="athlete@test.com",
        password="testpass123"
    )
    alumno = Alumno.objects.create(
        nombre="Test Athlete",
        usuario=user,
        entrenador=None  # No coach for simplicity
    )
    return user, alumno


@pytest.fixture
def coach_user(db):
    """Create coach user without Alumno profile"""
    user = User.objects.create_user(
        username="coach_test",
        email="coach@test.com",
        password="testpass123"
    )
    return user


@pytest.mark.django_db
class TestIntegrationStartView:
    """Tests for POST /api/integrations/{provider}/start"""
    
    def test_start_authenticated_athlete_returns_authorization_url(self, api_client, athlete_user):
        """
        GIVEN: Authenticated athlete user
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 200 with authorization_url and oauth_url (backward compat)
        """
        user, alumno = athlete_user
        api_client.force_authenticate(user=user)
        
        url = reverse('integration_start', kwargs={'provider': 'strava'})
        
        with patch('core.integration_views.IntegrationStartView._validate_provider_config', return_value=True):
            response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert "authorization_url" in response.data
        assert "oauth_url" in response.data  # Backward compatibility
        assert response.data["provider"] == "strava"
        
        # Both should contain OAuth URL
        assert "strava.com/oauth/authorize" in response.data["authorization_url"]
        assert response.data["authorization_url"] == response.data["oauth_url"]
    
    def test_start_unauthenticated_returns_401(self, api_client):
        """
        GIVEN: Unauthenticated user
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 401 Unauthorized
        """
        url = reverse('integration_start', kwargs={'provider': 'strava'})
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_start_invalid_provider_returns_400(self, api_client, athlete_user):
        """
        GIVEN: Authenticated athlete
        WHEN: POST /api/integrations/invalid_provider/start
        THEN: Returns 400 with error (fail-closed)
        """
        user, alumno = athlete_user
        api_client.force_authenticate(user=user)
        
        url = reverse('integration_start', kwargs={'provider': 'invalid_provider'})
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert response.data["error"] == "unknown_provider"
    
    def test_start_coach_without_alumno_returns_404(self, api_client, coach_user):
        """
        GIVEN: Authenticated coach user without Alumno profile
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 404 (athlete profile not found)
        """
        api_client.force_authenticate(user=coach_user)
        
        url = reverse('integration_start', kwargs={'provider': 'strava'})
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data
        assert response.data["error"] == "athlete_not_found"
    
    def test_start_creates_valid_oauth_state(self, api_client, athlete_user):
        """
        GIVEN: Authenticated athlete
        WHEN: POST /api/integrations/strava/start
        THEN: OAuth URL includes state parameter with signed data
        """
        user, alumno = athlete_user
        api_client.force_authenticate(user=user)
        
        url = reverse('integration_start', kwargs={'provider': 'strava'})
        
        with patch('core.integration_views.IntegrationStartView._validate_provider_config', return_value=True):
            response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        oauth_url = response.data["authorization_url"]
        
        # Verify state parameter exists
        assert "state=" in oauth_url
        
        # Verify URL structure
        assert "client_id=" in oauth_url
        assert "response_type=code" in oauth_url
        assert "redirect_uri=" in oauth_url
    
    def test_start_provider_not_configured_returns_500(self, api_client, athlete_user):
        """
        GIVEN: Authenticated athlete but Strava not configured (missing client ID)
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 500 with error
        """
        user, alumno = athlete_user
        api_client.force_authenticate(user=user)
        
        url = reverse('integration_start', kwargs={'provider': 'strava'})
        
        # Mock config validation to simulate missing config
        with patch('core.integration_views.IntegrationStartView._validate_provider_config', return_value=False):
            response = api_client.post(url)
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "error" in response.data
        assert response.data["error"] == "provider_not_configured"
