"""
core/tests_pr147_alerts.py — PR-147: Smart Alerts & Internal Messaging

Coverage:
  1. test_send_message_success
  2. test_athlete_cannot_send_message
  3. test_mark_message_read
  4. test_alert_inactive_4d_detected
  5. test_alert_acwr_spike_detected
  6. test_alert_streak_positive
  7. test_unread_count_correct
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    InternalMessage,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(
        username=username, password="x", first_name=username.capitalize()
    )


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _library(org):
    return WorkoutLibrary.objects.create(organization=org, name="Lib")


def _workout(org, library, session_type="base"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="W",
        discipline="run",
        session_type=session_type,
        estimated_duration_seconds=3600,
    )


def _assignment(org, athlete, workout, date, status=WorkoutAssignment.Status.PLANNED, **kw):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=date,
        day_order=1,
        status=status,
        **kw,
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ---------------------------------------------------------------------------
# Fixtures (pytest-style setup)
# ---------------------------------------------------------------------------


@pytest.fixture
def setup():
    org = _org("alerts-test")
    coach_user = _user("coach1")
    athlete_user = _user("carlos")
    _membership(coach_user, org, "coach")
    _membership(athlete_user, org, "athlete")
    coach = _coach(coach_user, org)
    athlete = _athlete(athlete_user, org)
    lib = _library(org)
    workout = _workout(org, lib)
    return {
        "org": org,
        "coach_user": coach_user,
        "athlete_user": athlete_user,
        "coach": coach,
        "athlete": athlete,
        "lib": lib,
        "workout": workout,
    }


# ---------------------------------------------------------------------------
# 1. test_send_message_success
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_send_message_success(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete_user = setup["athlete_user"]
    c = _client(coach_user)

    resp = c.post(f"/api/p1/orgs/{org.pk}/messages/", {
        "recipient_id": athlete_user.pk,
        "content": "Hola Carlos, ¿todo bien?",
        "alert_type": "inactive_4d",
        "whatsapp_sent": False,
    }, format="json")

    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    data = resp.data
    assert data["content"] == "Hola Carlos, ¿todo bien?"
    assert data["alert_type"] == "inactive_4d"
    assert data["sender_id"] == coach_user.pk
    assert data["recipient_id"] == athlete_user.pk
    assert data["read_at"] is None
    assert InternalMessage.objects.filter(organization=org).count() == 1


# ---------------------------------------------------------------------------
# 2. test_athlete_can_reply_to_coach (bidirectional messaging)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_athlete_can_reply_to_coach(setup):
    """Athletes can now reply to coaches (bidirectional messaging)."""
    org = setup["org"]
    athlete_user = setup["athlete_user"]
    coach_user = setup["coach_user"]
    c = _client(athlete_user)

    # Athlete → coach: should succeed (201)
    resp = c.post(f"/api/p1/orgs/{org.pk}/messages/", {
        "recipient_id": coach_user.pk,
        "content": "Hola coach, recibí tu mensaje!",
        "alert_type": "athlete_reply",
    }, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    assert InternalMessage.objects.count() == 1

    # Athlete → another athlete: should be forbidden (403)
    User = get_user_model()
    other_athlete_user = User.objects.create_user(username="other_a", password="pass")
    Membership.objects.create(
        user=other_athlete_user,
        organization=org,
        role="athlete",
        is_active=True,
    )
    resp2 = c.post(f"/api/p1/orgs/{org.pk}/messages/", {
        "recipient_id": other_athlete_user.pk,
        "content": "Hola compañero",
        "alert_type": "",
    }, format="json")
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST  # not a coach


# ---------------------------------------------------------------------------
# 3. test_mark_message_read
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_mark_message_read(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete_user = setup["athlete_user"]

    msg = InternalMessage.objects.create(
        organization=org,
        sender=coach_user,
        recipient=athlete_user,
        content="Test message",
        alert_type="",
    )
    assert msg.read_at is None

    c = _client(athlete_user)
    resp = c.patch(f"/api/p1/orgs/{org.pk}/messages/{msg.pk}/read/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["read_at"] is not None

    msg.refresh_from_db()
    assert msg.read_at is not None


# ---------------------------------------------------------------------------
# 4. test_alert_inactive_4d_detected
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_alert_inactive_4d_detected(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete = setup["athlete"]
    workout = setup["workout"]
    today = datetime.date.today()

    # Create 5 consecutive planned (not completed) assignments ending today
    for i in range(5):
        _assignment(
            org, athlete, workout,
            today - datetime.timedelta(days=i),
            status=WorkoutAssignment.Status.PLANNED,
        )

    c = _client(coach_user)
    resp = c.get(f"/api/p1/orgs/{org.pk}/athletes/{athlete.pk}/alerts/")
    assert resp.status_code == status.HTTP_200_OK

    alert_types = [a["type"] for a in resp.data["alerts"]]
    assert "inactive_4d" in alert_types

    alert = next(a for a in resp.data["alerts"] if a["type"] == "inactive_4d")
    assert alert["days_count"] >= 4
    assert alert["severity"] == "warning"
    assert "Carlos" in alert["message_template"]


# ---------------------------------------------------------------------------
# 5. test_alert_acwr_spike_detected
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_alert_acwr_spike_detected(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete = setup["athlete"]
    lib = setup["lib"]
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())

    # Prior 4 weeks: each week = 3600s completed
    for weeks_back in range(1, 5):
        week_start = monday - datetime.timedelta(weeks=weeks_back)
        pw = _workout(org, lib)
        _assignment(
            org, athlete, pw, week_start,
            status=WorkoutAssignment.Status.COMPLETED,
            actual_duration_seconds=3600,
        )

    # This week: 9000s completed (250% of 3600 avg)
    pw_this = _workout(org, lib)
    _assignment(
        org, athlete, pw_this, monday,
        status=WorkoutAssignment.Status.COMPLETED,
        actual_duration_seconds=9000,
    )

    c = _client(coach_user)
    resp = c.get(f"/api/p1/orgs/{org.pk}/athletes/{athlete.pk}/alerts/")
    assert resp.status_code == status.HTTP_200_OK

    alert_types = [a["type"] for a in resp.data["alerts"]]
    assert "acwr_spike" in alert_types

    alert = next(a for a in resp.data["alerts"] if a["type"] == "acwr_spike")
    assert alert["pct"] > 150
    assert alert["severity"] == "danger"


# ---------------------------------------------------------------------------
# 6. test_alert_streak_positive
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_alert_streak_positive(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete = setup["athlete"]
    workout = setup["workout"]
    today = datetime.date.today()

    # 7 consecutive completed days
    for i in range(7):
        _assignment(
            org, athlete, workout,
            today - datetime.timedelta(days=i),
            status=WorkoutAssignment.Status.COMPLETED,
        )

    c = _client(coach_user)
    resp = c.get(f"/api/p1/orgs/{org.pk}/athletes/{athlete.pk}/alerts/")
    assert resp.status_code == status.HTTP_200_OK

    alert_types = [a["type"] for a in resp.data["alerts"]]
    assert "streak_positive" in alert_types

    alert = next(a for a in resp.data["alerts"] if a["type"] == "streak_positive")
    assert alert["days_count"] == 7
    assert alert["severity"] == "success"


# ---------------------------------------------------------------------------
# 7. test_unread_count_correct
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_unread_count_correct(setup):
    org = setup["org"]
    coach_user = setup["coach_user"]
    athlete_user = setup["athlete_user"]

    # Create 3 messages: 2 unread, 1 read
    msg1 = InternalMessage.objects.create(
        organization=org, sender=coach_user, recipient=athlete_user,
        content="Msg 1", alert_type=""
    )
    msg2 = InternalMessage.objects.create(
        organization=org, sender=coach_user, recipient=athlete_user,
        content="Msg 2", alert_type=""
    )
    from django.utils import timezone
    InternalMessage.objects.create(
        organization=org, sender=coach_user, recipient=athlete_user,
        content="Msg 3 (read)", alert_type="",
        read_at=timezone.now(),
    )

    # Athlete lists messages
    c = _client(athlete_user)
    resp = c.get(f"/api/p1/orgs/{org.pk}/messages/")
    assert resp.status_code == status.HTTP_200_OK

    all_msgs = resp.data["results"]
    unread = [m for m in all_msgs if m["read_at"] is None]
    assert len(unread) == 2
    assert len(all_msgs) == 3
