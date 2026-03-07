# Task Capsule — PR-103: Coach + Athlete Domain Foundation

> **Phase:** P1 · **Risk:** Medium-High
> **Branch:** `p1/coach-athlete-foundation`
> **Scope:** Backend only — Coach + Athlete identity models + organization-scoped serializers + tests
> **Depends on:** PR-101 (Organization), PR-102 (Membership) merged and stable

---

## Objective

Introduce `Coach` and `Athlete` as formal domain entities that bridge the `User`
identity layer with the `Organization` tenancy layer.

In the current codebase, coaches are raw `User` objects and athletes are `Alumno`
objects scoped to `entrenador`. This PR does not remove or break those models.
Instead, it introduces the formal `Coach` and `Athlete` domain projections that
all P1+ features will build on.

These models are thin, organization-scoped wrappers that:
- link `User` ↔ `Organization` ↔ `Membership.role`
- provide the FK anchor for athlete-specific entities (profile, assignments, goals)
- establish the organizational context that all child records will inherit

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Medium-High |
| Blast radius | New models only; existing `Alumno` and legacy coach views untouched |
| Reversibility | Medium — migration reversible; downstream PRs depend on `Athlete` FK |
| CI impact | New migration + new tests; no change to existing tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                      ← add Coach + Athlete models
core/migrations/                    ← new migration
core/serializers_coach.py           ← new file: Coach + Athlete serializers
core/admin.py                       ← register new models
core/tests_coach_athlete.py         ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- Do not modify `Alumno`, `Entrenamiento`, `Actividad`, or any existing model.
- Do not modify existing views or `CoachTenantAPIViewMixin`.
- Do not create URL routes for these models in this PR — API endpoints are a
  separate task.
- No changes to `integrations/`, `frontend/`, settings, or CI.
- Do not attempt to migrate `Alumno` data into `Athlete` in this PR.

---

## Blast Radius Notes

- **Tenancy risk: Low for this PR.** New models are additive. The new `Athlete` model
  introduces a new FK anchor — no existing querysets are affected.
- **Coexistence note:** `Alumno` and `Athlete` will coexist. This is intentional.
  `Alumno` is the legacy Spanish-named model. `Athlete` is the new organization-first
  English-named entity. The migration path from `Alumno` to `Athlete` is scoped to
  a later, separate PR. Do not attempt it here.
- **Naming collision risk:** If a future developer confuses `Alumno` (legacy) with
  `Athlete` (new), data integrity risks emerge. Document this clearly in both model
  docstrings.

---

## Implementation Plan

### Step 1 — Add `Coach` model to `core/models.py`

```python
class Coach(models.Model):
    """
    Organization-scoped coach identity.

    A Coach is a User who holds a Membership.role = 'coach' or 'owner'
    within a specific Organization. This model makes that relationship
    explicit for use as a FK anchor in planning and assignment entities.

    Note: A User may be a Coach in multiple Organizations.
    Each Coach record represents one (User, Organization) pairing.

    Do NOT confuse with the legacy 'entrenador' User FK pattern on Alumno.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coach_profiles",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="coaches",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_coach_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return f"Coach:{self.user_id} @ {self.organization_id}"
```

### Step 2 — Add `Athlete` model to `core/models.py`

```python
class Athlete(models.Model):
    """
    Organization-scoped athlete identity.

    An Athlete is a User who holds a Membership.role = 'athlete'
    within a specific Organization. This model is the FK anchor for
    all athlete-specific domain entities: profile, goals, assignments,
    activities, and analytics.

    Organization scoping is non-nullable and fail-closed.
    A row without an organization must never exist.

    Do NOT confuse with the legacy 'Alumno' model.
    Alumno = legacy Spanish model (entrenador-scoped).
    Athlete = new organization-first model (organization-scoped).
    Migration from Alumno → Athlete is a separate, explicitly scoped PR.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="athlete_profiles",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athletes",
        db_index=True,
    )
    team = models.ForeignKey(
        "Team",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athletes",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_athlete_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "team", "is_active"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return f"Athlete:{self.user_id} @ {self.organization_id}"
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name coach_athlete_foundation
```

Confirm: two new tables created, no changes to existing tables.

### Step 4 — Create `core/serializers_coach.py`

Minimal read-only serializers for the new models. No write endpoints in this PR.

```python
# core/serializers_coach.py
from rest_framework import serializers
from .models import Coach, Athlete

class CoachSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coach
        fields = ["id", "user", "organization", "is_active", "created_at"]
        read_only_fields = fields

class AthleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Athlete
        fields = ["id", "user", "organization", "team", "is_active", "created_at"]
        read_only_fields = fields
```

---

## Test Plan

Create `core/tests_coach_athlete.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class CoachModelTests(TestCase):
    def test_coach_requires_organization(self):
        ...
    def test_one_active_coach_per_user_per_org(self):
        # Second active Coach for same (user, org) must raise IntegrityError
        ...
    def test_coach_in_multiple_organizations_allowed(self):
        # Same user can be Coach in two different orgs
        ...

class AthleteModelTests(TestCase):
    def test_athlete_requires_organization(self):
        ...
    def test_one_active_athlete_per_user_per_org(self):
        ...
    def test_athlete_optional_team_assignment(self):
        ...
    def test_athlete_organization_cascade_delete(self):
        # Deleting the Organization deletes Athlete
        ...

class LegacyCoexistenceTests(TestCase):
    def test_alumno_model_unaffected(self):
        # Verify Alumno can still be created and queried normally
        # This test protects against accidental legacy breakage
        ...
```

---

## Definition of Done

- [ ] `Coach` model in `core/models.py` — organization-scoped, `UniqueConstraint` on active pair
- [ ] `Athlete` model in `core/models.py` — organization-scoped, `UniqueConstraint` on active pair
- [ ] Both model docstrings explicitly distinguish from legacy `Alumno` / `entrenador` pattern
- [ ] Migration generated cleanly
- [ ] `core/serializers_coach.py` created with read-only serializers
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] `test_alumno_model_unaffected` test present and passing
- [ ] No existing model, view, or test modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration: `python manage.py migrate core <previous_migration_number>`
2. Remove `Coach` and `Athlete` from `core/models.py`.
3. Remove `core/serializers_coach.py` and `core/tests_coach_athlete.py`.
4. No impact on `Alumno`, `Entrenamiento`, or any existing model.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
