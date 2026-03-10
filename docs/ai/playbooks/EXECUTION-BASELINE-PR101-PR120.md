# Execution Baseline — PR-101 through PR-120
> **Quantoryn / MendietaTrailPlatform**
> Official execution lane for the P1 domain foundation and first product surface build-out.
> **Last updated:** 2026-03-09

---

## Purpose

This document is the authoritative sequencing record for the Quantoryn P1 build
from the Organization model (PR-101) through the first frontend surfaces (PR-120).

It does **not** replace individual task capsules. Those remain the specification
for each PR. This document establishes:

- sequencing logic and why it exists
- known divergences between the capsule stack and actual implementation
- current risks that must not be forgotten
- the dependency map that governs what can be built in parallel vs. sequentially
- what is explicitly out of scope for this batch

---

## Execution Principles

1. **Model-first → service → API → frontend.** Never reverse this order.
2. **One PR = one idea.** No bundling of unrelated concerns.
3. **Plan ≠ Real is a domain law, not a preference.** Every PR touching planning or
   execution models must include a named `PlanNotRealInvariantTests` class with
   explicit field-level assertions. These tests may never be removed to accommodate
   a feature request. A feature that requires their removal is architecturally wrong.
4. **Organization-first, fail-closed.** No query without an org filter. No entity
   without a non-nullable `organization` FK.
5. **Provider isolation.** All provider-specific logic lives in `integrations/`.
   Domain models (`core/`) must remain provider-agnostic. `provider` is a CharField,
   never a FK to a registry.
6. **Frontend and backend in separate PRs** unless the coupling is strictly required
   and explicitly justified. Mixed PRs increase blast radius and reduce reviewability.
7. **CI green is a hard requirement.** A PR is not done if any check is red.
   Never suppress a failing test.

---

## Baseline Summary

### Implemented (as of 2026-03-09, latest migration: 0072_completed_activity_normalization)

| Model(s) | Capsule | Migration | Test file(s) | Status |
|----------|---------|-----------|--------------|--------|
| Organization, Team | PR-101 | 0062 | tests_organization.py | ✅ Done |
| Membership | PR-102 | 0063 | tests_membership.py | ✅ Done |
| Coach, Athlete | PR-103 | 0064 | tests_coach_athlete.py | ✅ Done |
| AthleteCoachAssignment | PR-104 | 0065 | tests_athlete_coach_assignment.py | ✅ Done |
| AthleteProfile | PR-105 | 0066 | tests_athlete_profile.py | ✅ Done |
| RaceEvent | PR-106 | 0067 | tests_race_event.py | ✅ Done |
| AthleteGoal | PR-105 spec / PR-107 branch* | 0068 | tests_athlete_goal.py | ✅ Done |
| WorkoutLibrary | PR-107 capsule / PR-111 slot | 0069 | tests_workout_library.py | ✅ Done |
| PlannedWorkout, WorkoutBlock, WorkoutInterval | PR-108 capsule / PR-112 slot | 0070 | tests_planned_workout.py | ✅ Done |
| WorkoutAssignment + services_workout.py | PR-109 capsule / PR-113 slot | 0071 | tests_workout_assignment.py | ✅ Done |
| CompletedActivity (athlete bridge) + ActivityStream | PR-110 capsule / PR-114 slot | 0072 | tests_completed_activity.py | ✅ Done |
| AthleteGoal + RaceEvent CRUD API | PR-115 | no migration | tests_athlete_goal_api.py | ✅ Done |
| AthleteProfile CRUD API | PR-116 | no migration | tests_athlete_profile_api.py | ✅ Done |
| WorkoutAssignment API | PR-117 | no migration | tests_workout_assignment_api.py | ✅ Done |

*See Known Divergences, item D1.

### Not Yet Implemented (capsule-defined scope)

All capsules PR-107 through PR-110 are now implemented. Remaining work is in the "Not Yet Defined" extended lane below.

### Not Yet Defined (new scope, accepted product decisions)

| Content | Extended Lane Slot |
|---------|--------------------|
| AthleteGoal + RaceEvent CRUD API | PR-115 |
| AthleteProfile API | PR-116 |
| WorkoutAssignment API | PR-117 |
| Plan vs Real Reconciliation Foundation | PR-118 |
| Frontend: Athlete Goal Module | PR-119 |
| Frontend: Race Event Catalog + Athlete Weekly Schedule | PR-120 |

---

## Known Divergences

### D1 — PR-107 capsule not executed; branch naming collision

**What the capsule says:** PR-107 = WorkoutLibrary model.

**What actually happened:** Branch `p1/pr107-athlete-goal` delivered `AthleteGoal`
instead. AthleteGoal was originally specified in the PR-105 capsule alongside
AthleteProfile, but was blocked pending RaceEvent (PR-106). After RaceEvent was
implemented, AthleteGoal was delivered on a branch numerically labeled PR-107.

**Result:** The PR-107 capsule (WorkoutLibrary) has never been executed.
Everything from PR-107 through PR-110 in the capsule stack is one PR behind in
actual implementation.

**Resolution:** Do not renumber. Do not rewrite capsule history. WorkoutLibrary
is implemented as **PR-111** in the extended lane. The capsule PR-107 document
retains its original WorkoutLibrary specification with an addendum noting the
divergence.

---

### D2 — CompletedActivity.organization architectural mismatch

**What the domain spec requires:** `CompletedActivity.organization` should be a
`ForeignKey("Organization")` — the P1 tenant root model.

**What actually exists:** `CompletedActivity.organization` is currently
`ForeignKey(settings.AUTH_USER_MODEL)` — a User acting as an organization proxy.
This predates the `Organization` model (PR-101) and the P1 architecture.

**Result:** `CompletedActivity` is not yet on the organization-first architecture.
The `alumno` FK also points to legacy `Alumno`, not the new `Athlete` model.

**Resolution:**
- PR-114 (CompletedActivity normalization) adds an `Athlete` FK (nullable,
  backward-compatible) and introduces `ActivityStream`.
- The full migration of `organization` from User to the `Organization` model is
  **explicitly deferred** to a separate high-risk PR after PR-120. It requires
  a data migration and careful backward-compatibility planning.
- This debt is tracked here and must not be forgotten.

---

### D3 — AthleteGoal capsule origin split

AthleteGoal is specified in the PR-105 capsule (alongside AthleteProfile) but
was blocked and delivered separately. The PR-105 capsule addendum (see that file)
documents the split. Both AthleteProfile and AthleteGoal are fully implemented
and tested. The only residual effect is the branch naming (D1 above).

---

## Current Risks

| Risk | Severity | Owner PR | Notes |
|------|----------|----------|-------|
| `CompletedActivity.organization` → User (not Organization) | High | PR-114 partial; full migration post-PR-120 | Structural technical debt. Must not be ignored. |
| No API surface for any P1 domain model | Medium | PR-115, PR-116, PR-117 | AthleteGoal, RaceEvent, AthleteProfile are model-complete but unreachable from the product. |
| `StravaDiagnosticsView` is AllowAny; exposes `subscription_id` | Medium | Carry-over from P0 | Not in PR-111–120 scope. Separate P0 fix. |
| Plan≠Real formally tested in PR-112 | ✅ Resolved | PR-112 done | `PlanNotRealInvariantTests` class present and green (44 tests). |
| Planning domain chain unblocked | ✅ Resolved | PR-112 done | WorkoutLibrary + PlannedWorkout + Block + Interval all implemented. |
| `AlertDelivery` not wired | Low | Post-PR-120 | Alert objects created; no Slack/webhook notification. |
| Frontend has zero P1 domain coverage | Low-Medium | PR-119, PR-120 | No goal, race event, or schedule UI exists. |

---

## Dependency Map

```
PR-101 (Organization, Team)
├── PR-102 (Membership, OrgTenantMixin, require_role)
├── PR-103 (Coach, Athlete)
│   ├── PR-104 (AthleteCoachAssignment)
│   ├── PR-105 (AthleteProfile)
│   ├── PR-106 (RaceEvent)
│   │   └── PR-105b / branch p1/pr107-athlete-goal (AthleteGoal)
│   └── PR-111 (WorkoutLibrary)          ← next
│       └── PR-112 (PlannedWorkout, WorkoutBlock, WorkoutInterval)
│           └── PR-113 (WorkoutAssignment, services_workout.py)
│               └── PR-118 (PlanRealCompare, services_reconciliation.py)
│                           ↑ also requires PR-114
└── PR-114 (CompletedActivity + ActivityStream normalization)
    └── PR-118 (PlanRealCompare) ← shared dependency with PR-113

PR-102 (OrgTenantMixin)
└── PR-115 (AthleteGoal + RaceEvent API)
    └── PR-119 (Frontend: Goal Module)
└── PR-116 (AthleteProfile API)
└── PR-117 (WorkoutAssignment API)
    └── PR-120 (Frontend: Race Event + Athlete Schedule)
        ↑ also requires PR-115
```

**Parallelizable after PR-114 is done:**
- PR-115 and PR-116 can run in parallel.
- PR-119 and PR-120 can begin as soon as their respective API PRs land.

---

## Recommended Next PR

**PR-118 — Plan vs Real Reconciliation Foundation**

PR-115, PR-116, and PR-117 are complete. The full planning API surface is now
exposed. PR-118 adds the reconciliation foundation that links WorkoutAssignment
(planning) to CompletedActivity (execution) via PlanRealCompare.

See extended lane summary below for the full dependency chain.

---

## Extended Lane Summary (PR-111–PR-120)

| PR | Title | Type | Depends on |
|----|-------|------|------------|
| PR-111 | WorkoutLibrary | Model | PR-101, PR-103 |
| PR-112 | PlannedWorkout + WorkoutBlock + WorkoutInterval | Model | PR-111 |
| PR-113 | WorkoutAssignment + services_workout.py | Model + Service | PR-112, PR-103 |
| PR-114 | CompletedActivity + ActivityStream normalization | Model + Tests | PR-103, existing 0060 |
| PR-115 | AthleteGoal + RaceEvent CRUD API | API | PR-105/106/107, PR-102 |
| PR-116 | AthleteProfile CRUD API | API | PR-105, PR-102 |
| PR-117 | WorkoutAssignment API | API | PR-113, PR-115 pattern |
| PR-118 | Plan vs Real Reconciliation Foundation | Model + Service | PR-113, PR-114 |
| PR-119 | Frontend: Athlete Goal Module | Frontend | PR-115 |
| PR-120 | Frontend: Race Event Catalog + Athlete Schedule | Frontend | PR-115, PR-117 |

---

## Out of Scope for PR-111–PR-120

The following must not enter this lane under any circumstances:

**AI features:**
No AI-generated training plans, AI workout suggestions, prediction models, or
LLM integration. The platform must prove scientific integrity on real coach data
before AI augmentation is introduced.

**Analytics computation:**
No PMC calculation, TSS computation, CTL/ATL modeling. These require a stable
CompletedActivity → AthleteProfile pipeline that is not fully in place until
after PR-114 and the deferred org migration.

**Provider enablement:**
Garmin, Coros, Suunto, Polar, and Wahoo remain stubs. Only Strava is active.
Multi-provider rollout is a separate product decision with its own PR chain.

**Data migrations between legacy and new domain:**
- Alumno → Athlete backfill: separate explicit scoped PR.
- CompletedActivity.organization User → Organization migration: deferred post-PR-120.
  High blast radius. Requires an explicit ADR and migration plan.

**OAuth/webhook/token lifecycle changes:**
The Strava OAuth surface is a frozen contract. No changes. No new callback URLs.
StravaDiagnosticsView security concern is tracked separately.

**API versioning:**
The `/api/v1/` prefix is not introduced in this batch. The existing `/api/`
prefix is maintained for continuity. Versioning is a separate architectural decision.

**Anything that weakens Plan ≠ Real:**
No `actual_*` field on `PlannedWorkout`, `WorkoutBlock`, or `WorkoutAssignment`.
No FK from any planning model to any execution model. Any proposal to cross this
boundary requires a formal ADR and explicit approval before any implementation.

---

*Document owner: Antigravity (engineering agent) · See also: `docs/ai/CONSTITUTION.md`, `docs/ai/REPO_MAP.md`*
