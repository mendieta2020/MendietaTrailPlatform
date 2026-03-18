"""
core/tests_p1_bulk_team.py

PR-145: Tests for bulk team workout assignment.

Covers:
  1. Service: bulk_assign_team_workout — happy path, idempotency, empty team,
     cross-org planned_workout rejected, cross-org team rejected.
  2. API action: POST bulk-assign-team — coach success, role gate (athlete 403),
     missing fields 400, cross-org team 404, team_id list filter.

All usernames prefixed "bt_" to avoid collisions.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    Membership,
    Organization,
    PlannedWorkout,
    Team,
    WorkoutAssignment,
    WorkoutLibrary,
)
from core.services_workout import bulk_assign_team_workout

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


def _athlete(user, org, team=None):
    return Athlete.objects.create(user=user, organization=org, team=team)


def _library(org, name="bt_Lib"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _planned_workout(org, lib, name="bt_WO"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=lib,
        name=name,
        discipline="run",
        structure_version=1,
    )


DATE = datetime.date(2026, 4, 1)


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBulkAssignTeamWorkoutService:
    def setup_method(self):
        self.org = _org("bt-org-svc")
        self.other_org = _org("bt-org-other")
        self.coach_user = _user("bt_svc_coach")
        self.membership = _membership(self.coach_user, self.org, "coach")
        self.coach = _coach(self.coach_user, self.org)

        self.team = Team.objects.create(organization=self.org, name="bt_Team Alpha")
        self.lib = _library(self.org)
        self.wo = _planned_workout(self.org, self.lib)

        # Three athletes in the team
        self.a1 = _athlete(_user("bt_svc_a1"), self.org, team=self.team)
        self.a2 = _athlete(_user("bt_svc_a2"), self.org, team=self.team)
        self.a3 = _athlete(_user("bt_svc_a3"), self.org, team=self.team)

    def test_creates_assignment_per_team_athlete(self):
        created = bulk_assign_team_workout(
            planned_workout=self.wo,
            team=self.team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        assert len(created) == 3
        athlete_ids = {a.athlete_id for a in created}
        assert athlete_ids == {self.a1.id, self.a2.id, self.a3.id}

    def test_all_assignments_are_org_scoped(self):
        bulk_assign_team_workout(
            planned_workout=self.wo,
            team=self.team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        qs = WorkoutAssignment.objects.filter(organization=self.org, planned_workout=self.wo)
        assert qs.count() == 3
        assert all(a.organization_id == self.org.id for a in qs)

    def test_idempotent_second_call_skips_existing(self):
        bulk_assign_team_workout(
            planned_workout=self.wo,
            team=self.team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        second = bulk_assign_team_workout(
            planned_workout=self.wo,
            team=self.team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        # Second call: no new assignments created
        assert second == []
        assert WorkoutAssignment.objects.filter(
            organization=self.org, planned_workout=self.wo, scheduled_date=DATE
        ).count() == 3

    def test_empty_team_returns_empty_list(self):
        empty_team = Team.objects.create(organization=self.org, name="bt_Empty Team")
        result = bulk_assign_team_workout(
            planned_workout=self.wo,
            team=empty_team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        assert result == []
        assert WorkoutAssignment.objects.filter(
            organization=self.org, planned_workout=self.wo
        ).count() == 0

    def test_cross_org_planned_workout_raises(self):
        other_lib = _library(self.other_org, name="bt_OtherLib")
        other_wo = _planned_workout(self.other_org, other_lib, name="bt_OtherWO")
        with pytest.raises(ValidationError, match="planned_workout does not belong"):
            bulk_assign_team_workout(
                planned_workout=other_wo,
                team=self.team,
                organization=self.org,
                scheduled_date=DATE,
                assigned_by=self.coach_user,
            )

    def test_cross_org_team_raises(self):
        other_team = Team.objects.create(organization=self.other_org, name="bt_OtherTeam")
        with pytest.raises(ValidationError, match="team does not belong"):
            bulk_assign_team_workout(
                planned_workout=self.wo,
                team=other_team,
                organization=self.org,
                scheduled_date=DATE,
                assigned_by=self.coach_user,
            )

    def test_partial_idempotency_only_missing_athletes_created(self):
        # Pre-create assignment for a1 only
        WorkoutAssignment.objects.create(
            organization=self.org,
            athlete=self.a1,
            planned_workout=self.wo,
            scheduled_date=DATE,
            day_order=1,
            snapshot_version=self.wo.structure_version,
        )
        created = bulk_assign_team_workout(
            planned_workout=self.wo,
            team=self.team,
            organization=self.org,
            scheduled_date=DATE,
            assigned_by=self.coach_user,
        )
        # Only a2 and a3 should be created
        assert len(created) == 2
        created_athlete_ids = {a.athlete_id for a in created}
        assert self.a1.id not in created_athlete_ids
        assert {self.a2.id, self.a3.id} == created_athlete_ids


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBulkAssignTeamAction:
    def setup_method(self):
        self.org = _org("bt-org-api")
        self.other_org = _org("bt-org-api-other")

        self.coach_user = _user("bt_api_coach")
        _membership(self.coach_user, self.org, "coach")
        _coach(self.coach_user, self.org)

        self.athlete_user = _user("bt_api_athlete_user")
        self.athlete_member = _membership(self.athlete_user, self.org, "athlete")

        self.team = Team.objects.create(organization=self.org, name="bt_API Team")
        self.lib = _library(self.org)
        self.wo = _planned_workout(self.org, self.lib)

        self.a1 = _athlete(_user("bt_api_a1"), self.org, team=self.team)
        self.a2 = _athlete(_user("bt_api_a2"), self.org, team=self.team)

        self.url = f"/api/p1/orgs/{self.org.id}/assignments/bulk-assign-team/"

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_coach_bulk_assigns_all_team_athletes(self):
        resp = self._client(self.coach_user).post(
            self.url,
            {
                "planned_workout_id": self.wo.id,
                "team_id": self.team.id,
                "scheduled_date": "2026-04-01",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["created"] == 2
        assert len(resp.data["assignments"]) == 2
        assert WorkoutAssignment.objects.filter(
            organization=self.org, planned_workout=self.wo
        ).count() == 2

    def test_athlete_role_is_denied_403(self):
        resp = self._client(self.athlete_user).post(
            self.url,
            {
                "planned_workout_id": self.wo.id,
                "team_id": self.team.id,
                "scheduled_date": "2026-04-01",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_missing_required_fields_returns_400(self):
        resp = self._client(self.coach_user).post(self.url, {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "planned_workout_id" in resp.data
        assert "team_id" in resp.data
        assert "scheduled_date" in resp.data

    def test_invalid_date_returns_400(self):
        resp = self._client(self.coach_user).post(
            self.url,
            {
                "planned_workout_id": self.wo.id,
                "team_id": self.team.id,
                "scheduled_date": "not-a-date",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "scheduled_date" in resp.data

    def test_cross_org_team_returns_404(self):
        other_team = Team.objects.create(organization=self.other_org, name="bt_OtherTeam")
        resp = self._client(self.coach_user).post(
            self.url,
            {
                "planned_workout_id": self.wo.id,
                "team_id": other_team.id,
                "scheduled_date": "2026-04-01",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_org_planned_workout_returns_404(self):
        other_lib = _library(self.other_org, name="bt_OtherLib2")
        other_wo = _planned_workout(self.other_org, other_lib, name="bt_OtherWO2")
        resp = self._client(self.coach_user).post(
            self.url,
            {
                "planned_workout_id": other_wo.id,
                "team_id": self.team.id,
                "scheduled_date": "2026-04-01",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_401(self):
        resp = APIClient().post(
            self.url,
            {
                "planned_workout_id": self.wo.id,
                "team_id": self.team.id,
                "scheduled_date": "2026-04-01",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_second_call_is_idempotent_returns_201_with_zero_created(self):
        payload = {
            "planned_workout_id": self.wo.id,
            "team_id": self.team.id,
            "scheduled_date": "2026-04-01",
        }
        client = self._client(self.coach_user)
        client.post(self.url, payload, format="json")
        resp = client.post(self.url, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["created"] == 0
        # DB still has exactly 2 — no duplicates
        assert WorkoutAssignment.objects.filter(
            organization=self.org, planned_workout=self.wo
        ).count() == 2


# ---------------------------------------------------------------------------
# team_id list filter tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTeamIdListFilter:
    def setup_method(self):
        self.org = _org("bt-org-filter")
        self.coach_user = _user("bt_filter_coach")
        _membership(self.coach_user, self.org, "coach")
        _coach(self.coach_user, self.org)

        self.team_a = Team.objects.create(organization=self.org, name="bt_FilterTeamA")
        self.team_b = Team.objects.create(organization=self.org, name="bt_FilterTeamB")
        self.lib = _library(self.org)
        self.wo = _planned_workout(self.org, self.lib)

        self.athlete_a = _athlete(_user("bt_filter_a1"), self.org, team=self.team_a)
        self.athlete_b = _athlete(_user("bt_filter_b1"), self.org, team=self.team_b)

        date = datetime.date(2026, 4, 2)
        for athlete in [self.athlete_a, self.athlete_b]:
            WorkoutAssignment.objects.create(
                organization=self.org,
                athlete=athlete,
                planned_workout=self.wo,
                scheduled_date=date,
                snapshot_version=self.wo.structure_version,
            )

        self.url = f"/api/p1/orgs/{self.org.id}/assignments/"

    def _client(self):
        c = APIClient()
        c.force_authenticate(user=self.coach_user)
        return c

    def test_team_id_filter_returns_only_team_athletes(self):
        resp = self._client().get(self.url, {"team_id": self.team_a.id})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data.get("results", resp.data)
        assert len(data) == 1
        assert data[0]["athlete_id"] == self.athlete_a.id

    def test_team_id_filter_invalid_value_returns_400(self):
        resp = self._client().get(self.url, {"team_id": "abc"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "team_id" in resp.data
