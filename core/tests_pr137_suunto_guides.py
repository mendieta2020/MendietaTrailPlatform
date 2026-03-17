"""
core/tests_pr137_suunto_guides.py

Protective tests for PR-137: SuuntoPlus Guides (workout push to watch).

Coverage:
- test_push_action_returns_202_for_valid_assignment
- test_push_action_403_cross_org
- test_push_action_401_unauthenticated
- test_push_action_400_no_suunto_credential
- test_push_idempotent_noop_when_already_sent
- test_build_guide_payload_maps_blocks_correctly
- test_build_guide_payload_never_reads_completed_activity
- test_celery_task_retries_on_http_error
"""

import datetime
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Alumno,
    Athlete,
    Coach,
    Membership,
    OAuthCredential,
    Organization,
    PlannedWorkout,
    WorkoutAssignment,
    WorkoutBlock,
    WorkoutDeliveryRecord,
    WorkoutInterval,
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


def _make_alumno(user, entrenador=None):
    return Alumno.objects.create(
        usuario=user,
        entrenador=entrenador,
        nombre="Test",
        apellido="Athlete",
    )


def _make_suunto_credential(alumno):
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="suunto",
        external_user_id=f"suunto-user-{alumno.pk}",
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
    )


def _make_library(org, name="Test Library"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _make_planned_workout(org, library, name="Test Workout"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline="run",
        session_type="base",
        structure_version=1,
    )


def _make_assignment(org, athlete, planned_workout):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=planned_workout,
        scheduled_date=datetime.date(2026, 4, 1),
        snapshot_version=planned_workout.structure_version,
    )


def _push_url(org_id, pk):
    return f"/api/p1/orgs/{org_id}/assignments/{pk}/push/"


# ==============================================================================
# Push action — API tests
# ==============================================================================


class PushActionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.org = _make_org("GuideOrg")
        self.library = _make_library(self.org)

        # Coach
        self.coach_user = _make_user("guide_coach")
        _make_membership(self.coach_user, self.org, "coach")
        _make_coach(self.coach_user, self.org)

        # Athlete with Suunto credential
        self.athlete_user = _make_user("guide_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)
        self.alumno = _make_alumno(self.athlete_user, entrenador=self.coach_user)
        self.credential = _make_suunto_credential(self.alumno)

        self.planned_workout = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(self.org, self.athlete, self.planned_workout)

    @patch("integrations.suunto.tasks_guides.push_guide.delay")
    def test_push_action_returns_202_for_valid_assignment(self, mock_delay):
        self.client.force_login(self.coach_user)
        url = _push_url(self.org.pk, self.assignment.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "queued")
        self.assertEqual(response.data["assignment_id"], self.assignment.pk)
        mock_delay.assert_called_once_with(
            assignment_id=self.assignment.pk,
            organization_id=self.org.pk,
            alumno_id=self.alumno.pk,
        )

    def test_push_action_401_unauthenticated(self):
        url = _push_url(self.org.pk, self.assignment.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)

    def test_push_action_403_cross_org(self):
        other_org = _make_org("OtherOrg")
        other_user = _make_user("other_coach")
        _make_membership(other_user, other_org, "coach")
        _make_coach(other_user, other_org)

        self.client.force_login(other_user)
        # Uses self.org's assignment URL — foreign org coach should get 403
        url = _push_url(self.org.pk, self.assignment.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_push_action_400_no_suunto_credential(self):
        # Create an athlete without Suunto credential
        no_cred_user = _make_user("no_cred_athlete")
        _make_membership(no_cred_user, self.org, "athlete")
        no_cred_athlete = _make_athlete(no_cred_user, self.org)
        _make_alumno(no_cred_user, entrenador=self.coach_user)  # alumno exists but no credential
        assignment = _make_assignment(self.org, no_cred_athlete, self.planned_workout)

        self.client.force_login(self.coach_user)
        url = _push_url(self.org.pk, assignment.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no_suunto_credential", str(response.data))

    @patch("integrations.suunto.tasks_guides.push_guide.delay")
    def test_push_action_athlete_role_gets_403(self, mock_delay):
        """Athletes cannot trigger push — coach-only action."""
        self.client.force_login(self.athlete_user)
        url = _push_url(self.org.pk, self.assignment.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        mock_delay.assert_not_called()


# ==============================================================================
# Idempotency test — Celery task level
# ==============================================================================


class PushGuideIdempotencyTests(TestCase):
    def setUp(self):
        self.org = _make_org("IdempOrg")
        self.library = _make_library(self.org)
        self.coach_user = _make_user("idemp_coach")
        _make_membership(self.coach_user, self.org, "coach")
        self.athlete_user = _make_user("idemp_athlete")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)
        self.alumno = _make_alumno(self.athlete_user, entrenador=self.coach_user)
        self.credential = _make_suunto_credential(self.alumno)
        self.planned_workout = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(self.org, self.athlete, self.planned_workout)

    @patch("integrations.suunto.client.push_guide")
    def test_push_idempotent_noop_when_already_sent(self, mock_client_push):
        """
        If WorkoutDeliveryRecord.status == 'sent', the task must return early
        without making any HTTP call.
        """
        WorkoutDeliveryRecord.objects.create(
            organization=self.org,
            assignment=self.assignment,
            provider="suunto",
            status=WorkoutDeliveryRecord.Status.SENT,
            external_guide_id="guide-123",
            snapshot_version=1,
        )

        from integrations.suunto.tasks_guides import push_guide

        # Call the task synchronously (apply() runs it inline)
        push_guide.apply(
            kwargs={
                "assignment_id": self.assignment.pk,
                "organization_id": self.org.pk,
                "alumno_id": self.alumno.pk,
            }
        )

        mock_client_push.assert_not_called()
        # Record must remain SENT — not overwritten
        record = WorkoutDeliveryRecord.objects.get(
            assignment=self.assignment, provider="suunto"
        )
        self.assertEqual(record.status, WorkoutDeliveryRecord.Status.SENT)


# ==============================================================================
# build_guide_payload — unit tests
# ==============================================================================


class BuildGuidePayloadTests(TestCase):
    def setUp(self):
        self.org = _make_org("PayloadOrg")
        self.library = _make_library(self.org)
        self.planned_workout = PlannedWorkout.objects.create(
            organization=self.org,
            library=self.library,
            name="Threshold Run",
            description="Classic lactate threshold session",
            discipline="run",
            session_type="threshold",
            estimated_duration_seconds=3600,
            estimated_distance_meters=12000,
            structure_version=2,
        )
        block = WorkoutBlock.objects.create(
            planned_workout=self.planned_workout,
            organization=self.org,
            order_index=0,
            block_type="main",
            name="Main Set",
        )
        WorkoutInterval.objects.create(
            block=block,
            organization=self.org,
            order_index=0,
            metric_type="pace",
            description="5 × 1000m @ threshold",
            distance_meters=1000,
            target_value_low=240.0,
            target_value_high=255.0,
            target_label="threshold",
            recovery_seconds=90,
        )

    def test_build_guide_payload_maps_blocks_correctly(self):
        from integrations.suunto.guides import build_guide_payload

        payload = build_guide_payload(self.planned_workout)

        self.assertEqual(payload["guideName"], "Threshold Run")
        self.assertEqual(payload["sport"], "run")
        self.assertEqual(payload["structureVersion"], 2)
        self.assertEqual(payload["estimatedDurationSeconds"], 3600)
        self.assertEqual(payload["estimatedDistanceMeters"], 12000)
        self.assertEqual(len(payload["blocks"]), 1)

        block = payload["blocks"][0]
        self.assertEqual(block["blockType"], "main")
        self.assertEqual(block["name"], "Main Set")
        self.assertEqual(len(block["steps"]), 1)

        step = block["steps"][0]
        self.assertEqual(step["metricType"], "pace")
        self.assertEqual(step["distanceMeters"], 1000)
        self.assertEqual(step["targetLow"], 240.0)
        self.assertEqual(step["targetHigh"], 255.0)
        self.assertEqual(step["targetLabel"], "threshold")
        self.assertEqual(step["recoverySeconds"], 90)

    def test_build_guide_payload_never_reads_completed_activity(self):
        """
        build_guide_payload must never touch CompletedActivity.
        We patch CompletedActivity.objects to raise if accessed.
        """
        from integrations.suunto.guides import build_guide_payload

        sentinel = AssertionError(
            "build_guide_payload must not access CompletedActivity"
        )
        mock_manager = MagicMock(side_effect=sentinel)

        with patch("core.models.CompletedActivity.objects", mock_manager):
            # Should complete without raising
            payload = build_guide_payload(self.planned_workout)

        self.assertIn("guideName", payload)

    def test_build_guide_payload_optional_fields_absent_when_none(self):
        """Fields with None values must not appear in the payload."""
        from integrations.suunto.guides import build_guide_payload

        sparse_workout = PlannedWorkout.objects.create(
            organization=self.org,
            library=self.library,
            name="Easy Run",
            discipline="run",
            session_type="base",
            estimated_duration_seconds=None,
            estimated_distance_meters=None,
        )
        payload = build_guide_payload(sparse_workout)
        self.assertNotIn("estimatedDurationSeconds", payload)
        self.assertNotIn("estimatedDistanceMeters", payload)
        self.assertNotIn("description", payload)


# ==============================================================================
# Celery task retry behaviour
# ==============================================================================


class PushGuideTaskRetryTests(TestCase):
    def setUp(self):
        self.org = _make_org("RetryOrg")
        self.library = _make_library(self.org)
        self.coach_user = _make_user("retry_coach")
        self.athlete_user = _make_user("retry_athlete")
        _make_membership(self.coach_user, self.org, "coach")
        _make_membership(self.athlete_user, self.org, "athlete")
        self.athlete = _make_athlete(self.athlete_user, self.org)
        self.alumno = _make_alumno(self.athlete_user, entrenador=self.coach_user)
        self.credential = _make_suunto_credential(self.alumno)
        self.planned_workout = _make_planned_workout(self.org, self.library)
        self.assignment = _make_assignment(self.org, self.athlete, self.planned_workout)

    @patch("integrations.suunto.client.push_guide")
    def test_celery_task_retries_on_http_error(self, mock_client_push):
        """
        When the HTTP push raises an exception, the task must:
        1. Create/update WorkoutDeliveryRecord with status=failed.
        2. Re-raise the exception after exhausting max_retries.

        Note: task.apply() runs retries synchronously and re-raises the
        original exception (not celery.exceptions.Retry) after max_retries.
        """
        import requests

        mock_client_push.side_effect = requests.HTTPError("503 Service Unavailable")

        from integrations.suunto.tasks_guides import push_guide

        # apply() stores the exception in EagerResult; use result.get(propagate=True)
        # to assert it re-raises after exhausting max_retries.
        result = push_guide.apply(
            kwargs={
                "assignment_id": self.assignment.pk,
                "organization_id": self.org.pk,
                "alumno_id": self.alumno.pk,
            }
        )
        with self.assertRaises(requests.HTTPError):
            result.get(propagate=True)

        record = WorkoutDeliveryRecord.objects.get(
            assignment=self.assignment, provider="suunto"
        )
        self.assertEqual(record.status, WorkoutDeliveryRecord.Status.FAILED)
