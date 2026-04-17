"""
core/tests_pr171_backfill_on_connect.py — PR-171

Tests: 90-day Strava backfill triggered at OAuth connection time.

Coverage:
  1. signal_fires_backfill_task_with_days_90
       social_account_added fires → backfill_strava_athlete.delay called
       with days=90 and correct alumno_id.
  2. backfill_idempotent_no_duplicates
       Running backfill_strava_activities twice with identical Strava API
       responses produces exactly 1 CompletedActivity (update_or_create noop).
  3. backfill_respects_organization_scoping
       Activity written for org A is NOT visible under org B query.
  4. strava_api_429_propagates_for_task_retry
       When Strava returns 429, requests.HTTPError propagates so Celery
       retry policy applies (tested via backfill_strava_activities).
  5. no_alumno_profile_skips_backfill
       social_account_added for a user with no Alumno → backfill NOT queued.
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    Membership,
    Organization,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Sample Strava activity payload (minimal, valid)
# ---------------------------------------------------------------------------

_STRAVA_ACTIVITY_ID = 99991111
_STRAVA_ACTIVITY = {
    "id": _STRAVA_ACTIVITY_ID,
    "sport_type": "Run",
    "type": "Run",
    "start_date_local": "2026-01-15T08:00:00Z",
    "start_date": "2026-01-15T08:00:00Z",
    "elapsed_time": 3600,
    "distance": 10000.0,
    "total_elevation_gain": 50.0,
    "calories": 500.0,
    "average_heartrate": 155.0,
    "max_heartrate": 175.0,
    "average_watts": None,
    "average_speed": 2.78,
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _org(prefix: str) -> Organization:
    # Append short uuid to prevent slug conflicts across transaction=True test runs
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    return Organization.objects.create(name=slug, slug=slug)


def _uniq(prefix: str) -> str:
    """Return a unique string safe for use as username or slug."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _coach_user(org: Organization, prefix: str) -> User:
    uname = _uniq(prefix)
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="coach", is_active=True)
    return user


def _athlete_setup(coach: User, org: Organization, prefix: str) -> tuple[User, Alumno]:
    """Create athlete user + Membership + Alumno. Returns (user, alumno)."""
    uname = _uniq(prefix)
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    alumno = Alumno.objects.create(
        nombre=uname,
        apellido="Test",
        entrenador=coach,
        usuario=user,
    )
    return user, alumno


def _mock_response(data: list) -> MagicMock:
    """Return a MagicMock that looks like a successful requests.Response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = data
    return resp


def _make_sociallogin(user: User, strava_id: str = "55551111") -> MagicMock:
    """Build a minimal allauth sociallogin mock for a Strava connection."""
    account = MagicMock()
    account.provider = "strava"
    account.uid = strava_id
    account.extra_data = {
        "access_token": "tok-pr171",
        "refresh_token": "ref-pr171",
        "expires_at": int((timezone.now() + datetime.timedelta(hours=6)).timestamp()),
        "athlete": {"id": int(strava_id)},
    }
    sl = MagicMock()
    sl.account = account
    sl.user = user
    return sl


# ---------------------------------------------------------------------------
# Test 1 — signal fires → backfill task queued with days=90
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signal_fires_backfill_task_with_days_90():
    """social_account_added → backfill_strava_athlete.delay(days=90) enqueued.

    transaction.on_commit is mocked to invoke callbacks immediately so we can
    assert without needing a real transaction commit.
    """
    org = _org("org-signal-171")
    coach = _coach_user(org, "coach-sig171")
    athlete_user, alumno = _athlete_setup(coach, org, "ath-sig171")
    # Athlete row needed so the signal can resolve organization_id + athlete_id
    Athlete.objects.create(user=athlete_user, organization=org)

    # Unique strava_id prevents UniqueViolation across repeated test runs
    unique_strava_id = str(70000000 + int(uuid.uuid4().hex[:5], 16) % 9000000)
    sociallogin = _make_sociallogin(athlete_user, strava_id=unique_strava_id)

    with (
        patch("core.signals.drain_strava_events_for_athlete") as mock_drain,
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_bf,
        # Fire on_commit callbacks immediately — no real commit needed in test
        patch("core.signals.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        mock_drain.delay = MagicMock()
        mock_bf.delay = MagicMock()

        from allauth.socialaccount.signals import social_account_added
        social_account_added.send(
            sender=None,
            request=MagicMock(),
            sociallogin=sociallogin,
        )

    mock_bf.delay.assert_called_once()
    kwargs = mock_bf.delay.call_args.kwargs
    assert kwargs["days"] == 90
    assert kwargs["alumno_id"] == alumno.id


# ---------------------------------------------------------------------------
# Test 2 — idempotent: running backfill twice = 1 CompletedActivity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_idempotent_no_duplicates():
    """backfill_strava_activities called twice with same payload → 1 row only."""
    from integrations.strava.services_strava_ingest import backfill_strava_activities

    org = _org("org-idem-171")
    coach = _coach_user(org, "coach-idem171")
    _, alumno = _athlete_setup(coach, org, "ath-idem171")

    with patch("requests.get") as mock_get:
        # First call: page 1 has 1 activity, page 2 empty → stop
        # Second call: same page 1, same empty page 2 → noop
        mock_get.side_effect = [
            _mock_response([_STRAVA_ACTIVITY]),
            _mock_response([]),
            _mock_response([_STRAVA_ACTIVITY]),
            _mock_response([]),
        ]

        result1 = backfill_strava_activities(alumno_id=alumno.id, access_token="tok", days=90)
        result2 = backfill_strava_activities(alumno_id=alumno.id, access_token="tok", days=90)

    assert result1["created"] == 1
    assert result1["skipped"] == 0
    assert result2["created"] == 0
    assert result2["skipped"] == 1  # noop on second run

    assert (
        CompletedActivity.objects.filter(
            organization=org,
            provider_activity_id=str(_STRAVA_ACTIVITY_ID),
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Test 3 — organization scoping: org A activity not visible under org B
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_backfill_respects_organization_scoping():
    """Activities ingested for org A must not appear under org B queryset."""
    from integrations.strava.services_strava_ingest import backfill_strava_activities

    org_a = _org("org-a-171")
    org_b = _org("org-b-171")
    coach_a = _coach_user(org_a, "coach-a171")
    _, alumno_a = _athlete_setup(coach_a, org_a, "ath-a171")

    with patch("requests.get") as mock_get:
        mock_get.side_effect = [
            _mock_response([_STRAVA_ACTIVITY]),
            _mock_response([]),
        ]
        result = backfill_strava_activities(alumno_id=alumno_a.id, access_token="tok", days=90)

    assert result["created"] == 1
    assert CompletedActivity.objects.filter(organization=org_a).count() == 1
    assert CompletedActivity.objects.filter(organization=org_b).count() == 0


# ---------------------------------------------------------------------------
# Test 4 — Strava 429 propagates as HTTPError for Celery retry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_strava_api_429_propagates_for_task_retry():
    """When Strava returns 429, HTTPError is raised — not swallowed — so the task retries."""
    from integrations.strava.services_strava_ingest import backfill_strava_activities

    org = _org("org-429-171")
    coach = _coach_user(org, "coach-429-171")
    _, alumno = _athlete_setup(coach, org, "ath-429-171")

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError(response=mock_resp)
        mock_get.return_value = mock_resp

        with pytest.raises(req_lib.HTTPError):
            backfill_strava_activities(alumno_id=alumno.id, access_token="tok", days=90)


# ---------------------------------------------------------------------------
# Test 5 — user with no Alumno profile → backfill NOT queued
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_alumno_profile_skips_backfill():
    """User without an Alumno profile → signal exits early, backfill not enqueued."""
    uname = _uniq("orphan-171")
    orphan = User.objects.create_user(
        username=uname, password="x", email=f"{uname}@t.com"
    )
    unique_strava_id = str(90000000 + int(uuid.uuid4().hex[:5], 16) % 9000000)
    sociallogin = _make_sociallogin(orphan, strava_id=unique_strava_id)

    with (
        patch("core.signals.drain_strava_events_for_athlete") as mock_drain,
        patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_bf,
        patch("core.signals.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        mock_drain.delay = MagicMock()
        mock_bf.delay = MagicMock()

        from allauth.socialaccount.signals import social_account_added
        social_account_added.send(
            sender=None,
            request=MagicMock(),
            sociallogin=sociallogin,
        )

    mock_bf.delay.assert_not_called()
