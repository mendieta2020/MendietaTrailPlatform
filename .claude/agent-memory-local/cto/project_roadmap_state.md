# Project Roadmap State — CTO Memory
_Last updated: 2026-04-01 · Full audit completed — security sweep queued as PR-149_

## Phase
P2 — Historical Data, Analytics & Billing (IN PROGRESS)

## Launch Plan (confirmed 2026-03-28)
- **Mes 1 (Apr 2026)**: Fernando's own trail running team (100 athletes, real daily use)
- **Mes 2 (May 2026)**: Invite 10 external coaches
- **Mes 3 (Jun 2026)**: General market launch

## Target team profile (confirmed 2026-03-28)
- 100 trail running athletes
- ~70% Garmin, ~90% Strava connected
- Many do double/triple sessions per day
- Athletes do NOT have accounts yet — onboarding is the bottleneck
- Plans: Classic $38K ARS (up to 21K), Short $48K ARS (up to 42K), Ultra $60K ARS (60K+) — monthly
- MercadoPago handles automatic recurring charges

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
| PR-138 | p2/pr138-athlete-invite-flow | Public invite page + accept endpoint + MP redirect | ✅ |
| PR-139 | p2/pr139-athlete-dashboard | Athlete dashboard: home personalizado + clima + navegación separada por rol | ✅ |
| PR-141 | pr-141-athlete-device-roster-notifications | Athlete device status in roster + smart notification flow | ✅ |
| PR-128a | pr-128a-pmc-backend-trimp-ctl-atl-tsb | PMC backend: TRIMP cascade + CTL/ATL/TSB engine + 4 API endpoints | ✅ |
| PR-145a | pr-145a-workout-creator-pro | Workout Creator Pro: zone selector Z1-Z5, pace API, intensity bar | ✅ 2026-03-24 |
| PR-145b | pr-145b-library-upgrade | Library UX upgrade: search/filter/sort, empty state, WorkoutProfileChart, difficulty+D+, 4 builder modes, BlockType migration | ✅ 2026-03-25 |
| PR-145f | pr-145f-coach-calendar-crud | Coach Calendar CRUD: drag-to-move, delete, clone workout, copy week, delete week, context menu, undo toast | ✅ 2026-03-26 |
| PR-145g | main (810c395) | Coach event drawer (WorkoutCoachDrawer 480px) + coach_comment retention loop + athlete selector memory | ✅ 2026-03-27 |
| PR-145h | — | Plantilla semanal (compliance semanal, dots por día, badge praise, overload alert base) | ✅ 2026-03-27 |
| PR-147 | pr-147-smart-alerts | Smart Alerts Engine: InternalMessage, bell notification, MessagesDrawer, coach comment auto-message | ✅ 2026-03-28 |
| PR-148 | pr-148-real-compliance | Real compliance (actual/planned), bulk query, sessions_per_day, streak, weekly pulse, coach briefing, AlertModal WhatsApp | ✅ 2026-03-28 |
| PR-149 (old) | — | Athlete Registration + Onboarding + Google OAuth + Plan Selector | ✅ 2026-03-29 |
| PR-150 (old) | — | MP Connect UI + Universal Invite Link + BillingOrgMixin | ✅ 2026-03-30 |
| PR-151 (old) | — | Welcome Flow + Plan CRUD + Org Fix + Strava Alert | ✅ 2026-03-30 |
| PR-152 (old) | — | Trial 7 dias + Multiple Goals + Registration Alert | ✅ 2026-03-30 |
| PR-153 (old) | — | Athlete Profile + Injuries + Menstrual Cycle + MP Checkout | ✅ 2026-03-31 |
| PR-154 | pr-154-body-map-wellness-calendar | Body Map SVG + Calendar Blocked Days + Wellness Check-in + Menstrual Cycle Calendar | ✅ 2026-03-31 |
| PR-155 | pr-155-macro-view-wellness-coach | Vista Macro (TrainingWeek model + coach table + phases), Wellness Card 7 (recharts), Menstrual cycle overlay in AthleteMyTraining | ✅ 2026-04-01 |

## Audit 2026-04-01 — Findings

### CRITICAL
- **Disk C full** — blocks CI, must be cleaned before any PR can run

### HIGH — Security / Tenancy
- 5 legacy ViewSets without org filter: Equipo, Alumno, Plantilla, Carrera, AlumnoViewSet
- BillingOrgMixin.get_org() uses .first() — non-deterministic for multi-org coaches
- views_pmc._get_athlete_membership() uses .first() without org scope
- ALLOWED_HOSTS=['*'] when DEBUG=True

### MEDIUM
- Sentry scrubber partial (not all sensitive fields covered)
- Strava webhook subscription ID silent discard (no error raised)
- Ingestion ambiguity: unclear if all paths write to CompletedActivity vs legacy Actividad

### Frontend State (16/18 COMPLETE, 2 PARTIAL)
- Dashboard.jsx: PMC section empty (endpoint exists but not connected)
- Athletes.jsx: fitness column shows fake/hardcoded CTL value

### Schema State
- **54 models total**, **105 migrations applied**
- Latest migration: 0105_pr155_trainingweek.py
- New models since last audit: WellnessCheckIn (PR-154, migration 0102), TrainingWeek (PR-155, migration 0105 — no API endpoint yet)

## Prioritized PR Queue (post-audit, renumbered)

### PR-149 — Security Sweep ✅ 2026-04-01
- Fixed BillingOrgMixin.get_org() — deterministic multi-org resolution; requires org_id when ambiguous
- Fixed _get_athlete_membership() and _get_coach_membership() — same disambiguation
- Legacy ViewSets (Equipo, Alumno): models predate Organization FK; documented coach-user isolation; added cross-coach isolation tests
- 12 new protective tests (billing + PMC + legacy ViewSet cross-coach isolation)
- Housekeeping: deleted loose dev scripts (asignar_alumnos.py, simular_strava.py, etc.) and celerybeat artifacts
- Risk: HIGH (tenancy, Constitution Law 1) — RESOLVED

### PR-150 — Close Strava Ingestion Loop ✅ 2026-04-01
- Added dual-write in `_process_strava_event_body()` (core/tasks.py): after upsert_actividad(), calls `ingest_strava_activity()` in a try/except — failure never breaks the Actividad pipeline
- Changed `get_or_create` → `update_or_create` in `ingest_strava_activity()` so webhook updates refresh CompletedActivity fields
- PMC double-dispatch (recompute_pmc + compute_pmc_for_activity) both idempotent — documented with comment
- 11 new tests in `core/tests_pr150_dual_write.py`; all pass
- CLAUDE.md synced with current PR queue + PASO 0 protocol
- Risk: HIGH (data integrity, idempotency) — RESOLVED

### PR-151 — Dashboard Real
- Connect Dashboard.jsx to existing PMC endpoint (CTL/ATL/TSB chart)
- Replace fake fitness column in Athletes.jsx with real CTL from DailyLoad
- Risk: LOW (frontend only, endpoints already exist)

### Mes 1 Gate (onboarding 100 athletes)
- PR-152 — PWA + Push Notifications (service worker, manifest, installability)
- PR-153 — Pre-Expiry Notification (3 days before MP renewal, uses InternalMessage)

### Before Mes 2 (10 external coaches)
- PR-154 (new) — Staff/Coach/Nutritionist Invitation Flow
- PR-155 (new) — Periodizacion Visual (Macro/Meso/Micro en una pantalla)
- PR-156 — PMC Frontend chart (AthleteProgress reads DailyLoad)

### Before Mes 3 (general market launch)
- PR-157 — Videos en ejercicios de fuerza
- PR-158 — Historical backfill pipeline
- PR-159 — Calendar "+2 more" fix + expand day view

## Technical Debt
- FINDING-X4-A: ExternalIdentityViewSet legacy scope (low priority)
- Migration 0083 uses atomic=False (standard pattern for PostgreSQL FK+DDL)
- PR-132 was merged directly to main (no feature branch) — process gap corrected
- PR-134: OrgOAuthCredential uses fresh org instance in tests to avoid cached reverse OneToOne from post_save signal
- CLAUDE.md PR queue is stale — update after PR-149 security sweep
- ALLOWED_HOSTS=['*'] when DEBUG=True — acceptable for local dev but must never reach production
- TrainingWeek model (PR-155) has no API endpoint yet — needs exposure before Periodizacion Visual

## Key Technical Decisions
- atomic=False: standard for any migration combining DDL + DML on FK tables
- Lazy imports: Law 4 compliance for integrations/ imports in core/
- PASO 0 mandatory: all future prompts must start with branch creation
- transaction=True on IntegrityError tests: PostgreSQL aborts tx on violations
- Google OAuth: configured via Google Cloud Console for Quantoryn project
- Onboarding pattern: multi-step wizard with backend serializers per step

## Billing Architecture Summary

```
Quantoryn B2B: Coach pays Quantoryn (OrganizationSubscription)
Coach B2C:     Athlete pays Coach via MercadoPago (AthleteSubscription)
```

### Models built
- `OrganizationSubscription` — plan tier, trial, is_active
- `SubscriptionPlan` — configurable pricing (admin), mp_plan_id
- `CoachPricingPlan` — coach's pricing for athletes, price_ars
- `AthleteSubscription` — athlete->coach plan, status lifecycle
- `OrgOAuthCredential` — org-scoped OAuth credential (coach MP account)
- `AthleteInvitation` — token-based invite (PR-135), 30-day expiry, owner/admin only

### Integrations built
- `integrations/mercadopago/client.py` — mp_get/post/put
- `integrations/mercadopago/subscriptions.py` — create/get/cancel + create_coach_athlete_preapproval
- `integrations/mercadopago/webhook.py` — process_subscription_webhook (idempotent, B2B)
- `integrations/mercadopago/athlete_webhook.py` — process_athlete_subscription_webhook (idempotent, coach->athlete)
- `integrations/mercadopago/oauth.py` — mp_get_authorization_url + mp_exchange_code

## PMC Engine Architecture (PR-128a)
- `CompletedActivity`: +7 normalized biometric fields (avg_hr, max_hr, avg_power_w, avg_pace_s_km, tss_override, canonical_load, canonical_method)
- `AthleteHRProfile`: hr_max/hr_rest/threshold_pace_s_km per (org, user) — unique_together
- `ActivityLoad`: OneToOne with CompletedActivity, stores TSS + method
- `DailyLoad`: CTL/ATL/TSB/ARS per (org, user, date) — unique_together
- `core/services_pmc.py`: TRIMP cascade engine (override -> TRIMP -> rTSS -> duration)
- Celery tasks: compute_pmc_for_activity (post-create), compute_pmc_full_for_athlete (HR profile update)
- Endpoints: /api/athlete/pmc/, /api/athlete/hr-profile/, /api/coach/athletes/<m_id>/pmc/, /api/coach/team-readiness/

## Smart Alerts Architecture (PR-147)
- `InternalMessage` model: sender, recipient, organization, alert_type (6 types), body, is_read, created_at
- Alert types: general, overload, inactive, praise, coach_comment, system
- MessagesDrawer component: athlete and coach variants
- Bell notification in both AthleteLayout and Layout (coach)
- Auto-message on coach_comment save

## Real Compliance Architecture (PR-148)
- compliance_pct uses actual/planned ratio (distance or duration), not binary
- sessions_per_day: dot shows count when >1 session in a day
- streak: consecutive days with completed sessions
- weekly_pulse: weekly compliance trend
- coach briefing card: top-level team summary
- AlertModal with WhatsApp deep link

## PR-154 Architecture Summary (2026-03-31)
- **BodyMap.jsx**: Interactive SVG human figure, 20 zones, colored by severity
- **Calendar Blocked Days**: AthleteAvailability overlay, drag confirmation dialog
- **Menstrual Cycle Calendar**: cycle phase per day, colored border-top with Tooltip
- **WellnessCheckIn**: 5 Hooper-Index dimensions, UniqueConstraint(athlete+date), upsert, permanent dismiss
- New models: WellnessCheckIn (migration 0102), AthleteProfile.wellness_checkin_dismissed

## Test Baseline
~1349+ tests | CI: backend ✅ frontend ✅ (pending disk space fix)
