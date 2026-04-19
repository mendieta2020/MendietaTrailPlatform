"""
core/tests_pr173_oauth_callback.py — PR-173

Tests: OAuth callback drain task argument correctness + exception visibility.

Coverage:
  1. drain_called_with_strava_athlete_id_not_django_pk
       callback success path → drain_strava_events_for_athlete.delay called with
       provider="strava" and owner_id=<Strava external ID>, NOT alumno.id.
  2. drain_failure_logs_exception_not_warning
       When .delay() raises (e.g. broker unreachable), logger.exception is called
       so the full traceback is captured in Railway logs (not silently swallowed).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
from django.contrib.auth.models import User
from django.conf import settings

from core.models import Alumno, ExternalIdentity
from core.integration_models import OAuthIntegrationStatus
from core.oauth_state import generate_oauth_state

STRAVA_ATHLETE_ID = 55667788


def _make_token_response(athlete_id: int = STRAVA_ATHLETE_ID):
    mock = MagicMock()
    mock.ok = True
    mock.status_code = 200
    mock.json.return_value = {
        "access_token": "acc_token_pr173",
        "refresh_token": "ref_token_pr173",
        "expires_at": 1704132000,
        "athlete": {
            "id": athlete_id,
            "username": "pr173_athlete",
            "firstname": "PR173",
            "lastname": "Test",
        },
    }
    return mock


def _setup_fixtures():
    """Create minimal User + Alumno + SocialApp for callback tests."""
    user = User.objects.create_user(username=f"pr173_user_{STRAVA_ATHLETE_ID}", password="x")
    coach = User.objects.create_user(username=f"pr173_coach_{STRAVA_ATHLETE_ID}", password="x")
    alumno = Alumno.objects.create(usuario=user, entrenador=coach, nombre="PR173", apellido="Fix")

    from allauth.socialaccount.models import SocialApp
    SocialApp.objects.get_or_create(
        provider="strava",
        defaults={
            "name": "Strava",
            "client_id": getattr(settings, "STRAVA_CLIENT_ID", "ci_client"),
            "secret": getattr(settings, "STRAVA_CLIENT_SECRET", "ci_secret"),
        },
    )
    return user, alumno


@pytest.mark.django_db
class TestPR173DrainArguments:
    """Verify the OAuth callback drain enqueue uses the correct Strava athlete ID."""

    @patch("core.integration_callback_views.requests.post")
    @patch("core.integration_callback_views.drain_strava_events_for_athlete")
    def test_drain_called_with_strava_athlete_id_not_django_pk(
        self, mock_drain, mock_post, client
    ):
        """
        GIVEN: Strava OAuth callback succeeds for athlete with external_user_id=55667788
        WHEN:  IntegrationCallbackView processes the callback
        THEN:  drain_strava_events_for_athlete.delay is called with
               provider="strava", owner_id=55667788 (NOT alumno.id)
        """
        user, alumno = _setup_fixtures()
        mock_post.return_value = _make_token_response(STRAVA_ATHLETE_ID)

        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://testserver/api/integrations/strava/callback",
        )

        response = client.get(
            "/api/integrations/strava/callback",
            {"code": "auth_code_pr173", "state": state, "scope": "read,activity:read_all"},
        )

        assert response.status_code == 302
        assert "status=success" in response.url

        # CORE ASSERTION: drain must receive the Strava external athlete ID.
        # Before PR-173, this was called as .delay(alumno.id) — Django PK, WRONG.
        mock_drain.delay.assert_called_once_with(
            provider="strava",
            owner_id=STRAVA_ATHLETE_ID,
        )

        # Confirm alumno.id != STRAVA_ATHLETE_ID so this test is meaningful.
        assert alumno.id != STRAVA_ATHLETE_ID

    @patch("core.integration_callback_views.requests.post")
    @patch("core.integration_callback_views.drain_strava_events_for_athlete")
    def test_drain_failure_logs_exception_with_traceback(
        self, mock_drain, mock_post, client
    ):
        """
        GIVEN: drain_strava_events_for_athlete.delay() raises (e.g. broker down)
        WHEN:  OAuth callback processes
        THEN:  logger.exception is called (not logger.warning) so the full
               traceback is visible in Railway logs — failure is NOT silently swallowed.
               The callback still redirects to success (drain is non-critical).
        """
        user, alumno = _setup_fixtures()
        mock_post.return_value = _make_token_response(STRAVA_ATHLETE_ID + 1)

        # Simulate broker / Redis being unreachable at enqueue time.
        mock_drain.delay.side_effect = Exception("Redis connection refused")

        state = generate_oauth_state(
            provider="strava",
            user_id=user.id,
            alumno_id=alumno.id,
            redirect_uri="http://testserver/api/integrations/strava/callback",
        )

        with patch("core.integration_callback_views.logger") as mock_logger:
            response = client.get(
                "/api/integrations/strava/callback",
                {"code": "auth_code_pr173b", "state": state, "scope": "read,activity:read_all"},
            )

        assert response.status_code == 302
        # Callback still succeeds — drain failure is non-critical.
        assert "status=success" in response.url

        # logger.exception must have been called (captures traceback).
        # Before PR-173, only logger.warning was called (traceback lost).
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args
        assert call_args[0][0] == "oauth.callback.drain_task_failed"
        extra = call_args[1].get("extra", {})
        assert extra.get("provider") == "strava"
        assert "alumno_id" in extra
        assert "external_user_id" in extra

        # logger.warning must NOT have been called for drain (old behaviour).
        warning_calls = [
            str(c) for c in mock_logger.warning.call_args_list
            if "drain_task_failed" in str(c)
        ]
        assert warning_calls == [], "drain failure must use logger.exception, not logger.warning"
