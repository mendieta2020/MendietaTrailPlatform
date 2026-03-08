# Task Capsule — PR-110: CompletedActivity + ActivityStream (Provider-Agnostic)

> **Phase:** P1 · **Risk:** Medium
> **Branch:** `p1/completed-activity-normalization`
> **Scope:** Backend only — new domain CompletedActivity v2 model + ActivityStream + provider boundary tests
> **Depends on:** PR-103 (Athlete + Organization) merged and stable

---

## Objective

Introduce the organization-first `CompletedActivity` model and `ActivityStream` as the
formal execution-domain entities. These are the real-side counterpart to `PlannedWorkout`.

**The central invariant of this PR: a `CompletedActivity` is evidence, never intent.**

This model is provider-agnostic at its interface. Raw provider payloads are preserved
in `raw_payload` for audit and re-processing. All other fields receive only normalized
data that has passed through `integrations/<provider>/normalizer.py`.

Note: A `CompletedActivity` model already exists in `core/models.py` (added in
migration 0060). This PR reviews that model against the domain specification and
extends it to be organization-first, explicitly scoped to `Athlete` (not the legacy
`Alumno`), and protected by formal invariant tests. The goal is a clean, tested,
domain-grade model — not a replacement of existing functionality.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Medium |
| Blast radius | Existing CompletedActivity model may require field additions; provider boundary must be verified |
| Reversibility | Medium — any field additions are additive; no removals in this PR |
| CI impact | New tests for Plan≠Real and provider boundary; migration if fields added |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                              ← extend CompletedActivity + add ActivityStream
core/migrations/                            ← migration for any new fields or ActivityStream
core/tests_completed_activity.py            ← new test file — MUST include invariant tests
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- Do not touch `Actividad` (the legacy completed activity model) in any way.
- Do not add any FK from `CompletedActivity` to `PlannedWorkout` in this PR —
  reconciliation linkage is a separate future PR.
- Do not modify any file in `integrations/` — provider boundary is documented here
  but enforced through the existing normalizer pattern.
- Do not add execution fields to `PlannedWorkout` — Plan ≠ Real invariant.
- No URL routes, views, or serializers in this PR.
- No changes to `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Plan ≠ Real risk: HIGH.** This is the real-side model. The tests MUST explicitly
  assert that `CompletedActivity` contains no fields from the planning domain
  (no `duration_target`, no `distance_target`, no FK to `PlannedWorkout`). These
  assertions must be present as named test methods.
- **Provider boundary risk: Medium.** The `raw_payload` field is the only place
  provider-native data lives. All other fields must receive normalized values.
  The tests must assert that `provider` is a string field (not a FK to a provider
  registry) — this ensures the domain model remains decoupled from the registry.
- **Idempotency constraint:** `(organization, provider, provider_activity_id)` must
  be a unique constraint. This is the deduplication guarantee. Verify this constraint
  exists or add it.
- **Coexistence with legacy `Actividad`:** Both models coexist. `Actividad` is the
  legacy Spanish-named model with `source` enum. `CompletedActivity` is the new
  organization-first model with `Athlete` FK. The migration from `Actividad` to
  `CompletedActivity` is a separate, explicitly scoped PR.

---

## Implementation Plan

### Step 1 — Review and verify the existing `CompletedActivity` model

Read the current `CompletedActivity` model in `core/models.py`. Verify the following
fields are present. If any are missing, add them:

**Required fields:**
```python
organization     # ForeignKey(User → AUTH_USER_MODEL), non-nullable
athlete          # ForeignKey(Athlete), if not present — add nullable for now (migration)
provider         # CharField (string slug, not FK)
provider_activity_id  # CharField
sport            # CharField
started_at       # DateTimeField (timezone-aware)
duration_s       # PositiveIntegerField
distance_m       # FloatField
elevation_gain_m # FloatField, nullable
elevation_loss_m # FloatField, nullable
avg_hr_bpm       # PositiveSmallIntegerField, nullable
max_hr_bpm       # PositiveSmallIntegerField, nullable
avg_power_watts  # PositiveSmallIntegerField, nullable
normalized_power_watts  # PositiveSmallIntegerField, nullable
tss              # FloatField, nullable
calories_kcal    # FloatField, nullable
raw_payload      # JSONField (provider-native data, for audit/re-processing)
source_hash      # CharField (SHA-256 of key fields, for change detection)
ingested_at      # DateTimeField
```

**Idempotency constraint — verify this exists:**
```python
models.UniqueConstraint(
    fields=["organization", "provider", "provider_activity_id"],
    name="uniq_completed_activity_org_provider_id",
)
```

If the constraint is missing, add it in this PR.

**Field that must NOT exist:**
```python
# These fields belong on PlannedWorkout, never on CompletedActivity:
duration_target   # MUST NOT EXIST
distance_target   # MUST NOT EXIST
planned_workout   # FK to PlannedWorkout MUST NOT EXIST in this model
```

### Step 2 — Add `athlete` FK to `CompletedActivity` if missing

If the `Athlete` FK does not exist on `CompletedActivity`, add it as nullable
(to preserve backward compatibility with existing rows):

```python
athlete = models.ForeignKey(
    "Athlete",
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="completed_activities_v2",
    db_index=True,
    help_text=(
        "Organization-first Athlete FK. Nullable for backward compatibility "
        "with rows ingested before PR-110. Backfill is a separate task."
    )
)
```

### Step 3 — Add `ActivityStream` model

```python
class ActivityStream(models.Model):
    """
    Time-series data from a CompletedActivity.

    Stores heart rate, power, cadence, pace, altitude, GPS tracks
    sampled at provider-native resolution (typically 1–5 seconds).

    Stored separately from CompletedActivity to allow lightweight
    activity queries without loading the full stream data.

    Provider boundary: raw stream data (if needed for re-processing)
    lives in raw_data. The normalized data column is the only field
    that domain code should use.

    Multi-tenant: scoped through activity.organization (no direct org FK
    needed here — always query via activity__organization).
    """

    class StreamType(models.TextChoices):
        HEARTRATE = "heartrate", "Heart Rate"
        POWER = "power", "Power"
        CADENCE = "cadence", "Cadence"
        PACE = "pace", "Pace"
        ALTITUDE = "altitude", "Altitude"
        LATLNG = "latlng", "GPS Track"
        TEMPERATURE = "temperature", "Temperature"

    activity = models.ForeignKey(
        "CompletedActivity",
        on_delete=models.CASCADE,
        related_name="streams",
        db_index=True,
    )
    stream_type = models.CharField(
        max_length=20, choices=StreamType.choices, db_index=True
    )
    data = models.JSONField(
        help_text="List of numeric samples at native provider resolution."
    )
    resolution_s = models.FloatField(
        default=1.0,
        help_text="Seconds between samples (e.g. 1.0 = 1Hz sampling)."
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "stream_type"],
                name="uniq_stream_per_activity_type",
            )
        ]
        indexes = [
            models.Index(fields=["activity", "stream_type"]),
        ]

    def __str__(self):
        return f"Stream:{self.stream_type} → Activity:{self.activity_id}"
```

### Step 4 — Generate migration

```bash
python manage.py makemigrations core --name completed_activity_normalization
```

---

## Test Plan

Create `core/tests_completed_activity.py`.

This file MUST include Plan ≠ Real invariant tests and provider boundary tests.

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage — including mandatory invariant tests:**

```python
class PlanNotRealExecutionTests(TestCase):
    """
    Enforce the Plan ≠ Real invariant on the execution-side models.
    If these tests need to be removed to accommodate a feature, that
    feature violates the domain law and must be redesigned.
    """

    def test_completed_activity_has_no_duration_target_field(self):
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        self.assertNotIn("duration_target", field_names)
        self.assertNotIn("duration_target_s", field_names)

    def test_completed_activity_has_no_distance_target_field(self):
        field_names = [f.name for f in CompletedActivity._meta.get_fields()]
        self.assertNotIn("distance_target", field_names)
        self.assertNotIn("distance_target_m", field_names)

    def test_completed_activity_has_no_planned_workout_fk(self):
        fk_targets = [
            f.related_model.__name__
            for f in CompletedActivity._meta.get_fields()
            if hasattr(f, "related_model") and f.related_model is not None
        ]
        self.assertNotIn("PlannedWorkout", fk_targets)
        self.assertNotIn("Entrenamiento", fk_targets)


class ProviderBoundaryTests(TestCase):
    """
    Enforce provider isolation at the model layer.
    """

    def test_provider_field_is_string_not_fk(self):
        """
        provider must be a CharField (string slug), not a FK to a provider registry.
        This ensures the domain model is decoupled from the integration layer.
        """
        field = CompletedActivity._meta.get_field("provider")
        self.assertEqual(field.get_internal_type(), "CharField")

    def test_raw_payload_is_json_field(self):
        """raw_payload preserves provider-native data for audit/re-processing."""
        field = CompletedActivity._meta.get_field("raw_payload")
        self.assertEqual(field.get_internal_type(), "JSONField")


class IdempotencyTests(TestCase):
    def test_duplicate_activity_from_same_provider_raises_integrity_error(self):
        """(organization, provider, provider_activity_id) must be unique."""
        ...
    def test_same_provider_id_different_org_allowed(self):
        """Different organizations may ingest the same provider activity ID."""
        ...


class ActivityStreamTests(TestCase):
    def test_stream_requires_activity_and_type(self):
        ...
    def test_one_stream_per_activity_per_type(self):
        ...
    def test_stream_cascade_deletes_with_activity(self):
        ...


class LegacyCoexistenceTests(TestCase):
    def test_actividad_model_unaffected(self):
        """Verify legacy Actividad model is untouched."""
        ...
```

---

## Definition of Done

- [ ] `CompletedActivity` model verified against domain spec (all required fields present)
- [ ] `CompletedActivity` has idempotency constraint `(organization, provider, provider_activity_id)`
- [ ] `CompletedActivity` has NO target fields (duration_target, distance_target)
- [ ] `CompletedActivity` has NO FK to any planning model
- [ ] `provider` field is CharField (not FK) — provider boundary enforced
- [ ] `raw_payload` JSONField present
- [ ] `Athlete` FK added as nullable (backward-compatible)
- [ ] `ActivityStream` model with `StreamType` choices and stream-per-type constraint
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] `PlanNotRealExecutionTests` class present and all invariant tests pass
- [ ] `ProviderBoundaryTests` class present and all boundary tests pass
- [ ] Legacy `Actividad` model not modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration (rolls back any added fields and `ActivityStream` table).
2. Remove `ActivityStream` from `core/models.py`.
3. Revert any field additions to `CompletedActivity`.
4. `Actividad` is untouched throughout — no legacy rollback needed.
5. The idempotency constraint removal does not delete data.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*

---

## Addendum — 2026-03-08: Architecture Reality Note

Before implementing this capsule, the following pre-existing conditions in the
codebase must be understood:

### 1. `CompletedActivity.organization` points to User, not Organization

The current `CompletedActivity.organization` field is:
```python
organization = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
```
It uses the Django User model as an organization proxy. This predates the `Organization`
model introduced in PR-101 and is not on the organization-first P1 architecture.

**Scope of this PR (PR-110 / extended lane PR-114):**
- Add `athlete` FK (nullable, backward-compatible) — this is additive and safe.
- Add `ActivityStream` model — this is a new table; no blast radius.
- Add domain invariant tests — always additive.
- Do **not** migrate `organization` from User to Organization in this PR.

**The full `organization` FK migration** (User → Organization) is deferred to a
separate explicitly scoped PR after the extended lane (post-PR-120). It requires:
- A data migration that maps existing User FKs to Organization rows
- A careful backward-compatibility plan for Strava ingestion and existing queries
- An explicit ADR (architecture decision record)
This debt is tracked in `docs/ai/playbooks/EXECUTION-BASELINE-PR101-PR120.md`,
Known Divergences D2.

### 2. `CompletedActivity.alumno` points to legacy `Alumno`, not `Athlete`

The current model uses `alumno = ForeignKey("Alumno", ...)`. This PR adds
`athlete = ForeignKey("Athlete", null=True, blank=True, ...)` as the new-domain
FK alongside the legacy one. Both coexist. Backfill is a separate task.

### 3. `ActivityStream` does not yet exist

The `ActivityStream` model specified in this capsule is not yet implemented.
No migration, no model class, no tests. This PR creates it from scratch.
