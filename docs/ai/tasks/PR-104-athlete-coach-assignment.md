# Task Capsule — PR-104: AthleteCoachAssignment

> **Phase:** P1 · **Risk:** Medium
> **Branch:** `p1/athlete-coach-assignment`
> **Scope:** Backend only — AthleteCoachAssignment model + service + tests
> **Depends on:** PR-103 (Coach + Athlete) merged and stable

---

## Objective

Introduce `AthleteCoachAssignment` — the explicit record that assigns a coach to
an athlete within an organization, typed as `primary` or `assistant`.

This model encodes the coaching relationship at the data layer, enabling:
- correct scoping of athlete data to the responsible coach
- multi-coach support per athlete (one primary, N assistants)
- historical record of coaching relationships over time
- enforcement of the "one primary coach per athlete per org" rule

The model also enables `AthleteMembershipHistory` tracking as a future extension.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Medium |
| Blast radius | New model only; no existing query paths touched |
| Reversibility | Medium — migration reversible; PR-109 (WorkoutAssignment) depends on this |
| CI impact | New migration + new tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                          ← add AthleteCoachAssignment
core/migrations/                        ← new migration
core/services_assignment.py            ← new file: assignment service layer
core/tests_athlete_coach_assignment.py ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to existing models.
- No URL routes or API views in this PR.
- Do not add assignment logic to existing views.
- No changes to `integrations/`, `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Tenancy risk: Low.** New table only. The `organization` FK (non-nullable) ensures
  every assignment is organization-scoped. No cross-org access is possible at the
  model layer.
- **Business rule risk: Medium.** The "one primary coach per athlete per org at a
  time" rule must be enforced at the service layer (not just the database). Both a
  `UniqueConstraint` (database-level) and a service-level check (with clear error
  messaging) are required.
- **History preservation:** When a coaching relationship ends, the record is not
  deleted — `ended_at` is set. This preserves the full coaching history.

---

## Implementation Plan

### Step 1 — Add `AthleteCoachAssignment` to `core/models.py`

```python
class AthleteCoachAssignment(models.Model):
    """
    Explicit assignment of a Coach to an Athlete within an Organization.

    Role types:
    - primary: The lead coach. Only one primary assignment may be active
      per (athlete, organization) at any given time.
    - assistant: Supporting coach. Multiple allowed simultaneously.

    History: ended_at is set when the relationship ends.
    Assignments are never deleted — they are historical records.

    Tenancy: organization FK is non-nullable and must match both
    the Athlete.organization and Coach.organization.
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        ASSISTANT = "assistant", "Assistant"

    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="coach_assignments",
        db_index=True,
    )
    coach = models.ForeignKey(
        "Coach",
        on_delete=models.CASCADE,
        related_name="athlete_assignments",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_coach_assignments",
        db_index=True,
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="coach_assignments_made",
    )

    class Meta:
        constraints = [
            # One active primary coach per (athlete, organization) at a time
            models.UniqueConstraint(
                fields=["athlete", "organization"],
                condition=Q(role="primary", ended_at__isnull=True),
                name="uniq_active_primary_coach_per_athlete_org",
            )
        ]
        indexes = [
            models.Index(fields=["athlete", "organization", "role"]),
            models.Index(fields=["coach", "organization"]),
            models.Index(fields=["organization", "role"]),
        ]

    def __str__(self):
        status = "active" if self.ended_at is None else "ended"
        return (
            f"Athlete:{self.athlete_id} ← {self.role} Coach:{self.coach_id} "
            f"@ Org:{self.organization_id} [{status}]"
        )
```

### Step 2 — Create `core/services_assignment.py`

```python
"""
core/services_assignment.py

Service layer for AthleteCoachAssignment operations.
Business rules enforced here:
- One active primary coach per (athlete, organization) at a time.
- Athlete and Coach must belong to the same organization.
- Assignment history is preserved (no deletes).
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
    - athlete.organization == organization
    - coach.organization == organization
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
                "in this organization. End the current assignment before creating a new one."
            )
    return AthleteCoachAssignment.objects.create(
        athlete=athlete,
        coach=coach,
        organization=organization,
        role=role,
        assigned_by=assigned_by,
    )


def end_coach_assignment(assignment: AthleteCoachAssignment) -> AthleteCoachAssignment:
    """
    End an active assignment by setting ended_at to now.
    Does not delete the record — history is preserved.
    """
    if assignment.ended_at is not None:
        raise ValidationError("This assignment has already ended.")
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=["ended_at"])
    return assignment
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name athlete_coach_assignment
```

---

## Test Plan

Create `core/tests_athlete_coach_assignment.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class AthleteCoachAssignmentModelTests(TestCase):
    def test_primary_constraint_prevents_two_active_primary_assignments(self):
        # Second active primary for same (athlete, org) must fail
        ...
    def test_multiple_assistant_coaches_allowed(self):
        ...
    def test_ended_primary_allows_new_primary(self):
        # After end_coach_assignment(), a new primary can be assigned
        ...

class AssignmentServiceTests(TestCase):
    def test_assign_coach_to_athlete_success(self):
        ...
    def test_assign_raises_if_athlete_wrong_org(self):
        ...
    def test_assign_raises_if_coach_wrong_org(self):
        ...
    def test_assign_raises_on_duplicate_primary(self):
        ...
    def test_end_assignment_sets_ended_at(self):
        ...
    def test_end_already_ended_assignment_raises(self):
        ...
    def test_assignment_history_preserved_on_end(self):
        # ended assignment still exists in DB with ended_at set
        ...
```

---

## Definition of Done

- [ ] `AthleteCoachAssignment` model in `core/models.py`
- [ ] `UniqueConstraint` for one active primary coach per `(athlete, organization)`
- [ ] `core/services_assignment.py` with `assign_coach_to_athlete()` and `end_coach_assignment()`
- [ ] Service functions validated against org-scoping (athlete and coach must share org)
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] "Primary constraint prevents duplicate" test explicitly present
- [ ] "History preserved on end" test explicitly present
- [ ] No existing model or view modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `AthleteCoachAssignment` from `core/models.py`.
3. Delete `core/services_assignment.py` and `core/tests_athlete_coach_assignment.py`.
4. No impact on existing models.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
