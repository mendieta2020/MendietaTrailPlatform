# Task Capsule — PR-107: WorkoutLibrary

> **Phase:** P1 · **Risk:** Low
> **Branch:** `p1/workout-library`
> **Scope:** Backend only — WorkoutLibrary model + tests
> **Depends on:** PR-103 (Coach + Athlete) merged and stable

---

## Objective

Introduce `WorkoutLibrary` — the named, organization-scoped container for workout
templates. The library is the catalog from which coaches draw when composing
training weeks. It is the organizational root for all reusable training content.

This PR creates only the library container. `PlannedWorkout` (PR-108) will introduce
template workouts that reference the library. The two must be implemented in this order
because `PlannedWorkout.library` is a nullable FK to `WorkoutLibrary`.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Low |
| Blast radius | New table only; no existing code touched |
| Reversibility | High |
| CI impact | New migration + new tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                  ← add WorkoutLibrary
core/migrations/                ← new migration
core/tests_workout_library.py   ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to existing models.
- No URL routes or API views.
- Do not create `PlannedWorkout` here — that is PR-108 scope.
- No changes to `integrations/`, `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Tenancy risk: None.** `organization` FK is non-nullable. New table only.
- **Library vs Template:** The `WorkoutLibrary` is a container entity. Individual
  template workouts are `PlannedWorkout` records with `is_template=True` pointing
  to this library. The library itself has no direct connection to athletes —
  only to the organization and the coaches who own it.

---

## Implementation Plan

### Step 1 — Add `WorkoutLibrary` to `core/models.py`

```python
class WorkoutLibrary(models.Model):
    """
    Named collection of workout templates for an Organization.

    The library is the container from which coaches select and assign
    workouts to athletes. Templates inside the library are PlannedWorkout
    records with is_template=True and library FK pointing here.

    Visibility:
    - is_public=True: all coaches in the organization can view and use
      templates from this library.
    - is_public=False: private library, visible only to created_by coach.

    Multi-tenant: organization FK non-nullable. Cross-org access is denied.
    """
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="workout_libraries",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_public = models.BooleanField(
        default=True,
        help_text="If True, all coaches in the organization can access this library."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="workout_libraries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "name")
        indexes = [
            models.Index(fields=["organization", "is_public"]),
        ]
        ordering = ["name"]

    def __str__(self):
        visibility = "public" if self.is_public else "private"
        return f"{self.name} ({visibility}) — Org:{self.organization_id}"
```

### Step 2 — Generate migration

```bash
python manage.py makemigrations core --name workout_library
```

---

## Test Plan

Create `core/tests_workout_library.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class WorkoutLibraryModelTests(TestCase):
    def test_library_requires_organization_and_name(self):
        ...
    def test_name_unique_per_organization(self):
        ...
    def test_same_name_allowed_in_different_organizations(self):
        ...
    def test_is_public_defaults_to_true(self):
        ...
    def test_str_includes_name_and_visibility(self):
        ...
```

---

## Definition of Done

- [ ] `WorkoutLibrary` model with `organization`, `name`, `is_public`, `created_by`
- [ ] `unique_together` on `(organization, name)`
- [ ] `organization` FK non-nullable
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] No existing model or view modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `WorkoutLibrary` from `core/models.py`.
3. No impact on existing models.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
