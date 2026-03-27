"""
core/tests_pr145f_crud.py

PR-145f: Coach Calendar CRUD + Bulk Week Operations.

Coverage:
- test_move_assignment: PATCH scheduled_date → 200, date changes
- test_cannot_delete_completed: DELETE completed assignment → 400
- test_delete_planned: DELETE planned assignment → 204
- test_clone_workout: POST clone-workout → new PlannedWorkout, assignment updated
- test_clone_preserves_blocks: cloned workout has same block count
- test_clone_already_snapshot: POST clone-workout on snapshot → returns same workout (no double clone)
- test_copy_week_same_athlete: copy-week same athlete new date range
- test_copy_week_different_athlete: copy-week athlete B receives assignments
- test_copy_week_skips_completed: completed assignments not copied
- test_copy_week_day_order: double session in source → day_order correct in destination
- test_delete_week_protects_completed: delete-week never removes completed
- test_delete_week_returns_counts: response has deleted + protected_completed
- test_snapshot_hidden_from_library: is_assignment_snapshot=True not in library listing
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
    WorkoutBlock,
    WorkoutInterval,
    WorkoutLibrary,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
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


def _make_athlete(user, org):
    return Athlete.objects.create(user=user, organization=org)


def _make_library(org, name="Test Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _make_planned_workout(org, library, name="Test Workout"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
        session_type="base",
    )


def _make_assignment(org, athlete, planned_workout, scheduled_date=None, **kwargs):
    if scheduled_date is None:
        scheduled_date = datetime.date(2026, 5, 1)
    existing = WorkoutAssignment.objects.filter(
        organization=org,
        athlete=athlete,
        scheduled_date=scheduled_date,
    ).count()
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=scheduled_date,
        day_order=existing + 1,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------


class PR145fCRUDTestCase(TestCase):
    def setUp(self):
        self.org = _make_org("pr145f-org")
        self.coach_user = _make_user("coach145f")
        _make_membership(self.coach_user, self.org, "coach")

        self.athlete_user = _make_user("athlete145f")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)

        self.athlete2_user = _make_user("athlete145f_2")
        _make_membership(self.athlete2_user, self.org, "athlete")
        self.athlete2 = _make_athlete(self.athlete2_user, self.org)

        self.library = _make_library(self.org)
        self.workout = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(self.org, self.athlete, self.workout)

        self.client = APIClient()
        self.base_url = f"/api/p1/orgs/{self.org.id}/assignments/"
        self.detail_url = f"{self.base_url}{self.assignment.id}/"

    # -------------------------------------------------------------------------
    # Move (drag-to-move): PATCH scheduled_date
    # -------------------------------------------------------------------------

    def test_move_assignment(self):
        self.client.force_authenticate(user=self.coach_user)
        new_date = "2026-05-10"
        response = self.client.patch(
            self.detail_url, {"scheduled_date": new_date}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(str(self.assignment.scheduled_date), new_date)

    # -------------------------------------------------------------------------
    # DELETE individual session
    # -------------------------------------------------------------------------

    def test_cannot_delete_completed(self):
        self.assignment.status = "completed"
        self.assignment.save(update_fields=["status"])
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(WorkoutAssignment.objects.filter(pk=self.assignment.pk).exists())

    def test_delete_planned(self):
        self.client.force_authenticate(user=self.coach_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkoutAssignment.objects.filter(pk=self.assignment.pk).exists())

    # -------------------------------------------------------------------------
    # Clone workout
    # -------------------------------------------------------------------------

    def test_clone_workout(self):
        self.client.force_authenticate(user=self.coach_user)
        url = f"{self.detail_url}clone-workout/"
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, 200)

        self.assignment.refresh_from_db()
        # Assignment now points to the clone, not the original
        self.assertNotEqual(self.assignment.planned_workout_id, self.workout.id)
        # Clone is a snapshot
        clone = self.assignment.planned_workout
        self.assertTrue(clone.is_assignment_snapshot)
        self.assertIsNone(clone.library)
        # Original is untouched
        self.workout.refresh_from_db()
        self.assertFalse(self.workout.is_assignment_snapshot)
        self.assertIsNotNone(self.workout.library)

    def test_clone_preserves_blocks(self):
        # Add a block to original
        block = WorkoutBlock.objects.create(
            organization=self.org,
            planned_workout=self.workout,
            name="Warm up",
            block_type="warmup",
            order_index=1,
        )
        # Add an interval
        WorkoutInterval.objects.create(
            organization=self.org,
            block=block,
            description="Easy jog",
            duration_seconds=600,
            order_index=1,
        )

        self.client.force_authenticate(user=self.coach_user)
        url = f"{self.detail_url}clone-workout/"
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, 200)

        self.assignment.refresh_from_db()
        clone = self.assignment.planned_workout
        self.assertEqual(clone.blocks.count(), 1)
        self.assertEqual(clone.blocks.first().intervals.count(), 1)

    def test_clone_already_snapshot_returns_same(self):
        # First clone
        self.client.force_authenticate(user=self.coach_user)
        url = f"{self.detail_url}clone-workout/"
        self.client.post(url, format="json")

        self.assignment.refresh_from_db()
        first_clone_id = self.assignment.planned_workout_id

        # Second clone → should return same snapshot (no double clone)
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.planned_workout_id, first_clone_id)
        self.assertEqual(
            PlannedWorkout.objects.filter(is_assignment_snapshot=True).count(), 1
        )

    # -------------------------------------------------------------------------
    # Copy week
    # -------------------------------------------------------------------------

    def test_copy_week_same_athlete(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "source_athlete_id": self.athlete.id,
            "source_date_from": "2026-05-01",
            "source_date_to": "2026-05-07",
            "target_athlete_id": self.athlete.id,
            "target_week_start": "2026-05-11",
        }
        response = self.client.post(f"{self.base_url}copy-week/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data), 1)
        copied = WorkoutAssignment.objects.get(pk=response.data[0]["id"])
        self.assertEqual(str(copied.scheduled_date), "2026-05-11")
        self.assertEqual(copied.athlete, self.athlete)

    def test_copy_week_different_athlete(self):
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "source_athlete_id": self.athlete.id,
            "source_date_from": "2026-05-01",
            "source_date_to": "2026-05-07",
            "target_athlete_id": self.athlete2.id,
            "target_week_start": "2026-05-11",
        }
        response = self.client.post(f"{self.base_url}copy-week/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        copied = WorkoutAssignment.objects.get(pk=response.data[0]["id"])
        self.assertEqual(copied.athlete, self.athlete2)

    def test_copy_week_includes_completed_assignments(self):
        """
        PR-145f-fix: copy_week copies ALL assignments (planned + completed).
        New assignments always have status=PLANNED and no actual_* data.
        """
        # Mark the existing assignment as completed with actual data
        self.assignment.status = "completed"
        self.assignment.actual_duration_seconds = 3600
        self.assignment.actual_distance_meters = 10000
        self.assignment.rpe = 4
        self.assignment.save(update_fields=["status", "actual_duration_seconds", "actual_distance_meters", "rpe"])

        # Add a second planned assignment in the same week
        workout2 = _make_planned_workout(self.org, self.library, name="Session B")
        _make_assignment(
            self.org, self.athlete, workout2,
            scheduled_date=datetime.date(2026, 5, 3),
        )

        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "source_athlete_id": self.athlete.id,
            "source_date_from": "2026-05-01",
            "source_date_to": "2026-05-07",
            "target_athlete_id": self.athlete2.id,
            "target_week_start": "2026-05-11",
        }
        response = self.client.post(f"{self.base_url}copy-week/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        # Both assignments (completed + planned) must be copied
        self.assertEqual(len(response.data), 2)
        # All copies are PLANNED with no actual data
        for item in response.data:
            self.assertEqual(item["status"], "planned")
            self.assertIsNone(item["actual_duration_seconds"])
            self.assertIsNone(item["actual_distance_meters"])
            self.assertIsNone(item["rpe"])

    def test_copy_week_day_order(self):
        # Two assignments on same day
        workout2 = _make_planned_workout(self.org, self.library, name="Session B")
        _make_assignment(
            self.org, self.athlete, workout2,
            scheduled_date=datetime.date(2026, 5, 1),
        )
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "source_athlete_id": self.athlete.id,
            "source_date_from": "2026-05-01",
            "source_date_to": "2026-05-07",
            "target_athlete_id": self.athlete2.id,
            "target_week_start": "2026-05-11",
        }
        response = self.client.post(f"{self.base_url}copy-week/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        day_orders = sorted(item["day_order"] for item in response.data)
        self.assertEqual(day_orders, [1, 2])

    # -------------------------------------------------------------------------
    # Delete week
    # -------------------------------------------------------------------------

    def test_delete_week_protects_completed(self):
        # Mark the assignment as completed
        self.assignment.status = "completed"
        self.assignment.save(update_fields=["status"])
        # Add a planned assignment in the same week
        planned = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 5, 3),
        )
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete.id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-07",
        }
        response = self.client.post(f"{self.base_url}delete-week/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        # Completed must survive
        self.assertTrue(WorkoutAssignment.objects.filter(pk=self.assignment.pk).exists())
        # Planned must be deleted
        self.assertFalse(WorkoutAssignment.objects.filter(pk=planned.pk).exists())

    def test_delete_week_returns_counts(self):
        self.assignment.status = "completed"
        self.assignment.save(update_fields=["status"])
        planned = _make_assignment(
            self.org, self.athlete, self.workout,
            scheduled_date=datetime.date(2026, 5, 3),
        )
        self.client.force_authenticate(user=self.coach_user)
        payload = {
            "athlete_id": self.athlete.id,
            "date_from": "2026-05-01",
            "date_to": "2026-05-07",
        }
        response = self.client.post(f"{self.base_url}delete-week/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted"], 1)
        self.assertEqual(response.data["protected_completed"], 1)

    # -------------------------------------------------------------------------
    # PR-145f-fix2: update-snapshot endpoint
    # -------------------------------------------------------------------------

    def _make_snapshot(self):
        """Helper: clone self.assignment's workout into a snapshot."""
        self.client.force_authenticate(user=self.coach_user)
        self.client.post(f"{self.detail_url}clone-workout/", format="json")
        self.assignment.refresh_from_db()
        return self.assignment.planned_workout

    def test_update_snapshot_patches_workout_name(self):
        """PATCH update-snapshot changes snapshot name; original library workout untouched."""
        snapshot = self._make_snapshot()
        original_name = self.workout.name

        url = f"{self.detail_url}update-snapshot/"
        response = self.client.patch(url, {"name": "Fartlek editado"}, format="json")
        self.assertEqual(response.status_code, 200)

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.name, "Fartlek editado")

        # Original library workout must be untouched
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, original_name)

    def test_update_snapshot_blocked_for_library_workout(self):
        """update-snapshot returns 400 when the assignment workout is NOT a snapshot."""
        self.client.force_authenticate(user=self.coach_user)
        # self.assignment.planned_workout is the original library workout (not snapshot)
        url = f"{self.detail_url}update-snapshot/"
        response = self.client.patch(url, {"name": "Should fail"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_update_snapshot_requires_write_role(self):
        """update-snapshot returns 403 for athlete role."""
        self._make_snapshot()
        # Authenticate as athlete
        self.client.force_authenticate(user=self.athlete_user)
        url = f"{self.detail_url}update-snapshot/"
        response = self.client.patch(url, {"name": "Hacked"}, format="json")
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # Snapshot hidden from library listing
    # -------------------------------------------------------------------------

    def test_snapshot_hidden_from_library(self):
        # Create a snapshot workout
        snapshot = PlannedWorkout.objects.create(
            organization=self.org,
            library=None,
            name="Snapshot Workout",
            discipline="run",
            session_type="base",
            is_assignment_snapshot=True,
        )
        self.client.force_authenticate(user=self.coach_user)
        url = f"/api/p1/orgs/{self.org.id}/libraries/{self.library.id}/workouts/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = [w["id"] for w in (response.data.get("results") or response.data)]
        self.assertNotIn(snapshot.id, ids)
        # Original workout (in library) must appear
        self.assertIn(self.workout.id, ids)
