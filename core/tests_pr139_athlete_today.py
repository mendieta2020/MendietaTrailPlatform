"""
PR-139 — Athlete Today endpoint tests.
Covers: GET /api/athlete/today/
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()
URL = "/api/athlete/today/"


def _make_org(name=None):
    slug = uuid.uuid4().hex[:12]
    return Organization.objects.create(name=name or f"Org-{slug}", slug=slug)


def _make_user(password="pass1234"):
    email = f"user_{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(username=email, email=email, password=password)


def _make_athlete_setup(org=None):
    """Create user + membership(athlete) + Athlete record. Returns (user, membership, athlete, org)."""
    if org is None:
        org = _make_org()
    user = _make_user()
    membership = Membership.objects.create(
        user=user,
        organization=org,
        role=Membership.Role.ATHLETE,
        is_active=True,
    )
    athlete = Athlete.objects.create(user=user, organization=org, is_active=True)
    return user, membership, athlete, org


def _make_workout(org, library=None):
    """Create a WorkoutLibrary and PlannedWorkout for the org."""
    if library is None:
        library = WorkoutLibrary.objects.create(
            organization=org,
            name=f"Lib-{uuid.uuid4().hex[:6]}",
        )
    pw = PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Series 1000m x 6",
        description="Mantené cadencia >85rpm",
        discipline=PlannedWorkout.Discipline.RUN,
    )
    return pw


def _make_assignment(org, athlete, pw, scheduled_date=None, status_val=WorkoutAssignment.Status.PLANNED):
    if scheduled_date is None:
        scheduled_date = timezone.localdate()
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=pw,
        scheduled_date=scheduled_date,
        status=status_val,
    )


class AthleteTodayUnauthenticatedTest(TestCase):
    def test_unauthenticated_returns_401(self):
        client = APIClient()
        res = client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AthleteTodayRoleGuardTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_coach_role_returns_403(self):
        org = _make_org()
        user = _make_user()
        Membership.objects.create(
            user=user,
            organization=org,
            role=Membership.Role.COACH,
            is_active=True,
        )
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_role_returns_403(self):
        org = _make_org()
        user = _make_user()
        Membership.objects.create(
            user=user,
            organization=org,
            role=Membership.Role.OWNER,
            is_active=True,
        )
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_membership_returns_403(self):
        user = _make_user()
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AthleteTodayNoWorkoutTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_athlete_with_no_workout_today(self):
        user, _, _, _ = _make_athlete_setup()
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_workout"])
        self.assertNotIn("workout", res.data)

    def test_canceled_assignment_not_shown(self):
        user, _, athlete, org = _make_athlete_setup()
        pw = _make_workout(org)
        _make_assignment(org, athlete, pw, status_val=WorkoutAssignment.Status.CANCELED)
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_workout"])

    def test_skipped_assignment_not_shown(self):
        user, _, athlete, org = _make_athlete_setup()
        pw = _make_workout(org)
        _make_assignment(org, athlete, pw, status_val=WorkoutAssignment.Status.SKIPPED)
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_workout"])


class AthleteTodayWithWorkoutTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_athlete_with_planned_workout_today(self):
        user, _, athlete, org = _make_athlete_setup()
        pw = _make_workout(org)
        _make_assignment(org, athlete, pw)
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_workout"])
        w = res.data["workout"]
        self.assertEqual(w["title"], pw.name)
        self.assertEqual(w["date"], str(timezone.localdate()))

    def test_moved_assignment_is_shown(self):
        user, _, athlete, org = _make_athlete_setup()
        pw = _make_workout(org)
        _make_assignment(org, athlete, pw, status_val=WorkoutAssignment.Status.MOVED)
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_workout"])

    def test_workout_returns_correct_fields(self):
        user, _, athlete, org = _make_athlete_setup()
        pw = _make_workout(org)
        _make_assignment(org, athlete, pw)
        self.client.force_authenticate(user=user)
        res = self.client.get(URL)
        self.assertIn("title", res.data["workout"])
        self.assertIn("description", res.data["workout"])
        self.assertIn("date", res.data["workout"])


class AthleteTodayTenancyTest(TestCase):
    """Athlete in org A must not see a workout belonging to org B."""

    def setUp(self):
        self.client = APIClient()

    def test_cross_org_isolation(self):
        # Org A athlete with no workout
        user_a, _, _, org_a = _make_athlete_setup()

        # Org B with a workout
        org_b = _make_org("Org B")
        _, _, athlete_b, _ = _make_athlete_setup(org=org_b)
        pw_b = _make_workout(org_b)
        _make_assignment(org_b, athlete_b, pw_b)

        # Athlete A should not see Org B's workout
        self.client.force_authenticate(user=user_a)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_workout"])
