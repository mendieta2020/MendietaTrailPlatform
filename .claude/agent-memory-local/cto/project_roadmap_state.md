---
name: P1 Roadmap State
description: Current state of P1 roadmap — P1 audit complete, one PR remains before closure, then P2 begins
type: project
---

Last completed PR: PR-138 (Frontend CoachDashboard Suunto connection UI + fallback modal, merged 2026-03-18).

**Why:** Track roadmap progress to dictate next PR correctly.
**How to apply:** Use this to determine the next logical PR when the developer asks.

## P1 STATUS: AUDIT COMPLETE — ONE PR TO CLOSURE (2026-03-18)

P1 Closure Audit performed 2026-03-18. Full report: `Radiografia_CTO_Cierre_P1.txt` (repo root).

### Critical finding: D7 Celery Queue Bug
- `CELERY_TASK_ROUTES` routes `suunto.*` to `suunto_ingest` queue
- `app.conf.task_queues` in `celery.py` does NOT declare `Queue("suunto_ingest")`
- Result: Suunto tasks are silently unprocessed in production
- Fix: 1 line in `backend/celery.py`

### Blocking PR for P1 Closure:
- **PR-139**: Celery queue fix (`Queue("suunto_ingest")`) + ExternalIdentity PATCH unlink test
- Scope: ~30 LOC, risk LOW
- After PR-139 merges, P1 is CLOSED

### Controlled Debt carried into P2:
- D2: `CompletedActivity.organization` FK points to User (not Organization)
- D3: Alumno vs Athlete coexistence — entire ingestion pipeline uses Alumno
- FINDING-X4-A: ExternalIdentityViewSet uses legacy coach scope

### P2 Preview (do NOT start until PR-139 merged):
1. Legacy Migration epic (D2+D3): migrate ingestion from Alumno to Athlete, change CompletedActivity.organization FK
2. Athlete Portal: athlete-facing frontend
3. Notification Pipeline: Alert delivery
4. API Versioning: /api/v1/
5. Third Provider: Garmin or Coros

## Completed P1 PRs (all merged to main)

Suunto Epic:
- PR-134: Suunto OAuth Phase 1
- PR-135: Suunto FIT Activity Ingestion
- PR-136: Suunto Webhook Subscription
- PR-137: SuuntoPlus Guides
- PR-X3: Suunto Token Refresh
- PR-X4: ExternalIdentity API
- PR-138: Frontend Suunto Connection UI

P1 Core:
- PR-128a/b: WorkoutLibrary/PlannedWorkout/Block/Interval CRUD
- PR-129: Roster API (Coach, Athlete, Team, Membership, Assignment)
- PR-130: Tenancy isolation sweep
- PR-131a: SessionStatusView with memberships
- PR-131b: Frontend OrgContext + CoachDashboard
- PR-132: WorkoutAssignment filters

Test baseline: 935+ tests
