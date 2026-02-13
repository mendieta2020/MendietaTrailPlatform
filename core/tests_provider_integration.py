"""
P0 Critical Tests: Provider Registry and OAuth Callback Handler

Tests for capability-based provider abstraction and generic callback flow.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from core.providers import get_provider, list_providers, register_provider
from core.providers.base import IntegrationProvider


class TestProviderRegistry:
    """Test provider registry functions."""
    
    def test_strava_provider_registered(self):
        """Strava provider should be auto-registered on import."""
        provider = get_provider('strava')
        
        assert provider is not None, "Strava provider should be registered"
        assert provider.provider_id == 'strava'
        assert provider.display_name == 'Strava'
    
    def test_provider_not_found(self):
        """Unknown provider should return None (fail-closed)."""
        provider = get_provider('nonexistent_provider')
        
        assert provider is None, "Unknown provider should return None"
    
    def test_list_providers(self):
        """Should list all registered providers."""
        providers = list_providers()
        
        assert 'strava' in providers, "Strava should be in registered providers"
        assert isinstance(providers['strava'], IntegrationProvider)
    
    def test_provider_not_found_is_case_sensitive(self):
        """Provider lookup should be case-sensitive."""
        provider = get_provider('STRAVA')  # Wrong case
        
        assert provider is None, "Provider lookup should be case-sensitive"


class TestProviderCapabilities:
    """Test capability-based design for providers."""
    
    def test_strava_capabilities(self):
        """Strava should declare its capabilities correctly."""
        provider = get_provider('strava')
        caps = provider.capabilities()
        
        assert caps['supports_refresh'] is True, "Strava supports token refresh"
        assert caps['supports_activity_fetch'] is True, "Strava supports activity fetch"
        assert caps['supports_webhooks'] is True, "Strava supports webhooks"
        assert caps['supports_workout_push'] is False, "Strava does not support workout push yet"
    
    def test_strava_has_refresh_token_method(self):
        """Strava provider should implement refresh_token()."""
        provider = get_provider('strava')
        
        assert hasattr(provider, 'refresh_token'), "StravaProvider should have refresh_token method"
        assert callable(provider.refresh_token), "refresh_token should be callable"
    
    def test_strava_has_fetch_activities_method(self):
        """Strava provider should implement fetch_activities()."""
        provider = get_provider('strava')
        
        assert hasattr(provider, 'fetch_activities'), "StravaProvider should have fetch_activities method"
        assert callable(provider.fetch_activities), "fetch_activities should be callable"
    
    def test_unsupported_capability_raises_not_implemented(self):
        """Base provider should raise NotImplementedError for unsupported capabilities."""
        
        # Create a minimal test provider that doesn't support refresh
        class MinimalProvider(IntegrationProvider):
            @property
            def provider_id(self) -> str:
                return "minimal"
            
            @property
            def display_name(self) -> str:
                return "Minimal"
            
            def get_oauth_authorize_url(self, state: str, callback_uri: str) -> str:
                return "https://example.com/oauth"
            
            def exchange_code_for_token(self, code: str, callback_uri: str) -> dict:
                return {"access_token": "test"}
            
            def get_external_user_id(self, token_data: dict) -> str:
                return "123"
        
        provider = MinimalProvider()
        
        # Should raise NotImplementedError since capabilities() returns False for refresh
        with pytest.raises(NotImplementedError, match="minimal does not support token refresh"):
            provider.refresh_token("test_token")


@pytest.mark.django_db
class TestGenericOAuthCallback:
    """Test generic OAuth callback handler."""
    
    @patch('core.providers.strava.requests.post')  # Mock HTTP call, not provider
    def test_callback_uses_provider_registry(self, mock_requests_post, client, django_user_model):
        """Callback should use get_provider() instead of if/else branching."""
        # Setup
        coach = django_user_model.objects.create_user(username='coach', email='coach@test.com', password='test')
        from core.models import Alumno
        alumno = Alumno.objects.create(
            nombre="Test",
            apellido="Athlete",
            email="athlete@test.com",
            usuario=coach,
        )
        
        # Mock HTTP token exchange response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'expires_at': 1704085200,
            'athlete': {'id': 98765432},
        }
        mock_requests_post.return_value = mock_response
        
        # Mock state validation
        from django.core.signing import TimestampSigner
        signer = TimestampSigner()
        state_payload = {
            'user_id': coach.id,
            'alumno_id': alumno.id,
            'provider': 'strava',
            'redirect_uri': 'https://example.com/callback',
        }
        state_value = signer.sign_object(state_payload)
        
        # Make request
        with patch('core.integration_callback_views.validate_and_consume_nonce') as mock_validate_nonce:
            mock_validate_nonce.return_value = (state_payload, None)  # (payload, error)
            
            response = client.get('/api/integrations/strava/callback', {
                'code': 'test_auth_code',
                'state': state_value,
                'scope': 'read,activity:read_all',
            })
        
        # Assert: Token exchange was called (proves provider was used)
        assert mock_requests_post.called, "HTTP token exchange should be called"
        
        # Should redirect to success
        assert response.status_code == 302
    
    @patch('core.providers.get_provider')
    def test_callback_fails_closed_on_unknown_provider(self, mock_get_provider, client, django_user_model):
        """Callback should fail-closed if provider not registered."""
        # Setup
        coach = django_user_model.objects.create_user(username='coach', email='coach@test.com', password='test')
        from core.models import Alumno
        alumno = Alumno.objects.create(
            nombre="Test",
            apellido="Athlete",
            email="athlete@test.com",
            usuario=coach,
        )
        
        # Mock: provider not found
        mock_get_provider.return_value = None
        
        # Mock state validation
        state_payload = {
            'user_id': coach.id,
            'alumno_id': alumno.id,
            'redirect_uri': 'https://example.com/callback',
        }
        
        # Make request
        with patch('core.integration_callback_views.validate_and_consume_nonce') as mock_validate_nonce:
            mock_validate_nonce.return_value = (state_payload, None)
            
            response = client.get('/api/integrations/unknown_provider/callback', {
                'code': 'test_auth_code',
                'state': 'test_state',
                'scope': 'read',
            })
        
        # Assert: Should redirect to error (fail-closed)
        assert response.status_code == 302
        assert 'error' in response.url or 'unsupported_provider' in response.url
    
    @patch('core.providers.get_provider')
    def test_callback_fails_closed_on_token_exchange_error(self, mock_get_provider, client, django_user_model):
        """Callback should fail-closed if token exchange fails."""
        # Setup
        coach = django_user_model.objects.create_user(username='coach', email='coach@test.com', password='test')
        from core.models import Alumno
        alumno = Alumno.objects.create(
            nombre="Test",
            apellido="Athlete",
            email="athlete@test.com",
            usuario=coach,
        )
        
        # Mock provider that fails token exchange
        mock_provider = Mock()
        mock_provider.provider_id = 'strava'
        mock_provider.display_name = 'Strava'
        mock_provider.exchange_code_for_token.side_effect = Exception("Token exchange failed")
        mock_get_provider.return_value = mock_provider
        
        # Mock state validation
        state_payload = {
            'user_id': coach.id,
            'alumno_id': alumno.id,
            'redirect_uri': 'https://example.com/callback',
        }
        
        # Make request
        with patch('core.integration_callback_views.validate_and_consume_nonce') as mock_validate_nonce:
            mock_validate_nonce.return_value = (state_payload, None)
            
            response = client.get('/api/integrations/strava/callback', {
                'code': 'test_auth_code',
                'state': 'test_state',
                'scope': 'read',
            })
        
        # Assert: Should redirect to error (fail-closed)
        assert response.status_code == 302
        assert 'error' in response.url or 'token_exchange_failed' in response.url
    
    @patch('core.providers.get_provider')
    def test_callback_fails_closed_on_invalid_user_id(self, mock_get_provider, client, django_user_model):
        """Callback should fail-closed if external user ID cannot be extracted."""
        # Setup
        coach = django_user_model.objects.create_user(username='coach', email='coach@test.com', password='test')
        from core.models import Alumno
        alumno = Alumno.objects.create(
            nombre="Test",
            apellido="Athlete",
            email="athlete@test.com",
            usuario=coach,
        )
        
        # Mock provider that fails to extract user ID
        mock_provider = Mock()
        mock_provider.provider_id = 'strava'
        mock_provider.display_name = 'Strava'
        mock_provider.exchange_code_for_token.return_value = {
            'access_token': 'test_token',
            'athlete': {},  # Missing 'id'
        }
        mock_provider.get_external_user_id.side_effect = ValueError("Missing athlete ID")
        mock_get_provider.return_value = mock_provider
        
        # Mock state validation
        state_payload = {
            'user_id': coach.id,
            'alumno_id': alumno.id,
            'redirect_uri': 'https://example.com/callback',
        }
        
        # Make request
        with patch('core.integration_callback_views.validate_and_consume_nonce') as mock_validate_nonce:
            mock_validate_nonce.return_value = (state_payload, None)
            
            response = client.get('/api/integrations/strava/callback', {
                'code': 'test_auth_code',
                'state': 'test_state',
                'scope': 'read',
            })
        
        # Assert: Should redirect to error (fail-closed)
        assert response.status_code == 302
        assert 'error' in response.url or 'invalid_user_id' in response.url
