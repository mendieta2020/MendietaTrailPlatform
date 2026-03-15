"""
core/tests_p1_assignment_filters.py

PR-132: WorkoutAssignment query param filters + planned_workout_title.

Coverage:
  1. test_list_assignments_filter_by_athlete_id
  2. test_list_assignments_filter_by_date_range
  3. test_list_assignments_filter_combined
  4. test_list_assignments_no_filter_returns_all
  5. test_list_assignments_athlete_ignores_athlete_id_param
  6. test_planned_workout_title_in_response
  7. test_planned_workout_title_null_safe
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
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
from core.serializers_p1 import WorkoutAssignmentSerializer

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


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _library(org, name="Lib"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _planned_workout(org, library, name="Workout A"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
        session_type="base",
        estimated_duration_seconds=3600,
        estimated_distance_meters=10000,
    )


def _assignment(org, athlete, planned_workout, scheduled_date, **kwargs):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
        day_order=kwargs.pop("day_order", 1),
        **kwargs,
    )


def _url(org_id):
    return f"/api/p1/orgs/{org_id}/assignments/"


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ==============================================================================
# Tests
# ==============================================================================


@pytest.mark.django_db
class TestWorkoutAssignmentFilters:

    def setup_method(self):
        self.org = _org("filterorg")

        self.coach_user = _user("af_coach")
        self.athlete_user_1 = _user("af_athlete1")
        self.athlete_user_2 = _user("af_athlete2")

        _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user_1, self.org, "athlete")
        _membership(self.athlete_user_2, self.org, "athlete")

        self.coach = _coach(self.coach_user, self.org)
        self.athlete1 = _athlete(self.athlete_user_1, self.org)
        self.athlete2 = _athlete(self.athlete_user_2, self.org)

        self.lib = _library(self.org)
        self.pw = _planned_workout(self.org, self.lib, name="Tempo Run")

        # Assignment set:
        # athlete1: 2026-04-01, 2026-04-03
        # athlete2: 2026-04-02, 2026-04-10
        self.a1_apr01 = _assignment(
            self.org, self.athlete1, self.pw, datetime.date(2026, 4, 1)
        )
        self.a1_apr03 = _assignment(
            self.org, self.athlete1, self.pw, datetime.date(2026, 4, 3), day_order=2
        )
        self.a2_apr02 = _assignment(
            self.org, self.athlete2, self.pw, datetime.date(2026, 4, 2), day_order=1
        )
        self.a2_apr10 = _assignment(
            self.org, self.athlete2, self.pw, datetime.date(2026, 4, 10), day_order=2
        )

    # ------------------------------------------------------------------
    # 1. Filter by athlete_id (coach)
    # ------------------------------------------------------------------

    def test_list_assignments_filter_by_athlete_id(self):
        client = _authed_client(self.coach_user)
        resp = client.get(
            _url(self.org.pk), {"athlete_id": self.athlete1.pk}
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        ids = {r["id"] for r in results}
        assert ids == {self.a1_apr01.pk, self.a1_apr03.pk}

    # ------------------------------------------------------------------
    # 2. Filter by date range (coach)
    # ------------------------------------------------------------------

    def test_list_assignments_filter_by_date_range(self):
        client = _authed_client(self.coach_user)
        resp = client.get(
            _url(self.org.pk),
            {"date_from": "2026-04-02", "date_to": "2026-04-03"},
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        ids = {r["id"] for r in results}
        # 2026-04-02 (athlete2) and 2026-04-03 (athlete1) only
        assert ids == {self.a1_apr03.pk, self.a2_apr02.pk}

    # ------------------------------------------------------------------
    # 3. Combined: athlete_id + date range (coach)
    # ------------------------------------------------------------------

    def test_list_assignments_filter_combined(self):
        client = _authed_client(self.coach_user)
        resp = client.get(
            _url(self.org.pk),
            {
                "athlete_id": self.athlete1.pk,
                "date_from": "2026-04-02",
                "date_to": "2026-04-30",
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        ids = {r["id"] for r in results}
        # athlete1 in range Apr 02–30 → only 2026-04-03
        assert ids == {self.a1_apr03.pk}

    # ------------------------------------------------------------------
    # 4. No filter returns all (coach)
    # ------------------------------------------------------------------

    def test_list_assignments_no_filter_returns_all(self):
        client = _authed_client(self.coach_user)
        resp = client.get(_url(self.org.pk))
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        ids = {r["id"] for r in results}
        assert ids == {
            self.a1_apr01.pk,
            self.a1_apr03.pk,
            self.a2_apr02.pk,
            self.a2_apr10.pk,
        }

    # ------------------------------------------------------------------
    # 5. Athlete ignores athlete_id param (sees only own)
    # ------------------------------------------------------------------

    def test_list_assignments_athlete_ignores_athlete_id_param(self):
        client = _authed_client(self.athlete_user_1)
        # athlete1 passes athlete2's id — must be ignored, still sees own only
        resp = client.get(
            _url(self.org.pk), {"athlete_id": self.athlete2.pk}
        )
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        ids = {r["id"] for r in results}
        # Only athlete1's assignments
        assert ids == {self.a1_apr01.pk, self.a1_apr03.pk}

    # ------------------------------------------------------------------
    # 6. planned_workout_title appears in GET response
    # ------------------------------------------------------------------

    def test_planned_workout_title_in_response(self):
        client = _authed_client(self.coach_user)
        resp = client.get(_url(self.org.pk))
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        assert len(results) > 0
        for record in results:
            assert "planned_workout_title" in record
            assert record["planned_workout_title"] == "Tempo Run"

    # ------------------------------------------------------------------
    # 7. planned_workout_title returns None when planned_workout is None
    #    (Python-level null safety; DB schema does not allow null FK)
    # ------------------------------------------------------------------

    def test_planned_workout_title_null_safe(self):
        # Test the SerializerMethodField directly with a minimal stub that
        # has planned_workout_id=None — mirrors the defensive code path
        # without requiring a full DB-backed instance.
        class _Stub:
            planned_workout_id = None

        result = WorkoutAssignmentSerializer.get_planned_workout_title(
            None, _Stub()
        )
        assert result is None
