# Project Roadmap State — CTO Memory
_Last updated: 2026-04-03 · PR-160 Fixes funcionales + Calendar Pro + Diferenciación roles + Goal badge_

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

### PR-151 — Dashboard Nivel 1 ✅ 2026-04-02
- Team semaphore (5 cards: Overreaching/Fatigued/Productive/Optimal/Fresh) from /api/coach/team-readiness/
- ACWR per athlete (ATL/CTL): injury risk zones, attention table filtered to athletes needing action (ACWR>1.5, ACWR<0.8, overreaching/fatigued)
- PMC representativo: highest-CTL athlete chart rendered via getCoachAthletePMC(), switches with period selector
- Fitness Promedio (real avg CTL) and Riesgo Lesión (real ACWR>1.5 count) KPI cards
- Athletes.jsx: fake CTL formula replaced with real CTL from fitnessMap; tsb_zone colored dot + ACWR tooltip per athlete
- Compliance section: empty state placeholder (PR-152 will wire it)
- Risk: LOW (frontend only, no backend changes)

### PR-152 — Vista atleta enriquecida + Morning Readiness Score ✅ 2026-04-02
- One-Page Athlete View: CoachAthletePMC.jsx refactored with 7 KPI cards (Readiness, CTL, ATL, TSB, ACWR, Compliance, Bienestar)
- All 7 KPI cards have MUI Tooltip on hover with scientific explanation
- Readiness Score (0-100) computed in backend: 50% TSB + 50% latest WellnessCheckIn average; added to PMC endpoints
- 3 new backend endpoints: /api/coach/athletes/<m_id>/training-volume/, /wellness/, /compliance/
- 9-option metric filter dropdown: PMC, Compliance, Bienestar, Volumen Trail/Running, Volumen Horas, Volumen Ciclismo, Esfuerzo, Fuerza, Tiempo en Zonas (placeholder)
- Semanal/Mensual precision selector for volume/compliance metrics
- New components: WellnessHeatmap.jsx (5-row colored grid), VolumeBarChart + ComplianceBarChart (Recharts)
- ARSCard.jsx: MUI Tooltip added to all 4 cards
- AthleteProgress.jsx ARSCard bug fixed: pmcData.ars → pmcData.current.ars (same for ctl/atl/tsb)
- Backend tenancy: all 3 new endpoints use _resolve_athlete_membership (fail-closed, same pattern as CoachAthletePMCView)
- Risk: MEDIUM — RESOLVED

### PR-153 — GAP + Ramp Rate + CTL Projection + Volume Enhancements ✅ 2026-04-02
- GAP service: core/services_gap.py — simplified Minetti model (each 1% grade ≈ +10% metabolic cost)
- Ramp Rate (7d + 28d) computed from DailyLoad; added to PMC endpoint current object
- CTL Projection: 14 days forward using current 7d ramp rate; appended as projection[] to PMC response
- PMCChart.jsx: dashed light-blue projection line (ctlProjected field), vertical "today" marker, ramp rate text in legend with color coding (green/amber/red/blue)
- TrainingVolumeView: enhanced aggregation — elevation_gain_m per bucket for all sports; avg_gap_s_km + avg_gap_formatted for run/trail sport
- VolumeBarChart.jsx: GAP summary KPI + D+ total above chart; D+ and GAP in per-bucket tooltip
- CoachAnalytics.jsx: 2 new columns — GAP (avg last 7d run/trail, formatted) + Ramp Rate (colored badge)
- vol-hours filter renamed → "Volumen (Horas + Calorías)"
- TeamReadinessView: now returns avg_gap_formatted + ramp_rate_7d per athlete
- simulate_pr153_data management command: cycling activities (3x/wk Atleta Test, 2x/wk Carlos Test) + wellness check-ins, idempotent
- 11 backend tests pass (unit GAP + integration PMC ramp/projection + volume elevation/GAP)
- No migrations required (all computed on-the-fly)
- Risk: MEDIUM — RESOLVED

### PR-156 — Mi Progreso del Atleta: Readiness Hero + Goals + Weekly + PMC Humano + Wellness ✅ 2026-04-02
- AthleteProgress.jsx: complete redesign — 5 sections replacing ARSCard + PMC + HR form
- Section 1: Readiness Hero — score/100 + color band (green/amber/orange/red) + label + recommendation text
- Section 2: Goals Countdown — own goals with days_remaining; urgent (<7d) highlighted in rose; no goals → link to Perfil
- Section 3: Weekly Summary — 7-day circle indicators + sessions compliance + distance + duration + streak fire
- Section 4: PMC Chart (human labels) — Fitness/Fatiga/Forma instead of CTL/ATL/TSB; no ramp rate, no projection; trend text below
- Section 5: Wellness Prompt — if not submitted today: call-to-action; if submitted: 5 metric chips
- HR Profile form REMOVED from Mi Progreso (was coach-level config, not athlete UX)
- Backend A3: `readiness_recommendation` text added to `_compute_readiness()` return tuple; added to both PMC endpoints (athlete + coach)
- Backend A2: `AthleteWeeklySummaryView` — GET /api/athlete/weekly-summary/ — compliance, totals from CompletedActivity, 7-day array, streak
- Backend A1: `AthleteGoalsView` — GET /api/athlete/goals/ — own goals with days_remaining, sorted by date
- Backend: `AthleteWellnessTodayView` — GET /api/athlete/wellness/today/ — today's check-in or {submitted: false}
- PMCChart.jsx: `humanLabels` prop — when true: hides projection legend item, hides ramp rate, shows "Fitness/Fatiga/Forma"
- 6 backend tests in core/tests_pr156_athlete_progress.py — all pass
- No migrations required
- Risk: LOW — RESOLVED

### PR-155 — Limpieza del Edificio: Consolidar Sidebar + Eliminar Duplicación ✅ 2026-04-02
- Dashboard.jsx: removed "Alumnos Activos" + "Ingresos (Total)" KPI cards + PaymentsWidget; removed empty Compliance Semanal + AlertsWidget; now has ONLY 2 KPI cards + Semaphore + Attention Table + PMC Chart
- CoachDashboard.jsx: removed PmcSection entirely (PMC, KpiCards, recharts dependency); page is now org info + briefing + roster
- App.jsx: /athletes/:id route now redirects to /coach/athletes/:id/pmc via AthleteDetailRedirect
- Athletes.jsx: row click + NavigateNext button now navigate to /coach/athletes/:membership_id/pmc
- Layout.jsx: sidebar reordered into 3 labeled sections — DIARIO (Inicio/Calendario/Alumnos/Analytics), HERRAMIENTAS (Librería/Plantilla/Grupos), CONFIGURACIÓN (Finanzas/Conexiones/Mi Organización)
- public_report.html: projection simplified from 14-card grid to 1 line of text with projection_2w_ctl
- views_reports.py: projection_2w_ctl computed from last item in projection list, injected into snapshot before render
- FRONTEND_URL already existed in settings.py (confirmed); "Abrir Quantoryn" button already fixed in PR-154 hotfix
- Risk: LOW (frontend only, no backend models, no migrations)

### PR-159 — Sidebar Colapsable + Athlete Card (5 Tabs) + GroupPlanning Navigation ✅ 2026-04-03
- Sidebar colapsable coach (Layout.jsx) y atleta (AthleteLayout.jsx): 260px expandido → 60px colapsado; íconos con tooltip MUI; toggle button con ChevronLeft/Right; preferencia persistida en localStorage
- GroupPlanningView.jsx: flechas semana ← W14/W16 → (onNavigateWeek prop); back button ahora vuelve a Planificador (setCalendarView('macro'))
- MacroView.jsx: eliminado botón redundante "Planificar Wxx"
- CoachAthletePMC.jsx: refactorizado a 5 tabs (MUI Tabs): Rendimiento (existente), Perfil, Lesiones, Objetivos, Wellness
- AthleteProfileTab.jsx: coach lee y edita datos físicos (peso, altura, FC, VO2max, años entreno) via PATCH /api/coach/athletes/<m_id>/profile/
- AthleteInjuriesTab.jsx: lista lesiones + formulario agregar lesión via GET/POST /api/coach/athletes/<m_id>/card-injuries/
- AthleteGoalsTab.jsx: tarjetas de objetivos con días restantes, prioridad, distancia, D+
- AthleteWellnessTab.jsx: WellnessHeatmap reutilizado (60 días) + KPI bienestar promedio
- CoachNotes: textarea con auto-save (3s debounce) en todos los tabs via GET/PUT /api/coach/athletes/<m_id>/notes/
- Backend: core/views_athlete_card.py — 4 nuevas vistas (Profile, Injuries, Goals, Notes); usa _resolve_athlete_membership fail-closed
- core/tests_pr159_athlete_card.py — 8 tests, todos pasan
- frontend lint: 0 errores; build: success
- No migrations (usa Athlete.notes existente para coach_notes)
- Risk: MEDIUM — RESOLVED

### PR-158 — Planificador Pro: Historial Visual + Copiar Semana + Carga Estimada + Plan vs Real ✅ 2026-04-03
- Backend: `core/views_planning.py` — 5 new views (WorkoutHistoryView, GroupWorkoutHistoryView, CopyWeekView, EstimatedWeeklyLoadView, AthletePlanVsRealView)
- Workout history: day-by-day 6-week grid with repetition detection for individual athlete and group
- Copy week: idempotent (get_or_create) — copies WorkoutAssignments from source to target week, team-filtered
- Estimated weekly load: planned TSS + phase recommendation (descarga 50-70%, carga 80-100%, etc.) + vs previous week
- Plan vs Real: per-session compliance (distance or duration based), weekly summary
- 5 new API endpoints registered in core/urls.py
- Frontend: `HistorialPanel.jsx` — collapsible 6-week grid in Calendar week view with [📋] copy button per row
- Frontend: `WeeklyLoadEstimate.jsx` — real-time TSS estimation panel (green/amber/red) in Calendar week view
- Frontend: `planning.js` — 5 new API client functions
- MacroView.jsx: `onNavigateToWeek` prop — clicking week header navigates Calendar to that week in week view
- Calendar.jsx: `calViewMode` state for 'month'/'week' control; HistorialPanel + WeeklyLoadEstimate in week view
- AthleteMyTraining.jsx: PlanVsRealBar per week (progress bar + sessions/km/min) + compliance % badge on completed workout cards
- 9 tests in `core/tests_pr158_planificador_pro.py` — all pass
- frontend lint passes, build succeeds
- No migrations required
- Risk: MEDIUM — RESOLVED

### PR-157 — Auto-Periodización + Badge Calendario + Timeline Atleta + Historial Planificador ✅ 2026-04-02
- Backend: `core/services_periodization.py` — `auto_periodize_athlete()` + `suggest_cycle_pattern()`; idempotent (update_or_create); respects lesion phases
- Cycle patterns: 1:1 / 2:1 / 3:1 / 4:1 (distance-based suggestion)
- 5 new endpoints: POST auto-periodize athlete, POST auto-periodize group, GET recent-workouts, GET athlete/training-phases/, GET p1/orgs/<id>/athletes/<id>/training-phases/
- 10 tests in `core/tests_pr157_periodization.py`
- Frontend: Auto-periodizar grupo button + CICLO column in MacroView.jsx
- 6-week workout history panel in BulkAssignModal with consecutive-repetition warnings
- Periodization timeline in AthleteProgress.jsx (Section 3 between Goals and Weekly)
- Training phase colored badge (4px strip) in Calendar.jsx month view per week
- `frontend/src/api/periodization.js` — 5 API client functions
- No migrations required (TrainingWeek model already exists since PR-155)
- Risk: MEDIUM — RESOLVED

### PR-154 — Reporte Automático Compartible (WhatsApp + Email) ✅ 2026-04-02
- AthleteReport model: token (UUID hex, 64 chars), org FK, athlete/coach user FK, membership FK, snapshot JSON, expires_at (7 days TTL), view_count tracking
- Migration: 0106_pr154_athletereport.py
- POST /api/coach/athletes/<m_id>/report/ — creates report with stable snapshot (KPIs, volume by sport, compliance, wellness, GAP, projection)
- POST /api/coach/athletes/<m_id>/report/<token>/email/ — sends email with report link (no PDF dependency)
- GET /report/<token>/ — public page (no auth), Django template, Open Graph meta tags for WhatsApp preview
- Inline SVG PMC chart rendered from snapshot JSON (no matplotlib needed)
- Expired/invalid token → 404 with branded "Reporte expirado" page
- Frontend: "Compartir Reporte" button in CoachAthletePMC.jsx header
- ShareReportModal.jsx: period selector + coach message textarea + preview KPI cards + WhatsApp/Email/Copy Link actions
- frontend/src/api/reports.js: createReport + sendReportEmail
- 8 backend tests in core/tests_pr154_reports.py
- Risk: MEDIUM — RESOLVED

### Mes 1 Gate (onboarding 100 athletes)
- PR-152 — PWA + Push Notifications (service worker, manifest, installability)
- PR-153 — Pre-Expiry Notification (3 days before MP renewal, uses InternalMessage)

### PR-160 — Fixes funcionales + Calendar Pro + Diferenciación roles + Goal badge ✅ 2026-04-03
- Goal trophy badge: replaced red #dc2626 ribbon with gold gradient (#FFD700→#F97316) 🏆 in AthleteMyTraining and Calendar.jsx
- Goal badge shows distance + elevation subline; Calendar goal event title includes metrics
- AthleteGoalsTab.jsx: coach can now inline-edit (title, date, priority, status, distance, elevation) + delete goals via PATCH /api/p1/orgs/<org_id>/goals/<pk>/
- AthleteProfileCards.jsx: athlete can inline-edit + delete goals in Perfil page (onUpdateGoal prop)
- AthleteProfile.jsx: handleUpdateGoal wired; updateGoal imported from athlete.js API
- athlete.js API: updateGoal(orgId, goalId, data) added (PATCH)
- AthleteProfileTab.jsx: Datos Físicos edit form now includes weekly_available_hours, preferred_training_time, pace_1000m_seconds (was missing)
- AthleteWellnessTab.jsx: auto-generated interpretation text below heatmap (7-day averages → actionable coach alerts: pain, sleep, energy, stress, overtraining risk, all-good)
- Risk: LOW (frontend only, no backend changes, no migrations)

### Before Mes 2 (10 external coaches)
- PR-155 ✅ — Building cleanup (sidebar consolidation, duplicate removal) — DONE
- PR-156 ✅ — Mi Progreso del Atleta redesign (Readiness + Goals + Weekly + PMC humano + Wellness) — DONE
- PR-157 ✅ — Auto-Periodización + Badge Calendario + Timeline Atleta + Historial Planificador — DONE (2026-04-02)
- PR-160 ✅ — Fixes funcionales + Calendar Pro + Diferenciación roles + Goal badge — DONE (2026-04-03)

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
