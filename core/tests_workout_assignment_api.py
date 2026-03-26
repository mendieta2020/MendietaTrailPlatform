"""
core/tests_workout_assignment_api.py

API tests for PR-117: WorkoutAssignment endpoints.

Coverage:
- Unauthenticated rejected (401)
- No membership rejected (403)
- Inactive membership rejected (403)
- Coach can list assignments in org
- Athlete list returns only own assignments
- Coach can retrieve assignment in org
- Athlete can retrieve own assignment
- Athlete cannot retrieve another athlete's assignment (404)
- Cross-org coach cannot access via wrong org URL (403)
- Coach can create assignment (201)
- Athlete cannot create assignment (403)
- Coach cannot create assignment for cross-org athlete (400)
- Coach cannot create assignment with cross-org planned_workout (400)
- assigned_by is server-controlled
- organization is not in response
- scheduled_date accepted on create
- scheduled_date cannot be changed on update
- snapshot_version captured from planned_workout.structure_version on create
- Coach can update coach-controlled fields (status, coach_notes, overrides)
- Athlete can update athlete_notes on own assignment
- Athlete can update athlete_moved_date on own assignment
- Athlete cannot update status (ignored / read-only)
- Athlete cannot update coach_notes (ignored / read-only)
- Athlete cannot update target overrides (ignored / read-only)
- Athlete cannot update another athlete's assignment (404)
- effective_date reflects athlete_moved_date when set
- No DELETE endpoint exposed (405)
- No migration generated
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Athlete,
    Coach,
    Membership,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutLibrary,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Shared helpers
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


def _make_planned_workout(org, library, name="Test Workout", structure_version=1):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
        session_type="base",
        structure_version=structure_version,
    )


def _make_assignment(org, athlete, planned_workout, scheduled_date=None, **kwargs):
    if scheduled_date is None:
        scheduled_date = datetime.date(2026, 4, 1)
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
        **kwargs,
    )


def _list_url(org_id):
    return f"/api/p1/orgs/{org_id}/assignments/"


def _detail_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/assignments/{pk}/"


# ==============================================================================
# WorkoutAssignment API Tests
# ==============================================================================


class WorkoutAssignmentAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        # Org A — primary
        self.org = _make_org("AssignOrgA")
        self.library = _make_library(self.org)

        # Coach
        self.coach_user = _make_user("assign_coach_a")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete 1 — has an assignment
        self.athlete_user = _make_user("assign_athlete_a")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        # Athlete 2 — for cross-athlete tests
        self.athlete2_user = _make_user("assign_athlete_b")
        _make_membership(self.athlete2_user, self.org, "athlete")
        self.athlete2 = _make_athlete(self.athlete2_user, self.org)

        # PlannedWorkout
        self.workout = _make_planned_workout(self.org, self.library, structure_version=3)

        # Assignment for athlete 1
        self.assignment = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 4, 10),
            day_order=1,
        )
        # Assignment for athlete 2 (used in list/isolation tests)
        self.assignment2 = _make_assignment(
            self.org, self.athlete2, self.workout,
            scheduled_date=datetime.date(2026, 4, 11),
            day_order=1,
        )

        # Org B — for cross-org tests
        self.org_b = _make_org("AssignOrgB")
        self.library_b = _make_library(self.org_b, name="Lib B")
        self.coach_b_user = _make_user("assign_coach_b")
        _make_membership(self.coach_b_user, self.org_b, "coach")
        _make_coach(self.coach_b_user, self.org_b)

        self.athlete_b_user = _make_user("assign_athlete_b_cross")
        _make_membership(self.athlete_b_user, self.org_b, "athlete")
        self.athlete_b = _make_athlete(self.athlete_b_user, self.org_b)

        self.workout_b = _make_planned_workout(self.org_b, self.library_b, name="Workout B")

        self.list_url = _list_url(self.org.id)
        self.detail_url = _detail_url(self.org.id, self.assignment.pk)
        self.detail2_url = _detail_url(self.org.id, self.assignment2.pk)

    # -------------------------------------------------------------------------
    # Auth / membership gate
    # -------------------------------------------------------------------------

    def test_unauthenticated_list_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_retrieve_rejected(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 401)

    def test_no_membership_rejected(self):
        stranger = _make_user("assign_stranger")
        self.client.force_authenticate(user=stranger)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_rejected(self):
        inactive_user = _make_user("assign_inactive")
        _make_membership(inactive_user, self.org, "coach", is_active=False)
        self.client.force_authenticate(user=inactive_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # Coach list / retrieve
    # -------------------------------------------------------------------------

    def test_coach_can_list_all_assignments_in_org(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.assignment.pk, ids)
        self.assertIn(self.assignment2.pk, ids)

    def test_coach_list_excludes_other_org_assignments(self):
        assignment_b = _make_assignment(self.org_b, self.athlete_b, self.workout_b)
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.list_url)
        ids = [r["id"] for r in response.data["results"]]
        self.assertNotIn(assignment_b.pk, ids)

    def test_coach_can_retrieve_any_assignment_in_org(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail2_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.assignment2.pk)

    # -------------------------------------------------------------------------
    # Athlete list / retrieve
    # -------------------------------------------------------------------------

    def test_athlete_list_returns_only_own_assignments(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.assignment.pk, ids)
        self.assertNotIn(self.assignment2.pk, ids)

    def test_athlete_can_retrieve_own_assignment(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.assignment.pk)

    def test_athlete_cannot_retrieve_another_athlete_assignment(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.get(self.detail2_url)
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # Cross-org access
    # -------------------------------------------------------------------------

    def test_cross_org_coach_cannot_access_list(self):
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

    def test_cross_org_coach_cannot_access_detail(self):
        self.client.force_authenticate(user=self.coach_b_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------

    def test_coach_can_create_assignment(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete2.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-01",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            WorkoutAssignment.objects.filter(
                athlete=self.athlete2, scheduled_date=datetime.date(2026, 5, 1)
            ).exists()
        )

    def test_athlete_cannot_create_assignment(self):
        self.client.force_authenticate(user=self.athlete_user)
        payload = {
            "athlete_id": self.athlete.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-02",
            "day_order": 2,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 403)

    def test_coach_cannot_create_assignment_for_cross_org_athlete(self):
        """Athlete from Org B is not in Org A's queryset — serializer rejects."""
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete_b.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-03",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_coach_cannot_create_assignment_with_cross_org_planned_workout(self):
        """PlannedWorkout from Org B is not in Org A's queryset — serializer rejects."""
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete.pk,
            "planned_workout_id": self.workout_b.pk,
            "scheduled_date": "2026-05-04",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_assigned_by_is_server_controlled(self):
        """Client cannot supply assigned_by; it is set from request.user."""
        other_user = _make_user("assign_other_user")
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete2.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-05",
            "day_order": 1,
            "assigned_by_id": other_user.pk,  # should be ignored
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        obj = WorkoutAssignment.objects.get(pk=response.data["id"])
        self.assertEqual(obj.assigned_by_id, self.coach_user.pk)

    def test_organization_not_in_response(self):
        """organization is server-controlled and not exposed in the API response."""
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("organization", response.data)
        self.assertNotIn("organization_id", response.data)

    def test_created_assignment_organization_matches_url_org(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete2.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-06",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        obj = WorkoutAssignment.objects.get(pk=response.data["id"])
        self.assertEqual(obj.organization_id, self.org.id)

    def test_scheduled_date_accepted_on_create(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete2.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-06-15",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["scheduled_date"], "2026-06-15")

    def test_snapshot_version_captured_from_planned_workout_on_create(self):
        """snapshot_version must equal planned_workout.structure_version at creation time."""
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete2.pk,
            "planned_workout_id": self.workout.pk,
            "scheduled_date": "2026-05-07",
            "day_order": 1,
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["snapshot_version"], self.workout.structure_version)

    # -------------------------------------------------------------------------
    # scheduled_date immutability
    # -------------------------------------------------------------------------

    def test_scheduled_date_cannot_be_changed_on_update(self):
        """scheduled_date is read-only after creation; the value must not change."""
        original_date = self.assignment.scheduled_date
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url,
            {"scheduled_date": "2099-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.scheduled_date, original_date)

    # -------------------------------------------------------------------------
    # Coach update
    # -------------------------------------------------------------------------

    def test_coach_can_update_status(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"status": "completed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "completed")

    def test_coach_can_update_coach_notes(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url, {"coach_notes": "Focus on cadence."}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_notes, "Focus on cadence.")

    def test_coach_can_update_target_overrides(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.patch(
            self.detail_url,
            {
                "target_zone_override": "Z3",
                "target_pace_override": "4:30/km",
                "target_rpe_override": 7,
                "target_power_override": 250,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_zone_override, "Z3")
        self.assertEqual(self.assignment.target_pace_override, "4:30/km")
        self.assertEqual(self.assignment.target_rpe_override, 7)
        self.assertEqual(self.assignment.target_power_override, 250)

    # -------------------------------------------------------------------------
    # Athlete update — allowed fields
    # -------------------------------------------------------------------------

    def test_athlete_can_update_athlete_notes(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"athlete_notes": "Felt good today."}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_notes, "Felt good today.")

    def test_athlete_can_update_athlete_moved_date(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url,
            {"athlete_moved_date": "2026-04-12"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.athlete_moved_date, datetime.date(2026, 4, 12)
        )

    # -------------------------------------------------------------------------
    # Athlete update — blocked fields (read-only in athlete serializer)
    # -------------------------------------------------------------------------

    def test_athlete_can_mark_status_completed(self):
        """Athletes may PATCH status to 'completed' to self-report a finished workout.
        PR-145c made status writable for athletes so they can mark sessions done."""
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"status": "completed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "completed")

    def test_athlete_cannot_change_coach_notes(self):
        """coach_notes is read-only in athlete serializer — change must be ignored."""
        self.assignment.coach_notes = "Original coach note."
        self.assignment.save()
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"coach_notes": "Athlete tamper attempt."}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_notes, "Original coach note.")

    def test_athlete_cannot_change_target_zone_override(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"target_zone_override": "Z5"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_zone_override, "")  # unchanged

    def test_athlete_cannot_change_target_rpe_override(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail_url, {"target_rpe_override": 9}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.target_rpe_override)  # unchanged

    def test_athlete_cannot_update_another_athlete_assignment(self):
        self.client.force_authenticate(user=self.athlete_user)
        response = self.client.patch(
            self.detail2_url, {"athlete_notes": "Tamper."}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------------------
    # effective_date
    # -------------------------------------------------------------------------

    def test_effective_date_equals_scheduled_date_when_no_move(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["effective_date"],
            self.assignment.scheduled_date,
        )

    def test_effective_date_reflects_athlete_moved_date(self):
        self.assignment.athlete_moved_date = datetime.date(2026, 4, 15)
        self.assignment.save()
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["effective_date"], datetime.date(2026, 4, 15))

    # -------------------------------------------------------------------------
    # No DELETE
    # -------------------------------------------------------------------------

    def test_delete_not_exposed(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 405)

    # -------------------------------------------------------------------------
    # No migration generated (smoke check — import only)
    # -------------------------------------------------------------------------

    def test_no_migration_generated(self):
        """
        Importing WorkoutAssignment must not require any pending migrations.
        This is a lightweight smoke test; the real check is `makemigrations --check`
        in CI. The test simply verifies the model is importable and queryable.
        """
        count = WorkoutAssignment.objects.filter(organization=self.org).count()
        self.assertGreaterEqual(count, 2)
