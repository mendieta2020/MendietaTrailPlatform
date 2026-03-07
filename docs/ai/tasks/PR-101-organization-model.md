# Task Capsule — PR-101: Organization + Team Domain Foundation

> **Phase:** P1 · **Risk:** High
> **Branch:** `p1/organization-model`
> **Scope:** Backend only — new models + migrations + tests

---

## Objective

Introduce `Organization` and `Team` as the foundational domain entities for Quantoryn's
organization-first architecture. These two models become the tenant root for all future
domain entities. Every subsequent PR in the P1 domain sequence depends on these being
correct, tested, and stable.

`Organization` replaces the implicit "coach as tenant" pattern that currently exists
in the codebase. No existing code is removed in this PR — the new models are additive.
Wiring new tenancy enforcement to existing models is handled in PR-102 and PR-103.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | High |
| Blast radius | New models and migrations only; no existing query paths touched |
| Reversibility | Medium — migration can be reversed, but downstream PRs depend on this |
| CI impact | New migration + new tests; no change to existing tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py              ← add Organization + Team models
core/migrations/            ← new migration for Organization + Team
core/admin.py               ← register new models (optional but recommended)
core/tests_organization.py  ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to existing models (`Alumno`, `Entrenamiento`, `Actividad`, `Equipo`, etc.).
- No changes to existing views, serializers, or URL routes.
- No changes to `integrations/`.
- No changes to `frontend/`.
- No changes to `backend/settings.py` or `.github/workflows/`.
- Do not add `organization` FK to any existing model — that is PR-102 scope.
- Do not create `Membership` — that is PR-102 scope.

---

## Blast Radius Notes

- **Tenancy risk: None for this PR.** New models are standalone. No existing query paths
  are touched. The existing `entrenador`-as-tenant system is untouched.
- **Migration risk: Low.** Two new tables with no foreign key dependencies outside
  themselves. Fully reversible.
- **Naming conflict:** A model called `Equipo` already exists in `core/models.py` and
  serves as an informal "team" concept. `Team` (new) is a distinct, formal entity.
  Both can coexist. `Equipo` is marked as legacy and will be migrated or deprecated
  in a separate PR after the domain foundation is stable. Do not remove `Equipo` here.

---

## Implementation Plan

### Step 1 — Add `Organization` model to `core/models.py`

```python
class Organization(models.Model):
    """
    Tenant root for all Quantoryn domain entities.
    Every organization-scoped record must reference this model.

    Multi-tenant discipline: queries must always filter by organization.
    An organization without an active CoachSubscription is read-only.
    """
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "-created_at"]),
        ]

    def __str__(self):
        return self.name
```

### Step 2 — Add `Team` model to `core/models.py`

```python
class Team(models.Model):
    """
    A named subgroup within an Organization.
    Athletes are assigned to teams for training group segmentation.

    Tenancy: Team is scoped to Organization. Queries must filter by
    organization before filtering by team.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "name")
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.organization.name} / {self.name}"
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name organization_team_foundation
```

Verify the generated migration before committing. Confirm it creates only two new tables
with no changes to existing tables.

### Step 4 — Register in admin (optional for P1, recommended for usability)

```python
# core/admin.py
from .models import Organization, Team

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)
```

---

## Test Plan

Create `core/tests_organization.py`:

```bash
# 1. Django system check
python manage.py check

# 2. Check migration is clean (no unexpected changes)
python manage.py makemigrations --check --dry-run

# 3. Apply migration
python manage.py migrate --noinput

# 4. Run full test suite
python -m pytest -q
```

**Minimum test coverage for this PR:**

```python
class OrganizationModelTests(TestCase):
    def test_organization_created_with_required_fields(self):
        ...
    def test_organization_slug_is_unique(self):
        ...
    def test_organization_str_returns_name(self):
        ...

class TeamModelTests(TestCase):
    def test_team_requires_organization(self):
        ...
    def test_team_name_unique_per_organization(self):
        # Same name allowed in different orgs
        ...
    def test_team_str_includes_org_name(self):
        ...
    def test_team_cascade_deletes_with_organization(self):
        ...
```

---

## Definition of Done

- [ ] `Organization` model in `core/models.py` with all required fields
- [ ] `Team` model in `core/models.py` with `organization` FK (non-nullable)
- [ ] Migration generated cleanly (no unexpected alterations)
- [ ] `python manage.py check` → 0 issues
- [ ] `python manage.py makemigrations --check --dry-run` → no pending migrations
- [ ] `python -m pytest -q` → all tests green
- [ ] `core/tests_organization.py` created with minimum coverage listed above
- [ ] No existing model, view, or test modified
- [ ] CI green on push
- [ ] PR description notes: "Equipo coexists with Team as legacy model — deprecation is a separate task"

---

## Rollback Strategy

1. Reverse the migration: `python manage.py migrate core <previous_migration_number>`
2. Remove `Organization` and `Team` class definitions from `core/models.py`.
3. Remove `core/tests_organization.py`.
4. No data loss in existing tables — these are new tables only.
5. No downstream PRs should be merged until this PR is stable.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
