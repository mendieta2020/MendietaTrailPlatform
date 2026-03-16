---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-133 (tenancy isolation sweep for workout viewsets, merged 2026-03-16) + hotfix-roster-404 (merged 2026-03-16) + fix/auth-members-login (merged 2026-03-16)

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Next PR: PR-134 — Suunto OAuth Phase 1 (Connection and Authentication only). Brief delivered 2026-03-16.

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

TENANCY SWEEP DEBT (still pending):
- RaceEventViewSet, AthleteGoalViewSet, AthleteProfileViewSet, ReconciliationViewSet, AthleteAdherenceViewSet

Multi-provider expansion:
- PR-134: Suunto OAuth Phase 1 (connect/callback/disconnect) — IN DESIGN
- Existing infra: provider registry (6 providers registered, only strava enabled), IntegrationStartView/IntegrationCallbackView already provider-agnostic
- Key blocker: ExternalIdentity.Provider enum only has STRAVA (others commented out) — needs migration

Test coverage milestones:
- Total: 935+ tests (as of PR-133)
