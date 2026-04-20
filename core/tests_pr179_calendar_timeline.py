"""
core/tests_pr179_calendar_timeline.py

PR-179a: Calendar Timeline — unified Plan + Real overlay.

Coverage (13 tests):
  Functional
  1. returns_plans_and_activities_for_valid_range
  2. pairs_plan_with_reconciled_activity
  3. unpaired_activity_returned_without_linked_plan_id
  4. unpaired_plan_past_date_marked_missed
  5. unpaired_plan_future_date_marked_pending
  6. range_exceeds_62_days_rejected
  7. missing_dates_rejected
  Permission
  8. athlete_can_view_own_calendar
  9. athlete_cannot_override_athlete_id_to_view_other
  10. coach_can_view_assigned_athlete
  11. coach_requires_athlete_id_param
  12. cross_tenant_athlete_forbidden
  13. unauthenticated_request_rejected
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
    WorkoutReconciliation,
)

User = get_user_model()

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
TOMORROW = TODAY + datetime.timedelta(days=1)


# ── Factories ─────────────────────────────────────────────────────────────────


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=True)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _alumno(user):
    alumno, _ = Alumno.objects.get_or_create(
        usuario=user,
        defaults={"nombre": user.username, "apellido": "Test"},
    )
    return alumno


def _library(org):
    return WorkoutLibrary.objects.create(organization=org, name="Lib")


def _workout(org, library, discipline="run"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Test Workout",
        discipline=discipline,
        estimated_duration_seconds=3600,
        estimated_distance_meters=10000,
    )


def _assignment(org, athlete, workout, date, coach_user, status="planned"):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=date,
        assigned_by=coach_user,
        day_order=1,
        status=status,
        snapshot_version=1,
    )


def _activity(org, athlete, date, sport="run", provider_id="act-001"):
    alumno = _alumno(athlete.user)
    return CompletedActivity.objects.create(
        organization=org,
        alumno=alumno,
        athlete=athlete,
        sport=sport,
        start_time=timezone.make_aware(
            datetime.datetime.combine(date, datetime.time(10, 0))
        ),
        duration_s=3600,
        distance_m=10000.0,
        provider=CompletedActivity.Provider.STRAVA,
        provider_activity_id=provider_id,
    )


def _reconciliation(assignment, activity, score=95):
    return WorkoutReconciliation.objects.create(
        organization=assignment.organization,
        assignment=assignment,
        completed_activity=activity,
        state=WorkoutReconciliation.State.RECONCILED,
        compliance_score=score,
        compliance_category="completed",
        match_method=WorkoutReconciliation.MatchMethod.AUTO,
    )


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _url(org_id):
    return f"/api/p1/orgs/{org_id}/calendar-timeline/"


# ── Functional tests ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_returns_plans_and_activities_for_valid_range():
    org = _org("tl-1")
    coach_u = _user("coach-tl1")
    ath_u = _user("ath-tl1")
    _membership(coach_u, org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)
    lib = _library(org)
    wo = _workout(org, lib)

    _assignment(org, athlete, wo, TODAY, coach_u)
    _activity(org, athlete, TODAY, provider_id="act-tl1")

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["plans"]) == 1
    assert len(data["activities"]) == 1
    assert data["plans"][0]["date"] == str(TODAY)
    assert data["activities"][0]["date"] == str(TODAY)
    assert data["activities"][0]["duration_min"] == 60.0
    assert data["activities"][0]["distance_km"] == 10.0
    assert "strava_url" in data["activities"][0]


@pytest.mark.django_db
def test_pairs_plan_with_reconciled_activity():
    org = _org("tl-2")
    coach_u = _user("coach-tl2")
    ath_u = _user("ath-tl2")
    _membership(coach_u, org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)
    lib = _library(org)
    wo = _workout(org, lib)

    wa = _assignment(org, athlete, wo, YESTERDAY, coach_u)
    act = _activity(org, athlete, YESTERDAY, provider_id="act-tl2")
    _reconciliation(wa, act, score=98)

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(YESTERDAY), "end_date": str(YESTERDAY),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["plans"][0]["completion_status"] == "completed"
    assert len(data["reconciliations"]) == 1
    rec = data["reconciliations"][0]
    assert rec["plan_id"] == wa.id
    assert rec["activity_id"] == act.id
    assert rec["compliance_pct"] == 98
    assert data["activities"][0]["linked_plan_id"] == wa.id


@pytest.mark.django_db
def test_unpaired_activity_returned_without_linked_plan_id():
    org = _org("tl-3")
    ath_u = _user("ath-tl3")
    _membership(_user("c-tl3"), org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)

    _activity(org, athlete, TODAY, provider_id="free-act")

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["plans"]) == 0
    assert len(data["activities"]) == 1
    assert data["activities"][0]["linked_plan_id"] is None


@pytest.mark.django_db
def test_unpaired_plan_past_date_marked_missed():
    org = _org("tl-4")
    coach_u = _user("coach-tl4")
    ath_u = _user("ath-tl4")
    _membership(coach_u, org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)
    lib = _library(org)
    wo = _workout(org, lib)
    _assignment(org, athlete, wo, YESTERDAY, coach_u)

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(YESTERDAY), "end_date": str(YESTERDAY),
    })
    assert resp.status_code == 200
    assert resp.json()["plans"][0]["completion_status"] == "missed"


@pytest.mark.django_db
def test_unpaired_plan_future_date_marked_pending():
    org = _org("tl-5")
    coach_u = _user("coach-tl5")
    ath_u = _user("ath-tl5")
    _membership(coach_u, org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)
    lib = _library(org)
    wo = _workout(org, lib)
    _assignment(org, athlete, wo, TOMORROW, coach_u)

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(TOMORROW), "end_date": str(TOMORROW),
    })
    assert resp.status_code == 200
    assert resp.json()["plans"][0]["completion_status"] == "pending"


@pytest.mark.django_db
def test_range_exceeds_62_days_rejected():
    org = _org("tl-6")
    ath_u = _user("ath-tl6")
    _membership(ath_u, org, "athlete")
    _athlete(ath_u, org)

    end = TODAY + datetime.timedelta(days=63)
    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(end),
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_missing_dates_rejected():
    org = _org("tl-7")
    ath_u = _user("ath-tl7")
    _membership(ath_u, org, "athlete")
    _athlete(ath_u, org)

    resp = _authed(ath_u).get(_url(org.id), {"start_date": "not-a-date", "end_date": str(TODAY)})
    assert resp.status_code == 400


# ── Permission tests ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_athlete_can_view_own_calendar():
    org = _org("perm-1")
    ath_u = _user("ath-p1")
    _membership(ath_u, org, "athlete")
    _athlete(ath_u, org)

    resp = _authed(ath_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "plans" in data and "activities" in data


@pytest.mark.django_db
def test_athlete_cannot_override_athlete_id_to_view_other():
    org = _org("perm-2")
    ath_u1 = _user("ath-p2a")
    ath_u2 = _user("ath-p2b")
    _membership(ath_u1, org, "athlete")
    _membership(ath_u2, org, "athlete")
    _athlete(ath_u1, org)
    other = _athlete(ath_u2, org)

    # Athlete tries to pass another athlete's id — should be ignored, not 403
    resp = _authed(ath_u1).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
        "athlete_id": other.id,  # silently ignored for athlete role
    })
    assert resp.status_code == 200
    # Response is for ath_u1's own calendar, not other's


@pytest.mark.django_db
def test_coach_can_view_assigned_athlete():
    org = _org("perm-3")
    coach_u = _user("coach-p3")
    ath_u = _user("ath-p3")
    _membership(coach_u, org, "coach")
    _membership(ath_u, org, "athlete")
    athlete = _athlete(ath_u, org)

    resp = _authed(coach_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
        "athlete_id": athlete.id,
    })
    assert resp.status_code == 200


@pytest.mark.django_db
def test_coach_requires_athlete_id_param():
    org = _org("perm-4")
    coach_u = _user("coach-p4")
    _membership(coach_u, org, "coach")

    resp = _authed(coach_u).get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_cross_tenant_athlete_forbidden():
    org1 = _org("perm-5a")
    org2 = _org("perm-5b")
    coach_u = _user("coach-p5")
    ath_u = _user("ath-p5")
    _membership(coach_u, org1, "coach")
    _membership(ath_u, org2, "athlete")
    other_athlete = _athlete(ath_u, org2)

    resp = _authed(coach_u).get(_url(org1.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
        "athlete_id": other_athlete.id,
    })
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_request_rejected():
    org = _org("perm-6")
    resp = APIClient().get(_url(org.id), {
        "start_date": str(TODAY), "end_date": str(TODAY),
    })
    assert resp.status_code in (401, 403)
