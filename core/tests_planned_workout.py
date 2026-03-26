"""
Tests for PlannedWorkout, WorkoutBlock, and WorkoutInterval (PR-112).

Test classes:
  PlanNotRealInvariantTests       — domain law enforcement: planning ≠ execution
  PlannedWorkoutCreationTests     — basic model creation and field defaults
  PlannedWorkoutOrgConsistencyTests — library.organization must match workout.organization
  WorkoutBlockCreationTests       — block creation and ordering
  WorkoutBlockOrgConsistencyTests — block.organization must match workout.organization
  WorkoutIntervalCreationTests    — interval creation and ordering
  WorkoutIntervalOrgConsistencyTests — interval.organization must match block.organization
  WorkoutStructureConstraintTests — unique ordering constraints
  WorkoutStructureCascadeTests    — cascade delete behaviour
  LegacyCoexistenceTests          — Entrenamiento/legacy models unaffected
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    Organization,
    WorkoutLibrary,
    PlannedWorkout,
    WorkoutBlock,
    WorkoutInterval,
    Entrenamiento,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(username):
    return User.objects.create_user(username=username, password="x")


def _org(name="TestOrg"):
    return Organization.objects.create(name=name, slug=name.lower())


def _library(org, name="Lib", *, created_by=None):
    return WorkoutLibrary.objects.create(
        organization=org,
        name=name,
        created_by=created_by,
    )


def _workout(org, library, *, name="Workout A", discipline="run", session_type="base"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline=discipline,
        session_type=session_type,
    )


def _block(workout, *, order_index=0, block_type="warmup", name=""):
    return WorkoutBlock.objects.create(
        planned_workout=workout,
        organization=workout.organization,
        order_index=order_index,
        block_type=block_type,
        name=name,
    )


def _interval(block, *, order_index=0, metric_type="hr_zone"):
    return WorkoutInterval.objects.create(
        block=block,
        organization=block.organization,
        order_index=order_index,
        metric_type=metric_type,
    )


# ---------------------------------------------------------------------------
# Plan ≠ Real invariant tests  (MUST NOT be removed)
# ---------------------------------------------------------------------------

class PlanNotRealInvariantTests(TestCase):
    """
    Enforce the Plan ≠ Real invariant on the planning-side models.

    If these tests need to be removed to accommodate a feature, that
    feature violates the domain law and must be redesigned.
    """

    def test_planned_workout_has_no_actual_duration_field(self):
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        self.assertNotIn("actual_duration_seconds", field_names)
        self.assertNotIn("actual_duration_s", field_names)
        self.assertNotIn("duration_real", field_names)

    def test_planned_workout_has_no_actual_distance_field(self):
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        self.assertNotIn("actual_distance_meters", field_names)
        self.assertNotIn("actual_distance_m", field_names)
        self.assertNotIn("distance_real", field_names)

    def test_planned_workout_has_no_actual_hr_field(self):
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        self.assertNotIn("actual_hr", field_names)
        self.assertNotIn("avg_hr_bpm", field_names)
        self.assertNotIn("max_hr_bpm", field_names)

    def test_planned_workout_has_no_actual_power_field(self):
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        self.assertNotIn("actual_power_watts", field_names)
        self.assertNotIn("avg_power_watts", field_names)
        self.assertNotIn("normalized_power_watts", field_names)

    def test_planned_workout_has_no_completed_activity_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in PlannedWorkout._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("CompletedActivity", fk_targets)
        self.assertNotIn("Actividad", fk_targets)

    def test_planned_workout_has_no_completion_flag(self):
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        self.assertNotIn("completed", field_names)
        self.assertNotIn("is_completed", field_names)
        self.assertNotIn("completado", field_names)

    def test_planned_workout_estimated_duration_is_planning_only(self):
        """Verify that the estimated field name signals intent, not execution."""
        field = PlannedWorkout._meta.get_field("estimated_duration_seconds")
        self.assertIn("Planning only", field.help_text)

    def test_planned_workout_estimated_distance_is_planning_only(self):
        field = PlannedWorkout._meta.get_field("estimated_distance_meters")
        self.assertIn("Planning only", field.help_text)

    def test_workout_block_has_no_actual_fields(self):
        field_names = [f.name for f in WorkoutBlock._meta.get_fields()]
        self.assertNotIn("actual_duration_seconds", field_names)
        self.assertNotIn("actual_distance_meters", field_names)

    def test_workout_interval_has_no_actual_fields(self):
        field_names = [f.name for f in WorkoutInterval._meta.get_fields()]
        self.assertNotIn("actual_duration_seconds", field_names)
        self.assertNotIn("actual_distance_meters", field_names)
        self.assertNotIn("actual_hr", field_names)
        self.assertNotIn("actual_power", field_names)


# ---------------------------------------------------------------------------
# PlannedWorkout — creation + field defaults
# ---------------------------------------------------------------------------

class PlannedWorkoutCreationTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)

    def test_basic_creation(self):
        w = _workout(self.org, self.lib)
        self.assertEqual(w.organization, self.org)
        self.assertEqual(w.library, self.lib)
        self.assertEqual(w.name, "Workout A")
        self.assertEqual(w.discipline, "run")
        self.assertEqual(w.session_type, "base")

    def test_structure_version_defaults_to_1(self):
        w = _workout(self.org, self.lib)
        self.assertEqual(w.structure_version, 1)

    def test_session_type_defaults_to_other(self):
        w = PlannedWorkout.objects.create(
            organization=self.org,
            library=self.lib,
            name="Defaults Test",
            discipline="run",
        )
        self.assertEqual(w.session_type, PlannedWorkout.SessionType.OTHER)

    def test_estimated_fields_are_nullable(self):
        w = _workout(self.org, self.lib)
        self.assertIsNone(w.estimated_duration_seconds)
        self.assertIsNone(w.estimated_distance_meters)

    def test_estimated_fields_accept_values(self):
        w = PlannedWorkout.objects.create(
            organization=self.org,
            library=self.lib,
            name="Long Run",
            discipline="run",
            session_type="long",
            estimated_duration_seconds=5400,
            estimated_distance_meters=20000.0,
        )
        self.assertEqual(w.estimated_duration_seconds, 5400)
        self.assertEqual(w.estimated_distance_meters, 20000.0)

    def test_str_includes_name_discipline_and_version(self):
        w = _workout(self.org, self.lib, name="Tempo Run")
        s = str(w)
        self.assertIn("Tempo Run", s)
        self.assertIn("run", s)
        self.assertIn("v1", s)

    def test_discipline_choices(self):
        for choice_value, _ in PlannedWorkout.Discipline.choices:
            PlannedWorkout.objects.create(
                organization=self.org,
                library=self.lib,
                name=f"D-{choice_value}",
                discipline=choice_value,
            )

    def test_session_type_choices(self):
        for choice_value, _ in PlannedWorkout.SessionType.choices:
            PlannedWorkout.objects.create(
                organization=self.org,
                library=self.lib,
                name=f"S-{choice_value}",
                discipline="run",
                session_type=choice_value,
            )


# ---------------------------------------------------------------------------
# PlannedWorkout — org consistency enforcement
# ---------------------------------------------------------------------------

class PlannedWorkoutOrgConsistencyTests(TestCase):

    def test_workout_org_matches_library_org(self):
        org = _org("Org1")
        lib = _library(org)
        w = _workout(org, lib)
        self.assertEqual(w.organization, lib.organization)

    def test_cross_org_workout_raises_validation_error(self):
        org1 = _org("OrgA")
        org2 = _org("OrgB")
        lib_for_org1 = _library(org1, name="LibA")
        with self.assertRaises(ValidationError):
            PlannedWorkout.objects.create(
                organization=org2,  # different org from library
                library=lib_for_org1,
                name="Cross-org workout",
                discipline="run",
            )


# ---------------------------------------------------------------------------
# WorkoutBlock — creation and ordering
# ---------------------------------------------------------------------------

class WorkoutBlockCreationTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

    def test_basic_creation(self):
        b = _block(self.workout, order_index=0, block_type="warmup")
        self.assertEqual(b.planned_workout, self.workout)
        self.assertEqual(b.organization, self.org)
        self.assertEqual(b.block_type, "warmup")
        self.assertEqual(b.order_index, 0)

    def test_block_type_choices(self):
        for i, (choice_value, _) in enumerate(WorkoutBlock.BlockType.choices):
            WorkoutBlock.objects.create(
                planned_workout=self.workout,
                organization=self.org,
                order_index=i + 10,  # avoid collision with setUp block
                block_type=choice_value,
            )

    def test_video_url_blank_by_default(self):
        b = _block(self.workout)
        self.assertEqual(b.video_url, "")

    def test_video_url_accepts_url(self):
        b = WorkoutBlock.objects.create(
            planned_workout=self.workout,
            organization=self.org,
            order_index=99,
            block_type="strength",
            video_url="https://example.com/video.mp4",
        )
        self.assertEqual(b.video_url, "https://example.com/video.mp4")

    def test_str_includes_block_type_and_workout(self):
        b = _block(self.workout, block_type="main")
        s = str(b)
        self.assertIn("main", s)

    def test_blocks_ordered_by_order_index(self):
        _block(self.workout, order_index=2, block_type="cooldown")
        _block(self.workout, order_index=0, block_type="warmup")
        _block(self.workout, order_index=1, block_type="main")
        blocks = list(WorkoutBlock.objects.filter(planned_workout=self.workout))
        self.assertEqual([b.order_index for b in blocks], [0, 1, 2])


# ---------------------------------------------------------------------------
# WorkoutBlock — org consistency enforcement
# ---------------------------------------------------------------------------

class WorkoutBlockOrgConsistencyTests(TestCase):

    def test_cross_org_block_raises_validation_error(self):
        org1 = _org("OrgX")
        org2 = _org("OrgY")
        lib = _library(org1)
        workout = _workout(org1, lib)
        with self.assertRaises(ValidationError):
            WorkoutBlock.objects.create(
                planned_workout=workout,
                organization=org2,  # mismatch
                order_index=0,
                block_type="warmup",
            )


# ---------------------------------------------------------------------------
# WorkoutInterval — creation and ordering
# ---------------------------------------------------------------------------

class WorkoutIntervalCreationTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.block = _block(self.workout, order_index=0, block_type="main")

    def test_basic_creation(self):
        iv = _interval(self.block, order_index=0, metric_type="hr_zone")
        self.assertEqual(iv.block, self.block)
        self.assertEqual(iv.organization, self.org)
        self.assertEqual(iv.metric_type, "hr_zone")
        self.assertEqual(iv.order_index, 0)

    def test_metric_type_choices(self):
        for i, (choice_value, _) in enumerate(WorkoutInterval.MetricType.choices):
            WorkoutInterval.objects.create(
                block=self.block,
                organization=self.org,
                order_index=i + 10,
                metric_type=choice_value,
            )

    def test_prescription_fields_nullable(self):
        iv = _interval(self.block)
        self.assertIsNone(iv.duration_seconds)
        self.assertIsNone(iv.distance_meters)
        self.assertIsNone(iv.target_value_low)
        self.assertIsNone(iv.target_value_high)
        self.assertIsNone(iv.recovery_seconds)
        self.assertIsNone(iv.recovery_distance_meters)

    def test_prescription_fields_accept_values(self):
        iv = WorkoutInterval.objects.create(
            block=self.block,
            organization=self.org,
            order_index=5,
            metric_type="power",
            duration_seconds=300,
            distance_meters=1000.0,
            target_value_low=250.0,
            target_value_high=280.0,
            target_label="FTP 95–105%",
            recovery_seconds=120,
        )
        self.assertEqual(iv.duration_seconds, 300)
        self.assertEqual(iv.target_label, "FTP 95–105%")

    def test_video_url_blank_by_default(self):
        iv = _interval(self.block)
        self.assertEqual(iv.video_url, "")

    def test_intervals_ordered_by_order_index(self):
        _interval(self.block, order_index=2)
        _interval(self.block, order_index=0)
        _interval(self.block, order_index=1)
        intervals = list(WorkoutInterval.objects.filter(block=self.block))
        self.assertEqual([iv.order_index for iv in intervals], [0, 1, 2])


# ---------------------------------------------------------------------------
# WorkoutInterval — org consistency enforcement
# ---------------------------------------------------------------------------

class WorkoutIntervalOrgConsistencyTests(TestCase):

    def test_cross_org_interval_raises_validation_error(self):
        org1 = _org("OrgP")
        org2 = _org("OrgQ")
        lib = _library(org1)
        workout = _workout(org1, lib)
        block = _block(workout)
        with self.assertRaises(ValidationError):
            WorkoutInterval.objects.create(
                block=block,
                organization=org2,  # mismatch
                order_index=0,
                metric_type="pace",
            )


# ---------------------------------------------------------------------------
# Ordering constraint tests
# ---------------------------------------------------------------------------

class WorkoutStructureConstraintTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

    def test_duplicate_block_order_index_raises(self):
        _block(self.workout, order_index=0, block_type="warmup")
        with self.assertRaises((IntegrityError, ValidationError)):
            WorkoutBlock.objects.create(
                planned_workout=self.workout,
                organization=self.org,
                order_index=0,
                block_type="main",
            )

    def test_same_block_order_allowed_in_different_workouts(self):
        w2 = _workout(self.org, self.lib, name="Workout B")
        _block(self.workout, order_index=0, block_type="warmup")
        _block(w2, order_index=0, block_type="warmup")  # must not raise

    def test_duplicate_interval_order_index_raises(self):
        block = _block(self.workout, order_index=0)
        _interval(block, order_index=0)
        with self.assertRaises((IntegrityError, ValidationError)):
            WorkoutInterval.objects.create(
                block=block,
                organization=self.org,
                order_index=0,
                metric_type="pace",
            )

    def test_same_interval_order_allowed_in_different_blocks(self):
        block1 = _block(self.workout, order_index=0, block_type="warmup")
        block2 = _block(self.workout, order_index=1, block_type="main")
        _interval(block1, order_index=0)
        _interval(block2, order_index=0)  # must not raise


# ---------------------------------------------------------------------------
# Cascade delete tests
# ---------------------------------------------------------------------------

class WorkoutStructureCascadeTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.block = _block(self.workout, order_index=0)
        self.interval = _interval(self.block, order_index=0)

    def test_deleting_workout_cascades_to_blocks(self):
        workout_id = self.workout.pk
        self.workout.delete()
        self.assertFalse(WorkoutBlock.objects.filter(planned_workout_id=workout_id).exists())

    def test_deleting_workout_cascades_to_intervals(self):
        interval_id = self.interval.pk
        self.workout.delete()
        self.assertFalse(WorkoutInterval.objects.filter(pk=interval_id).exists())

    def test_deleting_block_cascades_to_intervals(self):
        block_id = self.block.pk
        self.block.delete()
        self.assertFalse(WorkoutInterval.objects.filter(block_id=block_id).exists())

    def test_deleting_library_orphans_workouts(self):
        """
        PR-145f: library FK is now SET_NULL (was CASCADE) to support
        is_assignment_snapshot workouts that have library=None.
        Deleting a library no longer deletes its workouts — they become orphaned
        with library=None instead.
        """
        workout_id = self.workout.pk
        self.lib.delete()
        # Workout still exists, library reference nulled out
        self.assertTrue(PlannedWorkout.objects.filter(pk=workout_id).exists())
        self.assertIsNone(PlannedWorkout.objects.get(pk=workout_id).library)


# ---------------------------------------------------------------------------
# Legacy coexistence — Entrenamiento must not be modified
# ---------------------------------------------------------------------------

class LegacyCoexistenceTests(TestCase):

    def test_entrenamiento_model_unaffected(self):
        """Verify legacy Entrenamiento model still exists and has its original fields."""
        field_names = [f.name for f in Entrenamiento._meta.get_fields()]
        # Legacy fields that must remain
        self.assertIn("alumno", field_names)
        self.assertIn("titulo", field_names)
        self.assertIn("completado", field_names)

    def test_planned_workout_and_entrenamiento_are_independent(self):
        """PlannedWorkout must not carry any FK pointing to Entrenamiento."""
        fk_targets = [
            f.related_model.__name__
            for f in PlannedWorkout._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("Entrenamiento", fk_targets)
