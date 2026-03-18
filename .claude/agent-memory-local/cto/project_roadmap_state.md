---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-X4 (ExternalIdentity API with strict org tenancy, merged 2026-03-17).

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

## ✅ SUUNTO BACKEND EPIC — CLOSED (2026-03-17)

All Suunto backend milestones are complete and merged:
- PR-134: Suunto OAuth Phase 1 (connect/callback/disconnect) — MERGED
- PR-135: Suunto FIT Activity Ingestion — MERGED
- PR-136: Suunto Webhook Subscription + Real-Time Delivery — MERGED
- PR-137: SuuntoPlus Guides (workout push to watch) — MERGED
- PR-X3: Suunto Token Refresh (auto-renovación OAuth) — MERGED
- PR-X4: Suunto ExternalIdentity API (endpoint + strict org tenancy) — MERGED

## ➡️ NEXT OFFICIAL STEP: Frontend React → P1 APIs integration

Connect the React frontend to the P1 backend APIs built during this phase.

P1 backend APIs completed:
- Organization, Team, Membership, Coach, Athlete, AthleteCoachAssignment (PR-129 + PR-130 tenancy)
- WorkoutLibrary, PlannedWorkout (PR-128a) + tenancy sweep (PR-133)
- WorkoutBlock, WorkoutInterval (PR-128b) + tenancy sweep (PR-133)
- WorkoutAssignment with filters (PR-132) + tenancy sweep (PR-133)
- WorkoutReconciliation (prior capsule PRs)
- AthleteProfile, RaceEvent, AthleteGoal (PR-115/116)
- Athlete Weekly Adherence (PR-119)
- SessionStatusView with memberships (PR-131a)

P1 frontend completed:
- OrgContext (multi-org switcher) + CoachDashboard + RosterSection (PR-131b)
- AssignmentCalendar in CoachDashboard (PR-131c)

Multi-provider expansion:
- PR-134: Suunto OAuth Phase 1 (connect/callback/disconnect) — MERGED
- PR-135: Suunto FIT Activity Ingestion — MERGED (tasks, client, parser, ingest service)
- PR-136: Suunto Webhook Subscription + Real-Time Delivery — MERGED
- PR-137: SuuntoPlus Guides (workout push to watch) — MERGED
- PR-X3: Suunto Token Auto-Refresh — MERGED
- PR-X4: Suunto ExternalIdentity API — MERGED
- Existing infra: provider registry (6 providers registered, only strava + suunto enabled)
- ExternalIdentity.Provider: STRAVA + SUUNTO (added in PR-134)
- StravaWebhookEvent model already supports multi-provider (provider field exists)

TENANCY SWEEP DEBT — RESOLVED:
- RaceEventViewSet, AthleteGoalViewSet, AthleteProfileViewSet, ReconciliationViewSet, AthleteAdherenceViewSet — completed as part of P1 sweep

Test coverage milestones:
- Total: 935+ tests (as of PR-133; additional tests added in PR-X3, PR-X4)

## Deferred Items (Technical Debt — future PRs)

- **FINDING-X4-A:** `ExternalIdentityViewSet.get_queryset` uses legacy coach scope (`alumno__entrenador`) instead of P1 org-membership pattern. Will be unified in D2/D3 tenancy debt cleanup.
- **FINDING-X4-B:** No test for explicit unlink via `PATCH alumno=null` on ExternalIdentity. Needs a targeted test in a future tenancy hardening PR.
