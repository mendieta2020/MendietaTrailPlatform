# Quantoryn — Domain Model Reference

> **Type:** Engineer-facing domain map
> **Audience:** Developers, agents, architects
> **Canonical product source of truth:** [`docs/product/DOMAIN_MODEL.md`](../product/DOMAIN_MODEL.md)
> **Integration architecture:** [`docs/vendor/integration_architecture.md`](../vendor/integration_architecture.md)
> **Last updated:** 2026-03-07

This document is the **navigational index** for the Quantoryn domain. It summarizes every
core entity, shows how they relate to each other, and links to the task capsules that
define their implementation.

For product philosophy, commercial model, and non-negotiable domain rules, see
[`docs/product/DOMAIN_MODEL.md`](../product/DOMAIN_MODEL.md).

---

## The Core Loop

Every entity in this domain serves one of the six stages in the coaching loop:

```
Coach plans
  → Athlete executes
  → Activity returns from provider
  → Plan vs Real reconciliation
  → Analytics
  → Coach decision
  → Plan adapts
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORGANIZATION                              │
│  (tenant root — every record below scopes to this)              │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │  Membership  │   │    Team      │   │  CoachSubscription   │ │
│  │  (roles:     │   │  (subgroups) │   │  (billing tier)      │ │
│  │  owner/coach │   └──────────────┘   └──────────────────────┘ │
│  │  athlete/    │                                                │
│  │  staff)      │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│    ┌────┴──────────────────────────────┐                        │
│    │                                   │                        │
│  ┌─▼──────┐                     ┌──────▼──────┐                │
│  │ Coach  │                     │   Athlete   │                │
│  └────────┘                     └──────┬──────┘                │
│      │                                 │                        │
│      │  AthleteCoachAssignment         │                        │
│      │  (primary / assistant)          │                        │
│      └──────────────────────────► AthleteProfile               │
│                                        │  AthleteGoal           │
│                                        │  AthleteMembershipHistory│
│                                        │                        │
│  PLANNING                              │  EXECUTION             │
│  ┌─────────────────────┐               │  ┌──────────────────┐  │
│  │  WorkoutLibrary     │               │  │ CompletedActivity│  │
│  │  (template catalog) │               │  │ (evidence only)  │  │
│  │         │           │               │  │        │         │  │
│  │  PlannedWorkout     │               │  │ ActivityStream   │  │
│  │  (intent only)      │               │  └────────┬─────────┘  │
│  │    │                │               │           │            │
│  │  WorkoutBlock       │               │  TrainingLoad          │
│  │    │                │  WorkoutAssignment        │            │
│  │  WorkoutInterval    ├───────────────► Athlete   │            │
│  └─────────────────────┘               │           │            │
│                                        │  ┌────────▼──────────┐ │
│  Plan ≠ Real ─────────────────────────►│  │  PlanRealCompare  │ │
│  (never merged, always explicit)       │  │  (reconciliation) │ │
│                                        │  └───────────────────┘ │
│  ┌──────────────────────┐              │                        │
│  │     RaceEvent        │◄─────────────┘ (AthleteGoal links)   │
│  └──────────────────────┘                                       │
│                                                                  │
│  INTEGRATIONS                                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ExternalIdentity   OAuthCredential   OAuthIntegrationStatus│ │
│  │                                                            │  │
│  │  Provider Registry: core/providers/<provider>.py          │  │
│  │  Adapters:          integrations/<provider>/provider.py   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Entity Reference

### Organizational Layer

| Entity | Role in domain | Implementation task |
|---|---|---|
| **Organization** | Tenant root. Every data record belongs to an organization. No cross-org access permitted. | [PR-101](../ai/tasks/PR-101-organization-model.md) |
| **Team** | Named subgroup within an organization (e.g. Team Initial, Team Elite). Scopes leaderboards and scheduling. | [PR-101](../ai/tasks/PR-101-organization-model.md) |
| **Membership** | The access gate between a User and an Organization. Role-typed. Fail-closed: no membership = deny. | [PR-102](../ai/tasks/PR-102-membership-roles.md) |

**Membership roles:**

| Role | Can plan workouts | Can view athlete data | Can be billed |
|---|---|---|---|
| `owner` | Yes | Yes | Yes (org owner) |
| `coach` | Yes | Scoped athletes only | Via org |
| `athlete` | No (view only) | Own data only | Via org |
| `staff` | No | Role-scoped subset | Via org |

---

### People Layer

| Entity | Role in domain | Implementation task |
|---|---|---|
| **Coach** | Organization-scoped identity for a user with coaching role. Anchor for WorkoutLibrary, assignments, decisions. | [PR-103](../ai/tasks/PR-103-coach-athlete-foundation.md) |
| **Athlete** | Organization-scoped identity for a user who executes training. Anchor for all execution and analytics records. | [PR-103](../ai/tasks/PR-103-coach-athlete-foundation.md) |
| **AthleteCoachAssignment** | Typed relationship (primary/assistant) between a Coach and an Athlete within an org. One active primary coach per athlete per org enforced. | [PR-104](../ai/tasks/PR-104-athlete-coach-assignment.md) |
| **AthleteProfile** | Physical and performance parameters (FTP, max HR, weight, VO2max). Feeds analytics computation. | [PR-105](../ai/tasks/PR-105-athlete-profile-goals.md) |
| **AthleteGoal** | Declared performance target (finish, time, distance PR) linked to a RaceEvent or date. | [PR-105](../ai/tasks/PR-105-athlete-profile-goals.md) |

---

### Planning Layer

> **Law:** Planning entities represent **intent only**. They never store execution outcomes.
> See [Plan ≠ Real](#plan--real-invariant) below.

| Entity | Role in domain | Implementation task |
|---|---|---|
| **WorkoutLibrary** | Named collection of template workouts owned by an organization. The source catalog for coach prescriptions. | [PR-107](../ai/tasks/PR-107-workout-library.md) |
| **PlannedWorkout** | A single coaching prescription. Contains sport, targets, and blocks. Version-controlled. Never stores actual outcomes. | [PR-108](../ai/tasks/PR-108-planned-workout-structure.md) |
| **WorkoutBlock** | A named phase within a PlannedWorkout (warm-up, main set, cool-down). Ordered sequence. | [PR-108](../ai/tasks/PR-108-planned-workout-structure.md) |
| **WorkoutInterval** | A single repeated unit within a WorkoutBlock. Carries power, HR, pace, and RPE targets. | [PR-108](../ai/tasks/PR-108-planned-workout-structure.md) |
| **WorkoutAssignment** | Delivery record: links a PlannedWorkout to a specific Athlete on a specific date. Supports athlete day-swap without modifying the prescription. | [PR-109](../ai/tasks/PR-109-workout-assignment.md) |

---

### Execution Layer

> **Law:** Execution entities represent **evidence only**. They never store planning intent.
> See [Plan ≠ Real](#plan--real-invariant) below.

| Entity | Role in domain | Implementation task |
|---|---|---|
| **CompletedActivity** | Immutable record of what an athlete actually did. Provider-agnostic. Idempotent on `(organization, provider, provider_activity_id)`. | [PR-110](../ai/tasks/PR-110-completed-activity-normalization.md) |
| **ActivityStream** | Time-series data (HR, power, cadence, GPS) from a CompletedActivity. Stored separately for query efficiency. | [PR-110](../ai/tasks/PR-110-completed-activity-normalization.md) |

---

### Science / Analytics Layer

| Entity | Role in domain | Notes |
|---|---|---|
| **TrainingLoad** | Per-session TSS quantification. Input to PMC modeling. | Derived from CompletedActivity. |
| **PlanRealCompare** | Explicit reconciliation record between a PlannedWorkout and a CompletedActivity. Computed — never manually created. | The output of the Plan vs Real engine. |
| **PMCModel** | Rolling fitness (CTL), fatigue (ATL), and form (TSB) — Banister/Coggan model per athlete per sport. | Stored in `analytics.PMCHistory`. |
| **CoachDecision** | Coach-authored or system-generated recommendation following Plan vs Real analysis. | Triggers from Alert or manual coach action. |

---

### Competition / Goals

| Entity | Role in domain | Implementation task |
|---|---|---|
| **RaceEvent** | Target competition in the organization's event catalog. Anchors AthleteGoal and training block periodization. | [PR-106](../ai/tasks/PR-106-race-event-model.md) |

---

### Integration Layer

| Entity | Role in domain | Source |
|---|---|---|
| **ExternalIdentity** | Links a Quantoryn user to their identity on an external provider (Strava athlete ID, Garmin user ID). Created UNLINKED on webhook receipt. | `core/models.py` |
| **OAuthCredential** | Stores access + refresh tokens for a specific (athlete, provider) pair. Never logged. Managed exclusively by `integrations/<provider>/`. | `core/models.py` |
| **OAuthIntegrationStatus** | Per-athlete integration health state: CONNECTED, DISCONNECTED, ERROR. Drives "reconnect" prompts in the UI. | `core/integration_models.py` |
| **ActivitySource** | The `provider` string slug on `CompletedActivity` / `Actividad.Source` enum. Canonical values: `strava`, `garmin`, `coros`, `suunto`, `polar`, `wahoo`, `manual`, `other`. | `core/models.py` |

**Provider registry:** `core/providers/registry.py`
**Provider adapters:** `integrations/<provider>/provider.py`
**Full integration architecture:** [`docs/vendor/integration_architecture.md`](../vendor/integration_architecture.md)

---

## Plan ≠ Real Invariant

This is the most important architectural rule in the domain. It is a scientific requirement, not a preference.

```
PlannedWorkout          CompletedActivity
(Coach's intent)        (Athlete's evidence)
      │                        │
      │                        │
      └────────┐   ┌───────────┘
               ▼   ▼
           PlanRealCompare
           (explicit reconciliation record)
           computed, never manually created
```

**Rules enforced by test:**
- `PlannedWorkout` has no `actual_*` fields.
- `PlannedWorkout` has no FK to `CompletedActivity`.
- `CompletedActivity` has no `target_*` fields.
- `CompletedActivity` has no FK to `PlannedWorkout`.

These invariant tests live in `core/tests_planned_workout.py` (PR-108) and
`core/tests_completed_activity.py` (PR-110) and must never be removed.

---

## Tenancy Rules

Every query in the system must satisfy all three conditions:

1. **Filter by `organization`** — all records are organization-scoped.
2. **Derive organization from authenticated user's Membership** — never from request params.
3. **Verify role** — use `require_role()` from `core/tenancy.py` for write operations.

Fail-closed: missing Membership → `PermissionDenied`. Missing organization → deny.

Tenancy service: `core/tenancy.py`
Tenancy gate: `Membership` model ([PR-102](../ai/tasks/PR-102-membership-roles.md))

---

## Build Sequence

The following PRs must be implemented in dependency order:

```
PR-101  Organization + Team
  └─► PR-102  Membership + Tenancy Gate
        └─► PR-103  Coach + Athlete Foundation
              ├─► PR-104  AthleteCoachAssignment
              ├─► PR-105  AthleteProfile + AthleteGoal
              └─► PR-107  WorkoutLibrary
                    └─► PR-108  PlannedWorkout + Block + Interval
                          └─► PR-109  WorkoutAssignment

PR-101  ─► PR-106  RaceEvent  (parallel track)
PR-103  ─► PR-110  CompletedActivity + ActivityStream  (parallel track)
```

---

## Related Documents

| Document | Purpose |
|---|---|
| [`docs/product/DOMAIN_MODEL.md`](../product/DOMAIN_MODEL.md) | Full product philosophy, commercial model, domain rules |
| [`docs/vendor/integration_architecture.md`](../vendor/integration_architecture.md) | Provider adapter architecture, OAuth flow, webhook ingestion |
| [`docs/ai/CONSTITUTION.md`](../ai/CONSTITUTION.md) | Non-negotiable engineering laws |
| [`docs/ai/REPO_MAP.md`](../ai/REPO_MAP.md) | Repository orientation map |
| [`docs/ai/playbooks/vendor_integration_playbook.md`](../ai/playbooks/vendor_integration_playbook.md) | Step-by-step guide for adding a new provider |
| [`docs/ai/agents/integration_agent.md`](../ai/agents/integration_agent.md) | Integration agent responsibilities and constraints |

---

*Last updated: 2026-03-07*
