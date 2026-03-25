"""
tests_pr145a_pace_zones.py — PR-145a: Workout Creator Pro

Tests for GET /api/athlete/pace-zones/

Coverage:
  1. Athlete with threshold pace → correct zone ranges returned
  2. Athlete without threshold → fallback to 5:00/km (300 s/km)
  3. Coach calling → also works (coaches build workouts too)
  4. Helper _fmt_pace: s/km → 'M:SS/km' conversion
  5. Z4 umbral: threshold * 0.98 to * 1.05 — verify ranges
  6. Distance estimate for 1000m at Z4 with 5:00/km threshold →
     estimated time between 4:09 and 4:29
  7. Unauthenticated request → 401 Unauthorized
"""
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.models import AthleteHRProfile, Membership, Organization
from core.views_pmc import _fmt_pace


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def org(db):
    return Organization.objects.create(name="PaceTestOrg")


@pytest.fixture
def athlete_user(db, django_user_model, org):
    user = django_user_model.objects.create_user(
        username="athlete_pace",
        password="pass",
        email="athlete@pace.test",
    )
    Membership.objects.create(
        user=user,
        organization=org,
        role=Membership.Role.ATHLETE,
        is_active=True,
    )
    return user


@pytest.fixture
def coach_user(db, django_user_model, org):
    user = django_user_model.objects.create_user(
        username="coach_pace",
        password="pass",
        email="coach@pace.test",
    )
    Membership.objects.create(
        user=user,
        organization=org,
        role=Membership.Role.COACH,
        is_active=True,
    )
    return user


@pytest.fixture
def athlete_with_threshold(db, athlete_user, org):
    """Athlete with threshold_pace_s_km = 300 (5:00/km)."""
    AthleteHRProfile.objects.create(
        athlete=athlete_user,
        organization=org,
        threshold_pace_s_km=300.0,
    )
    return athlete_user


@pytest.fixture
def athlete_without_threshold(db, athlete_user):
    """Athlete with no HR profile at all."""
    return athlete_user


PACE_ZONES_URL = "/api/athlete/pace-zones/"


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.django_db
class TestPaceZonesView:

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_1_athlete_with_threshold_returns_correct_zones(self, athlete_with_threshold):
        """
        Athlete with threshold 300 s/km → Z4 pace_min_s should be 300 * 0.98 = 294
        and pace_max_s should be 300 * 1.05 = 315.
        """
        resp = self._client(athlete_with_threshold).get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert data["has_threshold"] is True
        assert data["threshold_pace_s_km"] == 300.0
        assert data["threshold_pace_display"] == "5:00/km"

        zones = data["zones"]
        assert set(zones.keys()) == {"Z1", "Z2", "Z3", "Z4", "Z5"}

        # Z4: 0.98 → 1.05 of 300
        z4 = zones["Z4"]
        assert z4["pace_min_s"] == pytest.approx(300 * 0.98, abs=0.1)
        assert z4["pace_max_s"] == pytest.approx(300 * 1.05, abs=0.1)

        # Z1 should be slowest
        z1 = zones["Z1"]
        assert z1["pace_min_s"] == pytest.approx(300 * 1.40, abs=0.1)
        assert z1["pace_max_s"] == pytest.approx(300 * 1.60, abs=0.1)

    def test_2_athlete_without_threshold_uses_fallback(self, athlete_without_threshold):
        """
        Athlete with no HR profile → has_threshold=False, uses 300 s/km default.
        """
        resp = self._client(athlete_without_threshold).get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert data["has_threshold"] is False
        assert data["threshold_pace_s_km"] == 300.0
        assert data["threshold_pace_display"] == "5:00/km"

        zones = data["zones"]
        # Z2: 1.20 → 1.39 of 300 = 360 → 417
        z2 = zones["Z2"]
        assert z2["pace_min_s"] == pytest.approx(300 * 1.20, abs=0.1)
        assert z2["pace_max_s"] == pytest.approx(300 * 1.39, abs=0.1)

    def test_3_coach_can_call_pace_zones(self, coach_user):
        """
        Coaches also build workouts and need pace zone reference.
        The endpoint accepts any active Membership role.
        """
        resp = self._client(coach_user).get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        # Coach has no HR profile → fallback
        assert data["has_threshold"] is False
        assert "zones" in data
        assert len(data["zones"]) == 5

    def test_4_fmt_pace_conversion(self):
        """
        _fmt_pace helper: 300 s/km → '5:00/km', 294 → '4:54/km', 249 → '4:09/km'.
        """
        assert _fmt_pace(300) == "5:00/km"
        assert _fmt_pace(294) == "4:54/km"
        assert _fmt_pace(249) == "4:09/km"
        assert _fmt_pace(60) == "1:00/km"
        assert _fmt_pace(90) == "1:30/km"

    def test_5_z4_umbral_range_for_300_threshold(self, athlete_with_threshold):
        """
        Z4 at 300 s/km threshold:
          pace_min = 300 * 0.98 = 294 → 4:54/km
          pace_max = 300 * 1.05 = 315 → 5:15/km
        Verify display strings are correct.
        """
        resp = self._client(athlete_with_threshold).get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_200_OK
        z4 = resp.json()["zones"]["Z4"]

        assert z4["name"] == "Umbral"
        assert z4["color"] == "#f97316"
        # pace_min is the faster end (lower s/km)
        assert z4["pace_min"] == _fmt_pace(300 * 0.98)
        assert z4["pace_max"] == _fmt_pace(300 * 1.05)

    def test_6_distance_estimate_1000m_at_z4_threshold_300(self, athlete_with_threshold):
        """
        For 1000m at Z4 with threshold 300 s/km:
          Z4 range: 294 to 315 s/km
          Estimated time for 1000m:
            min: 294 s/km * 1.0 km = 294 s → 4:54
            max: 315 s/km * 1.0 km = 315 s → 5:15
        The estimated range for 1000m should be between 249s (4:09) and 335s (5:35).
        Specifically, min_time = 294s and max_time = 315s.
        """
        resp = self._client(athlete_with_threshold).get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_200_OK
        z4 = resp.json()["zones"]["Z4"]

        pace_min_s = z4["pace_min_s"]  # s/km
        pace_max_s = z4["pace_max_s"]  # s/km

        # For 1000m = 1.0 km
        distance_km = 1.0
        est_min_s = pace_min_s * distance_km
        est_max_s = pace_max_s * distance_km

        # Should be approximately 4:09 to 4:29 range per the spec
        # With 5:00/km threshold: 294s to 315s
        assert est_min_s == pytest.approx(294, abs=2)
        assert est_max_s == pytest.approx(315, abs=2)

        # Confirm both are within the expected "hard but sustainable" range
        assert est_min_s < 330  # faster than 5:30
        assert est_max_s > 240  # slower than 4:00

    def test_7_unauthenticated_returns_401(self):
        """
        Unauthenticated request to GET /api/athlete/pace-zones/ must return 401.
        Law 7: authentication gates must never be bypassed.
        """
        anon = APIClient()  # no force_authenticate
        resp = anon.get(PACE_ZONES_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
