"""
core/tests_pr145g_coach_drawer.py

Tests for PR-145g: coach_comment endpoint on WorkoutAssignment.

Coverage:
- Coach can add a comment → 200, persisted, coach_commented_at set
- Empty comment clears coach_commented_at → null
- Athlete receives 403 on coach-comment endpoint
- coach_comment and coach_commented_at visible in assignment list serializer
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (mirrors tests_workout_assignment_api.py conventions)
# ---------------------------------------------------------------------------

def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _make_coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _make_library(org, name="Default Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _make_planned_workout(org, library, name="Test Workout"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
        session_type="base",
    )


def _make_assignment(org, athlete, planned_workout):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=datetime.date(2026, 4, 1),
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class CoachCommentTests(TestCase):

    def setUp(self):
        self.org = _make_org("Test Org 145g")
        self.lib = _make_library(self.org)

        # Coach
        self.coach_user = _make_user("coach_145g")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete
        self.athlete_user = _make_user("athlete_145g")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Planned workout + assignment
        self.pw = _make_planned_workout(self.org, self.lib)
        self.assignment = _make_assignment(self.org, self.athlete, self.pw)

        self.url = (
            f"/api/p1/orgs/{self.org.id}/assignments/{self.assignment.id}/coach-comment/"
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    # ── Test 1: Coach can add a comment ────────────────────────────────────

    def test_add_coach_comment_success(self):
        client = self._client(self.coach_user)
        res = client.patch(self.url, {"coach_comment": "Excelente trabajo!"}, format="json")
        self.assertEqual(res.status_code, 200)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_comment, "Excelente trabajo!")
        self.assertIsNotNone(self.assignment.coach_commented_at)

    # ── Test 2: Empty comment clears timestamp ─────────────────────────────

    def test_add_coach_comment_clears_timestamp_when_empty(self):
        # Pre-set a comment
        self.assignment.coach_comment = "Old comment"
        self.assignment.save()

        client = self._client(self.coach_user)
        res = client.patch(self.url, {"coach_comment": ""}, format="json")
        self.assertEqual(res.status_code, 200)

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_comment, "")
        self.assertIsNone(self.assignment.coach_commented_at)

    # ── Test 3: Athlete cannot add coach comment ───────────────────────────

    def test_athlete_cannot_add_coach_comment(self):
        client = self._client(self.athlete_user)
        res = client.patch(self.url, {"coach_comment": "Intento!"}, format="json")
        self.assertEqual(res.status_code, 403)

    # ── Test 4: Fields visible in assignment list ──────────────────────────

    def test_coach_comment_visible_in_assignment_serializer(self):
        # Pre-set comment on assignment
        self.assignment.coach_comment = "Buen ritmo"
        self.assignment.save()

        client = self._client(self.coach_user)
        list_url = f"/api/p1/orgs/{self.org.id}/assignments/?athlete_id={self.athlete.id}"
        res = client.get(list_url)
        self.assertEqual(res.status_code, 200)

        results = res.data.get("results", res.data)
        self.assertTrue(len(results) > 0)
        first = results[0]
        self.assertIn("coach_comment", first)
        self.assertIn("coach_commented_at", first)
        self.assertEqual(first["coach_comment"], "Buen ritmo")
