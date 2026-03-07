# Task Capsule — PR-106: RaceEvent Model

> **Phase:** P1 · **Risk:** Low
> **Branch:** `p1/race-event-model`
> **Scope:** Backend only — RaceEvent model + tests
> **Depends on:** PR-101 (Organization) merged and stable

---

## Objective

Introduce `RaceEvent` — the target competition entity that anchors athlete goals,
training block periodization, and coach planning timelines.

`RaceEvent` is an organization-scoped catalog of upcoming competitions.
Coaches create race events; athletes link their goals to them.
The planning engine uses `RaceEvent.date` to compute the training block
leading into the race (periodization logic is a future PR).

This PR is deliberately narrow: model + migration + tests only.
No views, no athlete-race linkage, no analytics integration in this PR.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Low |
| Blast radius | New table only; no existing code touched |
| Reversibility | High — purely additive |
| CI impact | New migration + new tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                  ← add RaceEvent
core/migrations/                ← new migration
core/tests_race_event.py        ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- No changes to any existing model.
- No URL routes or API views in this PR.
- No linkage to `AthleteGoal.target_event` in this PR (FK was already defined
  as nullable in PR-105 to allow this decoupled creation order).
- No changes to `integrations/`, `frontend/`, settings, or CI.

---

## Blast Radius Notes

- **Tenancy risk: None.** New table. `organization` FK is non-nullable.
- **RaceEvent is an organization catalog, not a global registry.** Two organizations
  may register the same race independently. There is no shared global race database
  in P1. A global race registry is a future feature.

---

## Implementation Plan

### Step 1 — Add `RaceEvent` to `core/models.py`

```python
class RaceEvent(models.Model):
    """
    A target competition registered by an organization.

    Used as the anchor for AthleteGoal.target_event and training
    block periodization. Each organization maintains its own event catalog.

    Multi-tenant: organization FK is non-nullable.
    Queries must always filter by organization.
    """

    class Discipline(models.TextChoices):
        RUN = "run", "Running"
        TRAIL = "trail", "Trail Running"
        BIKE = "bike", "Cycling"
        SWIM = "swim", "Swimming"
        TRIATHLON = "triathlon", "Triathlon"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        A = "A", "A — Peak race"
        B = "B", "B — Secondary race"
        C = "C", "C — Training race"

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="race_events",
        db_index=True,
    )
    name = models.CharField(max_length=300)
    date = models.DateField(db_index=True)
    location = models.CharField(max_length=300, blank=True, default="")
    discipline = models.CharField(
        max_length=20, choices=Discipline.choices, db_index=True
    )
    distance_km = models.FloatField(null=True, blank=True)
    elevation_gain_m = models.FloatField(
        null=True, blank=True,
        help_text="Total elevation gain in meters (relevant for trail/MTB events)"
    )
    priority = models.CharField(
        max_length=5, choices=Priority.choices, db_index=True,
        blank=True, default="",
    )
    url = models.URLField(blank=True, default="", help_text="Official event URL")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="race_events_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "date"]),
            models.Index(fields=["organization", "discipline", "date"]),
            models.Index(fields=["organization", "priority", "date"]),
        ]
        ordering = ["date"]

    def __str__(self):
        return f"{self.name} ({self.date}) — {self.organization_id}"
```

### Step 2 — Generate migration

```bash
python manage.py makemigrations core --name race_event
```

---

## Test Plan

Create `core/tests_race_event.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class RaceEventModelTests(TestCase):
    def test_race_event_requires_organization_name_date_discipline(self):
        ...
    def test_optional_fields_nullable(self):
        # distance_km, elevation_gain_m, url, notes are all optional
        ...
    def test_two_orgs_can_have_same_race_name(self):
        # RaceEvent is org-scoped, not globally unique by name
        ...
    def test_ordering_by_date(self):
        ...
    def test_str_includes_name_date(self):
        ...
```

---

## Definition of Done

- [ ] `RaceEvent` model with `Discipline` and `Priority` choices
- [ ] `organization` FK non-nullable
- [ ] All measurement fields nullable (not all races have known distance)
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] No existing model or view modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `RaceEvent` from `core/models.py`.
3. No impact on existing models or `AthleteGoal.target_event` (nullable FK).

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*
