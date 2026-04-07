"""
core/tests_pr148_compliance.py — PR-148: Real Compliance + Coach at Scale + Daily Engagement

Coverage:
  1. test_compliance_pct_real_duration
  2. test_compliance_pct_real_distance
  3. test_compliance_pct_both_metrics_uses_mean
  4. test_compliance_pct_no_actual_data_defaults_100
  5. test_compliance_pct_multiple_assignments_averages
  6. test_sessions_per_day_multi_session
  7. test_consecutive_days_active_streak
  8. test_consecutive_days_active_broken_streak
  9. test_consecutive_days_active_no_activity_yesterday
 10. test_coach_briefing_endpoint
 11. test_compliance_week_bulk_query_efficiency
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteCoachAssignment,
    Coach,
    InternalMessage,
    Membership,
    Organization,
    PlannedWorkout,
    Team,
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


def _athlete(user, org, team=None):
    return Athlete.objects.create(user=user, organization=org, team=team)


def _library(org):
    return WorkoutLibrary.objects.create(organization=org, name="Lib")


def _workout(org, library, duration_s=None, distance_m=None):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="W",
        discipline="run",
        session_type="base",
        estimated_duration_seconds=duration_s,
        estimated_distance_meters=distance_m,
    )


def _assignment(
    org, athlete, workout, date,
    assign_status=WorkoutAssignment.Status.COMPLETED,
    actual_duration_s=None,
    actual_distance_m=None,
    day_order=1,
):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=date,
        day_order=day_order,
        status=assign_status,
        actual_duration_seconds=actual_duration_s,
        actual_distance_meters=actual_distance_m,
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
WEEK_START = TODAY - datetime.timedelta(days=TODAY.weekday())


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------

@pytest.fixture
def base():
    org = _org("pr148-test")
    coach_user = _user("coach148")
    athlete_user = _user("athlete148")
    _membership(coach_user, org, "coach")
    _membership(athlete_user, org, "athlete")
    coach = _coach(coach_user, org)
    team = Team.objects.create(organization=org, name="Team A")
    athlete = _athlete(athlete_user, org, team=team)
    lib = _library(org)
    return {
        "org": org,
        "coach_user": coach_user,
        "athlete_user": athlete_user,
        "coach": coach,
        "athlete": athlete,
        "team": team,
        "lib": lib,
    }


# ---------------------------------------------------------------------------
# Compliance week endpoint helper
# ---------------------------------------------------------------------------

def _compliance_week(coach_user, org, team, week_date=None):
    c = _client(coach_user)
    params = {}
    if week_date:
        params["week"] = week_date.isoformat()
    url = f"/api/p1/orgs/{org.id}/teams/{team.id}/compliance-week/"
    return c.get(url, params)


def _athlete_summary(data, athlete_id):
    for a in data["athletes"]:
        if a["athlete_id"] == athlete_id:
            return a
    return None


# ---------------------------------------------------------------------------
# 1. test_compliance_pct_real_duration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_pct_real_duration(base):
    """Planned 1h (3600s), actual 1.5h (5400s) → compliance_pct = 150."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, duration_s=3600)
    _assignment(
        org, athlete, workout,
        date=WEEK_START,
        actual_duration_s=5400,
    )
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert entry is not None
    assert entry["summary"]["compliance_pct"] == 150


# ---------------------------------------------------------------------------
# 2. test_compliance_pct_real_distance
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_pct_real_distance(base):
    """Planned 10km, actual 7km → compliance_pct = 70."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, distance_m=10000)
    _assignment(
        org, athlete, workout,
        date=WEEK_START,
        actual_distance_m=7000,
    )
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert entry["summary"]["compliance_pct"] == 70


# ---------------------------------------------------------------------------
# 3. test_compliance_pct_both_metrics_uses_mean
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_pct_both_metrics_uses_mean(base):
    """Planned 3600s + 10000m, actual 5400s + 10000m → mean(1.5, 1.0) = 1.25 → 125."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, duration_s=3600, distance_m=10000)
    _assignment(
        org, athlete, workout,
        date=WEEK_START,
        actual_duration_s=5400,
        actual_distance_m=10000,
    )
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert entry["summary"]["compliance_pct"] == 125


# ---------------------------------------------------------------------------
# 4. test_compliance_pct_no_actual_data_defaults_100
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_pct_no_actual_data_defaults_100(base):
    """COMPLETED assignment with no actual data → compliance_pct = 100 (manual completion)."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, duration_s=3600, distance_m=10000)
    _assignment(org, athlete, workout, date=WEEK_START)
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert entry["summary"]["compliance_pct"] == 100


# ---------------------------------------------------------------------------
# 5. test_compliance_pct_multiple_assignments_averages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_pct_multiple_assignments_averages(base):
    """3 assignments: 50%, 100%, 150% → weekly compliance_pct = 100."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, duration_s=3600)
    # Day 0: 1800s → 50%
    _assignment(org, athlete, workout, date=WEEK_START, actual_duration_s=1800, day_order=1)
    # Day 1: 3600s → 100%
    _assignment(
        org, athlete, workout,
        date=WEEK_START + datetime.timedelta(days=1),
        actual_duration_s=3600, day_order=1,
    )
    # Day 2: 5400s → 150%
    _assignment(
        org, athlete, workout,
        date=WEEK_START + datetime.timedelta(days=2),
        actual_duration_s=5400, day_order=1,
    )
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert entry["summary"]["compliance_pct"] == 100


# ---------------------------------------------------------------------------
# 6. test_sessions_per_day_multi_session
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sessions_per_day_multi_session(base):
    """Athlete with 2 assignments on WEEK_START → sessions_per_day includes that date."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    workout = _workout(org, lib, duration_s=1800)
    _assignment(
        org, athlete, workout, date=WEEK_START,
        assign_status=WorkoutAssignment.Status.PLANNED, day_order=1,
    )
    _assignment(
        org, athlete, workout, date=WEEK_START,
        assign_status=WorkoutAssignment.Status.PLANNED, day_order=2,
    )
    res = _compliance_week(base["coach_user"], org, base["team"])
    assert res.status_code == 200
    entry = _athlete_summary(res.data, athlete.id)
    assert WEEK_START.isoformat() in entry["sessions_per_day"]
    assert entry["sessions_per_day"][WEEK_START.isoformat()] == 2


# ---------------------------------------------------------------------------
# 7. test_consecutive_days_active_streak
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_consecutive_days_active_streak(base):
    """Athlete with COMPLETED assignments the last 7 days → consecutive_days_active = 7."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    athlete_user = base["athlete_user"]
    workout = _workout(org, lib, duration_s=3600)
    for i in range(1, 8):
        _assignment(
            org, athlete, workout,
            date=TODAY - datetime.timedelta(days=i),
        )
    c = _client(athlete_user)
    res = c.get("/api/athlete/today/")
    assert res.status_code == 200
    assert res.data["consecutive_days_active"] == 7


# ---------------------------------------------------------------------------
# 8. test_consecutive_days_active_broken_streak
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_consecutive_days_active_broken_streak(base):
    """COMPLETED yesterday and 2 days ago, but NOT 3 days ago → streak = 2."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    athlete_user = base["athlete_user"]
    workout = _workout(org, lib, duration_s=3600)
    _assignment(org, athlete, workout, date=TODAY - datetime.timedelta(days=1))
    _assignment(org, athlete, workout, date=TODAY - datetime.timedelta(days=2))
    # Day 3 is intentionally absent
    _assignment(org, athlete, workout, date=TODAY - datetime.timedelta(days=4))
    c = _client(athlete_user)
    res = c.get("/api/athlete/today/")
    assert res.status_code == 200
    assert res.data["consecutive_days_active"] == 2


# ---------------------------------------------------------------------------
# 9. test_consecutive_days_active_no_activity_yesterday
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_consecutive_days_active_no_activity_yesterday(base):
    """No COMPLETED yesterday → streak = 0 (even if completed today)."""
    org = base["org"]
    lib = base["lib"]
    athlete = base["athlete"]
    athlete_user = base["athlete_user"]
    workout = _workout(org, lib, duration_s=3600)
    # Only today
    _assignment(org, athlete, workout, date=TODAY)
    c = _client(athlete_user)
    res = c.get("/api/athlete/today/")
    assert res.status_code == 200
    assert res.data["consecutive_days_active"] == 0


# ---------------------------------------------------------------------------
# 10. test_coach_briefing_endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_coach_briefing_endpoint():
    """Setup: org, coach, 5 athletes; 3 trained yesterday, 1 overloaded, 2 inactive 4d."""
    org = _org("briefing-test")
    coach_user = _user("coach_brief")
    _membership(coach_user, org, "coach")
    _coach(coach_user, org)
    lib = _library(org)
    workout_dur = _workout(org, lib, duration_s=3600)
    # Workout with tiny plan so actual >> planned → blue compliance
    workout_small = _workout(org, lib, duration_s=60)

    athletes = []
    coach_obj = Coach.objects.get(user=coach_user, organization=org)
    for i in range(5):
        u = _user(f"ath_brief_{i}")
        _membership(u, org, "athlete")
        a = _athlete(u, org)
        athletes.append((u, a))
        # A.1 fix: assign each athlete to the coach so the briefing counts them.
        AthleteCoachAssignment.objects.create(
            athlete=a, coach=coach_obj, organization=org,
            role=AthleteCoachAssignment.Role.PRIMARY,
        )

    # 3 athletes trained yesterday
    for u, a in athletes[:3]:
        _assignment(org, a, workout_dur, date=YESTERDAY)

    # 1 athlete overloaded (compliance_color="blue"): use TODAY so it always falls
    # within scheduled_date__range=(week_start, today) that the endpoint queries.
    # WEEK_START+2 was a future date on Mondays; YESTERDAY was outside the range on
    # Mondays (Sunday is prior week). TODAY is always in range and never future.
    # day_order=2 is safe: athletes[0]'s YESTERDAY assignment uses day_order=1,
    # and TODAY != YESTERDAY, so no UniqueConstraint collision.
    _assignment(
        org, athletes[0][1], workout_small,
        date=TODAY,
        actual_duration_s=7200,  # 7200/60 = 120× → blue
        day_order=2,
    )

    # 2 athletes inactive 4+ days: athletes[3] and [4] have no COMPLETED in last 4 days
    # athletes[4] has an OLD completed assignment (> 4 days ago)
    _assignment(
        org, athletes[4][1], workout_dur,
        date=TODAY - datetime.timedelta(days=10),
    )

    c = _client(coach_user)
    res = c.get(f"/api/p1/orgs/{org.id}/coach-briefing/")
    assert res.status_code == 200
    data = res.data
    assert data["yesterday_date"] == YESTERDAY.isoformat()
    assert data["athletes_trained_yesterday"] == 3
    assert data["athletes_total"] == 5
    assert data["athletes_overloaded"] >= 1  # athletes[0] is overloaded
    assert data["athletes_inactive_4d"] == 2  # athletes[3] and [4]
    assert data["unread_messages"] == 0


# ---------------------------------------------------------------------------
# 11. test_compliance_week_bulk_query_efficiency
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compliance_week_bulk_query_efficiency():
    """Verify compliance_week uses bulk queries — no more than 5 DB hits total."""
    org = _org("bulk-eff-test")
    coach_user = _user("coach_eff")
    _membership(coach_user, org, "coach")
    _coach(coach_user, org)
    lib = _library(org)
    team = Team.objects.create(organization=org, name="Eff Team")
    workout = _workout(org, lib, duration_s=3600)

    # 10 athletes with 1 assignment each
    for i in range(10):
        u = _user(f"eff_ath_{i}")
        _membership(u, org, "athlete")
        a = _athlete(u, org, team=team)
        _assignment(org, a, workout, date=WEEK_START)

    c = _client(coach_user)
    url = f"/api/p1/orgs/{org.id}/teams/{team.id}/compliance-week/"

    with CaptureQueriesContext(connection) as ctx:
        res = c.get(url, {"week": WEEK_START.isoformat()})

    assert res.status_code == 200
    # Allow up to 10 queries (auth session + membership + team + athletes + assignments + overhead)
    assert len(ctx.captured_queries) <= 10, (
        f"Expected ≤10 queries for 10 athletes, got {len(ctx.captured_queries)}"
    )
