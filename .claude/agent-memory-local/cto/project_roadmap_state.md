# Project Roadmap State — CTO Memory
_Last updated: 2026-03-22 · Session post PR-134 merge_

## Phase
P2 — Historical Data, Analytics & Billing (IN PROGRESS)

## Completed PRs (P2)

| PR | Branch | Description | Merged |
|----|--------|-------------|--------|
| PR-125 | p2/pr125-* | Athlete.clean() cross-org validation | ✅ |
| PR-126 | p2/pr126-* | CompletedActivity.organization FK → Organization | ✅ |
| PR-127 | p2/pr127-* | Ingestion fills CompletedActivity.athlete FK | ✅ |
| PR-130 | p2/pr130-billing-gates | OrganizationSubscription + require_plan() decorator | ✅ 2026-03-21 |
| PR-131 | p2/pr131-mp-subscriptions | MercadoPago subscriptions + 15-day Pro trial (signal) | ✅ 2026-03-21 |
| PR-132 | — (main direct) | Billing views: status, subscribe, cancel + serializers | ✅ 2026-03-21 |
| PR-133 | p2/pr133-coach-pricing-plan | CoachPricingPlan + AthleteSubscription models + migration | ✅ 2026-03-22 |
| PR-134 | p2/pr134-coach-mp-oauth | Coach MP OAuth connect (OrgOAuthCredential + 3 views) | ✅ 2026-03-22 |

## Next PR Queue

### PR-135 🔴 NEXT — Athlete invitation + MP preapproval creation
- Coach creates CoachPricingPlan → generates MP preapproval link
- Sends invite to athlete (email/link)
- Creates AthleteSubscription(status=pending)
- Risk: Medium-High

### PR-136 — AthleteSubscription webhook handler
- Processes MP webhook for payment events
- Updates AthleteSubscription.status (active/overdue/cancelled)
- Idempotent (Law 5)
- Risk: Medium

### PR-128 — Real-side PMC (CTL/ATL/TSB)
- Computes CTL/ATL/TSB from CompletedActivity
- Core scientific feature
- Risk: Low-Medium

### PR-129 — Historical backfill pipeline
- Celery task to pull historical Strava activities
- Risk: Medium

## Billing Architecture Summary

```
Quantoryn B2B: Coach pays Quantoryn (OrganizationSubscription)
Coach B2C:     Athlete pays Coach via MercadoPago (AthleteSubscription)
```

### Models built
- `OrganizationSubscription` — plan tier, trial, is_active
- `SubscriptionPlan` — configurable pricing (admin), mp_plan_id
- `CoachPricingPlan` — coach's pricing for athletes, price_ars
- `AthleteSubscription` — athlete→coach plan, status lifecycle
- `OrgOAuthCredential` — org-scoped OAuth credential (coach MP account)

### Integrations built
- `integrations/mercadopago/client.py` — mp_get/post/put
- `integrations/mercadopago/subscriptions.py` — create/get/cancel
- `integrations/mercadopago/webhook.py` — process_subscription_webhook (idempotent)
- `integrations/mercadopago/oauth.py` — mp_get_authorization_url + mp_exchange_code

### What's missing to complete billing loop
1. ~~Coach MP OAuth (PR-134)~~ ✅ DONE
2. Athlete invite + preapproval (PR-135)
3. AthleteSubscription webhook handler (PR-136)

## Technical Debt
- FINDING-X4-A: ExternalIdentityViewSet legacy scope (low priority)
- Migration 0083 uses atomic=False (standard pattern for PostgreSQL FK+DDL)
- PR-132 was merged directly to main (no feature branch) — process gap corrected
- PR-134: OrgOAuthCredential uses fresh org instance in tests to avoid cached reverse OneToOne from post_save signal

## Key Technical Decisions
- atomic=False: standard for any migration combining DDL + DML on FK tables
- Lazy imports: Law 4 compliance for integrations/ imports in core/
- PASO 0 mandatory: all future prompts must start with branch creation
- transaction=True on IntegrityError tests: PostgreSQL aborts tx on violations

## Test Baseline
~1238+ tests | CI: backend ✅ frontend ✅
