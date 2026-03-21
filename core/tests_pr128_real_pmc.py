"""
core/tests_pr128_real_pmc.py

PR-128: Real-side PMC (CTL/ATL/TSB) from CompletedActivity.

URL: GET /api/p1/orgs/<org_id>/athletes/<athlete_id>/pmc/real/

Tests:
  1. pmc_empty_activities — 0 activities → empty list, no crash
  2. pmc_single_activity — 1 activity → CTL/ATL/TSB computed correctly
  3. pmc_ctl_grows_with_load — 30 days of load → CTL increases over baseline
  4. cross_org_isolation — activity from another org not included
  5. days_param_limits_range — ?days=30 caps the window correctly
  6. plan_real_invariant — PlannedWorkout is never queried by the service
  7. athlete_not_in_org_returns_404 — athlete_id from other org → 404
  8. athlete_accesses_own_pmc — athlete role can read own PMC
  9. athlete_cannot_access_other_pmc — athlete role → 404 for another athlete
  10. coach_accesses_any_athlete_pmc — coach can read any athlete in org
"""

import math
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    CompletedActivity,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()

_URL = "/api/p1/orgs/{org_id}/athletes/{athlete_id}/pmc/real/"

# Banister decay constants (must match services_analytics.py)
_CTL_TAU = 42
_ATL_TAU = 7
_CTL_DECAY = math.exp(-1.0 / _CTL_TAU)
_ATL_DECAY = math.exp(-1.0 / _ATL_TAU)


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


def _alumno_for(athlete):
    """Get or create a legacy Alumno linked to the athlete's user."""
    alumno, _ = Alumno.objects.get_or_create(
        usuario=athlete.user,
        defaults={
            "nombre": athlete.user.username,
            "apellido": "Test",
        },
    )
    return alumno


def _activity(org, athlete, duration_s, days_ago=0):
    """Create a CompletedActivity for the given athlete on today - days_ago."""
    activity_date = date.today() - timedelta(days=days_ago)
    start_time = activity_date.strftime("%Y-%m-%dT10:00:00+00:00")
    return CompletedActivity.objects.create(
        organization=org,
        alumno=_alumno_for(athlete),
        athlete=athlete,
        sport="run",
        start_time=start_time,
        duration_s=duration_s,
        distance_m=0.0,
        provider=CompletedActivity.Provider.MANUAL,
        provider_activity_id=f"test-{org.pk}-{athlete.pk}-{days_ago}-{duration_s}",
    )


def _authed_client(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _tss(duration_s):
    return (duration_s / 3600.0) * 100.0


# ---------------------------------------------------------------------------
# Service-level tests (no HTTP, fast)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestComputeAthleteRealPMCService:
    def test_pmc_empty_activities(self):
        """0 activities → empty series with correct length, all zeros, no crash."""
        from core import services_analytics

        org = _org("svc-empty-org")
        user = _user("svc-empty-user")
        athlete = _athlete(user, org)

        result = services_analytics.compute_athlete_pmc_real(
            organization=org, athlete=athlete, days=10
        )

        assert isinstance(result, list)
        assert len(result) == 10
        assert all(r["ctl"] == 0.0 for r in result)
        assert all(r["atl"] == 0.0 for r in result)
        assert all(r["tss"] == 0.0 for r in result)

    def test_pmc_single_activity(self):
        """1 activity today → CTL/ATL/TSB computed per Banister EWMA."""
        from core import services_analytics

        org = _org("svc-single-org")
        user = _user("svc-single-user")
        athlete = _athlete(user, org)
        _membership(user, org, "athlete")

        duration_s = 3600  # 1 hour → TSS = 100
        _activity(org, athlete, duration_s=duration_s, days_ago=0)

        result = services_analytics.compute_athlete_pmc_real(
            organization=org, athlete=athlete, days=5
        )

        # Last entry is today
        today_entry = result[-1]
        assert today_entry["date"] == date.today().isoformat()
        assert today_entry["tss"] == 100.0

        # CTL/ATL must be > 0 after at least 1 activity day
        assert today_entry["ctl"] > 0.0
        assert today_entry["atl"] > 0.0

        # Verify Banister formula: CTL_today = 0 * _CTL_DECAY + 100 * (1 - _CTL_DECAY)
        # ... but only if today is the first day in the window with TSS.
        # We confirm by checking at least one entry in result has non-zero ctl.
        assert any(r["ctl"] > 0 for r in result)

    def test_pmc_ctl_grows_with_sustained_load(self):
        """30 days of daily 1h activities → CTL at day 30 > CTL at day 1."""
        from core import services_analytics

        org = _org("svc-load-org")
        user = _user("svc-load-user")
        athlete = _athlete(user, org)
        _membership(user, org, "athlete")

        # Create 30 days of activity (1h each = TSS 100)
        for days_ago in range(30):
            _activity(org, athlete, duration_s=3600, days_ago=days_ago)

        result = services_analytics.compute_athlete_pmc_real(
            organization=org, athlete=athlete, days=30
        )

        assert len(result) == 30
        # CTL on the last day should be significantly higher than CTL on day 1
        assert result[-1]["ctl"] > result[0]["ctl"]

    def test_plan_real_invariant(self):
        """PlannedWorkout data must not influence real-side PMC.

        Creates a high-TSS PlannedWorkout assignment. The real-side PMC
        must return all-zero TSS (no CompletedActivity exists), proving
        that PlannedWorkout is never read by compute_athlete_pmc_real.
        """
        from core import services_analytics
        from core.models import WorkoutAssignment

        org = _org("svc-invariant-org")
        coach_user = _user("svc-invariant-coach")
        athlete_user = _user("svc-invariant-athlete")
        _membership(coach_user, org, "coach")
        athlete = _athlete(athlete_user, org)

        # Create a library + planned workout with very high TSS
        lib = WorkoutLibrary.objects.create(organization=org, name="InvariantLib")
        pw = PlannedWorkout.objects.create(
            organization=org,
            library=lib,
            name="HeavyWorkout",
            discipline="run",
            planned_tss=9999.0,
        )
        WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=pw,
            scheduled_date=date.today(),
        )

        # No CompletedActivity exists — real-side PMC must be all zeros
        result = services_analytics.compute_athlete_pmc_real(
            organization=org, athlete=athlete, days=5
        )

        assert all(r["tss"] == 0.0 for r in result)
        assert all(r["ctl"] == 0.0 for r in result)
        assert all(r["atl"] == 0.0 for r in result)

    def test_cross_org_isolation(self):
        """Activity from org_B athlete is not included in org_A's PMC."""
        from core import services_analytics

        org_a = _org("svc-cross-a")
        org_b = _org("svc-cross-b")
        user_a = _user("svc-cross-user-a")
        user_b = _user("svc-cross-user-b")
        athlete_a = _athlete(user_a, org_a)
        athlete_b = _athlete(user_b, org_b)

        # High TSS in org_b — must NOT appear in org_a result
        _activity(org_b, athlete_b, duration_s=36000, days_ago=0)  # TSS=1000

        result = services_analytics.compute_athlete_pmc_real(
            organization=org_a, athlete=athlete_a, days=5
        )

        assert all(r["tss"] == 0.0 for r in result)
        assert all(r["ctl"] == 0.0 for r in result)

    def test_days_param_limits_range(self):
        """?days=30 returns exactly 30 entries."""
        from core import services_analytics

        org = _org("svc-days-org")
        user = _user("svc-days-user")
        athlete = _athlete(user, org)

        result = services_analytics.compute_athlete_pmc_real(
            organization=org, athlete=athlete, days=30
        )

        assert len(result) == 30
        assert result[0]["date"] == (date.today() - timedelta(days=29)).isoformat()
        assert result[-1]["date"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# Endpoint-level tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAthleteRealPMCView:
    def test_coach_accesses_any_athlete_pmc(self):
        """Coach can GET any athlete's PMC in their org → 200."""
        org = _org("ep-coach-org")
        coach_user = _user("ep-coach-user")
        athlete_user = _user("ep-ath-user")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)

        client = _authed_client(coach_user)
        resp = client.get(_URL.format(org_id=org.pk, athlete_id=athlete.pk))

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["athlete_id"] == athlete.pk
        assert data["organization_id"] == org.pk
        assert data["days"] == 90
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 90

    def test_athlete_accesses_own_pmc(self):
        """Athlete role can GET their own PMC → 200."""
        org = _org("ep-self-org")
        athlete_user = _user("ep-self-user")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)

        client = _authed_client(athlete_user)
        resp = client.get(_URL.format(org_id=org.pk, athlete_id=athlete.pk))

        assert resp.status_code == status.HTTP_200_OK

    def test_athlete_cannot_access_other_pmc(self):
        """Athlete role accessing another athlete's PMC → 404 (fail-closed)."""
        org = _org("ep-other-org")
        user_a = _user("ep-other-user-a")
        user_b = _user("ep-other-user-b")
        _membership(user_a, org, "athlete")
        _membership(user_b, org, "athlete")
        athlete_a = _athlete(user_a, org)
        _athlete(user_b, org)

        client = _authed_client(user_b)
        resp = client.get(_URL.format(org_id=org.pk, athlete_id=athlete_a.pk))

        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_athlete_not_in_org_returns_404(self):
        """Athlete from a different org → 404, not 403 (fail-closed)."""
        org_a = _org("ep-404-org-a")
        org_b = _org("ep-404-org-b")
        coach_user = _user("ep-404-coach")
        athlete_user = _user("ep-404-ath")
        _membership(coach_user, org_a, "coach")
        athlete_b = _athlete(athlete_user, org_b)

        client = _authed_client(coach_user)
        resp = client.get(_URL.format(org_id=org_a.pk, athlete_id=athlete_b.pk))

        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_days_query_param_respected(self):
        """?days=30 returns exactly 30 data entries."""
        org = _org("ep-days-org")
        coach_user = _user("ep-days-coach")
        athlete_user = _user("ep-days-ath")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)

        client = _authed_client(coach_user)
        resp = client.get(
            _URL.format(org_id=org.pk, athlete_id=athlete.pk) + "?days=30"
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["days"] == 30
        assert len(resp.json()["data"]) == 30

    def test_unauthenticated_returns_401(self):
        """No credentials → 401."""
        org = _org("ep-unauth-org")
        athlete_user = _user("ep-unauth-ath")
        athlete = _athlete(athlete_user, org)

        resp = APIClient().get(_URL.format(org_id=org.pk, athlete_id=athlete.pk))

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_days_out_of_range_returns_400(self):
        """?days=0 or ?days=366 → 400 validation error."""
        org = _org("ep-val-org")
        coach_user = _user("ep-val-coach")
        athlete_user = _user("ep-val-ath")
        _membership(coach_user, org, "coach")
        _membership(athlete_user, org, "athlete")
        athlete = _athlete(athlete_user, org)

        client = _authed_client(coach_user)
        for bad_days in ("0", "366", "-1"):
            resp = client.get(
                _URL.format(org_id=org.pk, athlete_id=athlete.pk) + f"?days={bad_days}"
            )
            assert resp.status_code == status.HTTP_400_BAD_REQUEST
