"""
core/services_assignment.py

Service layer for AthleteCoachAssignment operations.

Business rules enforced here:
- One active primary coach per (athlete, organization) at a time.
- Athlete and Coach must belong to the same organization.
- Assignment history is preserved (no deletes — ended_at is set instead).

Usage:
    from core.services_assignment import assign_coach_to_athlete, end_coach_assignment
"""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AthleteCoachAssignment


def assign_coach_to_athlete(
    *,
    athlete,
    coach,
    organization,
    role: str,
    assigned_by,
) -> AthleteCoachAssignment:
    """
    Create a new AthleteCoachAssignment.

    Validates:
    - athlete.organization == organization (tenancy guard)
    - coach.organization == organization (tenancy guard)
    - If role == 'primary': no other active primary assignment exists
      for this (athlete, organization) pair.

    Raises ValidationError on any violation.
    Returns the created AthleteCoachAssignment.
    """
    if athlete.organization_id != organization.id:
        raise ValidationError("Athlete does not belong to this organization.")
    if coach.organization_id != organization.id:
        raise ValidationError("Coach does not belong to this organization.")

    if role == AthleteCoachAssignment.Role.PRIMARY:
        existing = AthleteCoachAssignment.objects.filter(
            athlete=athlete,
            organization=organization,
            role=AthleteCoachAssignment.Role.PRIMARY,
            ended_at__isnull=True,
        ).exists()
        if existing:
            raise ValidationError(
                "This athlete already has an active primary coach assignment "
                "in this organization. End the current assignment before "
                "creating a new one."
            )

    return AthleteCoachAssignment.objects.create(
        athlete=athlete,
        coach=coach,
        organization=organization,
        role=role,
        assigned_by=assigned_by,
    )


def end_coach_assignment(
    assignment: AthleteCoachAssignment,
) -> AthleteCoachAssignment:
    """
    End an active assignment by setting ended_at to now.

    Does not delete the record — history is preserved.
    Raises ValidationError if the assignment has already ended.
    """
    if assignment.ended_at is not None:
        raise ValidationError("This assignment has already ended.")
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=["ended_at", "updated_at"])
    return assignment
