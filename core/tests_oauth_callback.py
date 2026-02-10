"""
Tests for custom OAuth integration callback flow.

Tests cover:
- State validation and nonce consumption
- Multi-tenancy enforcement (alumno.usuario_id == state.user_id)
- Token exchange success/failure
- ExternalIdentity persistence with correct alumno link
- OAuthIntegrationStatus updates
- Error handling and redirects
"""
import json
import pytest
from unittest.mock import patch, Mock
from django.contrib.auth.models import User
from django.core.signing import Signer
from django.utils import timezone

from core.models import Alumno, ExternalIdentity
from core.integration_models import OAuthIntegrationStatus
from core.oauth_state import generate_oauth_state


@pytest.mark.django_db
class TestIntegrationCallback:
    """Test custom OAuth integration callback handler."""
    
    @patch('core.integration_callback_views.requests.post')
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    def test_callback_success_links_alumno(self, mock_drain, mock_post, client):
        """
        GIVEN: Valid OAuth callback with code and state containing alumno_id
        WHEN: Callback processes token exchange
        THEN: ExternalIdentity created with alumno linked, status=linked
        """
        # Setup: Create user and alumno
        user = User.objects.create_user(username="athlete1", password="test")
        coach = User.objects.create_user(username="coach1", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test",
            apellido="Athlete",
        )
        
        # Generate valid state with alumno_id
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Mock Strava token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token_123",
            "refresh_token": "test_refresh_token_456",
            "expires_at": 1704132000,  # 2024-01-01 12:00:00 UTC
            "athlete": {
                "id": 98765432,
                "username": "athlete1_strava",
                "firstname": "Test",
                "lastname": "Athlete",
            },
        }
        mock_post.return_value = mock_response
        
        # Invoke callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "test_authorization_code_xyz",
                "state": state,
                "scope": "read,activity:read_all",
            },
        )
        
        # Assert: Redirect to frontend with success
        assert response.status_code == 302
        assert "/integrations/callback" in response.url
        assert "status=success" in response.url
        assert "provider=strava" in response.url
        
        # Assert: ExternalIdentity created with alumno linked
        identity = ExternalIdentity.objects.get(
            provider="strava",
            external_user_id="98765432",
        )
        assert identity.alumno == alumno
        assert identity.status == ExternalIdentity.Status.LINKED
        assert identity.linked_at is not None
        
        # Assert: OAuthIntegrationStatus updated
        integration_status = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava",
        )
        assert integration_status.connected is True
        assert integration_status.athlete_id == "98765432"
        assert integration_status.error_reason == ""
        assert integration_status.expires_at is not None
        
        # Assert: Background sync triggered
        mock_drain.delay.assert_called_once_with(alumno.id)
    
    def test_callback_invalid_state_rejected(self, client):
        """
        GIVEN: Callback with tampered/invalid state
        WHEN: Callback validates state
        THEN: Redirects with error (state validation failed)
        """
        # Invalid state (not signed)
        fake_state = "invalid_state_not_signed"
        
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "some_code",
                "state": fake_state,
            },
        )
        
        # Assert: Redirect with error
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=state_malformed" in response.url
    
    def test_callback_expired_state_rejected(self, client):
        """
        GIVEN: Callback with expired state (timestamp > 10min old)
        WHEN: Callback validates state
        THEN: Redirects with error (state_expired)
        """
        # Create expired state manually
        import uuid
        from datetime import datetime, timedelta, timezone as dt_timezone
        
        nonce = str(uuid.uuid4())
        old_timestamp = int((datetime.now(dt_timezone.utc) - timedelta(minutes=15)).timestamp())
        
        payload = {
            "provider": "strava",
            "user_id": 999,
            "alumno_id": 888,
            "nonce": nonce,
            "ts": old_timestamp,
            "redirect_uri": "http://test.com/callback",
        }
        
        signer = Signer()
        expired_state = signer.sign(json.dumps(payload))
        
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "some_code",
                "state": expired_state,
            },
        )
        
        # Assert: Redirect with error
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=state_expired" in response.url
    
    @patch('core.integration_callback_views.requests.post')
    def test_callback_alumno_user_mismatch_rejected(self, mock_post, client):
        """
        GIVEN: State has alumno_id A owned by user X, but state has user_id Y
        WHEN: Callback validates multi-tenancy
        THEN: Rejects with 403 error (anti-hijack)
        """
        # Setup: Create two users and two alumnos
        user_a = User.objects.create_user(username="user_a", password="test")
        user_b = User.objects.create_user(username="user_b", password="test")
        
        coach = User.objects.create_user(username="coach", password="test")
        
        alumno_a = Alumno.objects.create(
            usuario=user_a,
            entrenador=coach,
            nombre="Alumno",
            apellido="A",
        )
        
        # Generate state with user_b's ID but alumno_a's ID (mismatch!)
        state = generate_oauth_state(
            provider="strava",
            user_id=user_b.id,  # ← Wrong user
            alumno_id=alumno_a.id,  # ← Belongs to user_a
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Invoke callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "test_code",
                "state": state,
            },
        )
        
        # Assert: Redirect with unauthorized error
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=unauthorized" in response.url
        
        # Assert: NO ExternalIdentity created
        assert not ExternalIdentity.objects.filter(alumno=alumno_a).exists()
    
    @patch('core.integration_callback_views.requests.post')
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    def test_callback_idempotent_reauthorization(self, mock_drain, mock_post, client):
        """
        GIVEN: Alumno already has ExternalIdentity linked
        WHEN: Re-authorizes (update permissions or refresh)
        THEN: Updates existing ExternalIdentity, no duplicate created
        """
        # Setup: Create alumno with existing identity
        user = User.objects.create_user(username="athlete2", password="test")
        coach = User.objects.create_user(username="coach2", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Existing",
            apellido="Athlete",
        )
        
        # Pre-existing identity
        existing_identity = ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="11111111",
            alumno=alumno,
            status=ExternalIdentity.Status.LINKED,
            linked_at=timezone.now(),
            profile={"old": "data"},
        )
        
        # Generate state
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Mock token response (SAME athlete_id)
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token_789",
            "refresh_token": "new_refresh_token_012",
            "expires_at": 1704218400,
            "athlete": {
                "id": 11111111,  # Same athlete ID
                "username": "athlete2_updated",
            },
        }
        mock_post.return_value = mock_response
        
        # Invoke callback (re-authorization)
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "new_code",
                "state": state,
            },
        )
        
        # Assert: Success
        assert response.status_code == 302
        assert "status=success" in response.url
        
        # Assert: SAME identity updated, NO duplicate
        assert ExternalIdentity.objects.filter(provider="strava", external_user_id="11111111").count() == 1
        
        updated_identity = ExternalIdentity.objects.get(id=existing_identity.id)
        assert updated_identity.alumno == alumno  # Still linked
        assert updated_identity.profile.get("username") == "athlete2_updated"  # Profile updated
    
    def test_callback_missing_code_fails(self, client):
        """
        GIVEN: Callback invoked without code parameter
        WHEN: Callback validates params
        THEN: Redirects with error
        """
        user = User.objects.create_user(username="athlete3", password="test")
        coach = User.objects.create_user(username="coach3", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test",
            apellido="Athlete3",
        )
        
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
        )
        
        # Missing 'code' parameter
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "state": state,
                # code missing!
            },
        )
        
        # Assert: Error
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=invalid_request" in response.url
    
    @patch('core.integration_callback_views.requests.post')
    def test_callback_token_exchange_failure_handled(self, mock_post, client):
        """
        GIVEN: Strava API returns 4xx/5xx during token exchange
        WHEN: Callback attempts token exchange
        THEN: Redirects with error, no ExternalIdentity created
        """
        user = User.objects.create_user(username="athlete4", password="test")
        coach = User.objects.create_user(username="coach4", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test",
            apellido="Athlete4",
        )
        
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
        )
        
        # Mock Strava API error
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = Exception("Bad request from Strava")
        mock_post.return_value = mock_response
        
        # Invoke callback
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "code": "invalid_code",
                "state": state,
            },
        )
        
        # Assert: Error redirect
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=token_exchange_failed" in response.url
        
        # Assert: NO ExternalIdentity created
        assert not ExternalIdentity.objects.filter(alumno=alumno).exists()
    
    def test_callback_user_denies_authorization(self, client):
        """
        GIVEN: User clicks "Deny" on Strava authorization page
        WHEN: Strava redirects with error=access_denied
        THEN: Callback redirects with user_denied error
        """
        response = client.get(
            "/api/integrations/strava/callback",
            {
                "error": "access_denied",
                "error_description": "The user denied your request",
            },
        )
        
        # Assert: User denial handled gracefully
        assert response.status_code == 302
        assert "status=error" in response.url
        assert "error=user_denied" in response.url
    
    @patch('core.integration_callback_views.requests.post')
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    def test_callback_redirect_uses_frontend_base_url(self, mock_drain, mock_post, client, settings):
        """
        GIVEN: FRONTEND_URL configured in settings
        WHEN: Callback redirects after success
        THEN: Redirect uses configured FRONTEND_URL, not hardcoded fallback
        """
        # Set custom frontend URL
        settings.FRONTEND_URL = "https://custom-frontend.example.com:8080"
        
        # Setup
        user = User.objects.create_user(username="athlete_redirect", password="test")
        coach = User.objects.create_user(username="coach_redirect", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Redirect",
            apellido="Test",
        )
        
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Mock token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "expires_at": 1704132000,
            "athlete": {"id": 12345678, "username": "test"},
        }
        mock_post.return_value = mock_response
        
        # Invoke callback
        response = client.get(
            "/api/integrations/strava/callback",
            {"code": "test_code", "state": state},
        )
        
        # Assert: Redirect uses custom FRONTEND_URL
        assert response.status_code == 302
        assert response.url.startswith("https://custom-frontend.example.com:8080/integrations/callback")
        assert "status=success" in response.url
    
    @patch('core.integration_callback_views.requests.post')
    @patch('core.integration_callback_views.drain_strava_events_for_athlete')
    def test_callback_redirect_not_hardcoded_port_3000(self, mock_drain, mock_post, client, settings):
        """
        GIVEN: FRONTEND_URL not explicitly set (uses default)
        WHEN: Callback redirects
        THEN: Does NOT use hardcoded :3000 (should use :5173 Vite default)
        """
        # Don't set FRONTEND_URL explicitly (use default)
        if hasattr(settings, 'FRONTEND_URL'):
            delattr(settings, 'FRONTEND_URL')
        
        # Setup
        user = User.objects.create_user(username="athlete_default", password="test")
        coach = User.objects.create_user(username="coach_default", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Default",
            apellido="Port",
        )
        
        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://localhost:8000/api/integrations/strava/callback",
        )
        
        # Mock token response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "expires_at": 1704132000,
            "athlete": {"id": 87654321, "username": "default_test"},
        }
        mock_post.return_value = mock_response
        
        # Invoke callback
        response = client.get(
            "/api/integrations/strava/callback",
            {"code": "test_code", "state": state},
        )
        
        # Assert: Redirect does NOT contain :3000
        assert response.status_code == 302
        assert ":3000" not in response.url, f"Should not hardcode :3000, got: {response.url}"
        
        # Assert: Should use :5173 (Vite default)
        assert ":5173" in response.url or "localhost:5173" in response.url, \
            f"Should use Vite default :5173, got: {response.url}"
