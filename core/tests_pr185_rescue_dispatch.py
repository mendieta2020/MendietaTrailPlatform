"""
core/tests_pr185_rescue_dispatch.py — PR-185 Bug #50

Tests for reconnect rescue dispatch: window logic, throttle, and fallback.

Coverage:
  T1. oldest failed StravaWebhookEvent → window_start = that event's received_at
  T2. no failed events → window = fallback 7 days
  T3. oldest failed event > 90d ago → window capped at 90d
  T4. rescue dispatched twice within 30 min → second call skipped (throttled)
  T5. rescue dispatched, wait > 30 min → second call allowed
  T6. rescue dispatch logged with correct source field
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.integration_callback_views import _dispatch_strava_rescue_backfill
from core.integration_models import OAuthIntegrationStatus
from core.models import (
    Alumno,
    Athlete,
    Membership,
    Organization,
    StravaWebhookEvent,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniq(prefix: str = "x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _org(prefix: str = "org") -> Organization:
    slug = _uniq(prefix)
    return Organization.objects.create(name=slug, slug=slug)


def _user_and_alumno(org: Organization) -> tuple[User, Alumno]:
    uname = _uniq("u")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role="athlete", is_active=True)
    Athlete.objects.create(user=user, organization=org)
    alumno = Alumno.objects.create(nombre=uname, apellido="TestRescue", usuario=user)
    return user, alumno


def _failed_event(owner_id: int, *, received_at=None) -> StravaWebhookEvent:
    uid = _uniq("evt")
    return StravaWebhookEvent.objects.create(
        event_uid=uid,
        object_type="activity",
        object_id=int(_uniq("").replace("-", "")[:6], 16),
        aspect_type="create",
        owner_id=owner_id,
        subscription_id=1,
        payload_raw={},
        received_at=received_at or timezone.now(),
        status=StravaWebhookEvent.Status.FAILED,
    )


STRAVA_ID = "68831859"


# ---------------------------------------------------------------------------
# T1 — oldest failed event used as window_start
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_uses_oldest_failed_event_window():
    org = _org()
    _, alumno = _user_and_alumno(org)
    old_event_time = timezone.now() - timedelta(days=30)
    _failed_event(int(STRAVA_ID), received_at=old_event_time)

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_task:
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args[1]
    # days should be ~30 (window from 30d ago to now)
    assert 28 <= kwargs["days"] <= 32
    assert kwargs["alumno_id"] == alumno.pk
    assert kwargs["organization_id"] == org.pk


# ---------------------------------------------------------------------------
# T2 — no failed events → fallback 7 days
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_fallback_7d_when_no_failed_events():
    org = _org()
    _, alumno = _user_and_alumno(org)

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_task:
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args[1]
    assert 6 <= kwargs["days"] <= 8


# ---------------------------------------------------------------------------
# T3 — oldest failed event > 90d → window capped at 90d
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_hard_cap_90d():
    org = _org()
    _, alumno = _user_and_alumno(org)
    very_old = timezone.now() - timedelta(days=120)
    _failed_event(int(STRAVA_ID), received_at=very_old)

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_task:
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    mock_task.delay.assert_called_once()
    kwargs = mock_task.delay.call_args[1]
    assert kwargs["days"] <= 90


# ---------------------------------------------------------------------------
# T4 — throttled within 30 min → second dispatch skipped
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_throttled_within_30min():
    org = _org()
    _, alumno = _user_and_alumno(org)

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_task:
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    # Second call must be suppressed
    assert mock_task.delay.call_count == 1

    status_row = OAuthIntegrationStatus.objects.get(alumno=alumno, provider="strava")
    assert status_row.last_rescue_dispatched_at is not None


# ---------------------------------------------------------------------------
# T5 — rescue after > 30 min → allowed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_allowed_after_throttle_window():
    org = _org()
    _, alumno = _user_and_alumno(org)

    old_dispatch = timezone.now() - timedelta(minutes=35)
    status_row, _ = OAuthIntegrationStatus.objects.get_or_create(
        alumno=alumno, provider="strava"
    )
    OAuthIntegrationStatus.objects.filter(pk=status_row.pk).update(
        last_rescue_dispatched_at=old_dispatch
    )

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete") as mock_task:
        _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    assert mock_task.delay.call_count == 1


# ---------------------------------------------------------------------------
# T6 — structured log contains correct source field
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rescue_log_source_oldest_failed_event():
    org = _org()
    _, alumno = _user_and_alumno(org)
    _failed_event(int(STRAVA_ID), received_at=timezone.now() - timedelta(days=5))

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete"):
        with patch("core.integration_callback_views.logger") as mock_log:
            _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    info_calls = [c for c in mock_log.info.call_args_list if c[0][0] == "strava.rescue.dispatched"]
    assert len(info_calls) == 1
    extra = info_calls[0][1]["extra"]
    assert extra["source"] == "oldest_failed_event"
    assert extra["athlete_id"] == STRAVA_ID


@pytest.mark.django_db
def test_rescue_log_source_fallback_7d():
    org = _org()
    _, alumno = _user_and_alumno(org)

    with patch("integrations.strava.tasks_backfill.backfill_strava_athlete"):
        with patch("core.integration_callback_views.logger") as mock_log:
            _dispatch_strava_rescue_backfill(alumno, STRAVA_ID, "strava")

    info_calls = [c for c in mock_log.info.call_args_list if c[0][0] == "strava.rescue.dispatched"]
    assert len(info_calls) == 1
    extra = info_calls[0][1]["extra"]
    assert extra["source"] == "fallback_7d"
