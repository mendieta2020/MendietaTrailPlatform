"""
core/tests_p1_workout_tenancy.py

PR-133: Tenancy isolation sweep for P1 Workout ViewSets (Law 1 — fail-closed).

ViewSets covered:
  1. WorkoutLibraryViewSet
  2. PlannedWorkoutViewSet
  3. WorkoutBlockViewSet
  4. WorkoutIntervalViewSet
  5. WorkoutAssignmentViewSet

Test categories per ViewSet (7 each = 35 total):
  1. cross_org_list_403          — org_B member → GET list of org_A → 403
  2. cross_org_detail_403_or_404 — org_B member → GET detail of org_A resource → 403|404
  3. cross_org_write_403         — org_B member → POST/PATCH on org_A → 403|404
  4. unauthenticated_401         — no credentials → 401
  5. no_membership_403           — authenticated user with no Membership anywhere → 403
  6. inactive_membership_403     — user with is_active=False Membership → 403
  7. cross_org_fk_injection_400  — authenticated org_A member POSTs invalid/cross-org
                                    FK payload → 400 (serializer rejects it)

WorkoutAssignment (category 7) carries HIGH injection risk because athlete_id
and planned_workout_id querysets are scoped to context["organization"] by the
serializer. An org_B athlete FK must be rejected before any record is created.

All usernames are prefixed with "tw_" to avoid collisions with other test data.
Each test is isolated per transaction rollback via @pytest.mark.django_db.
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
    WorkoutBlock,
    WorkoutInterval,
    WorkoutLibrary,
)

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


def _library(org, name="tw_Lib Alpha"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _planned_workout(org, library, name="tw_Workout Alpha"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
    )


def _workout_block(org, workout, order_index=1):
    return WorkoutBlock.objects.create(
        organization=org,
        planned_workout=workout,
        order_index=order_index,
    )


def _workout_interval(org, block, order_index=1):
    return WorkoutInterval.objects.create(
        organization=org,
        block=block,
        order_index=order_index,
    )


def _workout_assignment(org, athlete, planned_workout, assigned_by):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=datetime.date(2026, 3, 16),
        assigned_by=assigned_by,
        snapshot_version=1,
    )


def _url(org_id, path):
    return f"/api/p1/orgs/{org_id}/{path}"


# ==============================================================================
# 1. WorkoutLibraryViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestWorkoutLibraryViewSetTenancy:
    """
    Tenancy isolation for WorkoutLibraryViewSet.

    URL: /api/p1/orgs/<org_id>/libraries/  and  /api/p1/orgs/<org_id>/libraries/<pk>/
    organization is resolved from the URL; resolve_membership() is called in
    initial() — fail-closed for any missing or inactive Membership.

    Role rules: coach/owner full CRUD; athlete read-only (public only).
    """

    def setup_method(self):
        self.client = APIClient()

        # org_A: target organization
        self.org_a = _org("tw_lib_a")
        # org_B: adversary organization
        self.org_b = _org("tw_lib_b")

        # org_A actors
        self.owner_a = _user("tw_l_owner_a")
        self.coach_a_user = _user("tw_l_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.lib_a = _library(self.org_a, "tw_Lib Alpha")

        # org_B adversary
        self.coach_b_user = _user("tw_l_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        # Edge-case users
        self.no_membership_user = _user("tw_l_nomembership")
        self.inactive_user = _user("tw_l_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "libraries/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"libraries/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach has no active membership in org_A → list returns 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach targeting org_A library detail → 403 (denied before queryset)."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.lib_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing to org_A libraries → 403 (no membership)."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"name": "tw_Injected Lib"})
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
        org_A owner POSTs a WorkoutLibrary without the required `name` field → 400.

        WorkoutLibrarySerializer does not expose organization as a writable field
        (it is URL-injected). The boundary test verifies that the serializer
        enforces its required-field contract and rejects incomplete payloads
        before any record is persisted.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(self._list(), {})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 2. PlannedWorkoutViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestPlannedWorkoutViewSetTenancy:
    """
    Tenancy isolation for PlannedWorkoutViewSet.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/
         /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<pk>/

    Tenancy is doubly enforced: resolve_membership() gates on org, then
    initial() validates the library belongs to self.organization (fail-closed 404).
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tw_pw_a")
        self.org_b = _org("tw_pw_b")

        # org_A actors
        self.owner_a = _user("tw_pw_owner_a")
        self.coach_a_user = _user("tw_pw_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.lib_a = _library(self.org_a, "tw_PW Lib A")
        self.workout_a = _planned_workout(self.org_a, self.lib_a, "tw_Workout Alpha")

        # org_B adversary
        self.coach_b_user = _user("tw_pw_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        # Edge-case users
        self.no_membership_user = _user("tw_pw_nomembership")
        self.inactive_user = _user("tw_pw_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, f"libraries/{self.lib_a.id}/workouts/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"libraries/{self.lib_a.id}/workouts/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A library workouts list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A planned workout → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.workout_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST new workout to org_A library → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"name": "tw_Injected Workout", "discipline": "run"})
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
        org_A owner POSTs a PlannedWorkout without required fields → 400.

        PlannedWorkoutWriteSerializer requires `name` and `discipline` (both
        are non-nullable, non-blank, no default). An empty body must be rejected
        by the serializer before any database write occurs.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(self._list(), {})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 3. WorkoutBlockViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestWorkoutBlockViewSetTenancy:
    """
    Tenancy isolation for WorkoutBlockViewSet.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/blocks/
         /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/blocks/<pk>/

    initial() validates the full ancestor chain (library → workout) before
    operating. resolve_membership() gates on org first — fail-closed at the
    organization boundary.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tw_blk_a")
        self.org_b = _org("tw_blk_b")

        # org_A actors
        self.owner_a = _user("tw_blk_owner_a")
        self.coach_a_user = _user("tw_blk_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.lib_a = _library(self.org_a, "tw_Blk Lib A")
        self.workout_a = _planned_workout(self.org_a, self.lib_a, "tw_Blk Workout A")
        self.block_a = _workout_block(self.org_a, self.workout_a, order_index=1)

        # org_B adversary
        self.coach_b_user = _user("tw_blk_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        # Edge-case users
        self.no_membership_user = _user("tw_blk_nomembership")
        self.inactive_user = _user("tw_blk_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(
            self.org_a.id,
            f"libraries/{self.lib_a.id}/workouts/{self.workout_a.id}/blocks/",
        )

    def _detail(self, pk):
        return _url(
            self.org_a.id,
            f"libraries/{self.lib_a.id}/workouts/{self.workout_a.id}/blocks/{pk}/",
        )

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A workout blocks list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A workout block → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.block_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST new block to org_A workout → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"order_index": 2})
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
        org_A owner POSTs a WorkoutBlock with an invalid block_type choice → 400.

        WorkoutBlockSerializer validates block_type against BlockType.choices.
        Sending an unrecognised value must be rejected by the serializer before
        any database write occurs, confirming that enum validation is enforced
        at the API boundary.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(self._list(), {"block_type": "INVALID_BLOCK_TYPE", "order_index": 99})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 4. WorkoutIntervalViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestWorkoutIntervalViewSetTenancy:
    """
    Tenancy isolation for WorkoutIntervalViewSet.

    URL: /api/p1/orgs/<org_id>/libraries/<library_id>/workouts/<workout_id>/
         blocks/<block_id>/intervals/
         .../intervals/<pk>/

    initial() validates the full ancestor chain (library → workout → block).
    resolve_membership() gates on org first — fail-closed at the organization
    boundary.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tw_ivl_a")
        self.org_b = _org("tw_ivl_b")

        # org_A actors
        self.owner_a = _user("tw_ivl_owner_a")
        self.coach_a_user = _user("tw_ivl_coach_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        self.lib_a = _library(self.org_a, "tw_Ivl Lib A")
        self.workout_a = _planned_workout(self.org_a, self.lib_a, "tw_Ivl Workout A")
        self.block_a = _workout_block(self.org_a, self.workout_a, order_index=1)
        self.interval_a = _workout_interval(self.org_a, self.block_a, order_index=1)

        # org_B adversary
        self.coach_b_user = _user("tw_ivl_coach_b")
        _membership(self.coach_b_user, self.org_b, "coach")

        # Edge-case users
        self.no_membership_user = _user("tw_ivl_nomembership")
        self.inactive_user = _user("tw_ivl_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(
            self.org_a.id,
            (
                f"libraries/{self.lib_a.id}/workouts/{self.workout_a.id}/"
                f"blocks/{self.block_a.id}/intervals/"
            ),
        )

    def _detail(self, pk):
        return _url(
            self.org_a.id,
            (
                f"libraries/{self.lib_a.id}/workouts/{self.workout_a.id}/"
                f"blocks/{self.block_a.id}/intervals/{pk}/"
            ),
        )

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A block intervals list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A interval → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.interval_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST new interval to org_A block → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(self._list(), {"order_index": 2})
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
        org_A owner POSTs a WorkoutInterval with an invalid metric_type choice → 400.

        WorkoutIntervalSerializer validates metric_type against MetricType.choices.
        Sending an unrecognised value must be rejected before any database write
        occurs, confirming that enum validation is enforced at the API boundary.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {"metric_type": "INVALID_METRIC_TYPE", "order_index": 99},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 5. WorkoutAssignmentViewSet — Tenancy Isolation (HIGH FK injection risk)
# ==============================================================================


@pytest.mark.django_db
class TestWorkoutAssignmentViewSetTenancy:
    """
    Tenancy isolation for WorkoutAssignmentViewSet.

    URL: /api/p1/orgs/<org_id>/assignments/
         /api/p1/orgs/<org_id>/assignments/<pk>/

    HIGH FK injection risk: WorkoutAssignmentSerializer scopes the
    athlete_id and planned_workout_id querysets to context["organization"].
    Any FK from org_B injected into an org_A endpoint must be rejected with
    400 before any record is created — the queryset gate is the last defense.

    Role rules:
    - coach/owner: list all, retrieve any, create, update any.
    - athlete: list own only, retrieve own only, partial_update own (restricted
      fields). Cannot create assignments.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("tw_asgn_a")
        self.org_b = _org("tw_asgn_b")

        # org_A actors — full setup for create/write tests
        self.owner_a = _user("tw_as_owner_a")
        self.coach_a_user = _user("tw_as_coach_a")
        self.athlete_a_user = _user("tw_as_athlete_a")
        _membership(self.owner_a, self.org_a, "owner")
        _membership(self.coach_a_user, self.org_a, "coach")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.coach_a = _coach(self.coach_a_user, self.org_a)
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)

        # org_A workout fixtures — required for assignment FK
        self.lib_a = _library(self.org_a, "tw_Asgn Lib A")
        self.workout_a = _planned_workout(self.org_a, self.lib_a, "tw_Asgn Workout A")

        # org_A pre-existing assignment for retrieve/detail tests
        self.assignment_a = _workout_assignment(
            self.org_a, self.athlete_a, self.workout_a, self.owner_a
        )

        # org_B adversary — full setup so we can inject their FKs
        self.owner_b = _user("tw_as_owner_b")
        self.coach_b_user = _user("tw_as_coach_b")
        self.athlete_b_user = _user("tw_as_athlete_b")
        _membership(self.owner_b, self.org_b, "owner")
        _membership(self.coach_b_user, self.org_b, "coach")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.coach_b = _coach(self.coach_b_user, self.org_b)
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)

        # Edge-case users
        self.no_membership_user = _user("tw_as_nomembership")
        self.inactive_user = _user("tw_as_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "assignments/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"assignments/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach → GET org_A assignments list → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach → GET detail of org_A assignment → 403 or 404."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.get(self._detail(self.assignment_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach → POST to org_A assignments → 403."""
        self.client.force_authenticate(self.coach_b_user)
        r = self.client.post(
            self._list(),
            {
                "athlete_id": self.athlete_a.id,
                "planned_workout_id": self.workout_a.id,
                "scheduled_date": "2026-03-17",
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
        org_A owner POSTs a WorkoutAssignment with athlete_id from org_B → 400.

        WorkoutAssignmentSerializer.__init__ restricts the athlete_id queryset to
        Athlete.objects.filter(organization=context["organization"]). athlete_b
        belongs to org_B and is therefore outside the org_A queryset — DRF raises
        "Invalid pk — object does not exist" → 400 before any record is created.

        This is the primary high-risk injection vector: a malicious actor in org_A
        must never be able to create an assignment that references an athlete from
        a different organization.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {
                "athlete_id": self.athlete_b.id,  # org_B athlete — must be rejected
                "planned_workout_id": self.workout_a.id,
                "scheduled_date": "2026-03-18",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
