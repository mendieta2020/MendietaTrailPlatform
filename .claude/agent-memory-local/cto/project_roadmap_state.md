---
name: P2 Roadmap State
description: Current state of P2 roadmap — PR-125 staged, controlled debt items tracked, next PR dictated
type: project
---

Last completed PR: PR-124 (backfill legacy alumnos into athlete roster, merged 2026-03-18, commit 73c9f81).

**Staged (uncommitted):** PR-125 — Athlete.clean() cross-field org validation + 7 tests. Ready to commit.

## P1 STATUS: CLOSED (2026-03-18)

D7 Celery bug (suunto_ingest queue) was fixed — confirmed Queue("suunto_ingest") present in backend/celery.py line 50.

## CURRENT PHASE: P2 — Historical Data, Analytics & Billing

### Controlled Debt carried from P1:
- **D2**: `CompletedActivity.organization` FK points to `settings.AUTH_USER_MODEL` (User), NOT to Organization model. This is a critical tenancy debt — the "organization" field is actually a coach user, not a real Organization.
- **D3**: Alumno vs Athlete coexistence — entire ingestion pipeline (Strava, Suunto) writes to `alumno` FK on CompletedActivity. The `athlete` FK exists but is nullable and not backfilled for ingested rows.
- **FINDING-X4-A**: ExternalIdentityViewSet uses legacy coach scope (not Organization-scoped).

### What exists in P2 so far:
- `services_analytics.py`: compute_org_pmc() — planning-side only PMC (CTL/ATL/TSB) from WorkoutAssignment planned_tss
- `services_reconciliation.py`: auto_match_and_reconcile(), compute_weekly_adherence()
- `DashboardAnalyticsView`: planning-only PMC endpoint
- `AthleteAdherenceViewSet`: weekly adherence per athlete
- `ReconciliationViewSet`: manual + auto reconciliation actions

### What is missing for P2 North Star:
1. **CompletedActivity.organization FK migration** (D2): must point to Organization, not User
2. **Ingestion pipeline migration** (D3): Strava + Suunto ingest must write `athlete` FK (not just `alumno`)
3. **Real-side analytics**: PMC from actual execution data (CompletedActivity), not just planned
4. **Historical backfill pipeline**: bulk import of past activities for new athletes
5. **Billing integration**: subscription tiers, usage gates
6. **Multi-provider rollout**: Garmin, Coros, Polar, Wahoo activation

### PR sequence dictated:
- PR-125: Athlete identity integrity (STAGED — commit and ship)
- PR-126: CompletedActivity.organization FK migration (D2 fix)
- PR-127: Ingestion pipeline Alumno→Athlete migration (D3 fix)
- Then: Real-side analytics, historical backfill, billing

## Test baseline: 80+ test files, ~1000+ tests
