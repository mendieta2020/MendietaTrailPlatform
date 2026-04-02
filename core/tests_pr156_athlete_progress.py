"""
core/tests_pr156_athlete_progress.py

PR-156: Athlete self-serve progress endpoints.

Coverage:
  1. goals_returns_own_goals_sorted_by_date
  2. goals_tenancy_isolation — athlete sees only own goals, not another org's
  3. goals_days_remaining_calculated
  4. weekly_summary_compliance_pct
  5. weekly_summary_streak_calculation
  6. readiness_recommendation_text_matches_score
"""
import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    AthleteGoal,
    Membership,
    Organization,
    WorkoutAssignment,
    WorkoutLibrary,
    PlannedWorkout,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _goal(athlete, org, title, days_from_now, priority="A"):
    target = datetime.date.today() + datetime.timedelta(days=days_from_now)
    return AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        title=title,
        priority=priority,
        status=AthleteGoal.Status.ACTIVE,
        target_date=target,
    )


def _library(org, name="Lib"):
    return WorkoutLibrary.objects.create(
        organization=org,
        name=name,
    )


def _planned(org, lib):
    return PlannedWorkout.objects.create(
        organization=org,
        library=lib,
        name="Run",
        discipline="run",
        estimated_duration_seconds=3600,
    )


def _assignment(org, athlete, planned, date_, status):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned,
        scheduled_date=date_,
        status=status,
    )


# ---------------------------------------------------------------------------
# Test 1: goals returns own goals sorted by date
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_goals_returns_own_goals_sorted_by_date():
    org = _org("testorg1")
    user = _user("ath1")
    _membership(user, org, Membership.Role.ATHLETE)
    athlete = _athlete(user, org)

    _goal(athlete, org, "Race B", 60, priority="B")
    _goal(athlete, org, "Race A", 10, priority="A")

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/athlete/goals/")

    assert res.status_code == 200
    goals = res.data["goals"]
    assert len(goals) == 2
    # Sorted by date ascending — Race A (10 days) first
    assert goals[0]["name"] == "Race A"
    assert goals[1]["name"] == "Race B"


# ---------------------------------------------------------------------------
# Test 2: tenancy isolation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_goals_tenancy_isolation():
    org1 = _org("org-a")
    org2 = _org("org-b")

    user1 = _user("ath-a")
    user2 = _user("ath-b")
    _membership(user1, org1, Membership.Role.ATHLETE)
    _membership(user2, org2, Membership.Role.ATHLETE)
    athlete1 = _athlete(user1, org1)
    athlete2 = _athlete(user2, org2)

    _goal(athlete1, org1, "My Race", 30, priority="A")
    _goal(athlete2, org2, "Other Race", 30, priority="A")

    client = APIClient()
    client.force_authenticate(user=user1)
    res = client.get("/api/athlete/goals/")

    assert res.status_code == 200
    goals = res.data["goals"]
    assert len(goals) == 1
    assert goals[0]["name"] == "My Race"


# ---------------------------------------------------------------------------
# Test 3: days_remaining calculation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_goals_days_remaining_calculated():
    org = _org("org-days")
    user = _user("ath-days")
    _membership(user, org, Membership.Role.ATHLETE)
    athlete = _athlete(user, org)

    _goal(athlete, org, "Soon Race", 7, priority="A")

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/athlete/goals/")

    assert res.status_code == 200
    goal = res.data["goals"][0]
    assert goal["days_remaining"] == 7


# ---------------------------------------------------------------------------
# Test 4: weekly_summary compliance pct
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_weekly_summary_compliance_pct():
    org = _org("org-week")
    user = _user("ath-week")
    _membership(user, org, Membership.Role.ATHLETE)
    athlete = _athlete(user, org)

    lib = _library(org)
    planned = _planned(org, lib)

    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())

    # Create 4 planned assignments this week (3 completed, 1 pending)
    for i in range(3):
        _assignment(org, athlete, planned, week_start + datetime.timedelta(days=i),
                    WorkoutAssignment.Status.COMPLETED)
    _assignment(org, athlete, planned, week_start + datetime.timedelta(days=3),
                WorkoutAssignment.Status.PLANNED)

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/athlete/weekly-summary/")

    assert res.status_code == 200
    data = res.data
    assert data["planned_sessions"] == 4
    assert data["completed_sessions"] == 3
    assert data["compliance_pct"] == 75


# ---------------------------------------------------------------------------
# Test 5: streak calculation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_weekly_summary_streak():
    org = _org("org-streak")
    user = _user("ath-streak")
    _membership(user, org, Membership.Role.ATHLETE)
    athlete = _athlete(user, org)

    lib = _library(org)
    planned = _planned(org, lib)

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # 3 consecutive completed days ending yesterday
    for i in range(1, 4):
        day = today - datetime.timedelta(days=i)
        _assignment(org, athlete, planned, day, WorkoutAssignment.Status.COMPLETED)

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/athlete/weekly-summary/")

    assert res.status_code == 200
    assert res.data["streak_days"] == 3


# ---------------------------------------------------------------------------
# Test 6: readiness_recommendation matches score range
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_readiness_recommendation_matches_score():
    """
    _compute_readiness returns the correct recommendation text based on score.
    We test the logic directly rather than via the full PMC endpoint.
    """
    from core.views_pmc import _compute_readiness

    org = _org("org-read")
    user = _user("ath-read")

    # No Athlete or WellnessCheckIn → score is derived purely from TSB
    # TSB = +30 → load_score = 100 → wellness_score = 50 (neutral) → score = 75
    score, label, rec = _compute_readiness(user, org, 30.0)
    assert score >= 75
    assert "fuerte" in rec.lower() or "aprovechá" in rec.lower()

    # TSB = -30 → load_score = 0 → score = 25 (neutral wellness)
    score2, label2, rec2 = _compute_readiness(user, org, -30.0)
    assert score2 < 50
    assert len(rec2) > 0
