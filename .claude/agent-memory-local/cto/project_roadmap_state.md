# Project Roadmap State — CTO Memory
_Last updated: 2026-03-24 · Session post PR-145a open_

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
| PR-135 | p2/pr135-athlete-invitation | AthleteInvitation backend (model + 5 views + 14 tests) | ✅ 2026-03-22 |
| PR-136 | p2/pr136-athlete-subscription-webhook | AthleteSubscription webhook handler (MP payment sync, 10 tests) | ✅ 2026-03-22 |
| PR-137 | p2/pr137-billing-ui | Billing UI dashboard (Finanzas page + Athletes badges + sidebar gate) | ✅ 2026-03-22 |
| PR-138 | p2/pr138-athlete-invite-flow | Public invite page + accept endpoint + MP redirect | 🔄 OPEN 2026-03-23 |
| PR-139 | p2/pr139-athlete-dashboard | Athlete dashboard: home personalizado + clima + navegación separada por rol | 🔄 OPEN 2026-03-23 |
| PR-141 | pr-141-athlete-device-roster-notifications | Athlete device status in roster + smart notification flow | 🔄 OPEN 2026-03-23 |

| PR-128a | pr-128a-pmc-backend-trimp-ctl-atl-tsb | PMC backend: TRIMP cascade + CTL/ATL/TSB engine + 4 API endpoints | 🔄 OPEN 2026-03-23 |
| PR-145a | pr-145a-workout-creator-pro | Workout Creator Pro: zone selector Z1-Z5, pace API, intensity bar | 🔄 OPEN 2026-03-24 |

## Next PR Queue

### PR-128b — PMC Frontend chart (AthleteProgress page reads DailyLoad)
- Reads /api/athlete/pmc/ + /api/coach/athletes/<m_id>/pmc/
- Risk: Low

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
- `AthleteInvitation` — token-based invite (PR-135), 30-day expiry, owner/admin only

### Integrations built
- `integrations/mercadopago/client.py` — mp_get/post/put
- `integrations/mercadopago/subscriptions.py` — create/get/cancel + create_coach_athlete_preapproval (PR-135)
- `integrations/mercadopago/webhook.py` — process_subscription_webhook (idempotent, B2B)
- `integrations/mercadopago/athlete_webhook.py` — process_athlete_subscription_webhook (idempotent, coach→athlete, PR-136)
- `integrations/mercadopago/oauth.py` — mp_get_authorization_url + mp_exchange_code

### What's missing to complete billing loop
1. ~~Coach MP OAuth (PR-134)~~ ✅ DONE
2. ~~Athlete invite + preapproval (PR-135)~~ ✅ DONE
3. ~~AthleteSubscription webhook handler (PR-136)~~ ✅ DONE

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

### Frontend billing surfaces (PR-137)
- `Finanzas.jsx` — owner/admin-only: KPIs, plans management, subscription table + manual activation, invitations + copy-link
- `Athletes.jsx` — subscription status badge + filter tabs (no amounts for coaches)
- `Layout.jsx` — Finanzas locked for coach/member role (tooltip: "Solo para administradores")
- `billing.js` — 7 API service functions aligned to backend endpoints

### Frontend invite flow (PR-138)
- `InvitePage.jsx` — public route `/invite/:token`; states: loading, invalid, expired, already_used, pending
- `App.jsx` — public route `/invite/:token` (no ProtectedRoute)
- `billing.js` — added `getInvitation(token)` + `acceptInvitation(token)`

### PR-138 backend changes
- `InvitationDetailView`: no PII in public response; 200 for all states (expired/accepted/pending)
- `InvitationAcceptView`: IsAuthenticated; creates Membership (get_or_create, role=athlete) before MP redirect

### Frontend athlete surfaces (PR-139)
- `AthleteLayout.jsx` — separate sidebar for athlete role (Hoy, Mi Entrenamiento, Mi Progreso, Conexiones, Perfil)
- `AthleteDashboard.jsx` — personalized home: greeting + weather, today's workout card, onboarding checklist, subscription card
- `AthleteMyTraining.jsx` + `AthleteProgress.jsx` — premium placeholders
- `useWeather.js` — geolocation + OpenWeatherMap hook (silent fallback)
- `Layout.jsx` — delegates to AthleteLayout for role=athlete
- `App.jsx` — DashboardRouter + /athlete/training + /athlete/progress routes

### PR-139 backend changes
- `GET /api/athlete/today/` — IsAuthenticated + role=athlete guard via Membership; queries WorkoutAssignment (planned/moved, today's date); structured log athlete_today_fetched
- `core/views_athlete.py` — new file for athlete-only views
- `core/tests_pr139_athlete_today.py` — 11 tests: 401, 403 (coach/owner/no-membership), no-workout, canceled/skipped ignored, correct fields, cross-org isolation

## PMC Engine Architecture (PR-128a)
- `CompletedActivity`: +7 normalized biometric fields (avg_hr, max_hr, avg_power_w, avg_pace_s_km, tss_override, canonical_load, canonical_method)
- `AthleteHRProfile`: hr_max/hr_rest/threshold_pace_s_km per (org, user) — unique_together
- `ActivityLoad`: OneToOne with CompletedActivity, stores TSS + method
- `DailyLoad`: CTL/ATL/TSB/ARS per (org, user, date) — unique_together
- `core/services_pmc.py`: TRIMP cascade engine (override → TRIMP → rTSS → duration)
- Celery tasks: compute_pmc_for_activity (post-create), compute_pmc_full_for_athlete (HR profile update)
- Endpoints: /api/athlete/pmc/, /api/athlete/hr-profile/, /api/coach/athletes/<m_id>/pmc/, /api/coach/team-readiness/

## Test Baseline
~1329 + 6 = ~1335 tests | CI: backend ✅ frontend ✅

### PR-145a — Workout Creator Pro (2026-03-24)
- `GET /api/athlete/pace-zones/`: any active Membership (athlete OR coach), AthleteHRProfile.threshold_pace_s_km, fallback 300 s/km
- Zone Z1-Z5 → metric_type='hr_zone' + target_label='Z1'...'Z5' in WorkoutInterval
- WorkoutBuilder redesigned: zone selector, pace badge, estimated time badge, intensity bar, repeated blocks, step reordering
- Saving API unchanged (createWorkoutBlock + createWorkoutInterval)
