"""
Tests for WorkoutAssignment model and services_workout.py (PR-113).

Test classes:
  PlanNotRealAssignmentTests          — domain law: assignment stores no execution data
  WorkoutAssignmentCreationTests      — basic model creation and field defaults
  WorkoutAssignmentOrgConsistencyTests — cross-org invariant enforcement
  WorkoutAssignmentConstraintTests    — unique (athlete, scheduled_date, day_order)
  MultipleSameDaySessionTests         — ordered same-day assignment support
  EffectiveDateTests                  — effective_date property behaviour
  ServiceAssignTests                  — assign_workout_to_athlete()
  ServiceMoveTests                    — move_workout_assignment()
  ServicePersonalizeTests             — personalize_workout_assignment()
  ServiceAthleteNoteTests             — add_athlete_note_to_assignment()
  TemplateIntegrityTests              — PlannedWorkout never mutated by services
  LegacyCoexistenceTests              — legacy models unaffected
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    Organization,
    WorkoutLibrary,
    PlannedWorkout,
    WorkoutAssignment,
    Entrenamiento,
)
from core.services_workout import (
    assign_workout_to_athlete,
    move_workout_assignment,
    personalize_workout_assignment,
    add_athlete_note_to_assignment,
)

User = get_user_model()

TODAY = datetime.date(2026, 3, 9)
TOMORROW = TODAY + datetime.timedelta(days=1)
NEXT_WEEK = TODAY + datetime.timedelta(days=7)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(username):
    return User.objects.create_user(username=username, password="x")


def _org(name="TestOrg"):
    return Organization.objects.create(name=name, slug=name.lower().replace(" ", "-"))


def _athlete(org, username=None):
    from core.models import Athlete
    user = _user(username or f"ath_{org.slug}")
    return Athlete.objects.create(user=user, organization=org)


def _library(org, name="Lib"):
    return WorkoutLibrary.objects.create(organization=org, name=name)


def _workout(org, library, *, name="Test Workout", discipline="run"):
    return PlannedWorkout.objects.create(
        organization=org,
        library=library,
        name=name,
        discipline=discipline,
        session_type="base",
    )


def _assignment(org, athlete, workout, *, scheduled_date=None, day_order=1, **kwargs):
    return WorkoutAssignment.objects.create(
        organization=org,
        athlete=athlete,
        planned_workout=workout,
        scheduled_date=scheduled_date or TODAY,
        day_order=day_order,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Plan ≠ Real invariant tests  (MUST NOT be removed)
# ---------------------------------------------------------------------------

class PlanNotRealAssignmentTests(TestCase):
    """
    Enforce the Plan ≠ Real invariant on WorkoutAssignment.

    These tests assert that no execution outcome data lives on the
    assignment model. If any test here needs to be removed to accommodate
    a feature request, that feature violates the domain law and must be
    redesigned.
    """

    def test_no_actual_distance_field(self):
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        self.assertNotIn("actual_distance", field_names)
        self.assertNotIn("actual_distance_meters", field_names)
        self.assertNotIn("actual_distance_m", field_names)

    def test_no_actual_duration_field(self):
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        self.assertNotIn("actual_duration", field_names)
        self.assertNotIn("actual_duration_seconds", field_names)
        self.assertNotIn("actual_duration_s", field_names)

    def test_no_actual_hr_field(self):
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        self.assertNotIn("actual_hr", field_names)
        self.assertNotIn("avg_hr_bpm", field_names)
        self.assertNotIn("max_hr_bpm", field_names)

    def test_no_actual_power_field(self):
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        self.assertNotIn("actual_power_watts", field_names)
        self.assertNotIn("avg_power_watts", field_names)
        self.assertNotIn("normalized_power_watts", field_names)

    def test_no_completed_activity_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in WorkoutAssignment._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("CompletedActivity", fk_targets)
        self.assertNotIn("Actividad", fk_targets)

    def test_no_provider_fields(self):
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        self.assertNotIn("provider", field_names)
        self.assertNotIn("provider_activity_id", field_names)
        self.assertNotIn("raw_payload", field_names)

    def test_no_actual_prefix_fields(self):
        """Brute-force: no field on WorkoutAssignment starts with 'actual_'."""
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        actual_fields = [n for n in field_names if n.startswith("actual_")]
        self.assertEqual(
            actual_fields, [],
            f"Found actual_ fields on WorkoutAssignment: {actual_fields}",
        )

    def test_status_is_operational_not_execution_payload(self):
        """Status tracks workflow state, not athletic performance."""
        field = WorkoutAssignment._meta.get_field("status")
        # Verify the field holds only operational lifecycle choices
        choice_values = [c[0] for c in WorkoutAssignment.Status.choices]
        for v in choice_values:
            self.assertIn(v, ["planned", "moved", "completed", "skipped", "canceled"])


# ---------------------------------------------------------------------------
# Basic creation and field defaults
# ---------------------------------------------------------------------------

class WorkoutAssignmentCreationTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

    def test_basic_creation(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.organization, self.org)
        self.assertEqual(a.athlete, self.athlete)
        self.assertEqual(a.planned_workout, self.workout)
        self.assertEqual(a.scheduled_date, TODAY)
        self.assertEqual(a.day_order, 1)

    def test_status_defaults_to_planned(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.status, WorkoutAssignment.Status.PLANNED)

    def test_day_order_defaults_to_1(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.day_order, 1)

    def test_athlete_moved_date_defaults_to_null(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertIsNone(a.athlete_moved_date)

    def test_notes_default_blank(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.coach_notes, "")
        self.assertEqual(a.athlete_notes, "")

    def test_override_fields_default_blank_or_null(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.target_zone_override, "")
        self.assertEqual(a.target_pace_override, "")
        self.assertIsNone(a.target_rpe_override)
        self.assertIsNone(a.target_power_override)

    def test_snapshot_version_defaults_to_1(self):
        a = _assignment(self.org, self.athlete, self.workout)
        self.assertEqual(a.snapshot_version, 1)

    def test_str_includes_athlete_and_workout(self):
        a = _assignment(self.org, self.athlete, self.workout)
        s = str(a)
        self.assertIn(str(self.athlete.pk), s)
        self.assertIn(str(self.workout.pk), s)

    def test_status_choices_complete(self):
        values = {c[0] for c in WorkoutAssignment.Status.choices}
        self.assertEqual(values, {"planned", "moved", "completed", "skipped", "canceled"})


# ---------------------------------------------------------------------------
# Org consistency enforcement (clean)
# ---------------------------------------------------------------------------

class WorkoutAssignmentOrgConsistencyTests(TestCase):

    def test_cross_org_athlete_raises_validation_error(self):
        org1 = _org("OrgA")
        org2 = _org("OrgB")
        athlete_org2 = _athlete(org2, username="ath_b")
        lib = _library(org1)
        workout = _workout(org1, lib)
        with self.assertRaises(ValidationError):
            WorkoutAssignment.objects.create(
                organization=org1,
                athlete=athlete_org2,  # wrong org
                planned_workout=workout,
                scheduled_date=TODAY,
                day_order=1,
            )

    def test_cross_org_planned_workout_raises_validation_error(self):
        org1 = _org("OrgC")
        org2 = _org("OrgD")
        athlete = _athlete(org1, username="ath_c")
        lib_org2 = _library(org2, name="LibD")
        workout_org2 = _workout(org2, lib_org2, name="Org2 Workout")
        with self.assertRaises(ValidationError):
            WorkoutAssignment.objects.create(
                organization=org1,
                athlete=athlete,
                planned_workout=workout_org2,  # wrong org
                scheduled_date=TODAY,
                day_order=1,
            )

    def test_same_org_succeeds(self):
        org = _org("OrgOK")
        athlete = _athlete(org, username="ath_ok")
        lib = _library(org)
        workout = _workout(org, lib)
        a = WorkoutAssignment.objects.create(
            organization=org,
            athlete=athlete,
            planned_workout=workout,
            scheduled_date=TODAY,
            day_order=1,
        )
        self.assertIsNotNone(a.pk)


# ---------------------------------------------------------------------------
# Unique constraint: (athlete, scheduled_date, day_order)
# ---------------------------------------------------------------------------

class WorkoutAssignmentConstraintTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

    def test_duplicate_athlete_date_order_raises(self):
        _assignment(self.org, self.athlete, self.workout, day_order=1)
        with self.assertRaises((IntegrityError, ValidationError)):
            workout2 = _workout(self.org, self.lib, name="Workout 2")
            WorkoutAssignment.objects.create(
                organization=self.org,
                athlete=self.athlete,
                planned_workout=workout2,
                scheduled_date=TODAY,
                day_order=1,  # same athlete + date + order → collision
            )

    def test_same_athlete_same_date_different_order_allowed(self):
        w2 = _workout(self.org, self.lib, name="Afternoon Run")
        _assignment(self.org, self.athlete, self.workout, day_order=1)
        a2 = _assignment(self.org, self.athlete, w2, day_order=2)
        self.assertEqual(a2.day_order, 2)

    def test_different_athletes_same_date_same_order_allowed(self):
        athlete2 = _athlete(self.org, username="ath2")
        _assignment(self.org, self.athlete, self.workout, day_order=1)
        a2 = _assignment(self.org, athlete2, self.workout, day_order=1)
        self.assertEqual(a2.day_order, 1)

    def test_same_athlete_different_date_same_order_allowed(self):
        _assignment(self.org, self.athlete, self.workout, scheduled_date=TODAY, day_order=1)
        a2 = _assignment(self.org, self.athlete, self.workout, scheduled_date=TOMORROW, day_order=1)
        self.assertEqual(a2.scheduled_date, TOMORROW)


# ---------------------------------------------------------------------------
# Multiple sessions per day
# ---------------------------------------------------------------------------

class MultipleSameDaySessionTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)

    def test_athlete_can_have_three_sessions_on_same_day(self):
        w1 = _workout(self.org, self.lib, name="Morning Run")
        w2 = _workout(self.org, self.lib, name="Strength")
        w3 = _workout(self.org, self.lib, name="Evening Walk")
        a1 = _assignment(self.org, self.athlete, w1, day_order=1)
        a2 = _assignment(self.org, self.athlete, w2, day_order=2)
        a3 = _assignment(self.org, self.athlete, w3, day_order=3)
        pks = {a1.pk, a2.pk, a3.pk}
        self.assertEqual(len(pks), 3)

    def test_same_day_sessions_ordered_by_day_order(self):
        w1 = _workout(self.org, self.lib, name="AM")
        w2 = _workout(self.org, self.lib, name="PM")
        _assignment(self.org, self.athlete, w2, day_order=2)
        _assignment(self.org, self.athlete, w1, day_order=1)
        sessions = list(
            WorkoutAssignment.objects.filter(
                athlete=self.athlete, scheduled_date=TODAY
            )
        )
        self.assertEqual(sessions[0].day_order, 1)
        self.assertEqual(sessions[1].day_order, 2)


# ---------------------------------------------------------------------------
# effective_date property
# ---------------------------------------------------------------------------

class EffectiveDateTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)

    def test_effective_date_returns_scheduled_date_when_not_moved(self):
        a = _assignment(self.org, self.athlete, self.workout, scheduled_date=TODAY)
        self.assertEqual(a.effective_date, TODAY)

    def test_effective_date_returns_moved_date_when_set(self):
        a = _assignment(self.org, self.athlete, self.workout, scheduled_date=TODAY)
        a.athlete_moved_date = NEXT_WEEK
        a.save(update_fields=["athlete_moved_date", "updated_at"])
        self.assertEqual(a.effective_date, NEXT_WEEK)

    def test_scheduled_date_unchanged_after_move(self):
        a = _assignment(self.org, self.athlete, self.workout, scheduled_date=TODAY)
        a.athlete_moved_date = NEXT_WEEK
        a.save(update_fields=["athlete_moved_date", "updated_at"])
        a.refresh_from_db()
        self.assertEqual(a.scheduled_date, TODAY)  # unchanged
        self.assertEqual(a.athlete_moved_date, NEXT_WEEK)


# ---------------------------------------------------------------------------
# Service: assign_workout_to_athlete
# ---------------------------------------------------------------------------

class ServiceAssignTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.coach_user = _user("coach")

    def test_assign_creates_assignment(self):
        a = assign_workout_to_athlete(
            planned_workout=self.workout,
            athlete=self.athlete,
            organization=self.org,
            scheduled_date=TODAY,
            assigned_by=self.coach_user,
        )
        self.assertIsNotNone(a.pk)
        self.assertEqual(a.athlete, self.athlete)
        self.assertEqual(a.planned_workout, self.workout)
        self.assertEqual(a.scheduled_date, TODAY)

    def test_assign_captures_snapshot_version(self):
        self.workout.structure_version = 3
        self.workout.save(update_fields=["structure_version", "updated_at"])
        a = assign_workout_to_athlete(
            planned_workout=self.workout,
            athlete=self.athlete,
            organization=self.org,
            scheduled_date=TODAY,
        )
        self.assertEqual(a.snapshot_version, 3)

    def test_assign_with_coach_notes(self):
        a = assign_workout_to_athlete(
            planned_workout=self.workout,
            athlete=self.athlete,
            organization=self.org,
            scheduled_date=TODAY,
            coach_notes="Focus on cadence today.",
        )
        self.assertEqual(a.coach_notes, "Focus on cadence today.")

    def test_assign_cross_org_workout_raises(self):
        org2 = _org("OrgZ")
        lib2 = _library(org2, name="LibZ")
        workout_org2 = _workout(org2, lib2, name="Wrong Org Workout")
        with self.assertRaises(ValidationError):
            assign_workout_to_athlete(
                planned_workout=workout_org2,
                athlete=self.athlete,
                organization=self.org,
                scheduled_date=TODAY,
            )

    def test_assign_cross_org_athlete_raises(self):
        org2 = _org("OrgY")
        athlete_org2 = _athlete(org2, username="ath_y")
        with self.assertRaises(ValidationError):
            assign_workout_to_athlete(
                planned_workout=self.workout,
                athlete=athlete_org2,
                organization=self.org,
                scheduled_date=TODAY,
            )

    def test_assign_with_day_order(self):
        a = assign_workout_to_athlete(
            planned_workout=self.workout,
            athlete=self.athlete,
            organization=self.org,
            scheduled_date=TODAY,
            day_order=2,
        )
        self.assertEqual(a.day_order, 2)

    def test_assign_does_not_mutate_planned_workout(self):
        original_version = self.workout.structure_version
        original_name = self.workout.name
        assign_workout_to_athlete(
            planned_workout=self.workout,
            athlete=self.athlete,
            organization=self.org,
            scheduled_date=TODAY,
        )
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.structure_version, original_version)
        self.assertEqual(self.workout.name, original_name)


# ---------------------------------------------------------------------------
# Service: move_workout_assignment
# ---------------------------------------------------------------------------

class ServiceMoveTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.assignment = _assignment(
            self.org, self.athlete, self.workout, scheduled_date=TODAY
        )

    def test_move_sets_athlete_moved_date(self):
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_moved_date, NEXT_WEEK)

    def test_move_does_not_change_scheduled_date(self):
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.scheduled_date, TODAY)

    def test_move_sets_status_to_moved(self):
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, WorkoutAssignment.Status.MOVED)

    def test_move_with_new_day_order(self):
        move_workout_assignment(
            assignment=self.assignment, new_date=NEXT_WEEK, new_day_order=3
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.day_order, 3)

    def test_move_without_day_order_keeps_original(self):
        original_order = self.assignment.day_order
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.day_order, original_order)

    def test_move_does_not_mutate_planned_workout(self):
        original_name = self.workout.name
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, original_name)

    def test_athlete_can_move_multiple_times(self):
        move_workout_assignment(assignment=self.assignment, new_date=TOMORROW)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_moved_date, TOMORROW)
        move_workout_assignment(assignment=self.assignment, new_date=NEXT_WEEK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_moved_date, NEXT_WEEK)
        self.assertEqual(self.assignment.scheduled_date, TODAY)  # still original


# ---------------------------------------------------------------------------
# Service: personalize_workout_assignment
# ---------------------------------------------------------------------------

class ServicePersonalizeTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.assignment = _assignment(self.org, self.athlete, self.workout)

    def test_personalize_updates_coach_notes(self):
        personalize_workout_assignment(
            assignment=self.assignment, coach_notes="Stay in Z2 throughout."
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_notes, "Stay in Z2 throughout.")

    def test_personalize_updates_zone_override(self):
        personalize_workout_assignment(
            assignment=self.assignment, target_zone_override="Z3"
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_zone_override, "Z3")

    def test_personalize_updates_pace_override(self):
        personalize_workout_assignment(
            assignment=self.assignment, target_pace_override="4:30/km"
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_pace_override, "4:30/km")

    def test_personalize_updates_rpe_override(self):
        personalize_workout_assignment(
            assignment=self.assignment, target_rpe_override=7
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_rpe_override, 7)

    def test_personalize_updates_power_override(self):
        personalize_workout_assignment(
            assignment=self.assignment, target_power_override=280
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_power_override, 280)

    def test_personalize_none_fields_left_unchanged(self):
        """Passing None for a field must not overwrite an existing value."""
        self.assignment.target_zone_override = "Z2"
        self.assignment.save(update_fields=["target_zone_override", "updated_at"])
        personalize_workout_assignment(
            assignment=self.assignment,
            coach_notes="New note",
            target_zone_override=None,  # should not touch zone
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_zone_override, "Z2")
        self.assertEqual(self.assignment.coach_notes, "New note")

    def test_personalize_does_not_touch_planned_workout(self):
        original_version = self.workout.structure_version
        personalize_workout_assignment(
            assignment=self.assignment, target_zone_override="Z4"
        )
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.structure_version, original_version)

    def test_personalize_does_not_update_athlete_notes(self):
        self.assignment.athlete_notes = "My note"
        self.assignment.save(update_fields=["athlete_notes", "updated_at"])
        personalize_workout_assignment(
            assignment=self.assignment, coach_notes="Coach override"
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_notes, "My note")


# ---------------------------------------------------------------------------
# Service: add_athlete_note_to_assignment
# ---------------------------------------------------------------------------

class ServiceAthleteNoteTests(TestCase):

    def setUp(self):
        self.org = _org()
        self.athlete = _athlete(self.org)
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib)
        self.assignment = _assignment(self.org, self.athlete, self.workout)

    def test_add_athlete_note(self):
        add_athlete_note_to_assignment(
            assignment=self.assignment, note="Felt strong today."
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_notes, "Felt strong today.")

    def test_replace_athlete_note(self):
        add_athlete_note_to_assignment(assignment=self.assignment, note="First note")
        add_athlete_note_to_assignment(assignment=self.assignment, note="Updated note")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.athlete_notes, "Updated note")

    def test_athlete_note_does_not_touch_coach_notes(self):
        self.assignment.coach_notes = "Coach instruction"
        self.assignment.save(update_fields=["coach_notes", "updated_at"])
        add_athlete_note_to_assignment(
            assignment=self.assignment, note="Athlete feedback"
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.coach_notes, "Coach instruction")

    def test_athlete_note_does_not_touch_overrides(self):
        self.assignment.target_zone_override = "Z3"
        self.assignment.save(update_fields=["target_zone_override", "updated_at"])
        add_athlete_note_to_assignment(
            assignment=self.assignment, note="I felt pain"
        )
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.target_zone_override, "Z3")

    def test_athlete_note_does_not_mutate_planned_workout(self):
        original_name = self.workout.name
        add_athlete_note_to_assignment(
            assignment=self.assignment, note="Hard session"
        )
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.name, original_name)


# ---------------------------------------------------------------------------
# Template integrity: PlannedWorkout never mutated
# ---------------------------------------------------------------------------

class TemplateIntegrityTests(TestCase):
    """
    One PlannedWorkout can be assigned to many athletes.
    None of the assignment operations should modify the shared template.
    """

    def setUp(self):
        self.org = _org()
        self.lib = _library(self.org)
        self.workout = _workout(self.org, self.lib, name="Group Tempo Run")

    def _fresh_athlete(self, suffix):
        return _athlete(self.org, username=f"ath_{suffix}")

    def test_same_workout_assigned_to_multiple_athletes(self):
        a1 = self._fresh_athlete("t1")
        a2 = self._fresh_athlete("t2")
        a3 = self._fresh_athlete("t3")
        ass1 = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=a1,
            organization=self.org, scheduled_date=TODAY, day_order=1,
        )
        ass2 = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=a2,
            organization=self.org, scheduled_date=TODAY, day_order=1,
        )
        ass3 = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=a3,
            organization=self.org, scheduled_date=TODAY, day_order=1,
        )
        self.assertEqual(ass1.planned_workout, self.workout)
        self.assertEqual(ass2.planned_workout, self.workout)
        self.assertEqual(ass3.planned_workout, self.workout)

    def test_personalization_of_one_assignment_does_not_affect_template(self):
        athlete = self._fresh_athlete("tmpl1")
        assignment = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=athlete,
            organization=self.org, scheduled_date=TODAY,
        )
        personalize_workout_assignment(
            assignment=assignment,
            target_zone_override="Z4",
            target_rpe_override=8,
        )
        self.workout.refresh_from_db()
        # Template has no override fields — it's unchanged
        self.assertEqual(self.workout.name, "Group Tempo Run")
        self.assertEqual(self.workout.structure_version, 1)

    def test_personalization_of_one_assignment_does_not_affect_another(self):
        a1 = self._fresh_athlete("tmpl2")
        a2 = self._fresh_athlete("tmpl3")
        ass1 = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=a1,
            organization=self.org, scheduled_date=TODAY, day_order=1,
        )
        ass2 = assign_workout_to_athlete(
            planned_workout=self.workout, athlete=a2,
            organization=self.org, scheduled_date=TODAY, day_order=1,
        )
        personalize_workout_assignment(
            assignment=ass1, target_zone_override="Z5"
        )
        ass2.refresh_from_db()
        self.assertEqual(ass2.target_zone_override, "")  # unaffected


# ---------------------------------------------------------------------------
# Legacy coexistence
# ---------------------------------------------------------------------------

class LegacyCoexistenceTests(TestCase):

    def test_entrenamiento_model_unaffected(self):
        """Legacy Entrenamiento still exists with its original fields."""
        field_names = [f.name for f in Entrenamiento._meta.get_fields()]
        self.assertIn("alumno", field_names)
        self.assertIn("titulo", field_names)
        self.assertIn("completado", field_names)

    def test_workout_assignment_has_no_fk_to_entrenamiento(self):
        fk_targets = [
            f.related_model.__name__
            for f in WorkoutAssignment._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("Entrenamiento", fk_targets)
        self.assertNotIn("Alumno", fk_targets)
