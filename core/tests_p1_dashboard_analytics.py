"""
core/tests_p1_dashboard_analytics.py

PR-149: Tenancy and access tests for DashboardAnalyticsView.

URL: GET /api/p1/orgs/<org_id>/dashboard-analytics/

Tests:
  1. coach_gets_analytics — authenticated coach → 200 with correct keys
  2. cross_org_403 — coach from org_B → org_A endpoint → 403
  3. unauthenticated_401 — no token → 401
  4. athlete_role_403 — athlete membership → 403 (coach-only endpoint)
  5. pmc_series_org_scoped — TSS from org_B is not included in org_A result
"""

import pytest
from django.contrib.auth import get_user_model
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

_URL = "/api/p1/orgs/{org_id}/dashboard-analytics/"


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


def _athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _library(org, name="Lib"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _planned_workout(org, library, planned_tss=80.0):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Test Workout",
        discipline="run",
        planned_tss=planned_tss,
    )


def _assignment(org, athlete, planned_workout, scheduled_date="2026-03-10"):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
    )


def _authed_client(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDashboardAnalyticsView:
    def test_coach_gets_analytics(self):
        """Owner/coach receives 200 with required keys."""
        org = _org("da-org-a")
        coach_user = _user("da-coach-a")
        _membership(coach_user, org, "coach")

        client = _authed_client(coach_user)
        response = client.get(_URL.format(org_id=org.pk))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "active_athletes_count" in data
        assert "pmc_series" in data
        assert isinstance(data["pmc_series"], list)

    def test_pmc_series_contains_date_ctl_atl_tsb(self):
        """Each entry in pmc_series has the required fields."""
        org = _org("da-org-fields")
        coach_user = _user("da-coach-fields")
        _membership(coach_user, org, "owner")

        client = _authed_client(coach_user)
        response = client.get(_URL.format(org_id=org.pk))

        assert response.status_code == status.HTTP_200_OK
        series = response.json()["pmc_series"]
        assert len(series) > 0
        first = series[0]
        assert "date" in first
        assert "ctl" in first
        assert "atl" in first
        assert "tsb" in first

    def test_active_athletes_count_org_scoped(self):
        """active_athletes_count reflects only this org's athletes."""
        org_a = _org("da-org-count-a")
        org_b = _org("da-org-count-b")
        coach_user = _user("da-coach-count")
        _membership(coach_user, org_a, "coach")

        user_a1 = _user("da-ath-a1")
        user_a2 = _user("da-ath-a2")
        user_b1 = _user("da-ath-b1")
        _athlete(user_a1, org_a)
        _athlete(user_a2, org_a)
        _athlete(user_b1, org_b)  # should NOT be counted

        client = _authed_client(coach_user)
        response = client.get(_URL.format(org_id=org_a.pk))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["active_athletes_count"] == 2

    def test_cross_org_403(self):
        """Coach from org_B cannot access org_A dashboard analytics."""
        org_a = _org("da-org-cross-a")
        org_b = _org("da-org-cross-b")
        coach_b = _user("da-coach-cross-b")
        _membership(coach_b, org_b, "coach")

        client = _authed_client(coach_b)
        response = client.get(_URL.format(org_id=org_a.pk))

        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unauthenticated_401(self):
        """No credentials → 401."""
        org = _org("da-org-unauth")
        client = APIClient()
        response = client.get(_URL.format(org_id=org.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_athlete_role_403(self):
        """Athlete membership → 403 (analytics are coach/owner only)."""
        org = _org("da-org-ath-role")
        athlete_user = _user("da-ath-role")
        _membership(athlete_user, org, "athlete")

        client = _authed_client(athlete_user)
        response = client.get(_URL.format(org_id=org.pk))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_pmc_series_org_scoped(self):
        """TSS from org_B WorkoutAssignments must not appear in org_A PMC series."""
        org_a = _org("da-pmc-scope-a")
        org_b = _org("da-pmc-scope-b")
        coach_a = _user("da-pmc-coach-a")
        coach_b = _user("da-pmc-coach-b")
        _membership(coach_a, org_a, "coach")
        _membership(coach_b, org_b, "coach")

        # Create athlete + workout assignment in org_B with high TSS
        ath_b_user = _user("da-pmc-ath-b")
        ath_b = _athlete(ath_b_user, org_b)
        lib_b = _library(org_b, "Lib-B")
        pw_b = _planned_workout(org_b, lib_b, planned_tss=9999.0)
        _assignment(org_b, ath_b, pw_b, scheduled_date="2026-03-17")

        # org_A has no assignments
        client = _authed_client(coach_a)
        response = client.get(_URL.format(org_id=org_a.pk))

        assert response.status_code == status.HTTP_200_OK
        series = response.json()["pmc_series"]
        # All CTL/ATL values should be 0 (no TSS in org_A)
        assert all(entry["ctl"] == 0.0 for entry in series)
        assert all(entry["atl"] == 0.0 for entry in series)
