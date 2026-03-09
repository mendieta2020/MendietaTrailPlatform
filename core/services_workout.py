"""
core/services_workout.py

Service layer for WorkoutAssignment operations.

Enforces:
- Organization scoping: athlete and planned_workout must share the assignment org.
- Template immutability: PlannedWorkout is NEVER mutated by any service here.
- Day-swap rule: athlete_moved_date is set; scheduled_date is never changed.
- Personalization isolation: override fields live on the assignment only.
- Athlete write boundary: athletes write only to athlete_notes.

No API, no notifications, no async in this module.
"""

from django.core.exceptions import ValidationError

from .models import WorkoutAssignment


def assign_workout_to_athlete(
    *,
    planned_workout,
    athlete,
    organization,
    scheduled_date,
    day_order: int = 1,
    assigned_by=None,
    coach_notes: str = "",
) -> WorkoutAssignment:
    """
    Create a WorkoutAssignment linking a PlannedWorkout to an Athlete on a date.

    Validates:
    - planned_workout.organization == organization
    - athlete.organization == organization
    - No existing (athlete, scheduled_date, day_order) collision.

    Captures snapshot_version from the PlannedWorkout at assignment time.
    The PlannedWorkout is never modified by this operation.

    Returns the created WorkoutAssignment.
    """
    if planned_workout.organization_id != organization.id:
        raise ValidationError(
            "planned_workout does not belong to this organization."
        )
    if athlete.organization_id != organization.id:
        raise ValidationError(
            "athlete does not belong to this organization."
        )
    return WorkoutAssignment.objects.create(
        organization=organization,
        athlete=athlete,
        planned_workout=planned_workout,
        assigned_by=assigned_by,
        scheduled_date=scheduled_date,
        day_order=day_order,
        coach_notes=coach_notes,
        snapshot_version=planned_workout.structure_version,
    )


def move_workout_assignment(
    *,
    assignment: WorkoutAssignment,
    new_date,
    new_day_order: int | None = None,
) -> WorkoutAssignment:
    """
    Reschedule an assignment to a new date and/or day_order.

    Rules:
    - scheduled_date is NEVER modified; athlete_moved_date records the new date.
    - Status transitions to MOVED.
    - PlannedWorkout is never touched.
    - new_day_order is optional; if not provided, the existing day_order is kept.

    Returns the updated assignment.
    """
    update_fields = ["athlete_moved_date", "status", "updated_at"]
    assignment.athlete_moved_date = new_date
    assignment.status = WorkoutAssignment.Status.MOVED
    if new_day_order is not None:
        assignment.day_order = new_day_order
        update_fields.append("day_order")
    assignment.save(update_fields=update_fields)
    return assignment


def personalize_workout_assignment(
    *,
    assignment: WorkoutAssignment,
    coach_notes: str | None = None,
    target_zone_override: str | None = None,
    target_pace_override: str | None = None,
    target_rpe_override: int | None = None,
    target_power_override: int | None = None,
) -> WorkoutAssignment:
    """
    Apply assignment-level personalization overrides for a specific athlete.

    TEMPLATE IMMUTABILITY: This function updates only the WorkoutAssignment
    record. The shared PlannedWorkout template is NEVER modified. Coaches
    can reuse one template for many athletes and personalize each assignment
    independently via this function.

    Only the keyword arguments that are explicitly passed (not None) are
    updated. Pass None to leave a field unchanged.

    Returns the updated assignment.
    """
    update_fields = ["updated_at"]
    if coach_notes is not None:
        assignment.coach_notes = coach_notes
        update_fields.append("coach_notes")
    if target_zone_override is not None:
        assignment.target_zone_override = target_zone_override
        update_fields.append("target_zone_override")
    if target_pace_override is not None:
        assignment.target_pace_override = target_pace_override
        update_fields.append("target_pace_override")
    if target_rpe_override is not None:
        assignment.target_rpe_override = target_rpe_override
        update_fields.append("target_rpe_override")
    if target_power_override is not None:
        assignment.target_power_override = target_power_override
        update_fields.append("target_power_override")
    assignment.save(update_fields=update_fields)
    return assignment


def add_athlete_note_to_assignment(
    *,
    assignment: WorkoutAssignment,
    note: str,
) -> WorkoutAssignment:
    """
    Add or replace the athlete's note on a workout assignment.

    ATHLETE WRITE BOUNDARY: athletes may only write to athlete_notes.
    This function must never modify the prescription structure, coach notes,
    override fields, or status.

    Typical use cases:
    - "I cannot train today"
    - "I felt pain during this session"
    - "Session went well / badly"

    Returns the updated assignment.
    """
    assignment.athlete_notes = note
    assignment.save(update_fields=["athlete_notes", "updated_at"])
    return assignment
