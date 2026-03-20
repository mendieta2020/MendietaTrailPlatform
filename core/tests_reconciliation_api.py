"""
core/tests_reconciliation_api.py

PR-119: Reconciliation API tests.

Coverage:
- Unauthenticated → 401
- No membership → 403
- GET reconciliation → 404 when no record exists
- GET reconciliation → 200 with correct state after miss
- POST reconcile (auto) as coach → 200, valid state
- POST reconcile (manual, with activity) as coach → 200, state=reconciled
- POST reconcile as athlete → 403
- POST miss as coach → 200, state=missed
- POST miss as athlete → 403
- Athlete sees own reconciliation (404 for other athlete's assignment)
- Cross-org: outsider → 403
- GET adherence without week_start → 400
- GET adherence with invalid date → 400
- GET adherence as coach → 200, correct shape
- GET adherence as athlete (own) → 200
- GET adherence as athlete (other athlete) → 404
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    CompletedActivity,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Shared helpers (mirrors pattern from tests_workout_assignment_api.py)
# ---------------------------------------------------------------------------


def _make_org(name):
    slug = name.lower().replace(" ", "-")
    return Organization.objects.create(name=name, slug=slug)


def _make_user(username):
    return User.objects.create_user(username=username, password="testpass123")


def _make_membership(user, org, role, is_active=True):
    return Membership.objects.create(
        user=user, organization=org, role=role, is_active=is_active
    )


def _make_coach(user, org):
    return Coach.objects.create(user=user, organization=org)


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _make_library(org, name="Default Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _make_planned_workout(org, library, **kwargs):
    defaults = {
        "name": "Test Workout",
        "discipline": "run",
        "session_type": "base",
        "estimated_duration_seconds": 3600,
        "estimated_distance_meters": 10000,
    }
    defaults.update(kwargs)
    return PlannedWorkout.objects.create(organization=org, library=library, **defaults)


def _make_assignment(org, athlete, planned_workout, scheduled_date=None, **kwargs):
    if scheduled_date is None:
        scheduled_date = datetime.date(2026, 4, 1)
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
        day_order=kwargs.pop("day_order", 1),
        **kwargs,
    )


_activity_counter = 0  # module-level counter for unique provider_activity_id


def _make_activity(coach_user, alumno, athlete, org, sport="RUN", duration_s=3600,
                   distance_m=10000.0, start_time=None):
    """
    Create a CompletedActivity linked to both the legacy alumno FK and the new Athlete FK.
    organization=org is the Organization (D2 debt resolved: no longer a User FK).
    """
    global _activity_counter
    _activity_counter += 1
    if start_time is None:
        start_time = timezone.make_aware(datetime.datetime(2026, 4, 1, 8, 0, 0))
    return CompletedActivity.objects.create(
        organization=org,
        alumno=alumno,
        athlete=athlete,
        sport=sport,
        start_time=start_time,
        duration_s=duration_s,
        distance_m=distance_m,
        provider="manual",
        provider_activity_id=f"rec_api_test_{_activity_counter}_{sport}",
    )


# URL helpers
def _rec_detail_url(org_id, assignment_id):
    return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/"


def _rec_reconcile_url(org_id, assignment_id):
    return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/reconcile/"


def _rec_miss_url(org_id, assignment_id):
    return f"/api/p1/orgs/{org_id}/assignments/{assignment_id}/reconciliation/miss/"


def _adherence_url(org_id, athlete_id):
    return f"/api/p1/orgs/{org_id}/athletes/{athlete_id}/adherence/"


# ---------------------------------------------------------------------------
# Test fixtures base
# ---------------------------------------------------------------------------


class ReconciliationAPIBase(TestCase):
    """
    Base setUp shared across all reconciliation API test classes.

    Creates:
      org, coach_user (coach role), athlete_user (athlete role), athlete,
      alumno (legacy), library, planned_workout, assignment.
    """

    def setUp(self):
        self.client = APIClient()

        # Org A — primary
        self.org = _make_org("RecApiOrgA")
        self.library = _make_library(self.org)

        # Coach
        self.coach_user = _make_user("rec_api_coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete 1
        self.athlete_user = _make_user("rec_api_athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Legacy Alumno (required by CompletedActivity.alumno FK)
        from core.models import Alumno
        self.alumno = Alumno.objects.create(
            entrenador=self.coach_user,
            usuario=self.athlete_user,
            nombre="Rec",
            apellido="Test",
        )

        # PlannedWorkout and assignment
        self.workout = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 4, 1),
        )


# ---------------------------------------------------------------------------
# Auth and membership guards
# ---------------------------------------------------------------------------


class ReconciliationAuthTests(ReconciliationAPIBase):

    def test_unauthenticated_get_reconciliation_returns_401(self):
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 401)

    def test_unauthenticated_post_reconcile_returns_401(self):
        res = self.client.post(_rec_reconcile_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 401)

    def test_no_membership_returns_403(self):
        outsider = _make_user("rec_api_outsider")
        self.client.force_authenticate(user=outsider)
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 403)

    def test_inactive_membership_returns_403(self):
        inactive_user = _make_user("rec_api_inactive")
        _make_membership(inactive_user, self.org, "coach", is_active=False)
        self.client.force_authenticate(user=inactive_user)
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 403)


# ---------------------------------------------------------------------------
# GET reconciliation detail
# ---------------------------------------------------------------------------


class ReconciliationDetailTests(ReconciliationAPIBase):

    def test_get_reconciliation_404_when_no_record(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 404)

    def test_get_reconciliation_200_after_miss(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk))
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["state"], "missed")
        self.assertEqual(res.data["assignment_id"], self.assignment.pk)

    def test_reconciliation_response_does_not_expose_organization(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk))
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertNotIn("organization", res.data)
        self.assertNotIn("organization_id", res.data)

    def test_athlete_can_read_own_reconciliation(self):
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk))
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 200)

    def test_athlete_cannot_read_other_athlete_reconciliation(self):
        # Create a second athlete and assignment
        athlete2_user = _make_user("rec_api_athlete_b")
        _make_membership(athlete2_user, self.org, "athlete")
        athlete2 = _make_athlete(athlete2_user, self.org)
        assignment2 = _make_assignment(
            self.org, athlete2, self.workout,
            scheduled_date=datetime.date(2026, 4, 2),
            day_order=2,
        )
        # Mark it missed so a record exists
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(_rec_miss_url(self.org.pk, assignment2.pk))
        # Now athlete 1 tries to access athlete 2's reconciliation
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.get(_rec_detail_url(self.org.pk, assignment2.pk))
        self.assertEqual(res.status_code, 404)

    def test_cross_org_coach_cannot_access_reconciliation(self):
        other_org = _make_org("RecApiOrgB")
        other_user = _make_user("rec_api_other_coach")
        _make_membership(other_user, other_org, "coach")
        self.client.force_authenticate(user=other_user)
        res = self.client.get(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 403)


# ---------------------------------------------------------------------------
# POST reconcile
# ---------------------------------------------------------------------------


class ReconciliationReconcileTests(ReconciliationAPIBase):

    def test_post_reconcile_auto_as_coach_returns_200(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk), {}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.data["state"], ["reconciled", "unmatched", "ambiguous"])

    def test_post_reconcile_manual_with_activity_as_coach(self):
        activity = _make_activity(
            self.coach_user, self.alumno, self.athlete, self.org,
            sport="RUN", duration_s=3700, distance_m=10500,
        )
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk),
            {"completed_activity_id": activity.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["state"], "reconciled")
        self.assertEqual(res.data["completed_activity_id"], activity.pk)
        self.assertIsNotNone(res.data["compliance_score"])

    def test_post_reconcile_with_cross_org_activity_returns_404(self):
        # Activity belonging to a different org (different coach = different org)
        other_coach = _make_user("rec_api_other_coach2")
        other_org = _make_org("RecApiOrgC")
        other_athlete_user = _make_user("rec_api_other_athlete2")
        other_athlete = _make_athlete(other_athlete_user, other_org)
        from core.models import Alumno
        other_alumno = Alumno.objects.create(
            entrenador=other_coach,
            usuario=other_athlete_user,
            nombre="Other",
            apellido="Athlete",
        )
        foreign_activity = _make_activity(
            other_coach, other_alumno, other_athlete, other_org
        )
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk),
            {"completed_activity_id": foreign_activity.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_post_reconcile_as_athlete_returns_403(self):
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk), {}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_post_reconcile_idempotent(self):
        self.client.force_authenticate(user=self.coach_user)
        res1 = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk), {}, format="json"
        )
        res2 = self.client.post(
            _rec_reconcile_url(self.org.pk, self.assignment.pk), {}, format="json"
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        # One record, not two
        from core.models import WorkoutReconciliation
        count = WorkoutReconciliation.objects.filter(assignment=self.assignment).count()
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# POST miss
# ---------------------------------------------------------------------------


class ReconciliationMissTests(ReconciliationAPIBase):

    def test_post_miss_as_coach_returns_200_with_missed_state(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk), {}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["state"], "missed")
        self.assertIsNone(res.data["completed_activity_id"])

    def test_post_miss_as_athlete_returns_403(self):
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk), {}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_post_miss_with_notes_stored(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.post(
            _rec_miss_url(self.org.pk, self.assignment.pk),
            {"notes": "Athlete was sick"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("sick", res.data["notes"])

    def test_post_miss_no_delete_endpoint(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.delete(_rec_detail_url(self.org.pk, self.assignment.pk))
        self.assertEqual(res.status_code, 405)


# ---------------------------------------------------------------------------
# GET adherence
# ---------------------------------------------------------------------------


class AthleteAdherenceTests(ReconciliationAPIBase):

    def test_adherence_requires_week_start(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.get(_adherence_url(self.org.pk, self.athlete.pk))
        self.assertEqual(res.status_code, 400)
        self.assertIn("week_start", res.data)

    def test_adherence_rejects_invalid_date(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "not-a-date"},
        )
        self.assertEqual(res.status_code, 400)

    def test_adherence_returns_correct_shape_as_coach(self):
        self.client.force_authenticate(user=self.coach_user)
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 200)
        for key in (
            "week_start", "week_end", "organization_id", "athlete_id",
            "planned_count", "reconciled_count", "missed_count",
            "unmatched_count", "avg_compliance_score", "adherence_pct",
        ):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["organization_id"], self.org.pk)
        self.assertEqual(res.data["athlete_id"], self.athlete.pk)

    def test_adherence_counts_missed_assignment(self):
        # Mark this week's assignment as missed
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(_rec_miss_url(self.org.pk, self.assignment.pk))
        # assignment is on 2026-04-01 — week of 2026-03-30 (Mon–Sun)
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["planned_count"], 1)
        self.assertEqual(res.data["missed_count"], 1)
        self.assertEqual(res.data["reconciled_count"], 0)

    def test_adherence_athlete_can_see_own(self):
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 200)

    def test_adherence_athlete_cannot_see_other_athlete(self):
        athlete2_user = _make_user("rec_api_adh_athlete_b")
        _make_membership(athlete2_user, self.org, "athlete")
        athlete2 = _make_athlete(athlete2_user, self.org)
        self.client.force_authenticate(user=self.athlete_user)
        res = self.client.get(
            _adherence_url(self.org.pk, athlete2.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 404)

    def test_adherence_unauthenticated_returns_401(self):
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 401)

    def test_adherence_no_membership_returns_403(self):
        outsider = _make_user("rec_api_adh_outsider")
        self.client.force_authenticate(user=outsider)
        res = self.client.get(
            _adherence_url(self.org.pk, self.athlete.pk),
            {"week_start": "2026-03-30"},
        )
        self.assertEqual(res.status_code, 403)
