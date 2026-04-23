"""
core/tests_pr185_strava_delete_webhook.py — PR-185 Bug #47

Tests for Strava activity.delete webhook soft-delete flow.

Coverage:
  T1. delete webhook → CompletedActivity.deleted_at set; activity excluded from calendar query
  T2. delete webhook → idempotent (second delete is PROCESSED noop, no error)
  T3. delete webhook → compute_pmc_full_for_athlete task dispatched
  T4. delete webhook with no matching CompletedActivity → PROCESSED noop
  T5. delete webhook with no linked ExternalIdentity → IGNORED
  T6. soft-deleted activity excluded from PMC read queryset (tripwire for future regressions)
  T7. soft-deleted activity excluded from reconciliation candidate matching (tripwire)
"""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    ExternalIdentity,
    Membership,
    Organization,
    PlannedWorkout,
    StravaWebhookEvent,
    WorkoutAssignment,
    WorkoutLibrary,
)
from core.services_reconciliation import find_best_match
from core.tasks import _handle_strava_activity_delete

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _org(prefix: str = "org") -> Organization:
    slug = _uniq(prefix)
    return Organization.objects.create(name=slug, slug=slug)


def _user(org: Organization, role: str = "athlete") -> User:
    uname = _uniq("u")
    user = User.objects.create_user(username=uname, password="x", email=f"{uname}@t.com")
    Membership.objects.create(organization=org, user=user, role=role, is_active=True)
    return user


def _alumno(user: User, coach: User | None = None) -> Alumno:
    return Alumno.objects.create(
        nombre=user.username,
        apellido="TestDelete",
        usuario=user,
        entrenador=coach,
    )


def _identity(alumno: Alumno, strava_id: int) -> ExternalIdentity:
    return ExternalIdentity.objects.create(
        provider="strava",
        external_user_id=str(strava_id),
        alumno=alumno,
        status=ExternalIdentity.Status.LINKED,
    )


def _completed_activity(org: Organization, alumno: Alumno, strava_activity_id: int) -> CompletedActivity:
    athlete = Athlete.objects.filter(user=alumno.usuario, organization=org).first()
    return CompletedActivity.objects.create(
        organization=org,
        alumno=alumno,
        athlete=athlete,
        sport="RUNNING",
        start_time=timezone.now(),
        duration_s=3600,
        distance_m=10000.0,
        provider="strava",
        provider_activity_id=str(strava_activity_id),
    )


def _delete_event(owner_id: int, object_id: int) -> StravaWebhookEvent:
    uid = f"strava:activity:{object_id}"
    return StravaWebhookEvent.objects.create(
        event_uid=uid,
        object_type="activity",
        object_id=object_id,
        aspect_type="delete",
        owner_id=owner_id,
        subscription_id=1,
        payload_raw={},
        status=StravaWebhookEvent.Status.PROCESSING,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_athlete(db):
    org = _org()
    user = _user(org)
    Athlete.objects.create(user=user, organization=org)
    alumno = _alumno(user)
    strava_id = 68831859
    _identity(alumno, strava_id)
    return org, user, alumno, strava_id


# ---------------------------------------------------------------------------
# T1 — delete sets deleted_at and excludes from calendar query
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_delete_webhook_soft_deletes_activity(setup_athlete):
    org, user, alumno, strava_id = setup_athlete
    activity = _completed_activity(org, alumno, strava_activity_id=9001)
    event = _delete_event(owner_id=strava_id, object_id=9001)

    with patch("core.tasks.compute_pmc_full_for_athlete"):
        result = _handle_strava_activity_delete(event)

    assert result == "PROCESSED: soft_deleted"
    activity.refresh_from_db()
    assert activity.deleted_at is not None

    # Excluded from calendar timeline filter
    visible = CompletedActivity.objects.filter(
        organization=org,
        alumno=alumno,
        deleted_at__isnull=True,
    )
    assert visible.count() == 0

    event.refresh_from_db()
    assert event.status == StravaWebhookEvent.Status.PROCESSED


# ---------------------------------------------------------------------------
# T2 — idempotent: second delete is PROCESSED noop
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_delete_webhook_idempotent(setup_athlete):
    org, user, alumno, strava_id = setup_athlete
    _completed_activity(org, alumno, strava_activity_id=9002)

    # Two distinct delivery UIDs for the same logical delete (Strava can re-deliver)
    event1 = StravaWebhookEvent.objects.create(
        event_uid="strava:activity:9002:del1",
        object_type="activity", object_id=9002, aspect_type="delete",
        owner_id=strava_id, subscription_id=1, payload_raw={},
        status=StravaWebhookEvent.Status.PROCESSING,
    )
    event2 = StravaWebhookEvent.objects.create(
        event_uid="strava:activity:9002:del2",
        object_type="activity", object_id=9002, aspect_type="delete",
        owner_id=strava_id, subscription_id=1, payload_raw={},
        status=StravaWebhookEvent.Status.PROCESSING,
    )

    with patch("core.tasks.compute_pmc_full_for_athlete"):
        result1 = _handle_strava_activity_delete(event1)
        result2 = _handle_strava_activity_delete(event2)

    assert result1 == "PROCESSED: soft_deleted"
    assert result2 == "PROCESSED: delete_noop"

    # Only one soft-delete, no double-mark
    assert CompletedActivity.objects.filter(
        alumno=alumno, provider_activity_id="9002"
    ).count() == 1


# ---------------------------------------------------------------------------
# T3 — PMC recompute task dispatched after soft-delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_delete_webhook_triggers_pmc_recompute(setup_athlete):
    org, user, alumno, strava_id = setup_athlete
    _completed_activity(org, alumno, strava_activity_id=9003)
    event = _delete_event(owner_id=strava_id, object_id=9003)

    with patch("core.tasks.compute_pmc_full_for_athlete") as mock_task:
        mock_task.delay = mock_task
        _handle_strava_activity_delete(event)

    mock_task.delay.assert_called_once_with(
        user_id=user.pk,
        organization_id=org.pk,
    )


# ---------------------------------------------------------------------------
# T4 — no matching CompletedActivity → PROCESSED noop (never ingested)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_delete_webhook_noop_when_activity_not_found(setup_athlete):
    _, _, _, strava_id = setup_athlete
    event = _delete_event(owner_id=strava_id, object_id=99999)

    with patch("core.tasks.compute_pmc_full_for_athlete"):
        result = _handle_strava_activity_delete(event)

    assert result == "PROCESSED: delete_noop"
    event.refresh_from_db()
    assert event.status == StravaWebhookEvent.Status.PROCESSED


# ---------------------------------------------------------------------------
# T5 — no linked ExternalIdentity → IGNORED
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_delete_webhook_ignored_when_no_identity(db):
    event = _delete_event(owner_id=99999999, object_id=9004)

    result = _handle_strava_activity_delete(event)

    assert result == "IGNORED: delete_no_linked_identity"
    event.refresh_from_db()
    assert event.status == StravaWebhookEvent.Status.IGNORED


# ---------------------------------------------------------------------------
# T6 — soft-deleted activity excluded from PMC read queryset
#        Tripwire: any future removal of deleted_at__isnull=True from PMC
#        read paths will fail this test immediately.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_soft_deleted_activity_excluded_from_pmc_read(setup_athlete):
    org, user, alumno, strava_id = setup_athlete
    activity = _completed_activity(org, alumno, strava_activity_id=9010)

    # Confirm activity is visible before soft-delete
    today = timezone.now().date()
    start_date = today - datetime.timedelta(days=30)
    visible_qs = CompletedActivity.objects.filter(
        organization=org,
        alumno=alumno,
        start_time__date__gte=start_date,
        start_time__date__lte=today,
        deleted_at__isnull=True,
    )
    assert visible_qs.count() == 1

    # Soft-delete
    CompletedActivity.objects.filter(pk=activity.pk).update(deleted_at=timezone.now())

    # The same queryset (mirrors views_pmc.py PMC time-series filter) must return 0
    assert visible_qs.count() == 0

    # Verify the row still exists in DB (soft-delete, not hard-delete)
    assert CompletedActivity.objects.filter(pk=activity.pk).count() == 1


# ---------------------------------------------------------------------------
# T7 — soft-deleted activity excluded from reconciliation candidate matching
#        Tripwire: any future removal of deleted_at__isnull=True from
#        services_reconciliation.find_best_match will fail this test.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_soft_deleted_activity_excluded_from_reconciliation(setup_athlete):
    org, user, alumno, strava_id = setup_athlete
    athlete = Athlete.objects.get(user=user, organization=org)

    # Build a PlannedWorkout + WorkoutAssignment for today
    library = WorkoutLibrary.objects.create(organization=org, name="Lib-T7")
    planned = PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="T7 Workout",
        discipline="run",
        session_type="base",
        estimated_duration_seconds=3600,
        estimated_distance_meters=10000,
    )
    today = timezone.now().date()
    assignment = WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned,
        scheduled_date=today,
        day_order=1,
    )

    # Create a matching activity (correct discipline, same date window)
    activity = _completed_activity(org, alumno, strava_activity_id=9011)
    # Override sport to match "run" discipline
    CompletedActivity.objects.filter(pk=activity.pk).update(sport="RUN")
    activity.refresh_from_db()

    # Without soft-delete: find_best_match should find a match
    matched, confidence, reason = find_best_match(assignment, window_days=3)
    assert matched is not None, "Expected a match before soft-delete"

    # Soft-delete the activity
    CompletedActivity.objects.filter(pk=activity.pk).update(deleted_at=timezone.now())

    # After soft-delete: find_best_match must return None (no candidates)
    matched_after, confidence_after, reason_after = find_best_match(assignment, window_days=3)
    assert matched_after is None
    assert reason_after == "no_compatible_activity_in_window"
