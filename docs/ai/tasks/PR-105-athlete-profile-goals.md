# Task Capsule — PR-105: AthleteProfile + AthleteGoal

> **Phase:** P1 · **Risk:** Low-Medium
> **Branch:** `p1/athlete-profile-goals`
> **Scope:** Backend only — AthleteProfile + AthleteGoal models + tests
> **Depends on:** PR-103 (Coach + Athlete) merged and stable

---

## Objective

Introduce `AthleteProfile` and `AthleteGoal` — the physical performance data and
declared race/training objectives for an athlete.

`AthleteProfile` stores measurable physiological and performance parameters that
feed directly into analytics computation (training zones, TSS, PMC modeling).
It is the scientific foundation for personalized training.

`AthleteGoal` links declared athlete objectives to the race calendar
and training plan timeline. Goals serve as the target state that the training plan
is designed to achieve.

---

## Classification

| Dimension | Value |
|---|---|
| Phase | P1 |
| Risk | Low-Medium |
| Blast radius | New models only; no existing query paths affected |
| Reversibility | High — additive models, fully reversible migration |
| CI impact | New migration + new tests |

---

## Allowed Files (Allowlist)

Only these files may be modified or created in this PR:

```
core/models.py                      ← add AthleteProfile + AthleteGoal
core/migrations/                    ← new migration
core/tests_athlete_profile.py       ← new test file (create)
```

No other files. If a required change falls outside this list, **stop and ask**.

---

## Excluded Areas

- Do not modify `Alumno` or any existing model.
- No API views or serializers in this PR.
- No integration with analytics models in this PR (analytics reads from profile in a later PR).
- No changes to `integrations/`, `frontend/`, settings, or CI.
- Do not attempt to populate `AthleteProfile` from `Alumno` data — that is a separate migration task.

---

## Blast Radius Notes

- **Tenancy risk: None.** Both models carry `organization` FK (non-nullable). All
  queries must scope by `organization`. No existing code paths affected.
- **Physio data sensitivity:** `AthleteProfile` contains body weight, FTP, and
  HR max — health-adjacent data. Serializers for this model must never expose it to
  non-authorized roles. API views (future PR) must enforce `require_role` with
  `["owner", "coach", "staff"]` for write access, and athlete-read-own for read access.
- **AthleteGoal and RaceEvent dependency:** `AthleteGoal` has an optional FK to
  `RaceEvent`. Since `RaceEvent` is created in PR-106 (which has no direct dependency
  on PR-105), the FK must be nullable. Enforce `null=True, blank=True` on `target_event`.

---

## Implementation Plan

### Step 1 — Add `AthleteProfile` to `core/models.py`

```python
class AthleteProfile(models.Model):
    """
    Physical and performance profile for an Athlete.

    Values feed analytics computation: training zones, TSS scaling,
    PMC modeling, and injury risk thresholds.

    One profile per athlete per organization. Updates are timestamped
    for history tracking (future: store historical snapshots in a
    separate ProfileHistory table).

    Multi-tenant: organization FK non-nullable. Queries must scope by org.
    """
    athlete = models.OneToOneField(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="profile",
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_profiles",
        db_index=True,
    )
    birth_date = models.DateField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    height_cm = models.FloatField(null=True, blank=True)
    resting_hr_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    max_hr_bpm = models.PositiveSmallIntegerField(null=True, blank=True)
    ftp_watts = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Functional Threshold Power in watts (cycling)"
    )
    lactate_threshold_pace_s_per_km = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Lactate threshold pace in seconds per km (running)"
    )
    vo2max = models.FloatField(
        null=True, blank=True,
        help_text="VO2max in ml/kg/min (lab or estimated)"
    )
    training_age_years = models.PositiveSmallIntegerField(null=True, blank=True)
    dominant_discipline = models.CharField(
        max_length=20,
        choices=[
            ("run", "Running"), ("trail", "Trail Running"),
            ("bike", "Cycling"), ("swim", "Swimming"),
            ("triathlon", "Triathlon"), ("other", "Other"),
        ],
        blank=True, default="",
    )
    notes = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athlete_profile_updates",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization"]),
        ]

    def __str__(self):
        return f"Profile: Athlete:{self.athlete_id} @ Org:{self.organization_id}"
```

### Step 2 — Add `AthleteGoal` to `core/models.py`

```python
class AthleteGoal(models.Model):
    """
    A declared performance target for an Athlete.

    Goals drive the training plan timeline: the target_date anchors
    the training block periodization leading into the event.

    target_event is optional — goals may be time-based rather than
    event-based (e.g., "run 100km/week for 8 weeks").

    Multi-tenant: organization FK non-nullable.
    """

    class GoalType(models.TextChoices):
        FINISH = "finish", "Finish"
        PODIUM = "podium", "Podium"
        TIME_TARGET = "time_target", "Time Target"
        DISTANCE_PR = "distance_pr", "Distance PR"
        LOAD_BLOCK = "load_block", "Training Load Block"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ACHIEVED = "achieved", "Achieved"
        ABANDONED = "abandoned", "Abandoned"

    athlete = models.ForeignKey(
        "Athlete",
        on_delete=models.CASCADE,
        related_name="goals",
        db_index=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="athlete_goals",
        db_index=True,
    )
    goal_type = models.CharField(max_length=20, choices=GoalType.choices, db_index=True)
    target_event = models.ForeignKey(
        "RaceEvent",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="athlete_goals",
    )
    target_date = models.DateField(db_index=True)
    target_value = models.FloatField(
        null=True, blank=True,
        help_text="Numeric target, e.g. finish time in seconds"
    )
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.ACTIVE, db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["athlete", "status", "target_date"]),
            models.Index(fields=["organization", "status"]),
        ]
        ordering = ["target_date"]

    def __str__(self):
        return (
            f"Goal:{self.goal_type} for Athlete:{self.athlete_id} "
            f"on {self.target_date} [{self.status}]"
        )
```

### Step 3 — Generate migration

```bash
python manage.py makemigrations core --name athlete_profile_goals
```

Verify: two new tables, no changes to existing tables.

---

## Test Plan

Create `core/tests_athlete_profile.py`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python -m pytest -q
```

**Minimum test coverage:**

```python
class AthleteProfileTests(TestCase):
    def test_profile_requires_athlete_and_organization(self):
        ...
    def test_one_profile_per_athlete(self):
        # OneToOneField enforces this at DB level — test it
        ...
    def test_profile_fields_nullable(self):
        # Profile can be created with minimal data (all physio fields optional)
        ...
    def test_profile_organization_must_match_athlete_organization(self):
        # Business rule: profile.organization == athlete.organization
        # (enforced at service layer in future PR — document intent here)
        ...

class AthleteGoalTests(TestCase):
    def test_goal_requires_athlete_organization_type_date(self):
        ...
    def test_goal_target_event_is_optional(self):
        ...
    def test_goal_status_defaults_to_active(self):
        ...
    def test_goal_ordering_by_target_date(self):
        ...
```

---

## Definition of Done

- [ ] `AthleteProfile` model with all physio fields (all nullable except FKs)
- [ ] `AthleteProfile.athlete` is OneToOneField
- [ ] `AthleteProfile.organization` is non-nullable FK
- [ ] `AthleteGoal` model with `GoalType` and `Status` choices
- [ ] `AthleteGoal.target_event` is nullable FK (RaceEvent may not exist yet)
- [ ] `AthleteGoal.organization` is non-nullable FK
- [ ] Migration generated cleanly
- [ ] `python manage.py check` → 0 issues
- [ ] `python -m pytest -q` → all tests green
- [ ] No existing model or view modified
- [ ] CI green on push

---

## Rollback Strategy

1. Reverse migration.
2. Remove `AthleteProfile` and `AthleteGoal` from `core/models.py`.
3. No existing data affected.

---

*Capsule last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/product/DOMAIN_MODEL.md`*

---

## Addendum — 2026-03-08: Split Delivery

This PR was delivered in two passes.

**Pass 1 — AthleteProfile (delivered as PR-105):**
AthleteProfile was implemented and merged. Migration `0066_athlete_profile_goals.py`.
Tests: `core/tests_athlete_profile.py`. Model-level `clean()` + `save()→full_clean()`
enforces `profile.organization == athlete.organization` (fail-closed).

**AthleteGoal blocked:**
AthleteGoal requires a clean organization-first FK target (`RaceEvent`). The legacy
`Carrera` model has no `organization` FK and is not org-first. AthleteGoal was
therefore blocked pending PR-106 (RaceEvent).

**Pass 2 — AthleteGoal (delivered on branch `p1/pr107-athlete-goal`):**
After RaceEvent (PR-106) was implemented, AthleteGoal was delivered on a branch
numerically labeled PR-107. Migration `0068_athlete_goal.py`.
Tests: `core/tests_athlete_goal.py`. Both cross-org invariants (athlete-org and
target_event-org) enforced in `clean()`.

**Current status:** Both AthleteProfile and AthleteGoal are fully implemented and tested.
The only residual effect of the split delivery is a branch naming divergence at PR-107.
See `docs/ai/playbooks/EXECUTION-BASELINE-PR101-PR120.md`, Known Divergences D1.
