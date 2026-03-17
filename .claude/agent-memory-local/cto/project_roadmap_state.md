---
name: P1 Roadmap State
description: Current state of P1 roadmap — last completed PR, next PR to ship, and overall progress
type: project
---

Last completed PR: PR-136 (Suunto Webhook Subscription + Real-Time Delivery, merged 2026-03-17).

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

Current PR in design: PR-137 — SuuntoPlus Guides (workout push to watch). Brief delivered 2026-03-17. Branch: pr-137-suunto-guides.
Key decisions for PR-137:
- New model WorkoutDeliveryRecord (provider-agnostic, UniqueConstraint on assignment+provider)
- Builder pattern in integrations/suunto/guides.py (pure function, no DB)
- REST endpoint: @action on WorkoutAssignmentViewSet (POST .../push/)
- Celery task suunto.push_guide with exponential backoff
- Idempotency via snapshot_version comparison on delivery record
- CAP_OUTBOUND_WORKOUTS added to suunto capability set

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
- PR-135: Suunto FIT Activity Ingestion — MERGED (tasks, client, parser, ingest service)
- PR-136: Suunto Webhook Subscription + Real-Time Delivery — IN DESIGN
- Existing infra: provider registry (6 providers registered, only strava enabled)
- ExternalIdentity.Provider: STRAVA + SUUNTO (added in PR-134)
- StravaWebhookEvent model already supports multi-provider (provider field exists)

TENANCY SWEEP DEBT (still pending):
- RaceEventViewSet, AthleteGoalViewSet, AthleteProfileViewSet, ReconciliationViewSet, AthleteAdherenceViewSet

Test coverage milestones:
- Total: 935+ tests (as of PR-133)

Key architecture findings for PR-136:
- StravaWebhookEvent model has `provider` field (default="strava") — can reuse for suunto
- UniqueConstraint: (provider, event_uid) — already multi-provider compatible
- Suunto API uses `Ocp-Apim-Subscription-Key` header (Azure APIM pattern), NOT HMAC signature
- SUUNTO_SUBSCRIPTION_KEY is already used in client.py for API calls — same key for webhook verification
- Suunto is "webhook-push" architecture per vendor_integration_playbook.md
- Existing Celery task `suunto.ingest_workout` already handles FIT download + parse + persist
- CELERY_TASK_ROUTES needs `suunto.*` queue entry
