# Task Capsule — PR-102: Membership Roles + Fail-Closed Tenancy Gate

> **Phase:** P1 · **Risk:** High
> **Branch:** `p1/membership-roles`
> **Scope:** Backend only — Membership model + tenancy enforcement service + tests
> **Depends on:** PR-101 (Organization + Team) merged and stable

---

## Objective

Introduce the `Membership` model as the **explicit access gate** between users and
organizations. Implement a fail-closed tenancy resolution service that all future
organization-scoped views will use.

This PR is the security backbone of the P1 domain. Without `Membership`, any user
could access any organization's data. With `Membership`, access requires an explicit
active record with an appropriate role.

**Fail-closed rule:** No active membership record = deny. This is enforced at the
service layer, not left to individual views.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | High |
| Blast radius | New model + new tenancy service; existing `entrenador`-scoped views untouched |
| Reversibility | Medium — migration reversible; but downstream PRs depend on this service |
| CI impact | New migration + new tests; no change to existing tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py              ← add Membership model
core/tenancy.py             ← add organization-scoped resolver functions
core/migrations/            ← new migration for Membership
core/admin.py               ← register Membership (optional)
core/tests_membership.py    ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to existing models (`Alumno`, `Entrenamiento`, `Actividad`, etc.).
- No changes to `CoachTenantAPIViewMixin` (existing legacy tenancy — do not touch).
- No changes to existing views, serializers, or URL routes.
- Do not add `organization` FK to existing domain models — that is PR-103+ scope.
- No changes to `integrations/`, `frontend/`, or settings.
- Do not wire `Membership` into any existing view in this PR.

---

## Blast Radius Notes

- **Tenancy risk: None for this PR on existing paths.** The new `Membership` model
  and tenancy service are additive. Existing `entrenador`-scoped queries continue to
  work unchanged. The new service will be adopted in PR-103+ as new views are built.
- **Migration risk: Low.** One new table, no changes to existing tables.
- **Security note:** The `require_org_membership()` service function must be
  fail-closed: if no membership is found, it must raise `PermissionDenied` (not return
  `None` silently). Tests must prove this behavior explicitly.

---

## Implementation Plan

### Step 1 — Add `Membership` model to `core/models.py`

```python
class Membership(models.Model):
    """
    Access gate between a User and an Organization.

    Fail-closed: a user is authorized to access an organization's data only
    if they have an active Membership record with an appropriate role.
    Missing membership = deny, regardless of other user properties.

    Multi-tenant discipline:
    - All organization-scoped queries must validate membership first.
    - Never infer membership from request context — always resolve explicitly.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        COACH = "coach", "Coach"
        ATHLETE = "athlete", "Athlete"
        STAFF = "staff", "Staff"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
        db_index=True,
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    staff_title = models.CharField(
        max_length=60, blank=True, default="",
        help_text="e.g. physiotherapist, nutritionist, doctor, admin"
    )
    team = models.ForeignKey(
        "Team",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="memberships",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                condition=Q(is_active=True),
                name="uniq_active_membership_user_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "role", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.organization} [{self.role}]"
```

### Step 2 — Add tenancy resolution functions to `core/tenancy.py`

Add these alongside (not replacing) the existing functions in `core/tenancy.py`:

```python
from django.core.exceptions import PermissionDenied
from .models import Membership, Organization


def get_active_membership(user, organization_id: int) -> Membership:
    """
    Resolve an active Membership for (user, organization).

    Fail-closed: raises PermissionDenied if no active membership exists.
    Never returns None — callers can assume a valid Membership on success.

    Usage:
        membership = get_active_membership(request.user, org_id)
        # Proceeds only if membership is active
    """
    try:
        return Membership.objects.get(
            user=user,
            organization_id=organization_id,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active membership for this organization.")


def require_role(user, organization_id: int, allowed_roles: list[str]) -> Membership:
    """
    Resolve membership and verify the user has one of the allowed roles.

    Fail-closed: raises PermissionDenied on missing membership OR wrong role.

    Usage:
        membership = require_role(request.user, org_id, ["owner", "coach"])
    """
    membership = get_active_membership(user, organization_id)
    if membership.role not in allowed_roles:
        raise PermissionDenied(
            f"Role '{membership.role}' is not authorized for this action."
        )
    return membership


class OrgTenantMixin:
    """
    DRF ViewSet mixin for organization-scoped endpoints.

    Resolves and caches the active Membership on each request.
    Subclasses access `self.membership` and `self.organization` after
    calling `self.resolve_membership(org_id)`.

    Replaces the legacy CoachTenantAPIViewMixin for new P1+ views.
    Do not use this on existing views.
    """

    def resolve_membership(self, organization_id: int) -> Membership:
        membership = get_active_membership(self.request.user, organization_id)
        self.membership = membership
        self.organization = membership.organization
        return membership
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name membership_roles
```

Confirm the migration creates only the `Membership` table with no changes to existing
tables.

---

## Test Plan

Create `core/tests_membership.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class MembershipModelTests(TestCase):
    def test_active_membership_unique_per_user_org(self):
        # Two active memberships for same user+org must fail UniqueConstraint
        ...
    def test_two_inactive_memberships_allowed(self):
        # Historical memberships (is_active=False) are not constrained
        ...
    def test_membership_str_includes_role(self):
        ...

class TenancyResolverTests(TestCase):
    def test_get_active_membership_returns_membership(self):
        ...
    def test_get_active_membership_raises_if_no_membership(self):
        with self.assertRaises(PermissionDenied):
            get_active_membership(user, org_id)
    def test_get_active_membership_raises_if_inactive(self):
        # Inactive membership must also raise PermissionDenied
        ...
    def test_require_role_passes_for_allowed_role(self):
        ...
    def test_require_role_raises_for_wrong_role(self):
        with self.assertRaises(PermissionDenied):
            require_role(athlete_user, org_id, ["owner", "coach"])
    def test_require_role_raises_if_no_membership(self):
        ...
```

---

## Definition of Done

- [ ] `Membership` model in `core/models.py` with all required fields and constraints
- [ ] `Membership.Role` choices: `owner`, `coach`, `athlete`, `staff`
- [ ] `UniqueConstraint` on active membership per `(user, organization)` present
- [ ] `get_active_membership()` in `core/tenancy.py` — fail-closed, raises `PermissionDenied`
- [ ] `require_role()` in `core/tenancy.py` — fail-closed on role mismatch
- [ ] `OrgTenantMixin` class defined for future use by new views
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] All fail-closed behaviors covered by explicit tests
- [ ] No existing model, view, or tenancy function modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse the migration: `python manage.py migrate core <previous_migration_number>`
2. Remove `Membership` from `core/models.py`.
3. Remove new functions from `core/tenancy.py` (existing functions untouched).
4. No data loss in existing tables.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
