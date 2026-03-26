"""
core/tests_pr145d_compliance.py

PR-145d: Smart Compliance + RPE + Weather snapshot

Tests:
  1. compliance_planned → gray
  2. compliance_skipped → red
  3. compliance_completed_no_data → green (trust athlete)
  4. compliance_green → actual >= 90% planned
  5. compliance_yellow → actual 70–89% planned
  6. compliance_red → actual < 70% planned
  7. compliance_blue → actual >= 120% planned
  8. compliance_uses_max_ratio → distance green even when duration yellow
  9. compliance_recalculated_on_save → recalcs when status changes to completed
 10. rpe_field_stored → RPE 1-5 saved correctly
 11. rpe_out_of_range → ValidationError on RPE > 5
 12. weather_snapshot_stored → JSONField round-trips correctly
 13. athlete_location_fields → location_city/lat/lon stored correctly
"""

import pytest
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.models import (
    Athlete,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def coach_user(db, org):
    user = User.objects.create_user(username="coach_145d", password="pass")
    Membership.objects.create(user=user, organization=org, role="coach", is_active=True)
    return user


@pytest.fixture
def athlete_user(db, org):
    user = User.objects.create_user(username="athlete_145d", password="pass")
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    return user


@pytest.fixture
def athlete(db, org, athlete_user):
    return Athlete.objects.create(user=athlete_user, organization=org)


@pytest.fixture
def library(db, org, coach_user):
    return WorkoutLibrary.objects.create(
        organization=org,
        name="Lib 145d",
        created_by=coach_user,
    )


@pytest.fixture
def planned_workout(db, org, coach_user, library):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Base Run",
        discipline="run",
        created_by=coach_user,
        estimated_duration_seconds=3600,   # 60 min
        estimated_distance_meters=10000,   # 10 km
    )


def _make_assignment(org, athlete, pw, coach_user, status="planned",
                     actual_duration=None, actual_distance=None,
                     actual_elevation=None, rpe=None):
    """Helper: build and save a WorkoutAssignment."""
    a = WorkoutAssignment(
        organization=org,
        athlete=athlete,
        planned_workout=pw,
        assigned_by=coach_user,
        scheduled_date=date.today(),
        status=status,
        actual_duration_seconds=actual_duration,
        actual_distance_meters=actual_distance,
        actual_elevation_gain=actual_elevation,
        rpe=rpe,
    )
    a.save()
    return a


# ── Tests: calculate_compliance_color() ──────────────────────────────────────

@pytest.mark.django_db
class TestSmartCompliance:
    def test_compliance_planned(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="planned")
        assert a.compliance_color == "gray"

    def test_compliance_moved(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="moved")
        assert a.compliance_color == "gray"

    def test_compliance_skipped(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="skipped")
        assert a.compliance_color == "red"

    def test_compliance_canceled(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="canceled")
        assert a.compliance_color == "red"

    def test_compliance_completed_no_data(self, org, athlete, planned_workout, coach_user):
        """Completed with no actual data → green (trust athlete)."""
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="completed")
        assert a.compliance_color == "green"

    def test_compliance_green_duration(self, org, athlete, planned_workout, coach_user):
        """Actual duration = 95% planned → green."""
        # 95% of 3600 = 3420
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", actual_duration=3420,
        )
        assert a.compliance_color == "green"

    def test_compliance_yellow_duration(self, org, athlete, planned_workout, coach_user):
        """Actual duration = 75% planned → yellow (70–89%)."""
        # 75% of 3600 = 2700
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", actual_duration=2700,
        )
        assert a.compliance_color == "yellow"

    def test_compliance_red_duration(self, org, athlete, planned_workout, coach_user):
        """Actual duration = 60% planned → red (< 70%)."""
        # 60% of 3600 = 2160
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", actual_duration=2160,
        )
        assert a.compliance_color == "red"

    def test_compliance_blue_duration(self, org, athlete, planned_workout, coach_user):
        """Actual duration >= 120% planned → blue (exceeded plan)."""
        # 130% of 3600 = 4680
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", actual_duration=4680,
        )
        assert a.compliance_color == "blue"

    def test_compliance_uses_max_ratio(self, org, athlete, planned_workout, coach_user):
        """
        Distance ratio = green (95%), duration ratio = yellow (75%).
        Should return green because max(ratios) is used.
        Simulates rain forcing alternative route: more km, less time.
        """
        # Duration: 75% of 3600 = 2700 → would be yellow alone
        # Distance: 95% of 10000 = 9500 → green
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed",
            actual_duration=2700,
            actual_distance=9500,
        )
        assert a.compliance_color == "green"

    def test_compliance_recalculated_on_save(self, org, athlete, planned_workout, coach_user):
        """Compliance color is recalculated each time status=completed on save."""
        a = _make_assignment(org, athlete, planned_workout, coach_user, status="planned")
        assert a.compliance_color == "gray"

        a.status = "completed"
        a.actual_duration_seconds = 3420  # 95%
        a.save()
        assert a.compliance_color == "green"


# ── Tests: RPE field ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRPEField:
    def test_rpe_stored(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", rpe=4,
        )
        a.refresh_from_db()
        assert a.rpe == 4

    def test_rpe_null_allowed(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(
            org, athlete, planned_workout, coach_user,
            status="completed", rpe=None,
        )
        assert a.rpe is None

    def test_rpe_out_of_range_raises(self, org, athlete, planned_workout, coach_user):
        with pytest.raises(ValidationError):
            _make_assignment(
                org, athlete, planned_workout, coach_user,
                status="completed", rpe=6,
            )

    def test_rpe_below_range_raises(self, org, athlete, planned_workout, coach_user):
        with pytest.raises(ValidationError):
            _make_assignment(
                org, athlete, planned_workout, coach_user,
                status="completed", rpe=0,
            )


# ── Tests: weather_snapshot field ─────────────────────────────────────────────

@pytest.mark.django_db
class TestWeatherSnapshot:
    def test_weather_snapshot_stored(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user)
        snapshot = {
            "temp_c": 14,
            "feels_like": 12,
            "description": "Cielo despejado",
            "icon": "01d",
            "humidity": 55,
        }
        a.weather_snapshot = snapshot
        a.save(update_fields=["weather_snapshot"])
        a.refresh_from_db()
        assert a.weather_snapshot["temp_c"] == 14
        assert a.weather_snapshot["icon"] == "01d"

    def test_weather_snapshot_null_by_default(self, org, athlete, planned_workout, coach_user):
        a = _make_assignment(org, athlete, planned_workout, coach_user)
        assert a.weather_snapshot is None


# ── Tests: Athlete location fields ────────────────────────────────────────────

@pytest.mark.django_db
class TestAthleteLocationFields:
    def test_location_fields_stored(self, org, athlete):
        athlete.location_city = "Mendoza, Argentina"
        athlete.location_lat = -32.8895
        athlete.location_lon = -68.8458
        athlete.save()
        athlete.refresh_from_db()
        assert athlete.location_city == "Mendoza, Argentina"
        assert abs(athlete.location_lat - (-32.8895)) < 0.0001
        assert abs(athlete.location_lon - (-68.8458)) < 0.0001

    def test_location_fields_nullable(self, org, athlete):
        """lat/lon default to None, city defaults to empty string."""
        assert athlete.location_lat is None
        assert athlete.location_lon is None
        assert athlete.location_city == ""
