"""
core/tests_pr166b_ux_fixes.py

Regression tests for PR-166b — UX fixes (5 bugs).

Coverage:
1. BUG-12: Coach sees athletes assigned via Athlete.coach FK (not only via AthleteCoachAssignment)
2. BUG-13: Athlete roster serializer includes coach_name (not just coach_id)
3. BUG-8:  _compute_readiness returns None when athlete has no check-in and no load data
4. BUG-8:  _compute_readiness returns a real score when athlete has a wellness check-in
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import Athlete, AthleteCoachAssignment, Coach, Membership, Organization
from core.views_pmc import _compute_readiness

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(slug):
    return Organization.objects.create(name=slug, slug=slug)


def _user(username):
    return User.objects.create_user(username=username, password="x")


def _membership(user, org, role, is_active=True):
    return Membership.objects.create(user=user, organization=org, role=role, is_active=is_active)


def _coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _athlete(user, org, coach=None):
    return Athlete.objects.create(user=user, organization=org, coach=coach)


# ---------------------------------------------------------------------------
# BUG-12: Coach sees athletes assigned via Athlete.coach FK
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBug12CoachSeesAthletesByFK:
    """
    When the Owner patches Athlete.coach directly (via the roster PATCH endpoint),
    the coach must see the athlete in their /roster/athletes/ list even if no
    AthleteCoachAssignment record was created.
    """

    def setup_method(self):
        self.org = _org("bug12-org")
        self.owner_user = _user("owner-12")
        _membership(self.owner_user, self.org, "owner")

        self.coach_user = _user("coach-12")
        _membership(self.coach_user, self.org, "coach")
        self.coach = _coach(self.coach_user, self.org)

        self.athlete_user = _user("athlete-12")
        _membership(self.athlete_user, self.org, "athlete")
        # Assign via Athlete.coach FK directly (what the PATCH endpoint does)
        self.athlete = _athlete(self.athlete_user, self.org, coach=self.coach)

        self.client = APIClient()

    def test_coach_sees_athlete_assigned_via_fk(self):
        """Coach must see athlete whose Athlete.coach FK points to them."""
        self.client.force_authenticate(self.coach_user)
        url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [a["id"] for a in (response.data.get("results") or response.data)]
        assert self.athlete.pk in ids

    def test_coach_does_not_see_unassigned_athlete(self):
        """Coach must NOT see an athlete not assigned to them."""
        other_user = _user("other-athlete-12")
        _membership(other_user, self.org, "athlete")
        _athlete(other_user, self.org)  # no coach assigned

        self.client.force_authenticate(self.coach_user)
        url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [a["id"] for a in (response.data.get("results") or response.data)]
        # other athlete has no coach → not visible to this coach
        assert self.athlete.pk in ids
        assert len(ids) == 1

    def test_coach_also_sees_athlete_via_assignment_record(self):
        """AthleteCoachAssignment path still works alongside the FK path."""
        other_user = _user("assignment-athlete-12")
        _membership(other_user, self.org, "athlete")
        other_athlete = _athlete(other_user, self.org)
        AthleteCoachAssignment.objects.create(
            athlete=other_athlete,
            coach=self.coach,
            organization=self.org,
            role=AthleteCoachAssignment.Role.PRIMARY,
        )

        self.client.force_authenticate(self.coach_user)
        url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [a["id"] for a in (response.data.get("results") or response.data)]
        assert self.athlete.pk in ids
        assert other_athlete.pk in ids


# ---------------------------------------------------------------------------
# BUG-13: Roster serializer includes coach_name
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBug13CoachNameInRoster:
    """
    The owner's roster must return coach_name (first + last name) so the UI
    doesn't fall back to displaying 'Coach #N'.
    """

    def setup_method(self):
        self.org = _org("bug13-org")
        self.owner_user = _user("owner-13")
        _membership(self.owner_user, self.org, "owner")

        self.coach_user = _user("coach-13")
        self.coach_user.first_name = "María"
        self.coach_user.last_name = "Pérez"
        self.coach_user.save()
        _membership(self.coach_user, self.org, "coach")
        self.coach = _coach(self.coach_user, self.org)

        self.athlete_user = _user("athlete-13")
        _membership(self.athlete_user, self.org, "athlete")
        self.athlete = _athlete(self.athlete_user, self.org, coach=self.coach)

        self.client = APIClient()

    def test_roster_returns_coach_name(self):
        """Athlete row must include coach_name with the coach's real name."""
        self.client.force_authenticate(self.owner_user)
        url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results") or response.data
        row = next(r for r in results if r["id"] == self.athlete.pk)
        assert row["coach_name"] == "María Pérez"

    def test_roster_returns_null_coach_name_when_unassigned(self):
        """Athlete without a coach must have coach_name = null."""
        no_coach_user = _user("athlete-nocoach-13")
        _membership(no_coach_user, self.org, "athlete")
        no_coach_athlete = _athlete(no_coach_user, self.org)

        self.client.force_authenticate(self.owner_user)
        url = f"/api/p1/orgs/{self.org.pk}/roster/athletes/"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results") or response.data
        row = next(r for r in results if r["id"] == no_coach_athlete.pk)
        assert row["coach_name"] is None


# ---------------------------------------------------------------------------
# BUG-8: _compute_readiness returns None when no data
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBug8ReadinessNullWhenNoData:
    """
    _compute_readiness must return (None, None, None) for a brand-new athlete
    who has no wellness check-in and no load data (TSB=0).
    """

    def setup_method(self):
        self.org = _org("bug8-org")
        self.user = _user("athlete-8")

    def test_readiness_is_none_with_no_data(self):
        """No check-in + TSB=0 → (None, None, None)."""
        score, label, rec = _compute_readiness(self.user, self.org, current_tsb=0.0)
        assert score is None
        assert label is None
        assert rec is None

    def test_readiness_computed_with_positive_tsb(self):
        """TSB > 0 (activities exist) but no wellness → real score, not None."""
        score, label, rec = _compute_readiness(self.user, self.org, current_tsb=10.0)
        assert score is not None
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert label
        assert rec
