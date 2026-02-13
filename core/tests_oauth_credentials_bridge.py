"""
P0 OAuth Credentials Bridge Tests

Tests cover:
- SocialAccount + SocialToken persistence on successful OAuth callback
- Missing alumno.usuario → fail-closed with error_reason
- Missing SocialApp → fail-closed with error_reason
"""
import pytest
from unittest.mock import patch, Mock
from django.contrib.auth import get_user_model
from django.conf import settings
from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp

from core.models import Alumno
from core.integration_models import OAuthIntegrationStatus
from core.oauth_state import generate_oauth_state

User = get_user_model()


@pytest.mark.django_db
class TestOAuthCredentialsBridge:
    """Test P0 credentials bridge to SocialAccount/SocialToken"""
    
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    @patch('core.integration_callback_views.requests.post')
    def test_oauth_callback_persists_socialaccount_and_socialtoken_success(
        self, mock_post, mock_drain, client
    ):
        """
        GIVEN: Valid OAuth callback with user-linked alumno
        WHEN: Token exchange succeeds
        THEN: SocialAccount + SocialToken created AND backfill can obtain client
        """
        # Setup: Create user, coach, alumno
        user = User.objects.create_user(username="athlete_test", password="test")
        coach = User.objects.create_user(username="coach_test", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test",
            apellido="Athlete",
        )
        
        # Ensure SocialApp exists (required for SocialToken)
        social_app, _ = SocialApp.objects.get_or_create(
            provider="strava",
            defaults={
                "name": "Strava",
                "client_id": getattr(settings, "STRAVA_CLIENT_ID", "test_client_id"),
                "secret": getattr(settings, "STRAVA_CLIENT_SECRET", "test_secret"),
            }
        )
        
        # Mock Strava token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_bridge_123",
            "refresh_token": "test_refresh_bridge_456",
            "expires_at": 2000000000,  # 2033-05-18 - FAR FUTURE to avoid refresh logic
            "athlete": {
                "id": 68831859,
                "username": "athlete_test_strava",
                "firstname": "Test",
                "lastname": "Athlete",
            },
        }
        mock_post.return_value = mock_response
        
        # Generate valid state
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Execute callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "test_auth_code_bridge",
                "state": state,
                "scope": "read,activity:read_all",
            },
        )
        
        # Assert: Redirect to success
        assert response.status_code == 302
        assert "success" in response.url
        
        # Assert: SocialAccount created
        social_account = SocialAccount.objects.filter(
            user=user,
            provider="strava"
        ).first()
        assert social_account is not None, "SocialAccount should be created"
        assert social_account.uid == "68831859"
        
        # Assert: SocialToken created
        social_token = SocialToken.objects.filter(
            account=social_account
        ).first()
        assert social_token is not None, "SocialToken should be created"
        assert social_token.token == "test_access_bridge_123"
        assert social_token.token_secret == "test_refresh_bridge_456"
        assert social_token.expires_at is not None
        assert social_token.app == social_app
        
        # Assert: OAuthIntegrationStatus marked as connected
        integration_status = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava"
        )
        assert integration_status.connected is True
        assert integration_status.error_reason == ""
        
        # CRITICAL: Verify obtener_cliente_strava_para_alumno can now get client
        from core.services import obtener_cliente_strava_para_alumno
        client_obj = obtener_cliente_strava_para_alumno(alumno)
        assert client_obj is not None, "obtener_cliente_strava_para_alumno should return valid client"
        assert client_obj.access_token == "test_access_bridge_123"
    
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    @patch('core.integration_callback_views.requests.post')
    def test_oauth_callback_missing_user_marks_failed_and_no_token(
        self, mock_post, mock_drain, client
    ):
        """
        GIVEN: OAuth callback for alumno WITHOUT usuario link
        WHEN: Token exchange succeeds but alumno.usuario is None
        THEN: OAuthIntegrationStatus marked as failed, NO SocialToken created
        """
        # Setup: Create coach and alumno WITHOUT usuario
        coach = User.objects.create_user(username="coach_orphan", password="test")
        alumno = Alumno.objects.create(
            usuario=None,  # NO USER LINKED
            entrenador=coach,
            nombre="Orphan",
            apellido="Alumno",
            strava_athlete_id="12345678",
        )
        
        # Create a dummy user for state generation (OAuth flow needs user context)
        dummy_user = User.objects.create_user(username="dummy_oauth", password="test")
        
        # Mock Strava token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "orphan_access",
            "refresh_token": "orphan_refresh",
            "expires_at": 1704132000,
            "athlete": {"id": 12345678, "username": "orphan_athlete"},
        }
        mock_post.return_value = mock_response
        
        # Generate state with dummy user but actual alumno
        state = generate_oauth_state(
            provider="strava",
            user_id=dummy_user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Execute callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "orphan_code",
                "state": state,
            },
        )
        
        
        # Assert: Redirect to error
        assert response.status_code == 302
        # URL format varies, focus on database state instead
        
        # Assert: OAuthIntegrationStatus marked as failed
        integration_status = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava"
        )
        assert integration_status.connected is False
        assert integration_status.error_reason == "missing_user"
        assert "Alumno not linked to User" in integration_status.error_message
        
        # Assert: NO SocialToken created
        assert SocialToken.objects.filter(
            account__user=dummy_user,
            account__provider="strava"
        ).count() == 0
    
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    @patch('core.integration_callback_views.requests.post')
    def test_oauth_callback_missing_socialapp_marks_failed(
        self, mock_post, mock_drain, client
    ):
        """
        GIVEN: OAuth callback but SocialApp(provider='strava') does NOT exist
        WHEN: Token exchange succeeds
        THEN: OAuthIntegrationStatus marked as failed with missing_socialapp error
        """
        # Setup: Ensure NO SocialApp exists
        SocialApp.objects.filter(provider="strava").delete()
        
        # Create user and alumno
        user = User.objects.create_user(username="athlete_nosocialapp", password="test")
        coach = User.objects.create_user(username="coach_nosocialapp", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="NoApp",
            apellido="Athlete",
        )
        
        # Mock Strava token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "noapp_access",
            "refresh_token": "noapp_refresh",
            "expires_at": 1704132000,
            "athlete": {"id": 87654321, "username": "noapp_athlete"},
        }
        mock_post.return_value = mock_response
        
        # Generate valid state
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Execute callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "noapp_code",
                "state": state,
            },
        )
        
        # Assert: Redirect to error
        assert response.status_code == 302
        # URL format varies, focus on database state instead
        
        # Assert: OAuthIntegrationStatus marked as failed
        integration_status = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava"
        )
        assert integration_status.connected is False
        assert integration_status.error_reason == "missing_socialapp"
        assert "SocialApp" in integration_status.error_message
        
        # Assert: NO SocialToken created
        assert SocialToken.objects.filter(
            account__user=user,
            account__provider="strava"
        ).count() == 0
