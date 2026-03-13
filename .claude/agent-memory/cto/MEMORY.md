# CTO Agent Memory — Quantoryn Roadmap State

## Current Phase: P1 — Organization-First Coach Functionality
- P0 deployed to production and validated via smoke test: 2026-03-12
- P1 officially started: 2026-03-12
- 900 tests green (baseline was ~390 at PR-112)
- All Non-Negotiable Laws satisfied with test coverage
- Release Lockdown Mode: LIFTED — P1 feature work authorized

## P1 Roadmap (PR-127 to PR-131)
- PR-127: CONSTITUTION.md P1 upgrade + Law 4 provider boundary fix
- PR-128: WorkoutLibrary + PlannedWorkout CRUD API (org-scoped)
- PR-129: Coach + Athlete + Team roster API (org-scoped)
- PR-130: P1 tenancy isolation test sweep (new ViewSets)
- PR-131: Frontend coach dashboard — connect to P1 API

## PR History (completed, chronological)
- PR-112 baseline (~390 tests)
- PR-114: CompletedActivity normalization (migration 0072)
- PR-115/116/117: P1 org-first API (RaceEvent, AthleteGoal, AthleteProfile, WorkoutAssignment)
- PR-118: Reconciliation service + model (migration 0073)
- PR-119: Reconciliation API
- PR-120: AI context system (CONSTITUTION.md, REPO_MAP.md, Claude bootloader)
- PR-121: StravaDiagnosticsView hardening (AllowAny->IsAuthenticated, boolean-only response)
- PR-122: Structured logging + token refresh resilience (logging hardening, tenancy patch, # noqa: legacy)
- PR-123: Tenancy isolation test sweep — 69 tests for 8 ViewSets. FINDING-123-A documented
- PR-124: Fix CarreraViewSet — added entrenador FK to Carrera (migration 0074). FINDING-123-A resolved. 876 tests green.
- PR-125: Webhook idempotency test sweep — 13 tests in 5 groups. All gaps closed.
- PR-126: OAuth critical path hardening — 10 tests for disconnect + start edge cases. 900 tests green.

## Deferred Items (from P0, tracked for P1/P2)
1. API versioning (/api/v1/) — high risk, deferred to P2 [P2]
2. Alert delivery channel — AlertaRendimiento exists but no dispatch [P1]
3. HistorialFitness + PMCHistory — dual PMC stores, ambiguous lineage [P2]
4. integration_views.py:230 — provider boundary violation (Law 4) [PR-127 target]
5. core/services.py:33 — imports from integrations.outbound (Law 4 adjacent) [PR-127 target]

## P1 API Surface — What Exists vs What's Missing
### Already built (PRs 115-119):
- RaceEventViewSet: /api/p1/orgs/<org_id>/race-events/
- AthleteGoalViewSet: /api/p1/orgs/<org_id>/goals/
- AthleteProfileViewSet: /api/p1/orgs/<org_id>/profiles/
- WorkoutAssignmentViewSet: /api/p1/orgs/<org_id>/assignments/
- ReconciliationViewSet: /api/p1/orgs/<org_id>/assignments/<id>/reconciliation/
- AthleteAdherenceViewSet: /api/p1/orgs/<org_id>/athletes/<id>/adherence/

### Missing (P1 gaps):
- WorkoutLibrary CRUD (model exists, no API)
- PlannedWorkout CRUD under library (model exists, no org-first API — legacy AlumnoPlannedWorkoutViewSet only)
- Coach roster API (model exists, no API)
- Athlete roster API (model exists, no API)
- Team management API (model exists, no API)
- Membership management API (model exists, no API)

## Architecture Notes
- core/urls.py: legacy routes at /api/ root, P1 routes under /api/p1/orgs/<org_id>/
- AllowAny usage: auth_views.py (login/refresh/logout) + StravaWebhookView (required by Strava) — ALL ACCEPTABLE
- TenantModelViewSet: fail-closed, staff sees all, coach filters by entrenador/uploaded_by/alumno__entrenador
- OrgTenantMixin: P1 pattern for org-scoped ViewSets (used in views_p1.py)
- Last migration: 0074 (Carrera entrenador FK)
- Test count: 900 (as of PR-126)

## Deploy Infrastructure (verified)
- Railway: railway.toml present, healthcheckPath=/healthz, gunicorn WSGI, migrate on start
- Vercel: frontend/vercel.json present, security headers configured, SPA rewrites
- CI: ci.yml (backend+frontend), smoke-prod.yml, smoke-prod-issue-on-fail.yml
- Sentry: configured in both wsgi.py and celery.py with _scrub_sensitive
- Health endpoints: /healthz (db), /healthz/celery, /healthz/redis, /healthz/strava
