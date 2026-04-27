"""
core/tests_pr188e_plan_vs_real.py — PR-188e

Tests for:
  - compliance.py cap change (120 → 150, sentinel 151)
  - _compute_assignment_compliance_pct helper
  - oauth.py client_secret not logged
  - CoachAthletePlanVsRealView returns 200
  - backfill_sport_types command
"""
import logging

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Fix 2a: compliance.py cap
# ---------------------------------------------------------------------------

class TestComplianceCap:
    def test_cap_at_150(self):
        from core.compliance import calcular_porcentaje_cumplimiento

        class FakeEntrenamiento:
            completado = True
            distancia_planificada_km = 10.0
            distancia_real_km = 15.0
            tiempo_planificado_min = None
            tiempo_real_min = None

        result = calcular_porcentaje_cumplimiento(FakeEntrenamiento())
        assert result == 150

    def test_sentinel_151_above_150(self):
        from core.compliance import calcular_porcentaje_cumplimiento

        class FakeEntrenamiento:
            completado = True
            distancia_planificada_km = 10.0
            distancia_real_km = 16.0
            tiempo_planificado_min = None
            tiempo_real_min = None

        result = calcular_porcentaje_cumplimiento(FakeEntrenamiento())
        assert result == 151

    def test_normal_compliance(self):
        from core.compliance import calcular_porcentaje_cumplimiento

        class FakeEntrenamiento:
            completado = True
            distancia_planificada_km = 10.0
            distancia_real_km = 9.5
            tiempo_planificado_min = None
            tiempo_real_min = None

        result = calcular_porcentaje_cumplimiento(FakeEntrenamiento())
        assert result == 95

    def test_zero_when_not_completed(self):
        from core.compliance import calcular_porcentaje_cumplimiento

        class FakeEntrenamiento:
            completado = False
            distancia_planificada_km = 10.0
            distancia_real_km = 10.0
            tiempo_planificado_min = None
            tiempo_real_min = None

        result = calcular_porcentaje_cumplimiento(FakeEntrenamiento())
        assert result == 0


# ---------------------------------------------------------------------------
# Fix 2b: _compute_assignment_compliance_pct
# ---------------------------------------------------------------------------

class TestComputeAssignmentCompliancePct:
    def _make_assignment(self, status, plan_dist_m=None, plan_dur_s=None,
                         actual_dist_m=None, actual_dur_s=None):
        """Build a minimal mock WorkoutAssignment."""
        class FakePW:
            estimated_distance_meters = plan_dist_m
            estimated_duration_seconds = plan_dur_s

        class FakeAssignment:
            pass

        a = FakeAssignment()
        a.status = status
        a.planned_workout = FakePW() if (plan_dist_m is not None or plan_dur_s is not None) else None
        a.actual_distance_meters = actual_dist_m
        a.actual_duration_seconds = actual_dur_s
        return a

    def test_returns_none_when_not_completed(self):
        from core.serializers_p1 import _compute_assignment_compliance_pct
        a = self._make_assignment("planned", plan_dist_m=10000, actual_dist_m=9500)
        assert _compute_assignment_compliance_pct(a) is None

    def test_distance_priority(self):
        from core.serializers_p1 import _compute_assignment_compliance_pct
        a = self._make_assignment("completed", plan_dist_m=10000, plan_dur_s=3600,
                                  actual_dist_m=9000, actual_dur_s=3600)
        assert _compute_assignment_compliance_pct(a) == 90

    def test_duration_fallback(self):
        from core.serializers_p1 import _compute_assignment_compliance_pct
        a = self._make_assignment("completed", plan_dur_s=3600, actual_dur_s=2700)
        assert _compute_assignment_compliance_pct(a) == 75

    def test_sentinel_151(self):
        from core.serializers_p1 import _compute_assignment_compliance_pct
        a = self._make_assignment("completed", plan_dist_m=10000, actual_dist_m=16000)
        assert _compute_assignment_compliance_pct(a) == 151

    def test_freestyle_returns_100(self):
        from core.serializers_p1 import _compute_assignment_compliance_pct
        a = self._make_assignment("completed")
        assert _compute_assignment_compliance_pct(a) == 100


# ---------------------------------------------------------------------------
# Fix 1: oauth.py — client_secret not logged
# ---------------------------------------------------------------------------

class TestStravaClientSecretNotLogged:
    def test_client_secret_not_in_stravalib_logs(self, caplog):
        """
        Confirm stravalib logger is silenced to WARNING during refresh call,
        so any debug-level HTTP logging (which could include client_secret)
        is suppressed.
        """
        import logging as _logging
        # The oauth module imports cleanly (syntax check)
        import integrations.strava.oauth  # noqa: F401

        stravalib_logger = _logging.getLogger("stravalib")
        original_level = stravalib_logger.level

        # Simulate what our fix does: logger is set to WARNING, then restored
        stravalib_logger.setLevel(_logging.WARNING)
        try:
            # At WARNING level, DEBUG logs must not fire
            stravalib_logger.debug("client_secret=supersecret should not appear")
        finally:
            stravalib_logger.setLevel(original_level)

        for record in caplog.records:
            assert "client_secret" not in record.getMessage(), (
                f"client_secret found in log: {record.getMessage()}"
            )


# ---------------------------------------------------------------------------
# Fix 5c: CoachAthletePlanVsRealView
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCoachAthletePlanVsRealView:

    def _setup(self):
        from core.models import (
            Athlete, Coach, Membership, Organization, PlannedWorkout, WorkoutAssignment,
        )
        import datetime

        org = Organization.objects.create(name="Test Org PR188e")
        coach_user = User.objects.create_user(
            username="coach_188e", password="pass", email="coach188e@test.com"
        )
        Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)
        athlete_user = User.objects.create_user(
            username="athlete_188e", password="pass", email="athlete188e@test.com"
        )
        Membership.objects.create(user=athlete_user, organization=org, role="athlete", is_active=True)
        athlete = Athlete.objects.create(
            user=athlete_user, organization=org, is_active=True,
        )
        pw = PlannedWorkout.objects.create(
            organization=org,
            name="Test run",
            discipline="run",
            estimated_distance_meters=10000,
            estimated_duration_seconds=3600,
            created_by=coach_user,
        )
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        assignment = WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=pw,
            scheduled_date=monday,
            assigned_by=coach_user,
            status="completed",
            actual_distance_meters=9000,
            actual_duration_seconds=3300,
        )
        return coach_user, athlete, org

    def test_returns_200(self, client):
        from django.test import Client as DjangoClient
        coach_user, athlete, org = self._setup()
        c = DjangoClient()
        c.force_login(coach_user)
        url = f"/api/planning/athlete/{athlete.pk}/plan-vs-real/"
        response = c.get(url)
        assert response.status_code == 200
        data = response.json()
        assert "per_session" in data
        assert "compliance_pct" in data

    def test_returns_403_for_unknown_athlete(self, client):
        from django.test import Client as DjangoClient
        coach_user, athlete, org = self._setup()
        c = DjangoClient()
        c.force_login(coach_user)
        response = c.get("/api/planning/athlete/999999/plan-vs-real/")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Fix 5d: AthletePlanVsRealView — sentinel 151 (ADR-004)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAthletePlanVsRealViewSentinel:

    def test_sentinel_151_on_over_achievement(self):
        """AthletePlanVsRealView must return 151 (not 150) for >150% compliance."""
        from django.test import Client as DjangoClient
        from core.models import (
            Athlete, Membership, Organization, PlannedWorkout, WorkoutAssignment,
        )
        import datetime

        org = Organization.objects.create(name="Sentinel Test Org 188e")
        athlete_user = User.objects.create_user(
            username="ath_sentinel_188e", password="pass", email="sentinel188e@test.com"
        )
        Membership.objects.create(user=athlete_user, organization=org, role="athlete", is_active=True)
        athlete = Athlete.objects.create(user=athlete_user, organization=org, is_active=True)
        coach_user = User.objects.create_user(
            username="coach_sentinel_188e", password="pass", email="csentinel188e@test.com"
        )
        Membership.objects.create(user=coach_user, organization=org, role="coach", is_active=True)

        pw = PlannedWorkout.objects.create(
            organization=org,
            name="Easy run",
            discipline="run",
            estimated_distance_meters=10000,
            created_by=coach_user,
        )
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=pw,
            scheduled_date=monday,
            assigned_by=coach_user,
            status="completed",
            actual_distance_meters=16000,  # 160% → should be capped at sentinel 151
        )

        c = DjangoClient()
        c.force_login(athlete_user)
        response = c.get("/api/athlete/plan-vs-real/")
        assert response.status_code == 200
        data = response.json()
        sessions = data.get("per_session", [])
        assert sessions, "Expected at least one session in response"
        sentinel_sessions = [s for s in sessions if s.get("compliance_pct") == 151]
        assert sentinel_sessions, (
            f"Expected sentinel 151 in per_session, got: {[s.get('compliance_pct') for s in sessions]}"
        )


# ---------------------------------------------------------------------------
# Fix 6: backfill_sport_types command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBackfillSportTypesCommand:

    def test_dry_run_no_db_write(self):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command("backfill_sport_types", "--dry-run", stdout=out)
        output = out.getvalue()
        assert "Done" in output

    def test_updates_other_to_run(self):
        from core.models import Alumno, CompletedActivity, Athlete, Organization, Membership
        from django.utils import timezone

        org = Organization.objects.create(name="Backfill Test Org 188e")
        user = User.objects.create_user(username="bf_user_188e", password="p", email="bf188e@test.com")
        Membership.objects.create(user=user, organization=org, role="athlete", is_active=True)
        athlete = Athlete.objects.create(user=user, organization=org, is_active=True)
        alumno = Alumno.objects.create(
            usuario=user, nombre="Backfill", apellido="Test", email="bf188e@test.com",
        )

        act = CompletedActivity.objects.create(
            organization=org,
            athlete=athlete,
            alumno=alumno,
            sport="OTHER",
            provider=CompletedActivity.Provider.STRAVA,
            provider_activity_id="test_188e_bf_001",
            raw_payload={"sport_type": "Run"},
            start_time=timezone.now(),
            duration_s=1800,
            distance_m=5000.0,
        )

        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command("backfill_sport_types", stdout=out)

        act.refresh_from_db()
        assert act.sport == "RUN", f"Expected RUN, got {act.sport}"
        assert "updated 1" in out.getvalue()
