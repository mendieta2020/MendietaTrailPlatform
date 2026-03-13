"""
core/tests_p1_workout_library.py

PR-128a: WorkoutLibrary + PlannedWorkout CRUD API tests.

Groups:
  1 — WorkoutLibrary CRUD (6 tests)
  2 — PlannedWorkout CRUD (7 tests)
  3 — Tenancy isolation (3 tests)

Tenancy rules verified:
- organization is always derived from the URL (org_id).
- Coaches cannot read or write resources owned by another org.
- Unauthenticated requests are rejected with 401.
- Athletes can only see public libraries and their workouts.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import Membership, Organization, PlannedWorkout, WorkoutLibrary

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(name):
    return Organization.objects.create(name=name, slug=name.lower().replace(" ", "-"))


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _library(org, name="Lib A", is_public=True, created_by=None):
    return WorkoutLibrary.objects.create(
        organization=org, name=name, is_public=is_public, created_by=created_by
    )


def _workout(org, library, name="W1", discipline="run"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline=discipline,
        session_type="base",
    )


def _library_list_url(org_id):
    return f"/api/p1/orgs/{org_id}/libraries/"


def _library_detail_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/libraries/{pk}/"


def _workout_list_url(org_id, library_id):
    return f"/api/p1/orgs/{org_id}/libraries/{library_id}/workouts/"


def _workout_detail_url(org_id, library_id, pk):
    return f"/api/p1/orgs/{org_id}/libraries/{library_id}/workouts/{pk}/"


# ==============================================================================
# Group 1: WorkoutLibrary CRUD
# ==============================================================================

@pytest.mark.django_db
class TestWorkoutLibraryCRUD:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("LibOrg")
        self.coach_user = _user("lib_coach")
        _membership(self.coach_user, self.org, "coach")
        self.athlete_user = _user("lib_athlete")
        _membership(self.athlete_user, self.org, "athlete")

    def test_coach_can_list_libraries(self):
        _library(self.org, "Lib A")
        _library(self.org, "Lib B")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.get(_library_list_url(self.org.pk))
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 2

    def test_coach_can_create_library(self):
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.post(
            _library_list_url(self.org.pk),
            {"name": "Sprint Library", "description": "Speed work", "is_public": True},
        )
        assert r.status_code == 201
        assert r.data["name"] == "Sprint Library"
        assert WorkoutLibrary.objects.filter(
            organization=self.org, name="Sprint Library"
        ).exists()

    def test_coach_can_retrieve_library(self):
        lib = _library(self.org, "Lib A")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.get(_library_detail_url(self.org.pk, lib.pk))
        assert r.status_code == 200
        assert r.data["id"] == lib.pk

    def test_coach_can_update_library(self):
        lib = _library(self.org, "Lib A")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.patch(
            _library_detail_url(self.org.pk, lib.pk),
            {"name": "Lib A Updated"},
        )
        assert r.status_code == 200
        lib.refresh_from_db()
        assert lib.name == "Lib A Updated"

    def test_coach_can_delete_library(self):
        lib = _library(self.org, "Lib A")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.delete(_library_detail_url(self.org.pk, lib.pk))
        assert r.status_code == 204
        assert not WorkoutLibrary.objects.filter(pk=lib.pk).exists()

    def test_athlete_cannot_see_private_library(self):
        _library(self.org, "Private Lib", is_public=False)
        _library(self.org, "Public Lib", is_public=True)
        self.client.force_authenticate(user=self.athlete_user)
        r = self.client.get(_library_list_url(self.org.pk))
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 1
        assert results[0]["name"] == "Public Lib"

    def test_athlete_cannot_create_library(self):
        self.client.force_authenticate(user=self.athlete_user)
        r = self.client.post(
            _library_list_url(self.org.pk),
            {"name": "Athlete Lib", "is_public": True},
        )
        assert r.status_code == 403


# ==============================================================================
# Group 2: PlannedWorkout CRUD
# ==============================================================================

@pytest.mark.django_db
class TestPlannedWorkoutCRUD:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("WorkoutOrg")
        self.coach_user = _user("workout_coach")
        _membership(self.coach_user, self.org, "coach")
        self.athlete_user = _user("workout_athlete")
        _membership(self.athlete_user, self.org, "athlete")
        self.library = _library(self.org, "Main Library", is_public=True)

    def _payload(self, **extra):
        data = {"name": "Threshold Run", "discipline": "run", "session_type": "threshold"}
        data.update(extra)
        return data

    def test_coach_can_list_workouts(self):
        _workout(self.org, self.library, "W1")
        _workout(self.org, self.library, "W2")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.get(_workout_list_url(self.org.pk, self.library.pk))
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 2

    def test_coach_can_create_workout(self):
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.post(
            _workout_list_url(self.org.pk, self.library.pk),
            self._payload(),
        )
        assert r.status_code == 201
        assert r.data["name"] == "Threshold Run"
        assert PlannedWorkout.objects.filter(
            organization=self.org, library=self.library, name="Threshold Run"
        ).exists()

    def test_coach_can_retrieve_workout_with_blocks_field(self):
        w = _workout(self.org, self.library, "W1")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.get(_workout_detail_url(self.org.pk, self.library.pk, w.pk))
        assert r.status_code == 200
        assert r.data["id"] == w.pk
        assert "blocks" in r.data
        assert isinstance(r.data["blocks"], list)

    def test_coach_can_update_workout(self):
        w = _workout(self.org, self.library, "W1")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.patch(
            _workout_detail_url(self.org.pk, self.library.pk, w.pk),
            {"name": "Updated W1"},
        )
        assert r.status_code == 200
        w.refresh_from_db()
        assert w.name == "Updated W1"

    def test_coach_can_delete_workout(self):
        w = _workout(self.org, self.library, "W1")
        self.client.force_authenticate(user=self.coach_user)
        r = self.client.delete(_workout_detail_url(self.org.pk, self.library.pk, w.pk))
        assert r.status_code == 204
        assert not PlannedWorkout.objects.filter(pk=w.pk).exists()

    def test_athlete_can_read_workout_in_public_library(self):
        _workout(self.org, self.library, "W1")
        self.client.force_authenticate(user=self.athlete_user)
        r = self.client.get(_workout_list_url(self.org.pk, self.library.pk))
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 1

    def test_athlete_cannot_access_private_library_workouts(self):
        private_lib = _library(self.org, "Private Lib", is_public=False)
        _workout(self.org, private_lib, "Secret W")
        self.client.force_authenticate(user=self.athlete_user)
        r = self.client.get(_workout_list_url(self.org.pk, private_lib.pk))
        assert r.status_code == 404

    def test_athlete_cannot_create_workout(self):
        self.client.force_authenticate(user=self.athlete_user)
        r = self.client.post(
            _workout_list_url(self.org.pk, self.library.pk),
            {"name": "Athlete Workout", "discipline": "run", "session_type": "base"},
        )
        assert r.status_code == 403


# ==============================================================================
# Group 3: Tenancy isolation
# ==============================================================================

@pytest.mark.django_db
class TestTenancyIsolation:

    def setup_method(self):
        self.client = APIClient()
        self.org_a = _org("IsolationOrgA")
        self.org_b = _org("IsolationOrgB")
        self.coach_a = _user("iso_coach_a")
        _membership(self.coach_a, self.org_a, "coach")
        self.coach_b = _user("iso_coach_b")
        _membership(self.coach_b, self.org_b, "coach")

    def test_coach_cannot_access_other_org_library(self):
        lib_b = _library(self.org_b, "Lib B")
        self.client.force_authenticate(user=self.coach_a)
        # Attempt to retrieve org B's library through org A's URL namespace.
        r = self.client.get(_library_detail_url(self.org_a.pk, lib_b.pk))
        assert r.status_code == 404

    def test_coach_cannot_access_other_org_workout(self):
        lib_b = _library(self.org_b, "Lib B")
        w_b = _workout(self.org_b, lib_b, "W-B")
        self.client.force_authenticate(user=self.coach_a)
        r = self.client.get(
            _workout_detail_url(self.org_a.pk, lib_b.pk, w_b.pk)
        )
        assert r.status_code == 404

    def test_unauthenticated_rejected(self):
        r = self.client.get(_library_list_url(self.org_a.pk))
        assert r.status_code == 401
