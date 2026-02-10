"""
Provider-specific integration status endpoint.

GET /api/integrations/{provider}/status - Returns normalized integration status for provider
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Alumno
from core.integration_models import OAuthIntegrationStatus

User = get_user_model()


@pytest.mark.django_db
class TestProviderStatusEndpoint:
    """Tests for GET /api/integrations/{provider}/status endpoint"""
    
    def test_provider_status_unlinked(self, client):
        """
        GIVEN: Athlete with no integration linked
        WHEN: GET /api/integrations/strava/status
        THEN: Returns 200 with status=unlinked
        """
        user = User.objects.create_user(username="athlete_unlinked", password="test")
        coach = User.objects.create_user(username="coach", password="test")
        Alumno.objects.create(usuario=user, entrenador=coach, nombre="Test", apellido="Athlete")
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/integrations/strava/status",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "strava"
        assert data["status"] == "unlinked"
        assert data["external_user_id"] == ""
        assert data["athlete_id"] == ""
        assert data["linked_at"] is None
        assert data["last_sync_at"] is None
    
    def test_provider_status_connected(self, client):
        """
        GIVEN: Athlete with linked Strava integration
        WHEN: GET /api/integrations/strava/status
        THEN: Returns 200 with status=connected
        """
        user = User.objects.create_user(username="athlete_connected", password="test")
        coach = User.objects.create_user(username="coach2", password="test")
        alumno = Alumno.objects.create(usuario=user, entrenador=coach, nombre="Connected", apellido="Athlete")
        
        # Create connected integration status
        OAuthIntegrationStatus.objects.create(
            alumno=alumno,
            provider="strava",
            connected=True,
            athlete_id="12345678",
        )
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/integrations/strava/status",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "strava"
        assert data["status"] == "connected"
        assert data["external_user_id"] == "12345678"
        assert data["athlete_id"] == "12345678"
        assert data["linked_at"] is not None
    
    def test_provider_status_error(self, client):
        """
        GIVEN: Athlete with integration in error state
        WHEN: GET /api/integrations/strava/status
        THEN: Returns 200 with status=error
        """
        user = User.objects.create_user(username="athlete_error", password="test")
        coach = User.objects.create_user(username="coach3", password="test")
        alumno = Alumno.objects.create(usuario=user, entrenador=coach, nombre="Error", apellido="Athlete")
        
        # Create error integration status
        OAuthIntegrationStatus.objects.create(
            alumno=alumno,
            provider="strava",
            connected=False,
            error_reason="token_revoked",
            error_message="User revoked access",
        )
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.get(
            "/api/integrations/strava/status",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "strava"
        assert data["status"] == "error"
        assert data["error_reason"] == "token_revoked"
    
    def test_provider_status_requires_auth(self, client):
        """
        GIVEN: Unauthenticated request
        WHEN: GET /api/integrations/strava/status
        THEN: Returns 401
        """
        response = client.get("/api/integrations/strava/status")
        
        assert response.status_code == 401
    
    def test_provider_status_multi_tenant_safe(self, client):
        """
        GIVEN: Two athletes with different integrations
        WHEN: Each requests /api/integrations/strava/status
        THEN: Each sees only their own status
        """
        # Athlete A (connected)
        user_a = User.objects.create_user(username="athlete_a", password="test")
        coach = User.objects.create_user(username="coach4", password="test")
        alumno_a = Alumno.objects.create(usuario=user_a, entrenador=coach, nombre="Athlete", apellido="A")
        OAuthIntegrationStatus.objects.create(
            alumno=alumno_a,
            provider="strava",
            connected=True,
            athlete_id="11111111",
        )
        
        # Athlete B (unlinked)
        user_b = User.objects.create_user(username="athlete_b", password="test")
        alumno_b = Alumno.objects.create(usuario=user_b, entrenador=coach, nombre="Athlete", apellido="B")
        
        # Athlete A sees their connection
        refresh_a = RefreshToken.for_user(user_a)
        response_a = client.get(
            "/api/integrations/strava/status",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh_a.access_token)}",
        )
        assert response_a.status_code == 200
        assert response_a.json()["status"] == "connected"
        assert response_a.json()["athlete_id"] == "11111111"
        
        # Athlete B sees their own (unlinked)
        refresh_b = RefreshToken.for_user(user_b)
        response_b = client.get(
            "/api/integrations/strava/status",
            HTTP_AUTHORIZATION=f"Bearer {str(refresh_b.access_token)}",
        )
        assert response_b.status_code == 200
        assert response_b.json()["status"] == "unlinked"
        assert "111111" not in response_b.json()["athlete_id"]  # Does NOT see athlete A's ID
