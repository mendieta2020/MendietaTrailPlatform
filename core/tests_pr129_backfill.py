"""
core/tests_pr129_backfill.py

PR-129: Historical Strava backfill pipeline.

URL: POST /api/p1/orgs/<org_id>/athletes/<athlete_id>/backfill/strava/

Tests:
  1. endpoint_queues_task_with_correct_args
       Coach POSTs → task dispatched with organization_id, athlete_id, alumno_id
  2. athlete_without_strava_returns_400
       Athlete exists but has no SocialToken or OAuthCredential → 400
  3. athlete_other_org_returns_404
       athlete_id from a different org → 404 (fail-closed, not 403)
  4. unauthenticated_returns_401
       No credentials → 401
  5. athlete_role_cannot_trigger_backfill
       Athlete role → 403 PermissionDenied
  6. backfill_service_idempotent
       Calling backfill_strava_activities twice with identical API responses
       produces exactly 1 CompletedActivity (get_or_create semantics)
  7. backfill_service_raises_on_http_error
       Strava API returns 401/5xx → requests.HTTPError propagates so task retries
  8. task_structured_log_includes_required_fields
       Completion log contains organization_id, athlete_id, created, skipped
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    Membership,
    OAuthCredential,
    Organization,
)

User = get_user_model()

_BACKFILL_URL = "/api/p1/orgs/{org_id}/athletes/{athlete_id}/backfill/strava/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _alumno(user, entrenador, nombre="Test"):
    return Alumno.objects.create(
        usuario=user,
        entrenador=entrenador,
        nombre=nombre,
        apellido="Backfill",
    )


def _strava_credential(alumno):
    """Create an OAuthCredential for strava so the endpoint sees Strava as connected."""
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="strava",
        external_user_id="strava-123",
        access_token="fake_access_token",
        refresh_token="fake_refresh_token",
    )


def _authed_client(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _fake_strava_activities(count=2):
    """Return a minimal list of Strava activity dicts for mocking."""
    now = timezone.now()
    return [
        {
            "id": 1000 + i,
            "sport_type": "Run",
            "type": "Run",
            "start_date_local": (now - datetime.timedelta(days=i)).strftime(
                "%Y-%m-%dT10:00:00Z"
            ),
            "elapsed_time": 3600,
            "distance": 10000.0,
            "total_elevation_gain": 50.0,
            "calories": 600,
            "average_heartrate": 145.0,
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStravaBackfillEndpoint:
    def _setup_coach_and_athlete_with_strava(self, slug):
        org = _org(slug)
        coach_user = _user(f"{slug}-coach")
        athlete_user = _user(f"{slug}-athlete")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)
        alumno = _alumno(athlete_user, entrenador=coach_user)
        cred = _strava_credential(alumno)
        return org, coach_user, athlete_user, athlete, alumno, cred

    def test_endpoint_queues_task_with_correct_args(self):
        """Coach POST → task.delay called with organization_id, athlete_id, alumno_id."""
        org, coach_user, _, athlete, alumno, _ = self._setup_coach_and_athlete_with_strava(
            "bp-queue"
        )

        mock_result = MagicMock()
        mock_result.id = "celery-task-xyz"

        with patch(
            "integrations.strava.tasks_backfill.backfill_strava_athlete"
        ) as mock_task:
            mock_task.delay.return_value = mock_result
            client = _authed_client(coach_user)
            resp = client.post(
                _BACKFILL_URL.format(org_id=org.pk, athlete_id=athlete.pk)
            )

        assert resp.status_code == status.HTTP_202_ACCEPTED
        data = resp.json()
        assert data["status"] == "queued"
        assert data["athlete_id"] == athlete.pk
        assert data["task_id"] == "celery-task-xyz"

        mock_task.delay.assert_called_once_with(
            organization_id=org.pk,
            athlete_id=athlete.pk,
            alumno_id=alumno.pk,
        )

    def test_athlete_without_strava_returns_400(self):
        """Athlete with no Strava credential → 400 strava_not_connected."""
        org = _org("bp-no-strava")
        coach_user = _user("bp-no-strava-coach")
        athlete_user = _user("bp-no-strava-athlete")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)
        # Alumno exists but no OAuthCredential/SocialToken
        _alumno(athlete_user, entrenador=coach_user)

        client = _authed_client(coach_user)
        resp = client.post(_BACKFILL_URL.format(org_id=org.pk, athlete_id=athlete.pk))

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.json()["detail"] == "strava_not_connected"

    def test_athlete_other_org_returns_404(self):
        """Athlete from a different org → 404, not 403 (fail-closed)."""
        org_a = _org("bp-404a")
        org_b = _org("bp-404b")
        coach_user = _user("bp-404-coach")
        athlete_user = _user("bp-404-athlete")
        _membership(coach_user, org_a, "coach")
        athlete_b = _athlete(athlete_user, org_b)

        client = _authed_client(coach_user)
        resp = client.post(
            _BACKFILL_URL.format(org_id=org_a.pk, athlete_id=athlete_b.pk)
        )

        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_401(self):
        """No credentials → 401."""
        org = _org("bp-unauth")
        athlete_user = _user("bp-unauth-athlete")
        athlete = _athlete(athlete_user, org)

        resp = APIClient().post(
            _BACKFILL_URL.format(org_id=org.pk, athlete_id=athlete.pk)
        )

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_athlete_role_cannot_trigger_backfill(self):
        """Athlete role → 403 PermissionDenied."""
        org = _org("bp-athlete-role")
        coach_user = _user("bp-ar-coach")
        athlete_user = _user("bp-ar-athlete")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)
        alumno = _alumno(athlete_user, entrenador=coach_user)
        _strava_credential(alumno)

        client = _authed_client(athlete_user)
        resp = client.post(_BACKFILL_URL.format(org_id=org.pk, athlete_id=athlete.pk))

        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Service-level tests (no HTTP, no Celery)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBackfillStravaActivitiesService:
    """Tests for integrations.strava.services_strava_ingest.backfill_strava_activities."""

    def _setup_ingest_fixtures(self, slug):
        """Create org, coach user, and alumno with an active coach membership."""
        org = _org(slug)
        coach_user = _user(f"{slug}-coach")
        athlete_user = _user(f"{slug}-athlete")
        _membership(coach_user, org, "coach")
        alumno = _alumno(athlete_user, entrenador=coach_user, nombre=slug)
        return org, coach_user, athlete_user, alumno

    def test_idempotent_second_call_no_duplicate(self):
        """
        Calling backfill_strava_activities twice with the same activity list
        must produce exactly 1 CompletedActivity row (not 2).
        """
        from integrations.strava.services_strava_ingest import backfill_strava_activities

        _, _, _, alumno = self._setup_ingest_fixtures("bp-idem")
        activities = _fake_strava_activities(count=1)

        # Page 1 returns activities, page 2 returns empty list → stop
        def _mock_get(url, headers, params, timeout):
            page = params.get("page", 1)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = activities if page == 1 else []
            return mock_resp

        with patch("requests.get", side_effect=_mock_get):
            result1 = backfill_strava_activities(
                alumno_id=alumno.pk, access_token="tok", years=1
            )
            result2 = backfill_strava_activities(
                alumno_id=alumno.pk, access_token="tok", years=1
            )

        assert result1["created"] == 1
        assert result1["skipped"] == 0

        assert result2["created"] == 0
        assert result2["skipped"] == 1  # already exists — noop

        # Exactly 1 row in DB
        count = CompletedActivity.objects.filter(
            provider=CompletedActivity.Provider.STRAVA,
            provider_activity_id=str(activities[0]["id"]),
        ).count()
        assert count == 1

    def test_raises_on_http_error(self):
        """
        Strava API returns non-2xx → requests.HTTPError propagates so the
        Celery task can apply its retry policy.
        """
        from integrations.strava.services_strava_ingest import backfill_strava_activities

        _, _, _, alumno = self._setup_ingest_fixtures("bp-httperr")

        def _bad_get(url, headers, params, timeout):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized")
            return mock_resp

        with patch("requests.get", side_effect=_bad_get):
            with pytest.raises(req_lib.HTTPError):
                backfill_strava_activities(
                    alumno_id=alumno.pk, access_token="bad_token", years=1
                )

    def test_structured_log_includes_required_fields(self):
        """
        Task completion log must include organization_id, athlete_id,
        created, and skipped counts.
        """
        import logging

        from integrations.strava.tasks_backfill import backfill_strava_athlete

        _, _, _, alumno = self._setup_ingest_fixtures("bp-log")
        org = _org("bp-log-org")
        # Need an athlete row for the log fields
        athlete = Athlete.objects.create(user=alumno.usuario, organization=org)

        mock_client = MagicMock()
        mock_client.access_token = "fake_token"

        with patch(
            "core.models.Alumno.objects.get", return_value=alumno
        ), patch(
            "core.services.obtener_cliente_strava_para_alumno",
            return_value=mock_client,
        ), patch(
            "integrations.strava.services_strava_ingest.backfill_strava_activities",
            return_value={"created": 5, "skipped": 3, "errors": 0},
        ), patch.object(
            logging.getLogger("integrations.strava.tasks_backfill"),
            "info",
        ) as mock_log:
            backfill_strava_athlete(
                organization_id=org.pk,
                athlete_id=athlete.pk,
                alumno_id=alumno.pk,
            )

        mock_log.assert_called_once()
        _, kwargs = mock_log.call_args
        extra = kwargs.get("extra", {})

        assert extra["organization_id"] == org.pk
        assert extra["athlete_id"] == athlete.pk
        assert extra["created"] == 5
        assert extra["skipped"] == 3
        assert extra["outcome"] == "success"
