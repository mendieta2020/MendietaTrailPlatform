"""
core/tests_pr153_gap_ramprate.py

Tests for PR-153: GAP calculation, Ramp Rate, CTL Projection, and enhanced
training-volume endpoint (elevation, GAP per bucket).

8 targeted tests — no migration required (all computed on-the-fly).
"""
import pytest
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Alumno, DailyLoad, Membership, Organization
from core.services_gap import compute_gap, format_pace

User = get_user_model()


# ── Unit tests: GAP service ────────────────────────────────────────────────────

class TestComputeGap:
    def test_flat_terrain_gap_equals_actual_pace(self):
        """On flat terrain (no elevation), GAP should equal actual pace."""
        distance_m = 10_000  # 10 km
        duration_s = 3000    # 300 s/km = 5:00/km
        elevation_gain_m = 0.0
        gap = compute_gap(distance_m, elevation_gain_m, duration_s)
        actual_pace = duration_s / (distance_m / 1000)
        assert gap == pytest.approx(actual_pace, rel=0.01)

    def test_positive_grade_gap_faster_than_actual(self):
        """With 10% grade, GAP should be significantly faster than actual pace."""
        distance_m = 5_000      # 5 km
        elevation_gain_m = 500  # 10% average grade
        duration_s = 2500       # 500 s/km actual pace
        gap = compute_gap(distance_m, elevation_gain_m, duration_s)
        actual_pace = duration_s / (distance_m / 1000)
        assert gap is not None
        assert gap < actual_pace  # GAP is faster on uphill

    def test_zero_distance_returns_none(self):
        """Zero distance is invalid — should return None."""
        assert compute_gap(0, 100, 600) is None

    def test_zero_duration_returns_none(self):
        """Zero duration is invalid — should return None."""
        assert compute_gap(5000, 100, 0) is None

    def test_format_pace_output(self):
        """format_pace should convert 345 s/km → '5:45'."""
        assert format_pace(345.0) == "5:45"

    def test_format_pace_exact_minute(self):
        """format_pace should handle exact minutes: 300 s/km → '5:00'."""
        assert format_pace(300.0) == "5:00"


# ── Integration tests: Ramp Rate + Projection in PMC endpoint ─────────────────

@pytest.fixture
def org():
    return Organization.objects.create(name="TestOrg PR153", slug="testorg-pr153")


@pytest.fixture
def coach_user(org):
    u = User.objects.create_user(username="coach_pr153", password="x")
    Membership.objects.create(user=u, organization=org, role=Membership.Role.COACH, is_active=True)
    return u


@pytest.fixture
def athlete_user(org):
    u = User.objects.create_user(username="athlete_pr153", password="x")
    return u


@pytest.fixture
def athlete_membership(org, athlete_user):
    return Membership.objects.create(
        user=athlete_user, organization=org, role=Membership.Role.ATHLETE, is_active=True
    )


@pytest.fixture
def coach_client(coach_user):
    c = APIClient()
    c.force_authenticate(user=coach_user)
    return c


@pytest.mark.django_db
class TestRampRateAndProjection:
    def test_increasing_ctl_produces_positive_ramp_rate(
        self, coach_client, athlete_membership, org, athlete_user
    ):
        """Athlete with growing CTL should have positive ramp_rate_7d."""
        today = timezone.now().date()
        # Create DailyLoad: CTL increases 1.0 per day over 30 days
        for i in range(30, -1, -1):
            day = today - timedelta(days=i)
            ctl = 50.0 + (30 - i) * 1.0  # goes from 50 → 80
            DailyLoad.objects.create(
                organization=org,
                athlete=athlete_user,
                date=day,
                tss=100.0,
                ctl=ctl,
                atl=ctl * 1.1,
                tsb=ctl - ctl * 1.1,
                ars=55,
            )
        url = f"/api/coach/athletes/{athlete_membership.pk}/pmc/?days=30"
        res = coach_client.get(url)
        assert res.status_code == 200
        assert res.data["current"]["ramp_rate_7d"] > 0

    def test_detraining_produces_negative_ramp_rate(
        self, coach_client, athlete_membership, org, athlete_user
    ):
        """Athlete who stopped training (CTL declining) should have negative ramp_rate_7d."""
        today = timezone.now().date()
        # CTL declines 1.0 per day
        for i in range(30, -1, -1):
            day = today - timedelta(days=i)
            ctl = 80.0 - (30 - i) * 1.0  # goes from 80 → 50
            DailyLoad.objects.create(
                organization=org,
                athlete=athlete_user,
                date=day,
                tss=0.0,
                ctl=ctl,
                atl=ctl * 0.8,
                tsb=ctl - ctl * 0.8,
                ars=55,
            )
        url = f"/api/coach/athletes/{athlete_membership.pk}/pmc/?days=30"
        res = coach_client.get(url)
        assert res.status_code == 200
        assert res.data["current"]["ramp_rate_7d"] < 0

    def test_pmc_projection_returns_14_days(
        self, coach_client, athlete_membership, org, athlete_user
    ):
        """PMC endpoint projection should always return exactly 14 future dates."""
        today = timezone.now().date()
        for i in range(30, -1, -1):
            day = today - timedelta(days=i)
            DailyLoad.objects.create(
                organization=org,
                athlete=athlete_user,
                date=day,
                tss=100.0,
                ctl=60.0,
                atl=65.0,
                tsb=-5.0,
                ars=55,
            )
        url = f"/api/coach/athletes/{athlete_membership.pk}/pmc/?days=30"
        res = coach_client.get(url)
        assert res.status_code == 200
        projection = res.data.get("projection", [])
        assert len(projection) == 14
        # All projected dates should be in the future
        first_proj_date = projection[0]["date"]
        assert first_proj_date > today.isoformat()


@pytest.mark.django_db
class TestTrainingVolumeEnhanced:
    def test_volume_includes_elevation_gain(
        self, coach_client, athlete_membership, org, athlete_user
    ):
        """Training-volume buckets should include elevation_gain_m field."""
        from core.models import CompletedActivity
        from django.contrib.auth import get_user_model as _get_user

        # Create alumno for the athlete
        alumno = Alumno.objects.create(
            nombre="Test", apellido="PR153", usuario=athlete_user
        )

        today = timezone.now().date()
        CompletedActivity.objects.create(
            organization=org,
            alumno=alumno,
            sport="TRAIL",
            start_time=timezone.make_aware(
                timezone.datetime.combine(today - timedelta(days=3), timezone.datetime.min.time())
            ),
            duration_s=3600,
            distance_m=10000,
            elevation_gain_m=500.0,
            provider="manual",
            provider_activity_id="pr153_test_trail_1",
        )

        url = (
            f"/api/coach/athletes/{athlete_membership.pk}/training-volume/"
            f"?metric=distance&sport=run&precision=weekly&days=30"
        )
        res = coach_client.get(url)
        assert res.status_code == 200
        assert len(res.data["buckets"]) > 0
        bucket = res.data["buckets"][0]
        assert "elevation_gain_m" in bucket
        assert bucket["elevation_gain_m"] == pytest.approx(500.0, abs=1.0)

    def test_volume_run_includes_gap(
        self, coach_client, athlete_membership, org, athlete_user
    ):
        """Training-volume for run sport should include avg_gap_formatted in buckets."""
        from core.models import CompletedActivity

        alumno, _ = Alumno.objects.get_or_create(
            usuario=athlete_user,
            defaults={"nombre": "Test", "apellido": "PR153"},
        )

        today = timezone.now().date()
        CompletedActivity.objects.create(
            organization=org,
            alumno=alumno,
            sport="TRAIL",
            start_time=timezone.make_aware(
                timezone.datetime.combine(today - timedelta(days=2), timezone.datetime.min.time())
            ),
            duration_s=3600,
            distance_m=10000,
            elevation_gain_m=600.0,
            provider="manual",
            provider_activity_id="pr153_test_gap_trail",
        )

        url = (
            f"/api/coach/athletes/{athlete_membership.pk}/training-volume/"
            f"?metric=distance&sport=run&precision=weekly&days=30"
        )
        res = coach_client.get(url)
        assert res.status_code == 200
        assert len(res.data["buckets"]) > 0
        bucket = res.data["buckets"][0]
        assert "avg_gap_formatted" in bucket
        assert "avg_gap_s_km" in bucket
        # GAP should be faster than actual pace due to elevation
        actual_pace = 3600 / 10  # 360 s/km
        assert bucket["avg_gap_s_km"] < actual_pace
