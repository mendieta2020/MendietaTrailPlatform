---
name: quantoryn-generate
description: >
  Auto-invoke this skill whenever the user asks to create, add, or scaffold any of the
  following artifacts in the MendietaTrailPlatform / Quantoryn codebase: a Django model,
  a DRF serializer, a DRF ViewSet or APIView, a service function (core/services_*.py),
  a Celery task, a database migration, a pytest test file or test class, a React component,
  a frontend API service function, or any new module in core/ or integrations/. Also
  invoke when the user asks to "refactor" existing code to match project conventions, or
  when generated code needs to be validated against the architecture rules before being
  written to disk. This skill standardizes all code generation to enforce Quantoryn's
  non-negotiable laws: multi-tenancy (fail-closed), Plan≠Real invariant, provider
  boundary isolation, idempotency, structured logging, and CI stability.
---

# Quantoryn Code Generation — Conventions Enforcer

You are generating code for **Quantoryn**, a Scientific Operating System for endurance
coaching. Every artifact you produce must comply with the laws in `docs/ai/CONSTITUTION.md`.
This skill is your checklist, template library, and guardrail in one.

---

## Step 0 — Classify Before Writing

Before writing a single line, answer:

1. **What artifact type?** (Model / Serializer / ViewSet / Service / Task / Test / Component / API client)
2. **Phase?** Always P0 unless the user explicitly states P1/P2.
3. **Risk?** Default High for anything touching auth, tenancy, OAuth, or ingestion.
4. **Blast radius?** List the 3–5 files this new code will interact with.

If the blast radius exceeds 3 unrelated modules, stop and ask the user to split the task.

---

## Step 1 — Tenancy Check (Non-Negotiable)

Every backend artifact must pass this checklist before being written:

- [ ] All querysets filter by `organization` derived from the authenticated user's membership — **never** from a request parameter.
- [ ] No cross-org data can leak through serializer fields, annotations, or prefetch.
- [ ] Views inherit from `CoachTenantAPIViewMixin` (from `core/tenancy.py`) or explicitly document why they don't.
- [ ] If the endpoint touches athlete data, `require_athlete_for_coach()` is called.

If any item is unchecked, add the guard before writing other logic.

---

## Step 2 — Artifact Templates

### Django Model

```python
from django.db import models
from core.models import Organization  # always import the tenant root

class MyModel(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="my_models",
        db_index=True,
    )
    # ... domain fields ...

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "<discriminator_field>"]),
        ]

    def __str__(self) -> str:
        return f"MyModel({self.pk}) org={self.organization_id}"
```

**Rules:**
- `organization` FK is always first after `id`.
- Add a composite index on `(organization, <primary_filter_field>)`.
- Never use `null=True` on a FK without an explicit documented reason.
- Migrations are a separate PR unless the model and migration are the entire task.

---

### DRF Serializer

```python
from rest_framework import serializers
from core.models import MyModel

class MyModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MyModel
        fields = ["id", "organization", ...]  # explicit allowlist — never use "__all__"
        read_only_fields = ["id", "organization", "created_at"]

    def validate(self, attrs):
        # Cross-field validation here; never trust client-supplied organization id
        return attrs
```

**Rules:**
- Always use an explicit `fields` list — never `"__all__"`.
- `organization` is always `read_only` — it is set from the view, not from client input.
- Never expose fields belonging to other organizations via `SerializerMethodField`.

---

### DRF ViewSet

```python
from rest_framework.viewsets import ModelViewSet
from core.tenancy import CoachTenantAPIViewMixin
from core.models import MyModel
from .serializers import MyModelSerializer

class MyModelViewSet(CoachTenantAPIViewMixin, ModelViewSet):
    serializer_class = MyModelSerializer

    def get_queryset(self):
        # ALWAYS scope to the authenticated org — never skip this
        return MyModel.objects.filter(
            organization=self.request.user.current_organization
        ).select_related("organization")

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.current_organization)
```

**Rules:**
- Inherit `CoachTenantAPIViewMixin` first in the MRO.
- `get_queryset()` must filter by `organization` on line 1 — no exceptions.
- `perform_create()` injects `organization` from the authenticated user, never from `request.data`.
- Add explicit `http_method_names` if the viewset should not expose all HTTP verbs.

---

### Service Function (`core/services_*.py`)

```python
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

def do_something(*, organization_id: int, actor_id: int, **kwargs) -> MyModel:
    """
    Single-responsibility service. Raises ValueError on invalid input.
    Always org-scoped. Structured log on success and failure.
    """
    with transaction.atomic():
        # 1. Validate inputs
        # 2. Guard: check for existing record (idempotency)
        existing = MyModel.objects.filter(
            organization_id=organization_id, **kwargs
        ).first()
        if existing:
            return existing  # idempotent — return existing, do not duplicate

        # 3. Create
        obj = MyModel.objects.create(organization_id=organization_id, **kwargs)

    logger.info(
        "my_model.created",
        extra={
            "event_name": "my_model.created",
            "organization_id": organization_id,
            "actor_id": actor_id,
            "object_id": obj.pk,
            "outcome": "success",
        },
    )
    return obj
```

**Rules:**
- Services are pure Python — no HTTP, no provider imports.
- Provider logic never lives in `core/services_*.py` — it belongs in `integrations/`.
- Every service is idempotency-safe: check for existence before creating.
- Structured log fields: `event_name`, `organization_id`, `actor_id`, `outcome`, `reason_code`.
- Never log token values, passwords, or PII.

---

### Celery Task

```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def my_task(self, *, organization_id: int, record_id: int) -> None:
    """Idempotency-safe Celery task."""
    try:
        # Check existence before processing (idempotency guard)
        # ...
        logger.info(
            "my_task.completed",
            extra={
                "event_name": "my_task.completed",
                "organization_id": organization_id,
                "record_id": record_id,
                "outcome": "success",
            },
        )
    except Exception as exc:
        logger.warning(
            "my_task.retry",
            extra={
                "event_name": "my_task.retry",
                "organization_id": organization_id,
                "exc": str(exc),
            },
        )
        raise self.retry(exc=exc)
```

**Rules:**
- Always use keyword-only arguments (`*,`) to prevent positional confusion across Celery versions.
- Include an idempotency guard at the top of the task body.
- Never pass raw tokens or secrets as task arguments — pass IDs and fetch inside the task.
- Retry with exponential back-off; cap retries.

---

### pytest Test

```python
import pytest
from django.test import TestCase
from core.models import MyModel
from core.factories import OrganizationFactory, UserFactory  # adjust to actual factory paths

@pytest.mark.django_db
class TestMyModelService:
    def test_create_is_org_scoped(self, org, user):
        """Tenancy: result belongs to the correct org."""
        result = do_something(organization_id=org.id, actor_id=user.id)
        assert result.organization_id == org.id

    def test_create_is_idempotent(self, org, user):
        """Calling twice must not duplicate records."""
        r1 = do_something(organization_id=org.id, actor_id=user.id)
        r2 = do_something(organization_id=org.id, actor_id=user.id)
        assert r1.pk == r2.pk

    def test_no_cross_org_access(self, org, other_org, user):
        """Tenancy: cannot read another org's data."""
        other_obj = MyModel.objects.create(organization=other_org)
        result_qs = MyModel.objects.filter(organization=org)
        assert other_obj not in result_qs
```

**Rules:**
- Every test for a new service must include: org-scoped creation, idempotency, cross-org isolation.
- Use `@pytest.mark.django_db` — not `TestCase` unless Django class-based fixtures are required.
- Never suppress a failing test. Fix the root cause.

---

### React Component (Frontend)

```jsx
// frontend/src/components/MyFeature/MyComponent.jsx
import { useState, useEffect } from "react";
import { myApi } from "../../api/myApi";  // all backend calls through api/ layer

export function MyComponent({ organizationId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    myApi.fetchData(organizationId)
      .then(setData)
      .catch(setError);
  }, [organizationId]);

  if (error) return <p>Error loading data.</p>;
  if (!data) return <p>Loading…</p>;

  return (
    <div>
      {/* render data */}
    </div>
  );
}
```

**Rules:**
- Never store tokens or session state in `localStorage` — use React context or cookies.
- All API calls go through `frontend/src/api/` — never call `fetch` directly in a component.
- No provider-specific logic in the frontend (e.g., don't hardcode "Strava" strings in domain components).
- Zero ESLint warnings: run `npm run lint` before marking done.

---

## Step 3 — Plan ≠ Real Invariant Check

If the artifact involves training data, always confirm:

- [ ] Is this a **planned** artifact? → It must use `PlannedWorkout` / `WorkoutAssignment`.
- [ ] Is this a **real/executed** artifact? → It must use `CompletedActivity`.
- [ ] Does any code path implicitly merge or conflate them? → **STOP. Reject the pattern.**

Reconciliation between planned and real is always explicit, routed through
`core/services_reconciliation.py`. No shortcuts.

---

## Step 4 — Provider Boundary Check

If the artifact touches any provider (Strava, Garmin, etc.):

- [ ] Provider-specific parsing, field mapping, and API calls live in `integrations/<provider>/`.
- [ ] Domain models (`core/models.py`) do not import from `integrations/`.
- [ ] Services in `core/services_*.py` are provider-agnostic.

If a provider import would be needed in `core/`, stop and restructure.

---

## Step 5 — Final Output Format

After generating the code, always deliver:

1. **Files to create/modify** (exact paths)
2. **Migration needed?** (yes/no + why)
3. **Tests to add** (file + test names)
4. **CI commands to run:**
   ```
   python manage.py check
   python -m pytest -q
   npm run lint      # if frontend touched
   npm run build     # if frontend touched
   ```
5. **Rollback strategy** (how to undo if needed)
6. **LOC estimate** — flag if > 500 LOC and recommend splitting.
