# Quantoryn — Product Domain Model

> **Type:** Internal Architecture / Product Source of Truth
> **Status:** Canonical — all agent and engineering work must align with this document
> **Last updated:** 2026-03-07
> **See also:** `docs/ai/CONSTITUTION.md`, `docs/vendor/integration_architecture.md`

---

## 1. Core Philosophy

Quantoryn is a **Scientific Operating System for endurance organizations**.

It is not a fitness app. It is not a social network. It is the operational backbone that enables coaches to plan, prescribe, track, and adapt training for athletes — at scale, with scientific integrity.

**The core product loop:**

```
Coach plans
  → Athlete executes
  → Activity data returns from provider
  → Plan vs Real reconciliation
  → Training load analytics
  → Coach decision
  → Plan adaptation
```

Every entity in this domain exists to serve one of these six stages.
If a proposed feature does not fit clearly into this loop, its priority is lower.

**The scientific mandate:**

The platform must preserve the epistemic distinction between *intent* and *reality*:
- A planned workout is a prescription. It represents the coach's intent.
- A completed activity is evidence. It represents what actually happened.
- These two things are never merged, blended, or treated as equivalent.
- Reconciliation is an explicit, calculated operation — never an implicit assumption.

This is not a software constraint. It is a scientific requirement.

---

## 2. Product Roles and Commercial Model

### Roles

| Role | Description |
|---|---|
| **Platform Owner** | Quantoryn staff. Full system access. |
| **Owner** | Organization administrator. Creates the org, manages coaches, manages billing. |
| **Coach** | Designs training plans, prescribes workouts, monitors athletes, interprets analytics. |
| **Athlete** | Executes training, views their own analytics, manages their race calendar. |
| **Staff** | Support professionals attached to an organization: physiotherapist, nutritionist, doctor, admin. Staff have limited, role-defined access to athlete data. |

### Membership access model

Access to any organization's data requires an active `Membership` record.
A user without a membership to an organization cannot access that organization's data — this is enforced at the query layer, not the view layer.

### Commercial model

- **Coaches pay Quantoryn** based on athlete volume (subscription tier).
- **Athletes pay their coach or organization** — not Quantoryn directly.
- The billing unit is the organization's active athlete count.

**Subscription tiers (illustrative):**

| Tier | Athlete Limit | Notes |
|---|---|---|
| Starter | Up to 50 | For independent coaches |
| Pro | Up to 100 | For coaching groups |
| Enterprise | Unlimited | For academies, federations, clubs |

---

## 3. Organizational Layer

### Organization

The tenant root. Every piece of data in Quantoryn belongs to an organization.
A query without an organization context must be denied.

Key properties:
- `name` — display name
- `slug` — URL-safe unique identifier
- `is_active` — soft-deletable
- `created_at`

An organization represents a coaching business, academy, club, or federation.
One coach may own or belong to multiple organizations.

### Team

A logical subgroup within an organization.
Organizations often segment their athletes by level:

```
Organization: Mendieta Trail Academy
  ├── Team: Initial
  ├── Team: Intermediate
  ├── Team: Advanced
  └── Team: Elite
```

Key properties:
- `organization` (FK, non-nullable)
- `name`
- `description`
- `is_active`

Teams affect scheduling, leaderboard scoping, and group analytics.
They do not affect tenancy — tenancy is always at the organization level.

### Membership

The access gate between a `User` and an `Organization`.
A user is only authorized to act within an organization if they have an active membership with an appropriate role.

**Fail-closed rule:** No membership = deny. The system never infers membership from context.

Key properties:
- `user` (FK)
- `organization` (FK, non-nullable)
- `role` — one of: `owner`, `coach`, `athlete`, `staff`
- `staff_title` — optional specialization (physiotherapist, nutritionist, doctor, admin)
- `team` — optional FK to Team (for athletes assigned to a specific training group)
- `is_active`
- `joined_at`
- `left_at` — nullable; if set, membership is historical only

A single user may have memberships in multiple organizations, with different roles in each.

### Staff

Staff are users whose `Membership.role = "staff"`.
`staff_title` defines their function within the organization.

Staff have read access to athlete data scoped to their role:
- Physiotherapist: injury risk, load history
- Nutritionist: calorie and fueling data
- Doctor: health flags, HR zones
- Admin: roster, billing, scheduling

Staff do not plan workouts or prescribe training.

---

## 4. Athlete Domain

### Coach

A user with `Membership.role = "coach"` within an organization.

Coaches are the primary users of the platform. They:
- design workout templates
- prescribe weekly plans
- monitor athlete readiness and compliance
- interpret analytics
- make training decisions

A coach may belong to multiple organizations.
A coach may supervise athletes across teams.

### Athlete

A user with `Membership.role = "athlete"` within an organization.

Athletes:
- receive prescribed workouts
- execute training and connect external devices
- view their own analytics dashboard
- manage their race calendar and goals
- communicate with their coach

Athletes **cannot**:
- edit workout prescriptions
- modify training blocks, intervals, or scientific targets
- alter execution data imported from external providers

### AthleteProfile

Extended physical and performance profile for an athlete.
Stored separately from core identity to allow update history and periodic re-measurement.

Key properties:
- `athlete` (FK, one-to-one current profile)
- `birth_date`
- `weight_kg`
- `height_cm`
- `resting_hr`
- `max_hr`
- `ftp_watts` — Functional Threshold Power (cycling)
- `lactate_threshold_pace` — for running
- `vo2max` — optional, lab or estimated
- `training_age_years`
- `dominant_discipline` — PRIMARY sport
- `updated_at`

Profile values feed directly into analytics computation (TSS, training zones, PMC).

### AthleteCoachAssignment

An athlete may have multiple coaches. This model makes the assignment explicit and typed.

Key properties:
- `athlete` (FK)
- `coach` (FK)
- `organization` (FK, non-nullable — determines tenant scope)
- `role` — `primary` or `assistant`
- `assigned_at`
- `ended_at` — nullable; historical assignments are preserved

**Primary coach rule:** An athlete may have exactly one primary coach per organization at any given time. Multiple assistant coaches are allowed. This constraint is enforced at the application layer.

### AthleteMembershipHistory

Records the complete history of an athlete's organizational affiliations.
An athlete may move between organizations over their career.

Key properties:
- `athlete` (FK)
- `organization` (FK)
- `joined_at`
- `left_at` — nullable (null = current)
- `reason` — optional descriptive text

This model is immutable after creation (history must not be altered).

### AthleteGoal

A declared performance target for an athlete, scoped to a race or time period.

Key properties:
- `athlete` (FK)
- `organization` (FK, non-nullable)
- `goal_type` — `finish`, `podium`, `time_target`, `distance_pr`, `load_block`
- `target_event` — optional FK to RaceEvent
- `target_date`
- `target_value` — numeric (e.g., finish time in seconds)
- `description`
- `status` — `active`, `achieved`, `abandoned`
- `created_at`

---

## 5. Planning Domain

### WorkoutLibrary

A named collection of workout templates owned by an organization.
The library is the source from which coaches draw when prescribing individual sessions.

Key properties:
- `organization` (FK, non-nullable)
- `name`
- `description`
- `created_by` (FK to User)
- `is_public` — whether templates are visible to all coaches in the org
- `created_at`

A library is a container, not a workout itself. Workouts within a library are `PlannedWorkout` records with `is_template=True`.

### PlannedWorkout

The atomic unit of coaching prescription.

**Critical invariant: A `PlannedWorkout` represents the coach's intent only. It is never mutated by execution data, and never merged with a `CompletedActivity`. This is a non-negotiable domain law.**

Key properties:
- `organization` (FK, non-nullable — tenancy anchor)
- `title`
- `description`
- `sport` — `run`, `trail`, `bike`, `strength`, `mobility`, `swim`
- `scheduled_date` — target date (nullable for template workouts)
- `duration_target_s` — prescribed duration in seconds
- `distance_target_m` — prescribed distance in meters
- `is_template` — if True, lives in a WorkoutLibrary; if False, is an assigned session
- `library` — FK to WorkoutLibrary (nullable; only set for templates)
- `created_by` (FK to User — the prescribing coach)
- `created_at`
- `updated_at`
- `version` — integer, increments on change (prescription history)
- `schema_version` — for future structured format evolution

### WorkoutBlock

A named phase within a PlannedWorkout.
Examples: Warm-up, Main Set, Tempo Block, Cool-down.

Key properties:
- `workout` (FK to PlannedWorkout, non-nullable)
- `order` — integer, defines sequence
- `name`
- `description`
- `duration_target_s`
- `distance_target_m`

### WorkoutInterval

A single repeated unit within a WorkoutBlock.
Examples: 5x(1000m @ threshold), 3x(5min @ sweetspot).

Key properties:
- `block` (FK to WorkoutBlock, non-nullable)
- `order` — integer, defines sequence within block
- `repetitions`
- `duration_target_s` — per rep
- `distance_target_m` — per rep
- `power_target_watts` — optional
- `hr_target_bpm` — optional
- `pace_target_s_per_km` — optional
- `rpe_target` — Rate of Perceived Exertion 1–10
- `rest_duration_s` — rest between reps

**Prescription rule:** Interval targets are set by the coach. Athletes cannot modify them.

### WorkoutAssignment

Links a `PlannedWorkout` to a specific `Athlete` on a specific date.
This is the assignment layer — it records which workout was prescribed for whom, when.

Key properties:
- `workout` (FK to PlannedWorkout)
- `athlete` (FK)
- `organization` (FK, non-nullable)
- `assigned_by` (FK to User — the coach)
- `scheduled_date` — the originally assigned date
- `athlete_moved_date` — nullable; if athlete used day-swap, records new date
- `status` — `pending`, `completed`, `missed`, `skipped`
- `assigned_at`

**Athlete day-swap rule:** An athlete may move a workout to a different day.
`athlete_moved_date` records the new date. The original prescription is never changed.
This is the only modification right granted to athletes on planned workouts.

---

## 6. Activity Domain

### CompletedActivity

The immutable record of what an athlete actually did.

**Critical invariant: A `CompletedActivity` is evidence, not intent. It is never edited, merged with a plan, or used to infer prescription. It is the source of truth for execution.**

Key properties:
- `organization` (FK, non-nullable — fail-closed tenancy anchor)
- `athlete` (FK)
- `provider` — `strava`, `garmin`, `coros`, `suunto`, `polar`, `wahoo`, `manual`, `other`
- `provider_activity_id` — external ID from the provider (for idempotency)
- `sport` — normalized sport type
- `started_at` — timezone-aware datetime
- `duration_s` — actual duration in seconds
- `distance_m` — actual distance in meters
- `elevation_gain_m`
- `elevation_loss_m`
- `avg_hr_bpm`
- `max_hr_bpm`
- `avg_power_watts`
- `normalized_power_watts`
- `tss` — Training Stress Score
- `calories_kcal`
- `raw_payload` — original JSON from provider (preserved for re-processing)
- `ingested_at`
- `source_hash` — SHA-256 of key fields for change detection

**Idempotency constraint:** `(organization, provider, provider_activity_id)` is unique.
Duplicate deliveries from any provider are silently ignored.

**Provider boundary rule:** Raw payload parsing and normalization live exclusively in `integrations/<provider>/`. The domain model receives only normalized data.

### ActivityStream

Time-series data from a completed activity.
Heart rate, power, cadence, pace, altitude — sampled at 1–5 second intervals.

Key properties:
- `activity` (FK to CompletedActivity, non-nullable)
- `stream_type` — `heartrate`, `power`, `cadence`, `pace`, `altitude`, `latlng`
- `data` — JSONField (list of numeric samples)
- `resolution` — samples per second
- `recorded_at`

ActivityStream data is voluminous. It is stored separately from CompletedActivity
to allow lightweight activity queries without loading stream data.

---

## 7. Science / Analytics Domain

### TrainingLoad

Per-session quantification of training stress.
Derived from activity data; provides the input for PMC modeling.

Key properties:
- `activity` (FK to CompletedActivity, one-to-one)
- `tss` — Training Stress Score (primary load metric)
- `atl_contribution` — contribution to 7-day acute load
- `ctl_contribution` — contribution to 42-day chronic load
- `computed_at`

### PMCModel

The Performance Management Chart model (Banister/Coggan).

Tracks the athlete's rolling fitness, fatigue, and form across the full training history.
Updated after every new CompletedActivity.

Key properties:
- `athlete` (FK)
- `organization` (FK, non-nullable)
- `sport` — `ALL`, `RUN`, `BIKE`
- `date`
- `ctl` — Chronic Training Load (Fitness, 42-day exponential)
- `atl` — Acute Training Load (Fatigue, 7-day exponential)
- `tsb` — Training Stress Balance (Form = CTL − ATL)
- `tss_day` — total TSS on this date
- `computed_at`

Unique constraint: `(athlete, sport, date)`.

### PlanRealCompare

The explicit reconciliation record between a planned session and what was executed.
This is the machine-readable result of the Plan vs Real comparison.

**This record is computed — never manually created or edited.**

Key properties:
- `organization` (FK, non-nullable)
- `athlete` (FK)
- `planned_workout` (FK to PlannedWorkout, nullable — may be unmatched)
- `completed_activity` (FK to CompletedActivity, nullable — may be unmatched)
- `match_confidence` — float 0–1 (algorithmic match quality)
- `match_method` — string describing algorithm version
- `duration_delta_s` — actual minus planned duration
- `distance_delta_m` — actual minus planned distance
- `load_delta` — actual TSS minus planned load
- `compliance_score` — integer 0–100
- `classification` — `on_track`, `under`, `over`, `anomaly`, `no_plan`, `no_execution`
- `explanation` — human-readable summary
- `reconciled_at`

### CoachDecision

A coach-authored or system-generated recommendation following Plan vs Real analysis.

Key properties:
- `organization` (FK, non-nullable)
- `coach` (FK to User)
- `athlete` (FK)
- `trigger` — `manual`, `alert`, `compliance_drop`, `injury_risk`, `load_spike`
- `recommendation` — free text (coach-authored or AI-suggested)
- `action_type` — `reduce_load`, `increase_load`, `rest_day`, `consult_staff`, `maintain`
- `status` — `pending`, `applied`, `dismissed`
- `created_at`
- `applied_at` — nullable

---

## 8. Competition / Events

### RaceEvent

A target competition for one or more athletes in an organization.

Key properties:
- `organization` (FK, non-nullable)
- `name`
- `date`
- `location`
- `discipline` — `run`, `trail`, `bike`, `triathlon`, `other`
- `distance_km`
- `elevation_gain_m` — for trail / mountain events
- `is_priority` — flags A/B/C race hierarchy
- `url` — optional official event URL
- `notes`
- `created_by` (FK to User)

### AthleteGoal (see Section 4)

AthleteGoal links an athlete's declared target to a RaceEvent.
The planning engine uses `target_date` from AthleteGoal to compute the training block
leading into the race.

---

## 9. Community / Communication

### TeamLeaderboard

An aggregated performance metric view across athletes in a Team.
Used for internal coaching visibility and team motivation.

**Non-social-network rule:** Leaderboards display training metrics (load, consistency,
compliance) — not only competition results. They serve the coach's operational view.

Key properties:
- `organization` (FK, non-nullable)
- `team` (FK to Team, nullable — org-wide if null)
- `metric` — `weekly_load`, `monthly_distance`, `compliance_rate`, `consistency_score`
- `period_start`
- `period_end`
- `payload` — JSONField (ranked athlete list with metric values)
- `computed_at`

Unique constraint: `(organization, team, metric, period_start, period_end)`.

### ChatThread

A communication thread between coach and athlete (or between coach and team).

Key properties:
- `organization` (FK, non-nullable)
- `thread_type` — `coach_athlete`, `coach_team`, `staff_athlete`
- `coach` (FK to User)
- `athlete` (FK, nullable — null for team threads)
- `team` (FK to Team, nullable — null for direct threads)
- `created_at`

### ChatMessage

A single message within a ChatThread.

Key properties:
- `thread` (FK to ChatThread, non-nullable)
- `sender` (FK to User)
- `body` — text content
- `attachment_url` — optional
- `sent_at`
- `read_at` — nullable

Messages are immutable after creation. Deletion is soft (body replaced with `[deleted]`).

---

## 10. Integrations

### ExternalIdentity

Links a Quantoryn user to their identity on an external provider platform.
Created on webhook receipt even before the user has onboarded (UNLINKED state).

Key properties:
- `provider` — `strava`, `garmin`, `coros`, `suunto`, `polar`, `wahoo`
- `external_user_id` — provider-native user ID (string)
- `athlete` (FK, nullable — null until explicitly linked by coach/athlete)
- `status` — `unlinked`, `linked`, `disabled`
- `linked_at` — nullable
- `profile` — JSONField (provider-supplied profile snapshot)

Unique constraint: `(provider, external_user_id)`.

**Provider isolation rule:** Provider-specific logic for identity resolution lives in
`integrations/<provider>/`. This model is provider-agnostic.

### OAuthCredential

Stores OAuth access and refresh tokens for a specific athlete–provider pair.
Never logged. Never exposed in serializers. Never accessible without explicit coach scope.

Key properties:
- `athlete` (FK)
- `provider` — provider slug string (not a choices field — extensible without migration)
- `external_user_id`
- `access_token` — encrypted at rest
- `refresh_token` — encrypted at rest
- `expires_at` — nullable
- `updated_at`

Unique constraint: `(athlete, provider)`.

**Token rule:** Tokens never appear in any log event, Sentry payload, or API response.
Token refresh logic lives exclusively in `integrations/<provider>/`.

---

## 11. Billing

### CoachSubscription

Tracks an organization's billing relationship with Quantoryn.

Key properties:
- `organization` (FK, one-to-one)
- `tier` — `starter`, `pro`, `enterprise`, `trial`
- `athlete_limit` — maximum active athletes under this subscription
- `billing_cycle` — `monthly`, `annual`
- `status` — `active`, `past_due`, `cancelled`, `trialing`
- `current_period_start`
- `current_period_end`
- `stripe_customer_id` — external billing provider reference
- `stripe_subscription_id`
- `created_at`
- `updated_at`

**Billing enforcement rule:** When `active_athlete_count >= athlete_limit`, new athlete
enrollments are blocked until the coach upgrades their tier. This is enforced at the
`Membership` creation layer, not at the model level.

---

## 12. Sport Types

Supported disciplines and their canonical slugs:

| Slug | Display Name | Notes |
|---|---|---|
| `run` | Running | Road and track |
| `trail` | Trail Running | Off-road, mountain |
| `bike` | Cycling | Road, gravel, MTB, indoor |
| `strength` | Strength | Gym, weights, functional |
| `mobility` | Mobility | Yoga, stretching, recovery |
| `swim` | Swimming | Pool and open water |
| `triathlon` | Triathlon | Future — multi-sport composite |
| `other` | Other | Catch-all |

**Normalization rule:** Provider-native sport types (e.g., Strava's `TrailRun`,
Garmin's `trail_running`) must be mapped to these canonical slugs before
reaching the domain layer. Mapping lives in `integrations/<provider>/normalizer.py`.

---

## 13. Core Relationship Summary

```
Organization
 ├── CoachSubscription (1:1)
 ├── Team (1:N)
 ├── Membership (1:N)
 │    └── User → (Coach | Athlete | Staff role)
 ├── WorkoutLibrary (1:N)
 ├── RaceEvent (1:N)
 ├── TeamLeaderboard (1:N)
 ├── ChatThread (1:N)
 └── CoachDecision (1:N)

Athlete (via Membership)
 ├── AthleteProfile (1:1 current)
 ├── AthleteCoachAssignment (1:N — one primary, N assistants per org)
 ├── AthleteMembershipHistory (1:N)
 ├── AthleteGoal (1:N)
 ├── WorkoutAssignment (1:N)
 ├── CompletedActivity (1:N)
 ├── PMCModel (1:N by date+sport)
 ├── ExternalIdentity (1:N by provider)
 ├── OAuthCredential (1:N by provider)
 └── CoachDecision (1:N — received)

PlannedWorkout
 ├── WorkoutBlock (1:N, ordered)
 │    └── WorkoutInterval (1:N, ordered)
 └── PlanRealCompare (0:1 per completed activity match)

CompletedActivity
 ├── ActivityStream (1:N by stream_type)
 ├── TrainingLoad (1:1)
 └── PlanRealCompare (0:1 per planned workout match)
```

---

## 14. Non-Negotiable Domain Rules

These rules are constitutional. They cannot be relaxed without an explicit architectural decision record (ADR).

| # | Rule | Consequence of Violation |
|---|------|--------------------------|
| 1 | Organization-first | Every query must filter by `organization`. No organization context = deny. |
| 2 | Membership is the gate | Users access org data only through active `Membership` records. No exceptions. |
| 3 | Plan ≠ Real | `PlannedWorkout` and `CompletedActivity` are never merged, never aliased, never written to from each other. Reconciliation is always explicit and computed. |
| 4 | Provider boundary | All provider-specific code (OAuth, payload parsing, normalization) lives in `integrations/<provider>/`. Core domain code is provider-agnostic. |
| 5 | Idempotent ingestion | Any activity or event from an external provider must be safe to receive twice. No duplicate records may be created. |
| 6 | Athlete cannot edit prescription | An athlete may move a workout date. They may not edit blocks, intervals, targets, or any scientific parameter. |
| 7 | Tokens never leak | OAuth credentials never appear in logs, Sentry events, API responses, or error messages. |
| 8 | Coaches pay Quantoryn | The billing relationship is between Quantoryn and the organization (via coach/owner). Athletes are not billed by Quantoryn. |
| 9 | History is immutable | Membership history, activity data, and reconciliation records are never deleted or altered. Soft delete or status flags only. |
| 10 | Science is the authority | Load metrics, TSS computations, and PMC values are computed from data — never manually overridden by UI input. |

---

## 15. Strategic Product Consequences

### Why organization-first matters

Without `Organization` as the tenant root, it is impossible to:
- sell to academies, clubs, and federations (multi-coach, multi-team accounts)
- enforce subscription tier limits on athlete counts
- support coach-to-coach handoffs when athletes change coaches
- support staff (physio, nutritionist) with scoped access

The current `entrenador`-as-tenant model scales to single independent coaches.
Organization-first is required for B2B growth.

### Why Plan ≠ Real is a competitive advantage

Platforms that merge planned and actual data lose the ability to:
- compute compliance accurately
- attribute performance outcomes to specific training prescriptions
- identify systematic planning errors (coaches who over-prescribe)
- generate meaningful recommendations based on deviation patterns

Preserving the separation is what makes Quantoryn a scientific tool, not a logging app.

### Why provider-agnostic ingestion is required

Quantoryn's value is coach intelligence, not device intelligence.
If the domain model couples to Strava-specific fields, adding Garmin requires
a full domain refactor. Provider-agnostic normalization means new devices add
zero domain complexity.

### Why multiple coaches per athlete is required

Elite endurance athletes commonly work with:
- a primary running coach
- a cycling or strength specialist
- a nutritionist
- a physiotherapist

Quantoryn must model this reality, or coaches will manage it in spreadsheets.

---

## 16. Immediate Build Sequence

The following PRs build the domain foundation in strict dependency order.
Each PR depends on all previous PRs being merged and stable.

| PR | Title | Depends On | Risk |
|---|---|---|---|
| PR-101 | Organization + Team models | none | High |
| PR-102 | Membership + roles + tenancy gate | PR-101 | High |
| PR-103 | Coach + Athlete domain foundation | PR-102 | Medium-High |
| PR-104 | AthleteCoachAssignment | PR-103 | Medium |
| PR-105 | AthleteProfile + AthleteGoal | PR-103 | Low-Medium |
| PR-106 | RaceEvent | PR-102 | Low |
| PR-107 | WorkoutLibrary | PR-103 | Low |
| PR-108 | PlannedWorkout + Block + Interval | PR-107 | Medium |
| PR-109 | WorkoutAssignment | PR-108 + PR-103 | Low-Medium |
| PR-110 | CompletedActivity + ActivityStream | PR-103 | Medium |

**Do not begin PR-103 until PR-101 and PR-102 are merged and tested.**
**Do not begin PR-108 until PR-107 is merged and stable.**
**PR-110 must include a protective test confirming Plan ≠ Real invariant.**

---

*Last updated: 2026-03-07 · See also: `docs/ai/CONSTITUTION.md`, `docs/vendor/integration_architecture.md`*
