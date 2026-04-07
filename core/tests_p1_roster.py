"""
core/tests_p1_roster.py

PR-129: Roster API tests — CoachViewSet, AthleteRosterViewSet, TeamViewSet,
MembershipViewSet, AthleteCoachAssignmentViewSet.

Coverage groups:
  1. CoachViewSet           (~8 tests)
  2. AthleteRosterViewSet   (~8 tests)
  3. TeamViewSet            (~6 tests)
  4. MembershipViewSet      (~8 tests)
  5. AthleteCoachAssignmentViewSet (~8 tests)

Tenancy rules verified for each group:
- Cross-org request returns 403 (no active membership → deny).
- Cross-org FK (e.g. coach_id from another org) returns 400 at serializer validation.
- organization is never accepted from the request body.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Athlete, AthleteCoachAssignment, Coach, Membership, Organization, Team

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


def _coach(user, org, **kwargs):
    return Coach.objects.create(user=user, organization=org, **kwargs)


def _athlete(user, org, **kwargs):
    return Athlete.objects.create(user=user, organization=org, **kwargs)


def _team(org, name="Team A"):
    return Team.objects.create(organization=org, name=name)


def _assignment(athlete, coach, org, role="primary", assigned_by=None, ended_at=None):
    return AthleteCoachAssignment.objects.create(
        athlete=athlete,
        coach=coach,
        organization=org,
        role=role,
        assigned_by=assigned_by,
        ended_at=ended_at,
    )


def _url(org_id, path):
    return f"/api/p1/orgs/{org_id}/{path}"


# ==============================================================================
# 1. CoachViewSet
# ==============================================================================


@pytest.mark.django_db
class TestCoachViewSet:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("coachorg")
        self.org2 = _org("coachorg2")

        self.owner = _user("co_owner")
        self.coach_user = _user("co_coach")
        self.athlete_user = _user("co_athlete")
        self.outsider = _user("co_outsider")

        _membership(self.owner, self.org, "owner")
        self.coach_membership = _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")
        _membership(self.outsider, self.org2, "owner")

        self.coach = _coach(self.coach_user, self.org)
        self.athlete = _athlete(self.athlete_user, self.org)

    def _list(self):
        return _url(self.org.id, "coaches/")

    def _detail(self, pk):
        return _url(self.org.id, f"coaches/{pk}/")

    def test_owner_can_list_coaches(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert any(c["id"] == self.coach.id for c in results)

    def test_coach_can_list_coaches(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK

    def test_athlete_sees_only_assigned_coaches(self):
        # No active assignment → athlete sees empty list
        self.client.force_authenticate(self.athlete_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert results == []

    def test_athlete_sees_assigned_coach_after_assignment(self):
        _assignment(self.athlete, self.coach, self.org, role="primary")
        self.client.force_authenticate(self.athlete_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert any(c["id"] == self.coach.id for c in results)

    def test_owner_can_create_coach(self):
        new_user = _user("new_coach_x")
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code == status.HTTP_201_CREATED
        assert Coach.objects.filter(user=new_user, organization=self.org).exists()

    def test_coach_cannot_create_coach(self):
        new_user = _user("new_coach_y")
        self.client.force_authenticate(self.coach_user)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_coach_can_patch_own_profile(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.patch(self._detail(self.coach.id), {"bio": "Updated bio"})
        assert r.status_code == status.HTTP_200_OK
        self.coach.refresh_from_db()
        assert self.coach.bio == "Updated bio"

    def test_coach_cannot_patch_other_coach(self):
        other_user = _user("other_coach_z")
        _membership(other_user, self.org, "coach")
        other_coach = _coach(other_user, self.org)
        self.client.force_authenticate(self.coach_user)
        r = self.client.patch(self._detail(other_coach.id), {"bio": "Hacked"})
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_soft_deletes_coach(self):
        self.client.force_authenticate(self.owner)
        r = self.client.delete(self._detail(self.coach.id))
        assert r.status_code == status.HTTP_204_NO_CONTENT
        self.coach.refresh_from_db()
        assert self.coach.is_active is False

    def test_cross_org_user_gets_403(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get(_url(self.org.id, "coaches/"))
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 2. AthleteRosterViewSet
# ==============================================================================


@pytest.mark.django_db
class TestAthleteRosterViewSet:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("rosterorg")
        self.org2 = _org("rosterorg2")

        self.owner = _user("ro_owner")
        self.coach_user = _user("ro_coach")
        self.athlete_user = _user("ro_athlete")
        self.outsider = _user("ro_outsider")

        _membership(self.owner, self.org, "owner")
        _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")
        _membership(self.outsider, self.org2, "owner")

        self.coach = _coach(self.coach_user, self.org)
        self.athlete = _athlete(self.athlete_user, self.org)
        # Tenancy: coach must be assigned to see the athlete (PR-165e fix)
        AthleteCoachAssignment.objects.create(
            athlete=self.athlete, coach=self.coach, organization=self.org
        )

    def _list(self):
        return _url(self.org.id, "roster/athletes/")

    def _detail(self, pk):
        return _url(self.org.id, f"roster/athletes/{pk}/")

    def test_coach_can_list_athletes(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert any(a["id"] == self.athlete.id for a in results)

    def test_athlete_sees_only_own_record(self):
        other_athlete_user = _user("ro_athlete2")
        _membership(other_athlete_user, self.org, "athlete")
        _athlete(other_athlete_user, self.org)
        self.client.force_authenticate(self.athlete_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert len(results) == 1
        assert results[0]["id"] == self.athlete.id

    def test_owner_can_create_athlete(self):
        new_user = _user("ro_newathlete")
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code == status.HTTP_201_CREATED
        assert Athlete.objects.filter(user=new_user, organization=self.org).exists()

    def test_athlete_cannot_create_athlete(self):
        new_user = _user("ro_newathlete2")
        self.client.force_authenticate(self.athlete_user)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_coach_id_rejected(self):
        org2_coach_user = _user("ro_org2coach")
        _membership(org2_coach_user, self.org2, "coach")
        org2_coach = _coach(org2_coach_user, self.org2)
        self.client.force_authenticate(self.owner)
        r = self.client.patch(self._detail(self.athlete.id), {"coach_id": org2_coach.id})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_athlete_soft_delete(self):
        self.client.force_authenticate(self.owner)
        r = self.client.delete(self._detail(self.athlete.id))
        assert r.status_code == status.HTTP_204_NO_CONTENT
        self.athlete.refresh_from_db()
        assert self.athlete.is_active is False

    def test_owner_can_retrieve_athlete(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(self._detail(self.athlete.id))
        assert r.status_code == status.HTTP_200_OK
        assert r.data["id"] == self.athlete.id

    def test_cross_org_user_gets_403(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get(_url(self.org.id, "roster/athletes/"))
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 3. TeamViewSet
# ==============================================================================


@pytest.mark.django_db
class TestTeamViewSet:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("teamorg")
        self.org2 = _org("teamorg2")

        self.owner = _user("to_owner")
        self.coach_user = _user("to_coach")
        self.athlete_user = _user("to_athlete")
        self.outsider = _user("to_outsider")

        _membership(self.owner, self.org, "owner")
        _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")
        _membership(self.outsider, self.org2, "owner")

        self.team = _team(self.org, "Alpha Team")

    def _list(self):
        return _url(self.org.id, "teams/")

    def _detail(self, pk):
        return _url(self.org.id, f"teams/{pk}/")

    def test_coach_can_list_teams(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert any(t["id"] == self.team.id for t in results)

    def test_athlete_can_list_teams(self):
        self.client.force_authenticate(self.athlete_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK

    def test_owner_can_create_team(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {"name": "Beta Team", "description": ""})
        assert r.status_code == status.HTTP_201_CREATED
        assert Team.objects.filter(name="Beta Team", organization=self.org).exists()

    def test_duplicate_name_rejected(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {"name": "Alpha Team", "description": ""})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_coach_can_update_team(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.patch(self._detail(self.team.id), {"description": "Updated desc"})
        assert r.status_code == status.HTTP_200_OK

    def test_only_owner_can_destroy_team(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.delete(self._detail(self.team.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_soft_deletes_team(self):
        self.client.force_authenticate(self.owner)
        r = self.client.delete(self._detail(self.team.id))
        assert r.status_code == status.HTTP_204_NO_CONTENT
        self.team.refresh_from_db()
        assert self.team.is_active is False

    def test_cross_org_user_gets_403(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get(_url(self.org.id, "teams/"))
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 4. MembershipViewSet
# ==============================================================================


@pytest.mark.django_db
class TestMembershipViewSet:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("memberorg")
        self.org2 = _org("memberorg2")

        self.owner = _user("mo_owner")
        self.coach_user = _user("mo_coach")
        self.athlete_user = _user("mo_athlete")
        self.outsider = _user("mo_outsider")
        self.extra_user = _user("mo_extra")

        self.owner_membership = _membership(self.owner, self.org, "owner")
        self.coach_membership = _membership(self.coach_user, self.org, "coach")
        self.athlete_membership = _membership(self.athlete_user, self.org, "athlete")
        _membership(self.outsider, self.org2, "owner")

    def _list(self):
        return _url(self.org.id, "memberships/")

    def _detail(self, pk):
        return _url(self.org.id, f"memberships/{pk}/")

    def test_owner_can_list_memberships(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        ids = [m["id"] for m in results]
        assert self.owner_membership.id in ids
        assert self.coach_membership.id in ids
        assert self.athlete_membership.id in ids

    def test_athlete_cannot_list_memberships(self):
        self.client.force_authenticate(self.athlete_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_can_create_membership(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {"user_id": self.extra_user.id, "role": "staff"})
        assert r.status_code == status.HTTP_201_CREATED
        assert Membership.objects.filter(user=self.extra_user, organization=self.org).exists()

    def test_coach_cannot_create_membership(self):
        self.client.force_authenticate(self.coach_user)
        r = self.client.post(self._list(), {"user_id": self.extra_user.id, "role": "athlete"})
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_can_update_staff_title(self):
        self.client.force_authenticate(self.owner)
        r = self.client.patch(
            self._detail(self.coach_membership.id), {"staff_title": "Lead Coach"}
        )
        assert r.status_code == status.HTTP_200_OK
        self.coach_membership.refresh_from_db()
        assert self.coach_membership.staff_title == "Lead Coach"

    def test_last_owner_cannot_be_deactivated(self):
        # Only one active owner — deactivating must return 400
        self.client.force_authenticate(self.owner)
        r = self.client.patch(self._detail(self.owner_membership.id), {"is_active": False})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_last_owner_cannot_change_role(self):
        self.client.force_authenticate(self.owner)
        r = self.client.patch(self._detail(self.owner_membership.id), {"role": "coach"})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_second_owner_can_be_demoted_if_another_owner_exists(self):
        second_owner_user = _user("mo_owner2")
        second_membership = _membership(second_owner_user, self.org, "owner")
        self.client.force_authenticate(self.owner)
        r = self.client.patch(self._detail(second_membership.id), {"role": "coach"})
        # Two owners exist → demotion allowed
        assert r.status_code == status.HTTP_200_OK

    def test_cross_org_user_gets_403(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get(_url(self.org.id, "memberships/"))
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 5. AthleteCoachAssignmentViewSet
# ==============================================================================


@pytest.mark.django_db
class TestAthleteCoachAssignmentViewSet:

    def setup_method(self):
        self.client = APIClient()
        self.org = _org("assignorg")
        self.org2 = _org("assignorg2")

        self.owner = _user("as_owner")
        self.coach_user = _user("as_coach")
        self.athlete_user = _user("as_athlete")
        self.outsider = _user("as_outsider")

        _membership(self.owner, self.org, "owner")
        _membership(self.coach_user, self.org, "coach")
        _membership(self.athlete_user, self.org, "athlete")
        _membership(self.outsider, self.org2, "owner")

        self.coach = _coach(self.coach_user, self.org)
        self.athlete = _athlete(self.athlete_user, self.org)

    def _list(self):
        return _url(self.org.id, "coach-assignments/")

    def _detail(self, pk):
        return _url(self.org.id, f"coach-assignments/{pk}/")

    def _end(self, pk):
        return _url(self.org.id, f"coach-assignments/{pk}/end/")

    def test_owner_can_list_assignments(self):
        _assignment(self.athlete, self.coach, self.org, assigned_by=self.owner)
        self.client.force_authenticate(self.owner)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_200_OK
        results = r.data.get("results", r.data)
        assert len(results) == 1

    def test_create_happy_path(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {
            "athlete_id": self.athlete.id,
            "coach_id": self.coach.id,
            "role": "primary",
        })
        assert r.status_code == status.HTTP_201_CREATED
        assert AthleteCoachAssignment.objects.filter(
            athlete=self.athlete,
            coach=self.coach,
            organization=self.org,
            role="primary",
            ended_at__isnull=True,
        ).exists()

    def test_end_assignment_happy_path(self):
        assignment = _assignment(
            self.athlete, self.coach, self.org, role="primary", assigned_by=self.owner
        )
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._end(assignment.id))
        assert r.status_code == status.HTTP_200_OK
        assignment.refresh_from_db()
        assert assignment.ended_at is not None

    def test_duplicate_primary_rejected(self):
        # First active primary assignment
        _assignment(
            self.athlete, self.coach, self.org, role="primary", assigned_by=self.owner
        )
        # Second coach in same org
        other_coach_user = _user("as_coach2")
        _membership(other_coach_user, self.org, "coach")
        other_coach = _coach(other_coach_user, self.org)
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {
            "athlete_id": self.athlete.id,
            "coach_id": other_coach.id,
            "role": "primary",
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_end_already_ended_returns_400(self):
        assignment = _assignment(
            self.athlete,
            self.coach,
            self.org,
            role="assistant",
            assigned_by=self.owner,
            ended_at=timezone.now(),
        )
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._end(assignment.id))
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_athlete_cannot_create_assignment(self):
        self.client.force_authenticate(self.athlete_user)
        r = self.client.post(self._list(), {
            "athlete_id": self.athlete.id,
            "coach_id": self.coach.id,
            "role": "primary",
        })
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_athlete_id_rejected(self):
        # Athlete from org2 should not be usable in org's assignment
        org2_athlete_user = _user("as_org2athlete")
        _membership(org2_athlete_user, self.org2, "athlete")
        org2_athlete = _athlete(org2_athlete_user, self.org2)
        self.client.force_authenticate(self.owner)
        r = self.client.post(self._list(), {
            "athlete_id": org2_athlete.id,
            "coach_id": self.coach.id,
            "role": "primary",
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_assignment(self):
        assignment = _assignment(
            self.athlete, self.coach, self.org, role="assistant", assigned_by=self.owner
        )
        self.client.force_authenticate(self.owner)
        r = self.client.get(self._detail(assignment.id))
        assert r.status_code == status.HTTP_200_OK
        assert r.data["id"] == assignment.id

    def test_cross_org_user_gets_403(self):
        self.client.force_authenticate(self.outsider)
        r = self.client.get(_url(self.org.id, "coach-assignments/"))
        assert r.status_code == status.HTTP_403_FORBIDDEN
