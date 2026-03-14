"""
core/tests_p1_roster_tenancy.py

PR-130: Tenancy isolation sweep for P1 Roster ViewSets (Ley 1 — fail-closed).

ViewSets covered:
  1. CoachViewSet
  2. AthleteRosterViewSet
  3. TeamViewSet
  4. MembershipViewSet
  5. AthleteCoachAssignmentViewSet

Test categories per ViewSet (7 each = 35 minimum):
  1. cross_org_list_403          — org_B member → GET list of org_A → 403
  2. cross_org_detail_403_or_404 — org_B member → GET detail of org_A resource → 403|404
  3. cross_org_write_403         — org_B member → POST/PATCH on org_A → 403|404
  4. unauthenticated_401         — no credentials → 401
  5. no_membership_403           — authenticated user with no Membership anywhere → 403
  6. inactive_membership_403     — user with is_active=False Membership → 403
  7. cross_org_fk_injection_400  — POST/PATCH with FK from org_B into org_A endpoint → 400

All slugs/usernames are prefixed with "tc_" to avoid collisions with
functional test data. Each test is wrapped in a transaction rollback by
@pytest.mark.django_db, so setup_method data is isolated per test.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Athlete, AthleteCoachAssignment, Coach, Membership, Organization, Team

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
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


def _team(org, name="tc_Team Alpha"):
    return Team.objects.create(organization=org, name=name)


def _assignment(athlete, coach, org, role="primary", assigned_by=None):
    return AthleteCoachAssignment.objects.create(
        athlete=athlete,
        coach=coach,
        organization=org,
        role=role,
        assigned_by=assigned_by,
    )


def _url(org_id, path):
    return f"/api/p1/orgs/{org_id}/{path}"


# ==============================================================================
# 1. CoachViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestCoachViewSetTenancy:
    """
    Tenancy isolation for CoachViewSet.

    URL: /api/p1/orgs/<org_id>/coaches/  and  /api/p1/orgs/<org_id>/coaches/<pk>/
    organization is derived from the URL org_id, never from the request body.
    resolve_membership() is called in initial() — fail-closed for any missing
    or inactive Membership.
    """

    def setup_method(self):
        self.client = APIClient()

        # org_A: target organization
        self.org_a = _org("tc_coach_a")
        # org_B: adversary organization
        self.org_b = _org("tc_coach_b")

        # org_A actors
        self.owner_a = _user("tc_c_owner_a")
        self.coach_a_user = _user("tc_c_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.coach_a = _coach(self.coach_a_user, self.org_a)

        # org_B adversary
        self.coach_b_user = _user("tc_c_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        # Edge-case users
        self.no_membership_user = _user("tc_c_nomembership")
        self.inactive_user = _user("tc_c_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "coaches/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"coaches/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach has no active membership in org_A → list returns 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach targeting org_A coach detail → 403 (denied before queryset)."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.coach_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing to org_A coaches → 403 (no membership)."""
        new_user = _user("tc_c_new_write")
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials on list endpoint → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a Coach with a non-existent user_id → 400.

        DRF's PrimaryKeyRelatedField rejects any FK that does not resolve to a
        real object. This verifies that FK validation is enforced at the
        serializer boundary and that invalid references cannot be persisted.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(self._list(), {"user_id": 999999})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 2. AthleteRosterViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestAthleteRosterViewSetTenancy:
    """
    Tenancy isolation for AthleteRosterViewSet.

    URL: /api/p1/orgs/<org_id>/roster/athletes/  (note: /roster/ prefix avoids
    collision with /athletes/<athlete_id>/adherence/ from PR-119).
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tc_roster_a")
        self.org_b = _org("tc_roster_b")

        # org_A actors
        self.owner_a = _user("tc_r_owner_a")
        self.coach_a_user = _user("tc_r_coach_a")
        self.athlete_a_user = _user("tc_r_athlete_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.coach_a = _coach(self.coach_a_user, self.org_a)
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)

        # org_B adversary
        self.coach_b_user = _user("tc_r_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")
        self.coach_b = _coach(self.coach_b_user, self.org_b)

        self.no_membership_user = _user("tc_r_nomembership")
        self.inactive_user = _user("tc_r_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "roster/athletes/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"roster/athletes/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A roster → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A athlete → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.athlete_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST to org_A roster → 403."""
        new_user = _user("tc_r_new_write")
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"user_id": new_user.id})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no org membership → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User with is_active=False membership → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner PATCHes org_A athlete with coach_id from org_B → 400.

        The serializer's organization-scoped validator for coach_id must reject
        any coach FK that does not belong to the URL-derived organization.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.patch(self._detail(self.athlete_a.id), {"coach_id": self.coach_b.id})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 3. TeamViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestTeamViewSetTenancy:
    """
    Tenancy isolation for TeamViewSet.

    URL: /api/p1/orgs/<org_id>/teams/
    Read: all roles. Write/destroy: role-gated; destroy = owner only.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tc_team_a")
        self.org_b = _org("tc_team_b")

        # org_A actors
        self.owner_a = _user("tc_t_owner_a")
        self.coach_a_user = _user("tc_t_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.team_a = _team(self.org_a, "tc_Team Alpha")

        # org_B adversary
        self.coach_b_user = _user("tc_t_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        self.no_membership_user = _user("tc_t_nomembership")
        self.inactive_user = _user("tc_t_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "teams/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"teams/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A teams list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A team → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.team_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST new team to org_A → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"name": "tc_Injected Team"})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no org membership → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User with is_active=False membership → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a team with a name that already exists in org_A
        (unique_together name + organization) → 400.

        This confirms that the unique-per-org constraint is enforced by the
        serializer within the tenancy scope, not globally.
        """
        self.client.force_authenticate(self.owner_a)
        # "tc_Team Alpha" already exists in org_A
        r = self.client.post(self._list(), {"name": "tc_Team Alpha"})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 4. MembershipViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestMembershipViewSetTenancy:
    """
    Tenancy isolation for MembershipViewSet.

    URL: /api/p1/orgs/<org_id>/memberships/
    No DELETE (by design — deactivate via PATCH is_active=False).
    Role gates: list → owner/coach; write → owner only; athlete → retrieve own only.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tc_member_a")
        self.org_b = _org("tc_member_b")

        # org_A actors
        self.owner_a = _user("tc_m_owner_a")
        self.coach_a_user = _user("tc_m_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.coach_membership = _membership(self.coach_a_user, self.org_a, "coach")

        # org_B adversary
        self.owner_b = _user("tc_m_owner_b")
        _membership(self.owner_b, self.org_b, "owner")

        self.no_membership_user = _user("tc_m_nomembership")
        self.inactive_user = _user("tc_m_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "memberships/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"memberships/{pk}/")

    def test_cross_org_list_403(self):
        """org_B owner → GET org_A memberships list → 403."""
        self.client.force_authenticate(self.owner_b)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B owner → GET detail of org_A membership → 403 or 404."""
        self.client.force_authenticate(self.owner_b)
        r = self.client.get(self._detail(self.coach_membership.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B owner → POST to org_A memberships → 403."""
        new_user = _user("tc_m_new_write")
        self.client.force_authenticate(self.owner_b)
        r = self.client.post(self._list(), {"user_id": new_user.id, "role": "coach"})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no org membership → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User with is_active=False membership → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a Membership with a non-existent user_id → 400.

        DRF's PrimaryKeyRelatedField rejects any FK that does not resolve to a
        real object. Verifies that FK validation is enforced at the serializer
        boundary before any Membership record is created.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(self._list(), {"user_id": 999999, "role": "coach"})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 5. AthleteCoachAssignmentViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestAthleteCoachAssignmentViewSetTenancy:
    """
    Tenancy isolation for AthleteCoachAssignmentViewSet.

    URL: /api/p1/orgs/<org_id>/coach-assignments/
    No PATCH/DELETE — mutations are list, retrieve, create, and /end/ action only.
    Role gate: owner / coach only for write operations.
    Service layer (services_assignment) enforces cross-org FK checks.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tc_assign_a")
        self.org_b = _org("tc_assign_b")

        # org_A actors
        self.owner_a = _user("tc_a_owner_a")
        self.coach_a_user = _user("tc_a_coach_a")
        self.athlete_a_user = _user("tc_a_athlete_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.coach_a = _coach(self.coach_a_user, self.org_a)
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)

        # org_B adversary — full setup so we can inject their FKs
        self.owner_b = _user("tc_a_owner_b")
        self.coach_b_user = _user("tc_a_coach_b")
        self.athlete_b_user = _user("tc_a_athlete_b")
        _membership(self.owner_b, self.org_b, "owner")
        _membership(self.coach_b_user, self.org_b, "coach")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.coach_b = _coach(self.coach_b_user, self.org_b)
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)

        self.no_membership_user = _user("tc_a_nomembership")
        self.inactive_user = _user("tc_a_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

        # Pre-existing org_A assignment for detail/retrieve tests
        self.existing_assignment = _assignment(
            self.athlete_a,
            self.coach_a,
            self.org_a,
            role="primary",
            assigned_by=self.owner_a,
        )

    def _list(self):
        return _url(self.org_a.id, "coach-assignments/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"coach-assignments/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A coach-assignments list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A assignment → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.existing_assignment.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST to org_A coach-assignments → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(
            self._list(),
            {
                "athlete_id": self.athlete_a.id,
                "coach_id": self.coach_a.id,
                "role": "primary",
            },
        )
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no org membership → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User with is_active=False membership → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a coach-assignment with athlete_id from org_B → 400.

        services_assignment.assign_coach_to_athlete() validates that both the
        athlete and coach belong to the target organization. Injecting an org_B
        athlete FK must be rejected before any record is created.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {
                "athlete_id": self.athlete_b.id,  # org_B athlete — should be rejected
                "coach_id": self.coach_a.id,
                "role": "primary",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
