# Task Capsule — PR-108: PlannedWorkout + WorkoutBlock + WorkoutInterval

> **Phase:** P1 · **Risk:** Medium
> **Branch:** `p1/planned-workout-structure`
> **Scope:** Backend only — three new models + Plan≠Real protective tests
> **Depends on:** PR-107 (WorkoutLibrary) merged and stable

---

## Objective

Introduce the three-tier planning structure: `PlannedWorkout`, `WorkoutBlock`,
and `WorkoutInterval`. Together these models represent the full hierarchical
workout prescription that coaches author and athletes execute.

**This PR is the most architecturally significant in the planning domain.
It must reinforce the Plan ≠ Real invariant at every level.**

`PlannedWorkout` is the prescription. It represents what the coach intended.
It is never mutated by execution data. It never stores outcome values.
The only things it stores are the coach's intent: targets, structure, parameters.

This PR also creates template workout support (`is_template=True`) to enable
the WorkoutLibrary to hold reusable prescriptions.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Medium |
| Blast radius | Three new tables; Plan≠Real invariant must be guarded by explicit tests |
| Reversibility | Medium — downstream PRs (109) depend on PlannedWorkout FK |
| CI impact | New migration + new Plan≠Real protective tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                          ← add PlannedWorkout, WorkoutBlock, WorkoutInterval
core/migrations/                        ← new migration
core/tests_planned_workout.py           ← new test file — MUST include Plan≠Real tests
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- Do not modify `Entrenamiento` (the legacy planned workout model) in any way.
- Do not modify `Actividad` or `CompletedActivity` — these are the real-side models.
- Do not add any FK from `PlannedWorkout` to any execution-side model.
- Do not add any FK from any execution model to `PlannedWorkout` in this PR
  (reconciliation linkage is added only in a future Plan vs Real PR).
- No URL routes or API views.
- No changes to `integrations/`, `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Plan ≠ Real risk: HIGH.** This is the model that defines the planning side of
  the invariant. The tests MUST explicitly assert that `PlannedWorkout` contains no
  fields that store execution outcomes (actual distance, actual duration, actual power).
  Any such field added to this model in the future must be preceded by a formal ADR.
- **Legacy coexistence:** `Entrenamiento` (the legacy Spanish-named planned workout)
  continues to exist unchanged. `PlannedWorkout` is the new formal model.
  Both coexist until a data migration is scoped in a separate PR.
- **Versioning:** `PlannedWorkout.version` must increment when a coach modifies a
  workout prescription. This ensures the Plan vs Real reconciliation engine always
  knows which version of the plan was active at the time of execution.

---

## Implementation Plan

### Step 1 — Add `PlannedWorkout` to `core/models.py`

```python
class PlannedWorkout(models.Model):
    """
    The atomic unit of coaching prescription.

    PLAN ≠ REAL INVARIANT:
    This model stores INTENT ONLY. It must never store execution outcomes
    (actual distance, actual duration, actual HR, actual power).
    The CompletedActivity model is the source of truth for what happened.
    PlanRealCompare is the explicit reconciliation record.

    Modification rules:
    - Coach may edit any field and version increments.
    - Athlete may NOT edit any field on this model.
    - Athlete may only move the scheduled_date via WorkoutAssignment.athlete_moved_date.

    Templates:
    - is_template=True: reusable prescription in a WorkoutLibrary.
      scheduled_date is null for templates.
    - is_template=False: assigned workout with a specific date and athlete.
    """

    class Sport(models.TextChoices):
        RUN = "run", "Running"
        TRAIL = "trail", "Trail Running"
        BIKE = "bike", "Cycling"
        STRENGTH = "strength", "Strength"
        MOBILITY = "mobility", "Mobility"
        SWIM = "swim", "Swimming"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="planned_workouts",
        db_index=True,
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    sport = models.CharField(max_length=20, choices=Sport.choices, db_index=True)
    scheduled_date = models.DateField(
        null=True, blank=True, db_index=True,
        help_text="Target execution date. Null for library templates."
    )
    duration_target_s = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Prescribed duration in seconds."
    )
    distance_target_m = models.FloatField(
        null=True, blank=True,
        help_text="Prescribed distance in meters."
    )
    is_template = models.BooleanField(
        default=False, db_index=True,
        help_text="True = lives in WorkoutLibrary. False = assigned session."
    )
    library = models.ForeignKey(
        "WorkoutLibrary",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="template_workouts",
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="planned_workouts_created",
    )
    version = models.PositiveSmallIntegerField(
        default=1,
        help_text="Increments on each coach modification. Never reset."
    )
    schema_version = models.CharField(
        max_length=10, default="v1",
        help_text="Internal format version for structured workout data."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "sport", "scheduled_date"]),
            models.Index(fields=["organization", "is_template"]),
            models.Index(fields=["library"]),
        ]

    def __str__(self):
        date_str = str(self.scheduled_date) if self.scheduled_date else "template"
        return f"{self.title} [{self.sport}] {date_str} — Org:{self.organization_id}"
```

### Step 2 — Add `WorkoutBlock` to `core/models.py`

```python
class WorkoutBlock(models.Model):
    """
    A named phase within a PlannedWorkout.
    Examples: Warm-up, Main Set, Threshold Block, Cool-down.

    Blocks are ordered within the workout. Order must be explicitly set.
    Blocks define the macro structure of the session.
    """
    workout = models.ForeignKey(
        "PlannedWorkout",
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    order = models.PositiveSmallIntegerField(
        help_text="Defines the sequence of blocks within the workout."
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    duration_target_s = models.PositiveIntegerField(null=True, blank=True)
    distance_target_m = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("workout", "order")
        ordering = ["order"]

    def __str__(self):
        return f"Block:{self.order} '{self.name}' → Workout:{self.workout_id}"
```

### Step 3 — Add `WorkoutInterval` to `core/models.py`

```python
class WorkoutInterval(models.Model):
    """
    A single repeated unit within a WorkoutBlock.
    Examples: 5x(1000m @ threshold), 3x(5min @ sweetspot + 2min recovery).

    Interval targets are the coach's scientific prescription.
    Athletes may not modify any target field.

    All target fields are nullable — not all interval types use all targets.
    """
    block = models.ForeignKey(
        "WorkoutBlock",
        on_delete=models.CASCADE,
        related_name="intervals",
    )
    order = models.PositiveSmallIntegerField()
    repetitions = models.PositiveSmallIntegerField(default=1)
    duration_target_s = models.PositiveIntegerField(null=True, blank=True)
    distance_target_m = models.FloatField(null=True, blank=True)
    power_target_watts = models.PositiveSmallIntegerField(null=True, blank=True)
    power_target_max_watts = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_target_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_target_max_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    pace_target_s_per_km = models.PositiveIntegerField(null=True, blank=True)
    pace_target_max_s_per_km = models.PositiveIntegerField(null=True, blank=True)
    rpe_target = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Rate of Perceived Exertion, 1–10"
    )
    rest_duration_s = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Rest between repetitions in seconds"
    )
    notes = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        unique_together = ("block", "order")
        ordering = ["order"]

    def __str__(self):
        return (
            f"Interval:{self.order} x{self.repetitions} → Block:{self.block_id}"
        )
```

### Step 4 — Generate migration

```bash
python manage.py makemigrations core --name planned_workout_structure
```

---

## Test Plan

Create `core/tests_planned_workout.py`.

This file MUST include Plan ≠ Real protective tests.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage — including mandatory Plan ≠ Real tests:**

```python
class PlanNotRealInvariantTests(TestCase):
    """
    These tests document and enforce the Plan ≠ Real invariant.
    If any of these tests need to be removed to accommodate a feature,
    that feature violates the domain law and must be redesigned.
    """

    def test_planned_workout_has_no_actual_distance_field(self):
        """PlannedWorkout must not have fields named actual_distance or similar."""
        field_names = [f.name for f in PlannedWorkout._meta.get_fields()]
        prohibited = ["actual_distance", "actual_duration", "actual_hr", "actual_power"]
        for name in prohibited:
            self.assertNotIn(name, field_names, f"PlannedWorkout must not have '{name}'")

    def test_planned_workout_has_no_completed_activity_fk(self):
        """PlannedWorkout must not have a direct FK to CompletedActivity."""
        fk_targets = [
            f.related_model.__name__
            for f in PlannedWorkout._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("CompletedActivity", fk_targets)

    def test_workout_block_has_only_target_fields_not_actual(self):
        field_names = [f.name for f in WorkoutBlock._meta.get_fields()]
        for name in field_names:
            self.assertFalse(
                name.startswith("actual_"),
                f"WorkoutBlock must not have actual_ fields, found: {name}"
            )


class PlannedWorkoutModelTests(TestCase):
    def test_workout_requires_organization_title_sport(self):
        ...
    def test_template_workout_has_no_scheduled_date(self):
        ...
    def test_version_defaults_to_1(self):
        ...
    def test_library_fk_null_for_non_template(self):
        ...

class WorkoutBlockTests(TestCase):
    def test_block_requires_workout_order_name(self):
        ...
    def test_block_order_unique_per_workout(self):
        ...
    def test_blocks_ordered_by_order_field(self):
        ...

class WorkoutIntervalTests(TestCase):
    def test_interval_requires_block_and_order(self):
        ...
    def test_interval_order_unique_per_block(self):
        ...
    def test_all_target_fields_nullable(self):
        ...
```

---

## Definition of Done

- [ ] `PlannedWorkout` model with `Sport` choices, version field, is_template flag
- [ ] `PlannedWorkout` has NO actual_* fields (execution outcomes)
- [ ] `PlannedWorkout` has NO FK to `CompletedActivity` or `Actividad`
- [ ] `WorkoutBlock` ordered within workout
- [ ] `WorkoutInterval` with all target fields nullable
- [ ] Migration generated cleanly (three new tables)
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] `PlanNotRealInvariantTests` class present and all three invariant tests pass
- [ ] Legacy `Entrenamiento` model not modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `PlannedWorkout`, `WorkoutBlock`, `WorkoutInterval` from `core/models.py`.
3. `Entrenamiento` is untouched — no legacy impact.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
