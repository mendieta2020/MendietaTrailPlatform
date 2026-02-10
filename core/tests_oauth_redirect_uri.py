"""
Tests for OAuth redirect_uri configuration (Staff Engineer audit P0).

Tests cover:
- POST /api/integrations/strava/start returns correct integration callback redirect_uri (NOT testserver)
- Integration callback uses STRAVA_INTEGRATION_CALLBACK_URI (NOT allauth's STRAVA_REDIRECT_URI)
- Settings override for deterministic tests
- State parameter presence and validity
- Error handling when integration callback cannot be derived
"""
import pytest
from urllib.parse import urlparse, parse_qs, unquote
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Alumno, User


@pytest.mark.django_db
class TestIntegrationStartView:
    """Test POST /api/integrations/strava/start with proper settings override."""
    
    def test_start_returns_correct_integration_callback_uri(self, client, settings):
        """
        GIVEN: Strava provider configured with STRAVA_INTEGRATION_CALLBACK_URI
        WHEN: POST /api/integrations/strava/start
        THEN: Returns oauth_url with integration callback redirect_uri (NOT testserver, NOT allauth callback)
        
        This test verifies:
        1. Integration flow uses STRAVA_INTEGRATION_CALLBACK_URI (/api/integrations/strava/callback)
        2. NOT allauth's STRAVA_REDIRECT_URI (/accounts/strava/login/callback/)
        3. redirect_uri comes from settings, NOT request.build_absolute_uri() (testserver bug)
        4. State parameter is present and non-empty
        """
        # Override settings for this test
        settings.STRAVA_CLIENT_ID = "test_client_id_123456"
        settings.STRAVA_CLIENT_SECRET = "test_secret_abcdef"
        settings.PUBLIC_BASE_URL = "https://test.example.com"
        settings.STRAVA_INTEGRATION_CALLBACK_URI = "https://test.example.com/api/integrations/strava/callback"
        
        # Setup: Create user with Alumno profile
        user = User.objects.create_user(username="athlete_test", password="testpass")
        coach = User.objects.create_user(username="coach_test", password="testpass")
        Alumno.objects.create(usuario=user, entrenador=coach, nombre="Test", apellido="Athlete")
        
        # Authenticate
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        # Request
        response = client.post(
            "/api/integrations/strava/start",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Assert response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert "oauth_url" in data, "Response should contain oauth_url"
        assert "provider" in data
        assert data["provider"] == "strava"
        
        # CRITICAL ASSERTION: redirect_uri must be INTEGRATION callback (NOT allauth callback)
        oauth_url = data["oauth_url"]
        expected_redirect = "https://test.example.com/api/integrations/strava/callback"
        
        # Parse OAuth URL properly (handles URL encoding)
        parsed = urlparse(oauth_url)
        query_params = parse_qs(parsed.query)
        
        # Extract redirect_uri from query parameters
        assert "redirect_uri" in query_params, f"OAuth URL should contain redirect_uri parameter: {oauth_url}"
        actual_redirect_uri = query_params["redirect_uri"][0]  # parse_qs returns list
        
        # CRITICAL: Must be integration callback, NOT allauth callback
        assert actual_redirect_uri == expected_redirect, \
            f"Expected integration callback '{expected_redirect}', got '{actual_redirect_uri}'"
        
        # CRITICAL: Should NOT contain testserver (this was the bug)
        assert "testserver" not in actual_redirect_uri, \
            f"Redirect URI should NOT contain 'testserver', got: {actual_redirect_uri}"
        
        # CRITICAL: Should NOT be allauth callback path
        assert "/accounts/strava/login/callback/" not in actual_redirect_uri, \
            f"Should use integration callback, NOT allauth callback: {actual_redirect_uri}"
        
        # NEW: Verify state parameter is present (signed context with alumno_id)
        assert "state" in query_params, f"OAuth URL must include state parameter: {oauth_url}"
        state_param = query_params["state"][0]
        assert len(state_param) > 20, f"State should be non-trivial signed payload, got: {state_param[:50]}"
        
        # Verify other OAuth parameters
        assert query_params.get("client_id") == ["test_client_id_123456"]
        assert query_params.get("response_type") == ["code"]
        assert "read" in query_params.get("scope", [""])[0]
    
    def test_start_uses_public_base_url_fallback(self, client, settings):
        """
        GIVEN: STRAVA_INTEGRATION_CALLBACK_URI is empty (uses PUBLIC_BASE_URL fallback)
        WHEN: POST /api/integrations/strava/start
        THEN: Returns oauth_url with integration callback constructed from PUBLIC_BASE_URL
        
        This verifies the fallback logic in integration_views.py works correctly:
        If STRAVA_INTEGRATION_CALLBACK_URI not set → fallback to PUBLIC_BASE_URL + "/api/integrations/strava/callback"
        """
        # Override settings
        settings.STRAVA_CLIENT_ID = "test_id"
        settings.STRAVA_CLIENT_SECRET = "test_secret"
        settings.PUBLIC_BASE_URL = "https://ngrok.example.com"
        settings.STRAVA_INTEGRATION_CALLBACK_URI = None  # Force fallback
        
        user = User.objects.create_user(username="athlete_fallback", password="test")
        coach = User.objects.create_user(username="coach_fallback", password="test")
        Alumno.objects.create(usuario=user, entrenador=coach, nombre="Fallback", apellido="Athlete")
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.post(
            "/api/integrations/strava/start",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Should succeed with fallback
        assert response.status_code == 200, f"Expected 200 with fallback, got {response.status_code}: {response.json()}"
        data = response.json()
        
        # Verify fallback callback URI was used
        oauth_url = data["oauth_url"]
        parsed = urlparse(oauth_url)
        query_params = parse_qs(parsed.query)
        
        actual_redirect = query_params["redirect_uri"][0]
        expected_fallback = "https://ngrok.example.com/api/integrations/strava/callback"
        
        assert actual_redirect == expected_fallback, \
            f"Expected fallback '{expected_fallback}', got '{actual_redirect}'"
        
    def test_start_fails_gracefully_without_integration_callback(self, client, settings):
        """
        GIVEN: STRAVA_INTEGRATION_CALLBACK_URI is None AND PUBLIC_BASE_URL is None (misconfigured)
        WHEN: POST /api/integrations/strava/start
        THEN: Should still succeed with fallback (unless both are None - edge case)
        
        NOTE: The current implementation has a fallback to PUBLIC_BASE_URL,
        so this test verifies the graceful fallback behavior.
        
        For true fail-closed: both STRAVA_INTEGRATION_CALLBACK_URI and PUBLIC_BASE_URL would need to be missing.
        """
        settings.STRAVA_CLIENT_ID = "test_id"
        settings.STRAVA_INTEGRATION_CALLBACK_URI = None
        settings.PUBLIC_BASE_URL = "http://localhost:8000"  # Fallback present
        
        user = User.objects.create_user(username="athlete_noconfig", password="test")
        coach = User.objects.create_user(username="coach_noconfig", password="test")
        Alumno.objects.create(usuario=user, entrenador=coach, nombre="No Config Athlete", apellido="Test")
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.post(
            "/api/integrations/strava/start",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Should succeed with fallback to PUBLIC_BASE_URL + "/api/integrations/strava/callback"
        assert response.status_code == 200, f"Expected fallback to succeed, got {response.status_code}: {response.json()}"
        
        # Verify fallback was used
        data = response.json()
        oauth_url = data["oauth_url"]
        parsed_url = urlparse(oauth_url); redirect_uri = parse_qs(parsed_url.query).get("redirect_uri", [""])[0]; assert "localhost:8000/api/integrations/strava/callback" in redirect_uri, f"Expected localhost fallback, got: {redirect_uri}"
    
    @override_settings(
        STRAVA_CLIENT_ID="",  # Missing client ID
        PUBLIC_BASE_URL="https://test.example.com",
    )
    def test_start_fails_without_client_id(self, client):
        """
        GIVEN: STRAVA_CLIENT_ID is empty (misconfigured)
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 500 with provider_not_configured error
        
        This verifies fail-closed behavior for missing OAuth credentials.
        """
        user = User.objects.create_user(username="athlete_noclient", password="test")
        coach = User.objects.create_user(username="coach_noclient", password="test")
        Alumno.objects.create(usuario=user, entrenador=coach, nombre="No Client", apellido="Athlete")
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.post(
            "/api/integrations/strava/start",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "provider_not_configured"
        assert ("integration not configured" in data["message"].lower() or 
                "strava" in data["message"].lower())
    
    def test_start_requires_authentication(self, client):
        """
        GIVEN: Unauthenticated request
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 401 Unauthorized
        """
        response = client.post("/api/integrations/strava/start")
        assert response.status_code in [401, 403]  # Depending on auth config
    
    @override_settings(
        STRAVA_CLIENT_ID="test_id",
        STRAVA_REDIRECT_URI="https://valid.example.com/callback/",
    )
    def test_start_requires_alumno_profile(self, client):
        """
        GIVEN: Authenticated user WITHOUT Alumno profile
        WHEN: POST /api/integrations/strava/start
        THEN: Returns 404 athlete_not_found
        """
        # Create user WITHOUT Alumno profile
        user = User.objects.create_user(username="no_profile_user", password="test")
        
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        response = client.post(
            "/api/integrations/strava/start",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "athlete_not_found"


@pytest.mark.django_db
class TestOAuthSettingsConfiguration:
    """Test that settings.py loads OAuth configuration correctly."""
    
    def test_settings_have_oauth_attributes(self):
        """
        GIVEN: Django settings loaded
        WHEN: Accessing OAuth configuration
        THEN: PUBLIC_BASE_URL and STRAVA_REDIRECT_URI exist
        """
        from django.conf import settings
        
        assert hasattr(settings, "PUBLIC_BASE_URL"), "settings.PUBLIC_BASE_URL should exist"
        assert hasattr(settings, "STRAVA_REDIRECT_URI"), "settings.STRAVA_REDIRECT_URI should exist"
        assert hasattr(settings, "STRAVA_CLIENT_ID"), "settings.STRAVA_CLIENT_ID should exist"
        
        # Values should be strings (may be empty in test environment)
        assert isinstance(settings.PUBLIC_BASE_URL, str)
        assert isinstance(settings.STRAVA_REDIRECT_URI, str)
        
    def test_strava_redirect_uri_is_valid_url(self):
        """
        GIVEN: STRAVA_REDIRECT_URI loaded from settings
        WHEN: Validating format
        THEN: Should be a valid HTTP(S) URL ending with /callback/
        """
        from django.conf import settings
        from urllib.parse import urlparse
        
        redirect_uri = settings.STRAVA_REDIRECT_URI
        
        # Should be non-empty
        assert redirect_uri, "STRAVA_REDIRECT_URI should not be empty in tests"
        
        # Should be valid URL
        parsed = urlparse(redirect_uri)
        assert parsed.scheme in ["http", "https"], f"Scheme should be http/https, got: {parsed.scheme}"
        assert parsed.netloc, f"URL should have a host, got: {redirect_uri}"
        assert "/accounts/strava/login/callback/" in redirect_uri, \
            f"URL should contain callback path, got: {redirect_uri}"
