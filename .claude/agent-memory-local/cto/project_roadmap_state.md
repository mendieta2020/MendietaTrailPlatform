---
name: P2 Roadmap State
description: Current state of P2 roadmap — PR-131 completed, PR-132+ is next
type: project
---

Last completed PR: PR-131 (MercadoPago subscriptions foundation — SubscriptionPlan model, mp_preapproval_id, trial automático 15d, integrations/mercadopago/, webhook endpoint, migration 0082, 23/23 tests green, 2026-03-21).

## P1 STATUS: CLOSED (2026-03-18)

D7 Celery bug (suunto_ingest queue) was fixed — confirmed Queue("suunto_ingest") present in backend/celery.py line 50.

## CURRENT PHASE: P2 — Historical Data, Analytics & Billing

### Controlled Debt carried from P1:
- ~~**D2**: CompletedActivity.organization FK~~ ✅ Fixed in PR-126 (merged 2026-03-20)
- ~~**D3**: Alumno vs Athlete coexistence in ingestion~~ ✅ Fixed in PR-127 (in review 2026-03-20)
- **FINDING-X4-A**: ExternalIdentityViewSet uses legacy coach scope (not Organization-scoped).

### What exists in P2 so far:
- `services_analytics.py`: compute_org_pmc() — planning-side only PMC (CTL/ATL/TSB) from WorkoutAssignment planned_tss
- `services_reconciliation.py`: auto_match_and_reconcile(), compute_weekly_adherence()
- `DashboardAnalyticsView`: planning-only PMC endpoint
- `AthleteAdherenceViewSet`: weekly adherence per athlete
- `ReconciliationViewSet`: manual + auto reconciliation actions
- `Athlete.clean()`: cross-org validation — prevents Athlete belonging to org != membership.organization

### What is missing for P2 North Star:
1. **CompletedActivity.organization FK migration** (D2): must point to Organization, not User ← NEXT
2. **Ingestion pipeline migration** (D3): Strava + Suunto ingest must write `athlete` FK (not just `alumno`)
3. **Real-side analytics**: PMC from actual execution data (CompletedActivity), not just planned
4. **Historical backfill pipeline**: bulk import of past activities for new athletes
5. **Billing integration**: subscription tiers, usage gates
6. **Multi-provider rollout**: Garmin, Coros, Polar, Wahoo activation

### PR sequence dictated:
- ~~PR-125~~: Athlete identity integrity ✅ MERGED 2026-03-20
- ~~PR-126~~: CompletedActivity.organization FK migration (D2 fix) ✅ MERGED 2026-03-20
- ~~PR-127~~: Ingestion pipeline fills CompletedActivity.athlete FK (D3 fix) ✅ MERGED 2026-03-20
- ~~PR-128~~: Real-side analytics — PMC from CompletedActivity ✅ MERGED 2026-03-21
- ~~PR-129~~: Historical backfill pipeline ✅ MERGED 2026-03-21
- ~~PR-130~~: Billing integration — OrganizationSubscription + require_plan gate ✅ MERGED 2026-03-21
- ~~PR-131~~: MercadoPago subscriptions foundation — SubscriptionPlan, trial auto, webhook ✅ COMPLETED (pending merge) 2026-03-21
- **PR-132+**: Multi-provider rollout (Garmin, Coros, Polar, Wahoo) ← NEXT

## Test baseline: 1228+ tests (as of PR-131, 2026-03-21)
