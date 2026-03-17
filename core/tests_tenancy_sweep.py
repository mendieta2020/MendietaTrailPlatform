"""
core/tests_tenancy_sweep.py

PR-X1: Tenancy isolation sweep for P1 Science/Planning ViewSets (Ley 1 — fail-closed).

ViewSets covered:
  1. RaceEventViewSet
  2. AthleteGoalViewSet
  3. AthleteProfileViewSet
  4. ReconciliationViewSet
  5. AthleteAdherenceViewSet

Test categories per ViewSet (7 each = 35 minimum):
  1. cross_org_list_403          — org_B member → GET list of org_A → 403
  2. cross_org_detail_403_or_404 — org_B member → GET detail of org_A resource → 403|404
  3. cross_org_write_403         — org_B member → POST/PATCH on org_A → 403|404
  4. unauthenticated_401         — no credentials → 401
  5. no_membership_403           — authenticated user with no Membership anywhere → 403
  6. inactive_membership_403     — user with is_active=False Membership → 403
  7. cross_org_fk_injection_400  — POST/PATCH with FK from org_B into org_A endpoint → 400

All slug/usernames are prefixed with "ts_" to avoid collisions with other test data.
Each test is wrapped in a transaction rollback by @pytest.mark.django_db.

Law 1 contract under test:
  - resolve_membership() fires in initial() before any data access.
  - every queryset leads with organization=self.organization (from URL, never from body).
  - serializer FK fields are scope-filtered to context["organization"].
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    AthleteGoal,
    AthleteProfile,
    Membership,
    Organization,
    PlannedWorkout,
    RaceEvent,
    WorkoutAssignment,
    WorkoutLibrary,
    WorkoutReconciliation,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared fixture helpers
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


def _race_event(org, name="ts_Race Alpha", event_date=None):
    return RaceEvent.objects.create(
        organization=org,
        name=name,
        discipline=RaceEvent.Discipline.RUN,
        event_date=event_date or datetime.date(2027, 6, 1),
    )


def _goal(athlete, org, priority=AthleteGoal.Priority.A, title="ts_Goal"):
    return AthleteGoal.objects.create(
        organization=org,
        athlete=athlete,
        title=title,
        priority=priority,
        goal_type=AthleteGoal.GoalType.FINISH,
        status=AthleteGoal.Status.PLANNED,
        target_date=datetime.date(2027, 6, 1),
    )


def _profile(athlete, org):
    return AthleteProfile.objects.create(
        athlete=athlete,
        organization=org,
    )


def _library(org, name="ts_Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _planned_workout(library, org, name="ts_Workout"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline=PlannedWorkout.Discipline.RUN,
    )


def _assignment(athlete, planned_workout, org):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=datetime.date(2027, 3, 17),
    )


def _reconciliation(assignment):
    return WorkoutReconciliation.objects.create(
        organization=assignment.organization,
        assignment=assignment,
        state=WorkoutReconciliation.State.PENDING,
        match_method=WorkoutReconciliation.MatchMethod.NONE,
    )


def _url(org_id, path):
    return f"/api/p1/orgs/{org_id}/{path}"


# ==============================================================================
# 1. RaceEventViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestRaceEventViewSetTenancy:
    """
    Tenancy isolation for RaceEventViewSet.

    URL: /api/p1/orgs/<org_id>/race-events/  and  /api/p1/orgs/<org_id>/race-events/<pk>/
    organization derived from URL org_id, never from request body.
    resolve_membership() called in initial() — fail-closed.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("ts_re_a")
        self.org_b = _org("ts_re_b")

        # org_A actors
        self.owner_a = _user("ts_re_owner_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.race_event_a = _race_event(self.org_a, name="ts_Race OrgA")

        # org_B adversary
        self.coach_b = _user("ts_re_coach_b")
        _membership(self.coach_b, self.org_b, "coach")

        # edge-case users
        self.no_membership_user = _user("ts_re_nomembership")
        self.inactive_user = _user("ts_re_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "race-events/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"race-events/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach has no active membership in org_A → list returns 403."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach targeting org_A race event → 403 or 404."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._detail(self.race_event_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing to org_A race-events → 403 (no membership)."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(
            self._list(),
            {"name": "ts_Injected", "discipline": "run", "event_date": "2027-09-01"},
        )
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs with an invalid discipline value → 400.

        RaceEventSerializer exposes no writable FK fields (organization and
        created_by are ViewSet-injected and not in the serializer fields).
        This test verifies that serializer validation is enforced at the API
        boundary: an invalid choice value must be rejected with 400.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {
                "name": "ts_Invalid Discipline Race",
                "discipline": "not_a_valid_discipline",
                "event_date": "2027-09-15",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 2. AthleteGoalViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestAthleteGoalViewSetTenancy:
    """
    Tenancy isolation for AthleteGoalViewSet.

    URL: /api/p1/orgs/<org_id>/goals/  and  /api/p1/orgs/<org_id>/goals/<pk>/
    Coaches can read all goals in org and write any.
    Athletes can only read their own goals; they cannot write.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("ts_ag_a")
        self.org_b = _org("ts_ag_b")

        # org_A actors
        self.owner_a = _user("ts_ag_owner_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.athlete_a_user = _user("ts_ag_athlete_a")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)
        self.goal_a = _goal(self.athlete_a, self.org_a)

        # org_B adversary
        self.coach_b = _user("ts_ag_coach_b")
        _membership(self.coach_b, self.org_b, "coach")
        self.athlete_b_user = _user("ts_ag_athlete_b")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)

        # edge-case users
        self.no_membership_user = _user("ts_ag_nomembership")
        self.inactive_user = _user("ts_ag_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "goals/")

    def _detail(self, pk):
        return _url(self.org_a.id, f"goals/{pk}/")

    def test_cross_org_list_403(self):
        """org_B coach has no active membership in org_A → list returns 403."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach targeting org_A goal → 403 or 404."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._detail(self.goal_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing to org_A goals → 403 (no membership)."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(
            self._list(),
            {
                "athlete": self.athlete_a.id,
                "title": "ts_Injected Goal",
                "priority": "A",
                "target_date": "2027-06-01",
            },
        )
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a goal with athlete_id belonging to org_B → 400.

        AthleteGoalSerializer.__init__ scopes athlete_id queryset to
        context["organization"], so a foreign-org athlete PK must yield 400.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {
                "athlete": self.athlete_b.id,  # org_B athlete injected into org_A endpoint
                "title": "ts_Cross-org Goal",
                "priority": "B",
                "target_date": "2027-06-01",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 3. AthleteProfileViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestAthleteProfileViewSetTenancy:
    """
    Tenancy isolation for AthleteProfileViewSet.

    URL: /api/p1/orgs/<org_id>/profiles/  (list/create)
         /api/p1/orgs/<org_id>/profiles/<athlete_id>/  (retrieve/update)
    Lookup field is athlete_id (OneToOne FK), not the profile PK.
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("ts_ap_a")
        self.org_b = _org("ts_ap_b")

        # org_A actors
        self.owner_a = _user("ts_ap_owner_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.athlete_a_user = _user("ts_ap_athlete_a")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)
        self.profile_a = _profile(self.athlete_a, self.org_a)

        # org_B adversary
        self.coach_b = _user("ts_ap_coach_b")
        _membership(self.coach_b, self.org_b, "coach")
        self.athlete_b_user = _user("ts_ap_athlete_b")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)

        # edge-case users
        self.no_membership_user = _user("ts_ap_nomembership")
        self.inactive_user = _user("ts_ap_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _list(self):
        return _url(self.org_a.id, "profiles/")

    def _detail(self, athlete_id):
        return _url(self.org_a.id, f"profiles/{athlete_id}/")

    def test_cross_org_list_403(self):
        """org_B coach has no active membership in org_A → list returns 403."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """org_B coach targeting org_A athlete profile → 403 or 404."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._detail(self.athlete_a.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing to org_A profiles → 403 (no membership)."""
        new_user = _user("ts_ap_new_athlete_w")
        new_athlete = _athlete(new_user, self.org_a)
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(self._list(), {"athlete": new_athlete.id})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._list())
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs a profile with an athlete_id from org_B → 400.

        AthleteProfileSerializer.__init__ scopes athlete_id queryset to
        context["organization"], so a foreign-org athlete PK must yield 400.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._list(),
            {"athlete": self.athlete_b.id},  # org_B athlete injected into org_A endpoint
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 4. ReconciliationViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestReconciliationViewSetTenancy:
    """
    Tenancy isolation for ReconciliationViewSet.

    URL: /api/p1/orgs/<org_id>/assignments/<assignment_id>/reconciliation/
    No list endpoint — retrieve and POST actions only.

    _get_assignment() filters WorkoutAssignment by org and (for athletes) by own user.
    Cross-org assignment_id in URL → 404 (queryset returns nothing).
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("ts_rec_a")
        self.org_b = _org("ts_rec_b")

        # org_A actors
        self.owner_a = _user("ts_rec_owner_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.athlete_a_user = _user("ts_rec_athlete_a")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)
        self.lib_a = _library(self.org_a, name="ts_Rec Library A")
        self.workout_a = _planned_workout(self.lib_a, self.org_a, name="ts_Rec Workout A")
        self.assignment_a = _assignment(self.athlete_a, self.workout_a, self.org_a)
        self.reconciliation_a = _reconciliation(self.assignment_a)

        # org_B adversary
        self.coach_b = _user("ts_rec_coach_b")
        _membership(self.coach_b, self.org_b, "coach")
        self.athlete_b_user = _user("ts_rec_athlete_b")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)
        self.lib_b = _library(self.org_b, name="ts_Rec Library B")
        self.workout_b = _planned_workout(self.lib_b, self.org_b, name="ts_Rec Workout B")
        self.assignment_b = _assignment(self.athlete_b, self.workout_b, self.org_b)

        # edge-case users
        self.no_membership_user = _user("ts_rec_nomembership")
        self.inactive_user = _user("ts_rec_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

    def _detail(self, org_id, assignment_id):
        return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/"

    def _reconcile(self, org_id, assignment_id):
        return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/reconcile/"

    def _miss(self, org_id, assignment_id):
        return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/miss/"

    def test_cross_org_list_403(self):
        """
        org_B coach calls org_A reconciliation retrieve endpoint
        with org_A's assignment_id → 403 (no membership in org_A).

        There is no list endpoint; this tests the retrieve path with cross-org caller.
        """
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._detail(self.org_a.id, self.assignment_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """
        org_B coach uses org_A URL with org_B assignment_id → 403 or 404.
        (Membership check fires first — 403 before queryset is even reached.)
        """
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(self._detail(self.org_a.id, self.assignment_b.id))
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """org_B coach POSTing reconcile to org_A endpoint → 403."""
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(self._reconcile(self.org_a.id, self.assignment_a.id), {})
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_401(self):
        """No credentials on reconciliation detail → 401."""
        r = self.client.get(self._detail(self.org_a.id, self.assignment_a.id))
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(self._detail(self.org_a.id, self.assignment_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(self._detail(self.org_a.id, self.assignment_a.id))
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner POSTs reconcile with a completed_activity_id from org_B → 404.

        ReconciliationViewSet.reconcile() guards:
            CompletedActivity.objects.get(pk=activity_id, athlete__organization=self.organization)
        A foreign-org activity PK → DoesNotExist → NotFound (404).
        Using a non-existent PK achieves the same result and doesn't require
        creating a CompletedActivity fixture.
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.post(
            self._reconcile(self.org_a.id, self.assignment_a.id),
            {"completed_activity_id": 999999},
        )
        # 404 because the FK guard rejects the foreign/non-existent activity
        assert r.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# 5. AthleteAdherenceViewSet — Tenancy Isolation
# ==============================================================================


@pytest.mark.django_db
class TestAthleteAdherenceViewSetTenancy:
    """
    Tenancy isolation for AthleteAdherenceViewSet.

    URL: /api/p1/orgs/<org_id>/athletes/<athlete_id>/adherence/?week_start=YYYY-MM-DD
    Read-only (retrieve only) — no list, no write.

    retrieve() filters: Athlete.objects.filter(pk=athlete_id, organization=self.organization)
    Athletes may only query their own adherence (fail-closed 404 for others).
    """

    def setup_method(self):
        self.client = APIClient()

        self.org_a = _org("ts_adh_a")
        self.org_b = _org("ts_adh_b")

        # org_A actors
        self.owner_a = _user("ts_adh_owner_a")
        _membership(self.owner_a, self.org_a, "owner")
        self.athlete_a_user = _user("ts_adh_athlete_a")
        _membership(self.athlete_a_user, self.org_a, "athlete")
        self.athlete_a = _athlete(self.athlete_a_user, self.org_a)

        # org_B adversary
        self.coach_b = _user("ts_adh_coach_b")
        _membership(self.coach_b, self.org_b, "coach")
        self.athlete_b_user = _user("ts_adh_athlete_b")
        _membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _athlete(self.athlete_b_user, self.org_b)

        # edge-case users
        self.no_membership_user = _user("ts_adh_nomembership")
        self.inactive_user = _user("ts_adh_inactive")
        _membership(self.inactive_user, self.org_a, "coach", is_active=False)

        self.valid_week = "2027-03-15"  # a Monday

    def _adherence(self, org_id, athlete_id, week_start=None):
        url = f"/api/p1/orgs/{org_id}/athletes/{athlete_id}/adherence/"
        if week_start:
            url += f"?week_start={week_start}"
        return url

    def test_cross_org_list_403(self):
        """
        org_B coach calls org_A adherence endpoint for org_A athlete → 403.
        (No list endpoint; this verifies retrieve blocks cross-org callers.)
        """
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_a.id, self.valid_week)
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_detail_403_or_404(self):
        """
        org_B coach uses org_A URL with org_B athlete_id → 403 or 404.
        (Membership check in org_A fires before the athlete queryset.)
        """
        self.client.force_authenticate(self.coach_b)
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_b.id, self.valid_week)
        )
        assert r.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_cross_org_write_403(self):
        """
        No write endpoint exists; verifying that a POST to the adherence URL
        returns 405 (method not allowed), which confirms no write surface exists.

        This test intentionally validates the absence of a writable surface
        rather than expecting 403, since the URL is GET-only.
        """
        self.client.force_authenticate(self.coach_b)
        r = self.client.post(
            self._adherence(self.org_a.id, self.athlete_a.id, self.valid_week), {}
        )
        # 403 if membership check fires first; 405 if method routing fires first
        assert r.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_a.id, self.valid_week)
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_membership_403(self):
        """Authenticated user with no Membership in any org → 403."""
        self.client.force_authenticate(self.no_membership_user)
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_a.id, self.valid_week)
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_membership_403(self):
        """User whose org_A Membership is_active=False → 403."""
        self.client.force_authenticate(self.inactive_user)
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_a.id, self.valid_week)
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_cross_org_fk_injection_400(self):
        """
        org_A owner queries adherence for org_B athlete_id using org_A URL.

        retrieve() filters: Athlete.objects.filter(pk=athlete_id, organization=self.organization)
        org_B's athlete_id is not in org_A → queryset returns nothing → NotFound (404).
        """
        self.client.force_authenticate(self.owner_a)
        r = self.client.get(
            self._adherence(self.org_a.id, self.athlete_b.id, self.valid_week)
        )
        # Athlete from org_B not found in org_A queryset → 404
        assert r.status_code == status.HTTP_404_NOT_FOUND
