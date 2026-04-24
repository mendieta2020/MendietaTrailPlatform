"""
core/tests_weather_task.py

PR-188: Weather snapshot backfill via Celery Beat (Bug #63).

Tests:
  1. test_enrich_respects_date_window
  2. test_enrich_skips_assignments_without_location
  3. test_enrich_is_idempotent
  4. test_enrich_tolerates_owm_failure
  5. test_enrich_respects_tenancy
  6. test_enrich_emits_structured_logs
"""

import logging
from datetime import date, timedelta
from unittest.mock import patch

import pytest
import requests

from django.contrib.auth import get_user_model

from core.models import (
    Athlete,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)
from core.tasks import enrich_upcoming_snapshots

User = get_user_model()

MOCK_SNAPSHOT = {
    "temp_c": 18,
    "feels_like": 17,
    "description": "Despejado",
    "icon": "01d",
    "humidity": 55,
    "wind_kmh": 12,
    "precipitation_pct": 0,
}

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org PR188", slug="org-pr188")


@pytest.fixture
def coach_user(db, org):
    user = User.objects.create_user(username="coach_pr188", password="pass")
    Membership.objects.create(user=user, organization=org, role="coach", is_active=True)
    return user


@pytest.fixture
def athlete_user(db, org):
    user = User.objects.create_user(username="athlete_pr188", password="pass")
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    return user


@pytest.fixture
def athlete(db, org, athlete_user):
    return Athlete.objects.create(
        user=athlete_user,
        organization=org,
        location_lat=40.4168,
        location_lon=-3.7038,
    )


@pytest.fixture
def athlete_no_location(db, org):
    user = User.objects.create_user(username="athlete_noloc_pr188", password="pass")
    Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
    return Athlete.objects.create(user=user, organization=org)


@pytest.fixture
def library(db, org, coach_user):
    return WorkoutLibrary.objects.create(
        organization=org,
        name="Lib PR188",
        created_by=coach_user,
    )


@pytest.fixture
def planned_workout(db, org, coach_user, library):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name="Test Workout PR188",
        discipline="run",
        created_by=coach_user,
    )


def _make_assignment(org, athlete, pw, scheduled_date, coach_user=None, day_order=1):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=pw,
        assigned_by=coach_user,
        scheduled_date=scheduled_date,
        day_order=day_order,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEnrichUpcomingSnapshots:

    def test_enrich_respects_date_window(self, org, athlete, planned_workout, coach_user):
        """Only assignments in [today, today+4] are enriched."""
        today = date.today()
        in_scope = [today, today + timedelta(days=2), today + timedelta(days=4)]
        out_of_scope = [today - timedelta(days=1), today + timedelta(days=5)]
        for i, d in enumerate(in_scope + out_of_scope):
            _make_assignment(org, athlete, planned_workout, d, coach_user, day_order=i + 1)

        with patch("core.services_weather.get_weather_for_date", return_value=MOCK_SNAPSHOT):
            result = enrich_upcoming_snapshots()

        assert result["enriched"] == 3, f"expected 3, got {result}"

    def test_enrich_skips_assignments_without_location(
        self, org, athlete, athlete_no_location, planned_workout, coach_user
    ):
        """Assignments whose athlete has no location_lat are excluded by the queryset."""
        today = date.today()
        wa_with = _make_assignment(org, athlete, planned_workout, today, coach_user)
        _make_assignment(org, athlete_no_location, planned_workout, today + timedelta(days=1), coach_user)

        with patch("core.services_weather.get_weather_for_date", return_value=MOCK_SNAPSHOT):
            result = enrich_upcoming_snapshots()

        assert result["enriched"] == 1
        assert result["skipped_no_location"] == 0
        wa_with.refresh_from_db()
        assert wa_with.weather_snapshot == MOCK_SNAPSHOT

    def test_enrich_is_idempotent(self, org, athlete, planned_workout, coach_user):
        """Running the task twice produces the same outcome — no IntegrityError or drift."""
        today = date.today()
        wa = _make_assignment(org, athlete, planned_workout, today, coach_user)
        assert wa.weather_snapshot is None

        with patch("core.services_weather.get_weather_for_date", return_value=MOCK_SNAPSHOT):
            result1 = enrich_upcoming_snapshots()
            result2 = enrich_upcoming_snapshots()

        wa.refresh_from_db()
        assert wa.weather_snapshot == MOCK_SNAPSHOT
        assert result1["enriched"] == 1
        assert result2["enriched"] == 1
        assert result1["errors"] == 0
        assert result2["errors"] == 0

    def test_enrich_tolerates_owm_failure(self, org, athlete, planned_workout, coach_user):
        """OWM network failures are swallowed; task returns cleanly."""
        today = date.today()
        _make_assignment(org, athlete, planned_workout, today, coach_user)

        with patch(
            "core.services_weather.get_weather_for_date",
            side_effect=requests.RequestException("OWM timeout"),
        ):
            result = enrich_upcoming_snapshots()

        assert result["skipped_owm_failure"] >= 1
        assert result["errors"] == 0

    def test_enrich_respects_tenancy(self, org, athlete, planned_workout, coach_user):
        """Each assignment is written only to itself — no cross-org data access."""
        user_b = User.objects.create_user(username="coach_pr188_b", password="pass")
        org_b = Organization.objects.create(name="Org PR188 B", slug="org-pr188-b")
        Membership.objects.create(user=user_b, organization=org_b, role="coach", is_active=True)

        user_b_ath = User.objects.create_user(username="athlete_pr188_b", password="pass")
        Membership.objects.create(user=user_b_ath, organization=org_b, role="athlete", is_active=True)
        athlete_b = Athlete.objects.create(
            user=user_b_ath,
            organization=org_b,
            location_lat=48.8566,
            location_lon=2.3522,
        )
        lib_b = WorkoutLibrary.objects.create(
            organization=org_b, name="Lib B PR188", created_by=user_b
        )
        pw_b = PlannedWorkout.objects.create(
            organization=org_b, library=lib_b,
            name="PW B PR188", discipline="run", created_by=user_b,
        )

        today = date.today()
        wa_a = _make_assignment(org, athlete, planned_workout, today, coach_user)
        wa_b = _make_assignment(org_b, athlete_b, pw_b, today, user_b)
        snapshot_before_b = wa_b.weather_snapshot

        with patch("core.services_weather.get_weather_for_date", return_value=MOCK_SNAPSHOT):
            result = enrich_upcoming_snapshots()

        wa_a.refresh_from_db()
        wa_b.refresh_from_db()

        assert wa_a.weather_snapshot == MOCK_SNAPSHOT
        assert wa_b.weather_snapshot == MOCK_SNAPSHOT
        assert result["enriched"] == 2
        assert wa_a.organization_id == org.pk
        assert wa_b.organization_id == org_b.pk
        assert wa_a.pk != wa_b.pk

    def test_enrich_emits_structured_logs(
        self, org, athlete, planned_workout, coach_user, caplog
    ):
        """Task emits weather.enrich.started and .completed with correct extras."""
        today = date.today()
        _make_assignment(org, athlete, planned_workout, today, coach_user)

        with caplog.at_level(logging.INFO, logger="core.tasks"):
            with patch("core.services_weather.get_weather_for_date", return_value=MOCK_SNAPSHOT):
                enrich_upcoming_snapshots()

        messages = [r.getMessage() for r in caplog.records]
        assert any("weather.enrich.started" in m for m in messages), (
            f"weather.enrich.started not found in {messages}"
        )
        assert any("weather.enrich.completed" in m for m in messages), (
            f"weather.enrich.completed not found in {messages}"
        )

        for record in caplog.records:
            attrs = record.__dict__
            if "weather.enrich.completed" in record.getMessage():
                assert "run_id" in attrs, "run_id missing from completed record"
                assert "enriched" in attrs
                assert "skipped_no_location" in attrs
                assert "skipped_owm_failure" in attrs
                assert "errors" in attrs
            if "weather.enrich.assignment_success" in record.getMessage():
                assert "organization_id" in attrs, "organization_id missing from success record"

        for record in caplog.records:
            assert "weather_snapshot" not in record.__dict__, (
                f"weather_snapshot leaked into log record: {record.getMessage()}"
            )
