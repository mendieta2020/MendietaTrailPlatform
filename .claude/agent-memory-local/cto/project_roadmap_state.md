---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-134 (Suunto OAuth Phase 1, merged/deployed). OAuthCredential stores Suunto tokens.

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Current PR in design: PR-135 — Suunto FIT Activity Ingestion (branch: pr-135-suunto-fit-ingestion). Brief delivered 2026-03-16.

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
- PR-134: Suunto OAuth Phase 1 (connect/callback/disconnect) — DONE, deployed
- PR-135: Suunto FIT Activity Ingestion — IN DESIGN (brief delivered 2026-03-16)
- Existing infra: provider registry (6 providers registered, only strava enabled)
- ExternalIdentity.Provider: STRAVA + SUUNTO (added in PR-134)

TENANCY SWEEP DEBT (still pending):
- RaceEventViewSet, AthleteGoalViewSet, AthleteProfileViewSet, ReconciliationViewSet, AthleteAdherenceViewSet

Test coverage milestones:
- Total: 935+ tests (as of PR-133)

Key architecture findings for PR-135:
- CompletedActivity idempotency: UniqueConstraint on (organization, provider, provider_activity_id)
- CompletedActivity does NOT have avg_hr/max_hr fields — HR data goes in raw_payload JSON only
- TIPO_ACTIVIDAD choices: RUN, TRAIL, CYCLING, MTB, SWIMMING, STRENGTH, CARDIO, INDOOR_BIKE, REST, OTHER
- Celery queues: default, strava_ingest, analytics_recompute, notifications — need suunto_ingest queue
- Suunto settings: SUUNTO_CLIENT_ID, SUUNTO_CLIENT_SECRET already in settings.py
