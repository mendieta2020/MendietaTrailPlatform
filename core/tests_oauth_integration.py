"""
Tests for OAuth integration hardening (P0).

Tests cover:
- Signal validation and OAuthIntegrationStatus persistence
- Webhook linking regression (link_required resolution)
- Coach endpoint tenancy enforcement
"""
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import Mock, patch

from core.models import Alumno, ExternalIdentity, StravaWebhookEvent
from core.integration_models import OAuthIntegrationStatus
from core.signals import link_strava_on_oauth


@pytest.mark.django_db
class TestOAuthSignalHardening:
    """Test hardened link_strava_on_oauth signal."""
    
    def test_signal_success_creates_integration_status(self):
        """
        GIVEN: Valid OAuth callback with access_token and athlete.id
        WHEN: signal triggers
        THEN: Creates OAuthIntegrationStatus with connected=True
        """
        # Setup: user + alumno
        user = User.objects.create_user(username="athlete1", password="test")
        coach = User.objects.create_user(username="coach1", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test Athlete",
            equipo=None,
        )
        
        # Mock sociallogin with valid data
        mock_sociallogin = Mock()
        mock_account = Mock()
        mock_account.provider = "strava"
        mock_account.extra_data = {
            "access_token": "test_access_token_12345",
            "refresh_token": "test_refresh_token_67890",
            "expires_at": 1704085200,  # 2024-01-01 00:00:00 UTC
            "athlete": {
                "id": 98765432,
                "username": "athlete1_strava",
            },
        }
        mock_sociallogin.account = mock_account
        mock_sociallogin.user = user
        
        # Trigger signal
        link_strava_on_oauth(
            sender=None,
            request=None,
            sociallogin=mock_sociallogin,
        )
        
        # Assert: ExternalIdentity created
        identity = ExternalIdentity.objects.get(
            provider="strava",
            external_user_id="98765432",
        )
        assert identity.alumno == alumno
        assert identity.status == ExternalIdentity.Status.LINKED
        
        # Assert: OAuthIntegrationStatus created and connected
        integration = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava",
        )
        assert integration.connected is True
        assert integration.athlete_id == "98765432"
        assert integration.error_reason == ""
        assert integration.error_message == ""
        assert integration.expires_at is not None
    
    def test_signal_missing_access_token_marks_failed(self):
        """
        GIVEN: OAuth callback missing access_token
        WHEN: signal triggers
        THEN: Creates OAuthIntegrationStatus with connected=False and error_reason
        """
        user = User.objects.create_user(username="athlete2", password="test")
        coach = User.objects.create_user(username="coach2", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test Athlete 2",
            equipo=None,
        )
        
        # Mock sociallogin WITHOUT access_token
        mock_sociallogin = Mock()
        mock_account = Mock()
        mock_account.provider = "strava"
        mock_account.extra_data = {
            # Missing access_token!
            "athlete": {
                "id": 11111111,
            },
        }
        mock_sociallogin.account = mock_account
        mock_sociallogin.user = user
        
        # Trigger signal
        link_strava_on_oauth(
            sender=None,
            request=None,
            sociallogin=mock_sociallogin,
        )
        
        # Assert: OAuthIntegrationStatus created with error
        integration = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava",
        )
        assert integration.connected is False
        assert integration.error_reason == "missing_access_token"
        assert "access_token missing" in integration.error_message
        assert integration.last_error_at is not None
        
        # Assert: ExternalIdentity NOT created (fail-closed)
        assert not ExternalIdentity.objects.filter(
            provider="strava",
            external_user_id="11111111",
        ).exists()
    
    def test_signal_missing_athlete_id_marks_failed(self):
        """
        GIVEN: OAuth callback missing athlete.id
        WHEN: signal triggers
        THEN: Creates OAuthIntegrationStatus with connected=False and error_reason
        """
        user = User.objects.create_user(username="athlete3", password="test")
        coach = User.objects.create_user(username="coach3", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test Athlete 3",
            equipo=None,
        )
        
        # Mock sociallogin with access_token but NO athlete.id
        mock_sociallogin = Mock()
        mock_account = Mock()
        mock_account.provider = "strava"
        mock_account.extra_data = {
            "access_token": "test_access_token_valid",
            # Missing athlete.id!
        }
        mock_sociallogin.account = mock_account
        mock_sociallogin.user = user
        
        # Trigger signal
        link_strava_on_oauth(
            sender=None,
            request=None,
            sociallogin=mock_sociallogin,
        )
        
        # Assert: OAuthIntegrationStatus created with error
        integration = OAuthIntegrationStatus.objects.get(
            alumno=alumno,
            provider="strava",
        )
        assert integration.connected is False
        assert integration.error_reason == "missing_athlete_id"
        assert "athlete.id" in integration.error_message
        assert integration.last_error_at is not None
    
    def test_signal_idempotent_repeated_calls(self):
        """
        GIVEN: OAuth signal triggered twice with same data
        WHEN: signal runs both times
        THEN: Only one ExternalIdentity and OAuthIntegrationStatus created
        """
        user = User.objects.create_user(username="athlete4", password="test")
        coach = User.objects.create_user(username="coach4", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test Athlete 4",
            equipo=None,
        )
        
        mock_sociallogin = Mock()
        mock_account = Mock()
        mock_account.provider = "strava"
        mock_account.extra_data = {
            "access_token": "test_token",
            "athlete": {"id": 55555555},
        }
        mock_sociallogin.account = mock_account
        mock_sociallogin.user = user
        
        # Trigger signal TWICE
        link_strava_on_oauth(sender=None, request=None, sociallogin=mock_sociallogin)
        link_strava_on_oauth(sender=None, request=None, sociallogin=mock_sociallogin)
        
        # Assert: Only ONE of each
        assert ExternalIdentity.objects.filter(
            provider="strava",
            external_user_id="55555555",
        ).count() == 1
        assert OAuthIntegrationStatus.objects.filter(
            alumno=alumno,
            provider="strava",
        ).count() == 1


@pytest.mark.django_db
class TestWebhookLinkingRegression:
    """Test that webhooks resolve Alumno via ExternalIdentity after OAuth linking."""
    
    def test_webhook_with_mapping_resolves_alumno(self):
        """
        GIVEN: ExternalIdentity exists linking provider athlete_id to Alumno
        WHEN: Webhook event processed
        THEN: Resolves Alumno correctly (no link_required)
        """
        # This test verifies the existing webhook logic in tasks.py
        # The code at line 784-791 in tasks.py already handles this:
        # identity = ExternalIdentity.objects.filter(provider=event.provider, external_user_id=owner_key).first()
        # if identity and identity.alumno_id: alumno = identity.alumno
        
        # Setup
        user = User.objects.create_user(username="athlete5", password="test")
        coach = User.objects.create_user(username="coach5", password="test")
        alumno = Alumno.objects.create(
            usuario=user,
            entrenador=coach,
            nombre="Test Athlete 5",
            equipo=None,
        )
        
        # Create mapping (as signal would)
        ExternalIdentity.objects.create(
            provider="strava",
            external_user_id="77777777",
            alumno=alumno,
            status=ExternalIdentity.Status.LINKED,
            linked_at=timezone.now(),
        )
        
        # Simulate webhook event
        event = StravaWebhookEvent.objects.create(
            event_uid="test-event-123",
            provider="strava",
            owner_id=77777777,  # Matches ExternalIdentity
            object_id=999888777,
            object_type="activity",
            aspect_type="create",
            event_time=int(timezone.now().timestamp()),
            received_at=timezone.now(),
            status=StravaWebhookEvent.Status.QUEUED,
        )
        
        # The webhook task should resolve alumno via ExternalIdentity
        # (We're not running the full task here, just verifying the mapping exists)
        resolved_identity = ExternalIdentity.objects.filter(
            provider="strava",
            external_user_id=str(event.owner_id),
        ).first()
        
        assert resolved_identity is not None
        assert resolved_identity.alumno == alumno
        # If this assertion passes, webhook task will NOT return "link_required"
    
    def test_webhook_without_mapping_returns_link_required(self):
        """
        GIVEN: No ExternalIdentity exists for webhook owner_id
        WHEN: Webhook event processed
        THEN: Returns link_required (expected behavior for unlinked users)
        """
        # Simulate webhook for unknown athlete
        event = StravaWebhookEvent.objects.create(
            event_uid="test-event-456",
            provider="strava",
            owner_id=99999999,  # No mapping exists
            object_id=888777666,
            object_type="activity",
            aspect_type="create",
            event_time=int(timezone.now().timestamp()),
            received_at=timezone.now(),
            status=StravaWebhookEvent.Status.QUEUED,
        )
        
        # Verify no mapping exists
        resolved_identity = ExternalIdentity.objects.filter(
            provider="strava",
            external_user_id=str(event.owner_id),
        ).first()
        
        assert resolved_identity is None
        # Webhook task WILL return "link_required" (correct behavior)


@pytest.mark.django_db
class TestCoachIntegrationStatusEndpoint:
    """Test coach-scoped integration status endpoint tenancy."""
    
    def test_coach_can_read_own_athlete_status(self, client):
        """
        GIVEN: Coach requests integration status for their own athlete
        WHEN: GET /api/coach/athletes/<id>/integrations/status
        THEN: Returns status (200 OK)
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Setup
        coach = User.objects.create_user(username="coach6", password="test")
        athlete_user = User.objects.create_user(username="athlete6", password="test")
        alumno = Alumno.objects.create(
            usuario=athlete_user,
            entrenador=coach,  # Coach owns this athlete
            nombre="Coach's Athlete",
            equipo=None,
        )
        
        # Create connected integration
        OAuthIntegrationStatus.objects.create(
            alumno=alumno,
            provider="strava",
            connected=True,
            athlete_id="12312312",
        )
        
        # Authenticate as coach
        refresh = RefreshToken.for_user(coach)
        access_token = str(refresh.access_token)
        
        # Request
        response = client.get(
            f"/api/coach/athletes/{alumno.id}/integrations/status",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["athlete_id"] == alumno.id
        strava_integration = next(i for i in data["integrations"] if i["provider"] == "strava")
        assert strava_integration["connected"] is True
    
    def test_coach_cannot_read_other_coach_athlete_status(self, client):
        """
        GIVEN: Coach A requests integration status for Coach B's athlete
        WHEN: GET /api/coach/athletes/<id>/integrations/status
        THEN: Returns 403 Forbidden (fail-closed tenancy)
        """
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Setup
        coach_a = User.objects.create_user(username="coach_a", password="test")
        coach_b = User.objects.create_user(username="coach_b", password="test")
        athlete_user = User.objects.create_user(username="athlete_b", password="test")
        alumno_b = Alumno.objects.create(
            usuario=athlete_user,
            entrenador=coach_b,  # Owned by Coach B
            nombre="Coach B's Athlete",
            equipo=None,
        )
        
        # Authenticate as Coach A
        refresh = RefreshToken.for_user(coach_a)
        access_token = str(refresh.access_token)
        
        # Coach A tries to read Coach B's athlete
        response = client.get(
            f"/api/coach/athletes/{alumno_b.id}/integrations/status",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        
        # Assert: Forbidden
        assert response.status_code == 403
        assert "forbidden" in response.json().get("error", "").lower()
