# Task Capsule — PR-109: WorkoutAssignment

> **Phase:** P1 · **Risk:** Low-Medium
> **Branch:** `p1/workout-assignment`
> **Scope:** Backend only — WorkoutAssignment model + assignment service + tests
> **Depends on:** PR-108 (PlannedWorkout) + PR-103 (Athlete) merged and stable

---

## Objective

Introduce `WorkoutAssignment` — the record that assigns a `PlannedWorkout` to a
specific `Athlete` on a specific date. This is the prescription delivery layer.

The assignment is distinct from the prescription itself:
- `PlannedWorkout` = the reusable prescription (coach's intent, version-controlled)
- `WorkoutAssignment` = the delivery: who receives it, when, and what happened

Athlete day-swap capability is implemented here. Athletes may move a workout to a
different day — this is recorded on `WorkoutAssignment.athlete_moved_date` and
never changes the original `PlannedWorkout` or its `scheduled_date`.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Low-Medium |
| Blast radius | New table only; Plan ≠ Real invariant must be respected in this model |
| Reversibility | High |
| CI impact | New migration + new tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                      ← add WorkoutAssignment
core/migrations/                    ← new migration
core/services_workout.py            ← new file: assignment + day-swap service
core/tests_workout_assignment.py    ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- Do not modify `PlannedWorkout`, `WorkoutBlock`, or `WorkoutInterval`.
- Do not link `WorkoutAssignment` to `CompletedActivity` here — reconciliation
  is a future Plan vs Real PR.
- No URL routes or API views in this PR.
- No changes to `integrations/`, `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Plan ≠ Real risk: Low for this PR.** `WorkoutAssignment` records delivery, not
  execution. It must never store execution outcomes. Status transitions (`pending` →
  `completed`) are the only outcome information stored here, and only after
  reconciliation in a future PR.
- **Day-swap invariant:** When an athlete moves a workout, `athlete_moved_date` is set.
  `scheduled_date` is never modified. The prescription (`PlannedWorkout`) is never
  touched. This must be enforced at the service layer and covered by an explicit test.
- **Athlete permission rule:** Only the assigned athlete (or their coach) may call
  `athlete_move_workout_day()`. Enforced at the service layer; API views enforce this
  via `require_role`.

---

## Implementation Plan

### Step 1 — Add `WorkoutAssignment` to `core/models.py`

```python
class WorkoutAssignment(models.Model):
    """
    Assigns a PlannedWorkout to a specific Athlete on a specific date.

    PLAN ≠ REAL: This model records delivery and scheduling only.
    It does not store execution outcomes. Completion is recorded on
    CompletedActivity. The link between assignment and completion
    is established by PlanRealCompare (future PR).

    Athlete day-swap: An athlete may move their workout to a different day.
    athlete_moved_date records the new date. scheduled_date is never modified.
    The prescription (PlannedWorkout) is never modified by this operation.

    Multi-tenant: organization FK non-nullable.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        MISSED = "missed", "Missed"
        SKIPPED = "skipped", "Skipped"

    workout = models.ForeignKey(
        "PlannedWorkout",
        on_delete=models.CASCADE,
        related_name="assignments",
        db_index=True,
    )
    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="workout_assignments",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_assignments",
        db_index=True,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assignments_made",
    )
    scheduled_date = models.DateField(
        db_index=True,
        help_text="Original assignment date. Never modified after creation."
    )
    athlete_moved_date = models.DateField(
        null=True, blank=True, db_index=True,
        help_text=(
            "If the athlete used day-swap, this records the new execution date. "
            "scheduled_date is never changed."
        )
    )
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workout", "athlete"],
                name="uniq_workout_assignment_per_athlete",
            )
        ]
        indexes = [
            models.Index(fields=["athlete", "scheduled_date", "status"]),
            models.Index(fields=["organization", "scheduled_date"]),
            models.Index(fields=["athlete", "athlete_moved_date"]),
        ]

    def __str__(self):
        date = self.athlete_moved_date or self.scheduled_date
        return (
            f"Assignment: Athlete:{self.athlete_id} ← "
            f"Workout:{self.workout_id} on {date} [{self.status}]"
        )

    @property
    def effective_date(self):
        """Returns athlete_moved_date if set, otherwise scheduled_date."""
        return self.athlete_moved_date or self.scheduled_date
```

### Step 2 — Create `core/services_workout.py`

```python
"""
core/services_workout.py

Service layer for WorkoutAssignment operations.
Enforces:
- Day-swap rule: athlete_moved_date set; scheduled_date never changed.
- Athlete permission: only assigned athlete or their coach may day-swap.
- Organization scoping: workout.organization == athlete.organization.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from .models import WorkoutAssignment


def assign_workout_to_athlete(
    *,
    workout,
    athlete,
    organization,
    assigned_by,
    scheduled_date,
) -> WorkoutAssignment:
    """
    Create a WorkoutAssignment linking a PlannedWorkout to an Athlete.

    Validates:
    - workout.organization == organization
    - athlete.organization == organization
    - No existing assignment for this (workout, athlete) pair.
    """
    if workout.organization_id != organization.id:
        raise ValidationError("Workout does not belong to this organization.")
    if athlete.organization_id != organization.id:
        raise ValidationError("Athlete does not belong to this organization.")
    return WorkoutAssignment.objects.create(
        workout=workout,
        athlete=athlete,
        organization=organization,
        assigned_by=assigned_by,
        scheduled_date=scheduled_date,
    )


def athlete_move_workout_day(
    *,
    assignment: WorkoutAssignment,
    new_date,
    requesting_user,
) -> WorkoutAssignment:
    """
    Move a workout to a different day (athlete day-swap).

    Rules:
    - Only the assigned athlete or their coach may call this.
    - scheduled_date is NEVER modified.
    - athlete_moved_date records the new date.
    - If athlete_moved_date is already set, it is overwritten (athletes
      may adjust the day more than once before execution).

    Returns the updated assignment.
    """
    is_athlete = assignment.athlete.user_id == requesting_user.id
    is_coach = assignment.assigned_by_id == requesting_user.id
    if not (is_athlete or is_coach):
        raise PermissionDenied("Only the assigned athlete or their coach may move this workout.")
    assignment.athlete_moved_date = new_date
    assignment.save(update_fields=["athlete_moved_date", "updated_at"])
    return assignment
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name workout_assignment
```

---

## Test Plan

Create `core/tests_workout_assignment.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class WorkoutAssignmentModelTests(TestCase):
    def test_assignment_requires_workout_athlete_organization_date(self):
        ...
    def test_unique_assignment_per_workout_athlete(self):
        ...
    def test_status_defaults_to_pending(self):
        ...
    def test_effective_date_returns_moved_date_if_set(self):
        ...
    def test_effective_date_returns_scheduled_date_if_not_moved(self):
        ...

class DaySwapTests(TestCase):
    def test_athlete_can_move_workout_day(self):
        # scheduled_date unchanged after move
        ...
    def test_scheduled_date_not_modified_after_move(self):
        original_date = assignment.scheduled_date
        athlete_move_workout_day(assignment=assignment, new_date=new_date, ...)
        assignment.refresh_from_db()
        self.assertEqual(assignment.scheduled_date, original_date)
    def test_non_athlete_non_coach_cannot_move_workout(self):
        with self.assertRaises(PermissionDenied):
            ...
    def test_athlete_can_move_workout_multiple_times(self):
        ...

class PlanNotRealAssignmentTests(TestCase):
    def test_workout_assignment_has_no_actual_field(self):
        """Assignment must not store execution outcomes."""
        field_names = [f.name for f in WorkoutAssignment._meta.get_fields()]
        for name in field_names:
            self.assertFalse(name.startswith("actual_"), f"Found actual_ field: {name}")
```

---

## Definition of Done

- [ ] `WorkoutAssignment` model with `Status` choices and `athlete_moved_date`
- [ ] `UniqueConstraint` on `(workout, athlete)`
- [ ] `effective_date` property on model
- [ ] `organization` FK non-nullable
- [ ] `core/services_workout.py` with `assign_workout_to_athlete()` + `athlete_move_workout_day()`
- [ ] `athlete_move_workout_day()` never modifies `scheduled_date` — test proves this
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] `PlanNotRealAssignmentTests` present and passing
- [ ] No existing model or view modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `WorkoutAssignment` from `core/models.py`.
3. Delete `core/services_workout.py` and `core/tests_workout_assignment.py`.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
