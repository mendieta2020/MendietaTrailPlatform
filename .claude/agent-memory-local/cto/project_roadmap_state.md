# Project Roadmap State — CTO Memory
_Last updated: 2026-04-23 · PR-185 READY FOR REVIEW (cleanup bundle: soft-delete, rescue backfill, ordering, DEBUG). PR-184 READY FOR REVIEW. PR-183 READY FOR REVIEW (Sentry). PR-182/181 READY FOR REVIEW. PR-180 merged. Next queue: merge queue in PR order → PR-186 (Bug #51 sport mapping investigation)._

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

### PR-163 — Calendar Pro: Custom month grid + shared components ✅ 2026-04-04
- Custom CalendarGrid replacing react-big-calendar month view (week view unchanged)
- Shared WorkoutCard, GoalCard, WeekHeader, CalendarGrid components in components/calendar/
- Shared utilities in utils/calendarHelpers.js (sportColor, compliance, buildCalendarWeeks)
- AthleteSearchSelector: MUI Autocomplete with recents (athletes only, no groups)
- CoachWeekOverview: weekly compliance table when no athlete selected (/api/coach/team-readiness/)
- Compliance: 6 ranges (0%/1-30%/31-70%/71-110%/111-150%/>150% purple Exceso), no 150 cap
- Training phase badge (Carga/Descarga/etc) per week row in grid
- GoalCard: gold gradient, days-remaining, priority badge
- TODAY: orange left border; past unfinished: red tint background
- Coach comment 💬 icon on cards with coach_comment field
- Fix: handleEventDrop guards against drag-moving goal events (PR-163 step 5)
- Internal card-to-card drag (handleGridCardMove) + library drag (handleLibraryDropOnDate)
- AthleteMyTraining: inline grid replaced with CalendarGrid (role=athlete); removes ~250 LOC duplication
- No backend changes, no migrations required
- Frontend: lint 0 errors, build success
- Risk: MEDIUM (major frontend refactor) — RESOLVED

### PR-165c — Pre-Launch Hotfix: Coach/Staff Profiles + UX Polish ✅ 2026-04-06
- Auto-create Coach record when user joins via TeamJoinView with role='coach' (fixes empty COACHES tab)
- MyCoachProfileView: GET/PATCH /api/me/coach-profile/ — coach self-edit (bio, specialties, certifications, years_exp)
- CoachProfile.jsx: new page at /coach/profile (linked from sidebar)
- StaffProfile.jsx: new page at /staff/profile (linked from sidebar)
- Layout.jsx: 'Mi Perfil' item added to coach CONFIGURACIÓN section and staff GESTIÓN section (desktop + mobile)
- Avatar fix: top-right avatar now shows actual user initials (was hardcoded 'C')
- Dashboard.jsx: org name chip + role badge shown above "Panel de Control" heading
- CoachInfoCard: shows placeholder "Tu coach será asignado pronto" when no coach assigned
- AthleteDashboard: removed duplicate device-connection onboarding banner; DeviceBanner unified to teal (#00D4AA)
- Finanzas EditPlanModal: toggle switch for is_active/Activo state added
- RosterSection: Staff tab added (owner-only) — shows team members filtered by role='staff'
- OnboardingForm: province/city/postal/profession/clothing_size/blood_type promoted to required section; optional accordion renamed to "Datos deportivos avanzados"
- 6 backend tests (tests_pr165c_hotfix.py) — all pass
- frontend lint: 0 errors; build: success
- No migrations required
- Risk: MEDIUM — RESOLVED

### PR-162 — Production Ready: Security + Saves rotos + Onboarding polish ✅ 2026-04-03
- Fix 0 (CRITICAL SECURITY): DashboardRouter now uses activeOrg.role from OrgContext (not memberships[0].role) → athletes always see AthleteDashboard
- CoachRoute guard added in App.jsx: athletes redirected to /dashboard if they try to access /calendar, /athletes, /teams, /library, /plantilla, /coach/*, /coach-dashboard, /finance
- Fix 1: AthleteProfile.jsx handleSaveCard — null → '' bug fixed for numeric fields (weight_kg, height_cm, etc.) → PATCH no longer returns 400
- Fix 2: AthleteProfileTab.jsx startEditAvail — day_of_week was i+1 (1-7, invalid for model) → now i (0-6) → availability save no longer returns 400
- Fix 4 (empty states): AthleteMyTraining → empty state when no assignments (with Strava CTA); AthleteProgress → empty PMC chart state (with Strava CTA)
- Fix 7 (coach calendar cards): CoachEventComponent shows ✅ indicator when workout is completed
- Risk: CRITICAL security + LOW UX fixes

### PR-161 — Body Map Pro + Fixes funcionales + Sync coach↔atleta + Ubicación→Clima ✅ 2026-04-03
- AthleteInjuriesTab.jsx: react-body-highlighter Model integrated (front/back toggle, dark bg, severity colors yellow/orange/red); clicking a muscle pre-fills the injury form with the mapped zone
- AthleteProfileTab.jsx: Datos Personales section now editable (birth_date, emergency_contact, instagram_handle) via PATCH /api/coach/athletes/<m_id>/profile/; Disponibilidad Semanal now editable (clickable day toggles) via PUT /api/p1/orgs/<org_id>/athletes/<athlete_id>/availability/ using useOrg context for orgId
- Calendar.jsx: GoalEditDialog component added; goal trophy events are now clickable → opens edit dialog (title, date, priority, status, distance, elevation); updateGoal imported from athlete.js
- AthleteMyTraining.jsx: trophy badge clickable → AthleteGoalEditDialog; goalDateMap enriched with goal id + all fields; calendar limited to 4 weeks (weeks.slice(0,4))
- AthleteProfile.jsx: location_city field added in Conexiones & Ubicación section; inline edit saves via updateAthleteRecord (PATCH /api/p1/orgs/<org_id>/athletes/<athlete_id>/); info text "Tu ubicación se usa para mostrar el clima"
- athlete.js: updateAthleteRecord(orgId, athleteId, data) added
- No backend changes, no migrations
- Frontend: lint 0 errors, build success
- Risk: MEDIUM (new dependency react-body-highlighter)

### PR-179a — Unified Plan + Real overlay for calendar timeline ✅ 2026-04-20
- See PR-331 (merged)

### PR-179b — Unified Card + Modal Expandido + Weather + Coach View Parity ✅ 2026-04-20
- Backend: `/calendar-timeline/` enriched with `description`, `intensity_steps`, `weather`,
  `athlete_notes`, `rpe`, `coach_notes`, `estimated_elevation_m`; `coach_comment` omitted
  for athlete-role (role-scoped field); prefetch_related blocks/intervals added to queryset
- services_weather.py: `wind_kmh` + `precipitation_pct` (OWM `pop` field) added to snapshot
- New: `UnifiedCard.jsx` — 7 variants (A pending / B on-plan / C under / D over / E missed /
  F free / G rest); one card per assignment replacing WorkoutCard + ActivityPill
- New: `WorkoutModal.jsx` — 3 cases; intensity steps list; MiniWorkoutProfile graph;
  compliance bar; athlete sentiment; coach-only comment section; no Strava link/watch button
- useWeatherIcon.js: `weatherBadgeProps()` with 7 threshold rules (freeze/heat/rain/wind)
- CalendarGrid.jsx: wired UnifiedCard + WorkoutModal; planDetailsMap prop
- Calendar.jsx: fix TDZ bug — dateFrom/dateTo moved before useEffect that deps on them;
  coachPlanDetailsMap built from timeline plans
- AthleteMyTraining.jsx: calPlanDetailsMap passed to CalendarGrid
- MessagesDrawer.jsx: athlete_session_note added to notification click-through guard
- 9 backend tests (tests_pr179b_unified_card.py) — all pass; 22/22 total with PR-179a
- frontend lint: 0 errors; build: success (pre-existing chunk warning)
- Deferred to PR-179c: historical comparison (last 3 executions)
- Risk: MEDIUM — RESOLVED

### PR-179b-hotfix — 6 Critical Regressions from Production Validation 🔄 READY FOR REVIEW
- Branch: p2/pr179b-hotfix-6-critical-fixes
- BUG 1: Dual modal on athlete card click — role guard in CalendarGrid.handleCardOpen; drawer deep-link coach-only; athletes use WorkoutModal exclusively. Files: CalendarGrid.jsx, AthleteMyTraining.jsx
- BUG 2: Weather wiring (Case A only) — structured warn when upcoming assignments in ±4d window lack weather_snapshot. Case B (real weather from Strava) DEFERRED — requires CompletedActivity schema extension; provider field extraction in core/ would violate Law 4. Follow-up PR needed. Files: AthleteMyTraining.jsx
- BUG 3: Notification "Ver sección" navigation — extended chip to workout_modified and plan_adjusted alert_types; all 4 types with reference_id navigate to modal. Files: MessagesDrawer.jsx
- BUG 4: Effort-based compliance for cross-family run pairings — TRAILRUNNING added to sport map; _effort_detail() helper with formula: effort = distance_km × (1 + elevation_m / 1000); used only for cross-discipline run pairings. 51/51 reconciliation tests pass. Files: services_reconciliation.py, tests_reconciliation.py
- BUG 5: Zone-based colors in MiniWorkoutProfile — Z1-Z5 palette keyed on target_label; was #CBD5E1 uniform gray. Files: MiniWorkoutProfile.jsx
- BUG 6: Prominent compliance badge — full-width bottom strip with semantic labels (Óptimo/Revisar/Alerta) + color-coded typography. Files: UnifiedCard.jsx
- Validation: python manage.py check ✅ | 51/51 tests ✅ | npm run lint ✅ | npm run build ✅
- Architecture review: all 9 Constitution laws PASS (quantoryn-review subagent)
- Risk: MEDIUM — READY FOR REVIEW

### PR-180 — Strava OAuth Lifecycle: Token Refresh + Reconnect Backfill ✅ 2026-04-21
- Branch: p2/pr180-strava-oauth-lifecycle | Merged: commit c21e42d via PR #334 (merge 9ecb8fe)
- **Bug #34 FIXED**: Auto-refresh expired access_token — `refresh_strava_token` helper in `integrations/strava/oauth.py`; `select_for_update` for concurrent-safe refresh; mirrors OAuthCredential + SocialToken allauth; 60s buffer before expiration; structured log events: `strava.token.refreshed.ok` / `strava_401` / `rate_limited` / `unexpected_error`; new reason_code `strava_token_refresh_failed` distinct from `missing_strava_auth`
- **Bug #36 FIXED**: Reconnect now dispatches `trigger_strava_backfill` — callback resolves org via `_derive_org_from_alumno` (3-level fallback: coach Membership → user Membership → Athlete record); removes `_backfill_athlete is None` hard guard; `backfill_strava_athlete` accepts `athlete_id=None`; ingestion proceeds even when `entrenador_id=None`
- **Bug #33 NOT FIXED** (upstream): `Alumno.entrenador_id` not persisting after coach assignment — this PR adds RESILIENCE via Membership fallback but does not fix the upstream coach persistence logic. **HIGH priority follow-up PR.**
- Skills audit: `/quantoryn-review` — APPROVED WITH CONDITIONS (order_by fix applied; `_derive_org_from_alumno` dedup with `services_strava_ingest._derive_organization` deferred to follow-up); `/simplify` — no critical fixes; SocialAccount-inside-atomic-block optimization deferred (Low-Medium, safe-to-merge)
- 9 protective tests T1-T9 in `core/tests_pr180_strava_oauth_lifecycle.py`; 6/6 PR-175 regression tests updated and passing
- Validation: `manage.py check` ✅ | `pytest pr180` 9/9 ✅ | `pytest pr175` 6/6 ✅ | full suite ✅ | npm lint ✅ | npm build ✅
- Risk: HIGH (OAuth token lifecycle, backfill dispatch) — RESOLVED

### PR-182 — Bug Bundle Post-PR-180 Validation 🔄 READY FOR REVIEW
- Branch: p2/pr182-bug-bundle-post-pr180-validation
- **Bug #40 FIXED**: MP webhook type discrimination — `process_athlete_subscription_webhook` now accepts `webhook_type` from `?type=` query param; `payment` and `subscription_authorized_payment` resolve preapproval_id via new `get_mp_payment` helper (metadata.preapproval_id → POI.transaction_data.subscription_id). `subscription_preapproval` (fast path) and None (backward compat) unchanged.
- **Law 6 pre-existing violation REMOVED**: `[DEBUG PR-167]` `print()` statements in `create_coach_athlete_preapproval` that logged full MP response body to Railway stdout. Removed as part of PR-182 file diff.
- **Bug #41a FIXED**: Strava sport mapping expanded — STRENGTH (WeightTraining/Workout/Crossfit/Yoga/Pilates), SWIM, WALK (Hike/Wheelchair), OTHER (all remaining sports). `decide_activity_creation` relaxed: distance required only for RUN/TRAIL/BIKE/SWIM/WALK; STRENGTH/OTHER gate on duration > 0. SportType Literal extended. Provider-only change (Law 4).
- **_SPORT_TO_DISCIPLINE aliases added**: BIKE, SWIM, WALK → correct discipline slugs for reconciliation matching (PR-182).
- **Bug #27 FIXED**: `find_best_match` tiebreaker — exact-discipline + exact-date wins over multi-candidate ambiguity. Two exact matches still fail-closed. Structured log: `reconciliation.match.tiebreak_exact`.
- **Bug #29 FIXED**: `AthleteMyTraining.jsx` unmount cleanup — `sessionStorage.removeItem` on both keys to prevent stale deep-link state across navigation. (Deep-link open logic was already present from PR-179b.)
- **Bug #30 FIXED**: `WorkoutCoachDrawer.jsx` top metric chips relabeled "Plan" (was unlabeled "Duración"/"Distancia") — disambiguates from real metrics in Plan vs Real table below. `WorkoutModal.jsx` already correctly separates Plan/Real sections; no change needed.
- **Bug #32 FIXED**: `MiniWorkoutProfile.jsx` — detects absence of structured intensity data and renders "Intensidad libre" striped placeholder instead of misleading flat gray bars.
- **17 new protective tests**: 6 MP webhook (T1-T6) + 8 Strava sport mapping (T1-T8) + 3 reconciliation tiebreaker (T1-T3). 54/54 reconciliation suite + full backend suite pass.
- **quantoryn-review**: APPROVED after Law 6 fix applied (print() removal). All laws pass.
- Validation: `manage.py check` ✅ | 17/17 new tests ✅ | 54/54 reconciliation ✅ | full suite ✅ | npm lint ✅ | npm build ✅
- Constitution deviation (~650 LOC) approved by Fernando Mendieta (product owner) 2026-04-22.
- Risk: HIGH (MP webhook critical path + reconciliation engine) — READY FOR REVIEW

### PR-181 — Railway Env Vars Refactor: ADR-003 + Operations Runbook 🔄 READY FOR REVIEW
- Branch: p2/pr181-railway-infra-formalization
- **Scope**: documentation-only PR that formalizes the Railway dynamic-references pattern applied manually on 2026-04-22 after two production incidents (backend 2026-04-21, worker 2026-04-22).
- **Files created**: `docs/decisions/ADR-003-railway-env-vars-references.md`, `docs/infra/railway-runbook.md`.
- **Files modified**: `CLAUDE.md` (new Infrastructure section), `docs/decisions/README.md` (ADR-003 index row).
- **ADR-003**: establishes that all Railway-internal service env vars (Postgres, Redis, Celery broker/backend) MUST use `${{Service.VAR}}` references. External API secrets remain static. Includes re-evaluation triggers and quarterly dry-run requirement.
- **Runbook**: 9 sections covering services map, variable reference table (backend + worker), Postgres rotation procedure, external secrets rotation (7 categories including MP webhook secret pending ticket WCS-36049), audit procedure, 2 troubleshooting guides, new-service onboarding checklist, and an incidents log with the two 2026-04-21/22 incidents documented.
- **Validation**: Fernando manually rotated Postgres password on 2026-04-22 after refactor completed; zero downtime. Documented as the first incidents log entry validating section 3 procedure.
- **No code changes. No migrations. No env var changes in repo.** All env var changes already applied directly in Railway UI.
- Risk: LOW (documentation only) — READY FOR REVIEW

### PR-183 — Sentry LoggingIntegration for structured logs capture ✅ READY FOR REVIEW
- Branch: `p2/pr183-sentry-logging-integration`
- **Motivation**: Observability gap discovered during PR-182 post-validation (2026-04-22) via Claude Code + Sentry MCP. Structured events like `mp.athlete_webhook.not_found`, `strava.token.refreshed.*`, `strava.backfill.dispatched` were invisible in Sentry because the SDK default only captures unhandled exceptions, treating `logger.warning()` calls as breadcrumbs only.
- **Fix**: Add `LoggingIntegration(level=WARNING, event_level=WARNING)` to sentry_sdk.init in both tiers: `backend/wsgi.py` (web) + `backend/celery.py` (async worker).
- **Effect**: Every `logger.warning()` and above is now captured as a Sentry event/issue, making the Sentry MCP integration (Claude Code <-> Sentry) useful for structured log analysis.
- **Risk note**: Potential noise from third-party library warnings (Django core, DRF, allauth) that emit `logger.warning()` calls. Monitor Sentry event volume for 24-48h post-deploy. If the spike is unmanageable, a follow-up PR will restrict scope via a Python `LOGGING` handler in `settings.py` scoped only to `core`, `integrations`, `quantoryn.reconciliation` loggers.
- **Validation**: `python manage.py check` + `pytest -q` full suite (no new tests, regression only) + `npm run lint` + `npm run build`.
- Risk: LOW (infra config, zero business logic changes, no migrations).

### PR-185 — Cleanup Bundle: Soft-Delete + Rescue Backfill + Ordering + DEBUG ✅ MERGED
- Merged 2026-04-22. CI green. Soft-delete, rescue dispatch, DEBUG fix, ordering fix.

### PR-186 — MP preapproval_id stamp + Strava token hardening + disconnect log fix ✅ MERGED
- Branch: p2/pr186-mp-preapproval-stamp
- **Bug #54 FIXED**: AthleteSubscription.mp_preapproval_id stamped on existing records
  (core/views_billing.py + core/views_onboarding.py — get_or_create + post-stamp)
- **Bug #61 FIXED**: client.token_expires set in obtener_cliente_strava()
  (core/services.py — 3 locations)
- **Bug #64 FIXED**: disconnect log now derives org_id from Membership, not entrenador_id
  (core/integration_views.py)
- **Bug #65 FIXED**: stravalib.exc.AccessUnauthorized classified as strava_401
  (integrations/strava/oauth.py)
- **Bug #66 FIXED**: billiard + Celery superuser warnings suppressed
  (backend/settings.py)
- Runbook updated: WCS-36049 resolved, MERCADOPAGO_WEBHOOK_SECRET documented
- Tests: core/tests_pr186_mp_preapproval_stamp.py (T1, T2)

### PR-185 — Cleanup Bundle: Soft-Delete + Rescue Backfill + Ordering + DEBUG 🔄 READY FOR REVIEW
- Branch: `p2/pr185-cleanup-bundle`
- **Bug #44 FIXED**: `AlumnoViewSet` missing `ordering = ['nombre']` (DRF OrderingFilter was silently ignored). `filterwarnings` added for drf-yasg DeprecationWarning. staticfiles sub-item deferred to post-merge CI observation.
- **Bug #46 VALIDATED** (no code change): `test_athlete_organization_cascade_delete` already passes on current main — likely fixed as side-effect of PR-183 or PR-184.
- **Bug #47 FIXED**: `CompletedActivity` soft-delete via new `deleted_at` field. Strava `activity.delete` webhook now sets `deleted_at` (replaces old IGNORED stub). PMC recompute dispatched after deletion. Full queryset audit: 9 read sites patched with `deleted_at__isnull=True` (services_analytics, services_pmc, services_reconciliation, views_athlete, views_p1 ×2, views_pmc ×3, views_reports ×2, views_planning). Integrations (`update_or_create`) intentionally unfiltered — restore-on-reingestion policy (see design notes). Migrations 0116 (deleted_at + indexes).
- **Bug #48 FIXED**: `DEBUG = get_env_variable(..., required=False)` — Railway deploy no longer requires DEBUG in env.
- **Bug #50 FIXED**: OAuth rescue backfill now uses smart window logic: oldest failed `StravaWebhookEvent` for this athlete → fallback 7d → hard cap 90d. Throttled per-athlete via `last_rescue_dispatched_at` (30 min). Structured logs: dispatched / skipped_recent / skipped_org_unresolved. Migration 0117 (last_rescue_dispatched_at). Index on StravaWebhookEvent(owner_id, status).
- **14 protective tests**: 7 rescue dispatch (T1-T7) + 7 strava delete webhook (T1-T7 incl. T6 PMC tripwire + T7 reconciliation tripwire). 14/14 PASS.
- **Design notes**: restore-on-reingestion policy — `update_or_create` in ingest paths preserves `deleted_at`, keeping soft-deleted rows hidden in reads. Re-evaluation needed if Strava "activity restored" webhook is ever implemented.
- Validation: `manage.py check` ✅ | `makemigrations --check` ✅ | 14/14 PR-185 tests ✅ | full suite pending (in progress at time of commit prep)
- Risk: MEDIUM (soft-delete is new data lifecycle path; query audit is broad but each change is a 1-line filter addition) — READY FOR REVIEW

### PR-184 — Strava sport mapping hotfix 🔄 READY FOR REVIEW
- Branch: `p2/pr184-strava-sport-mapping-fix`
- **Motivation**: PR-182 updated `normalizer.py::_normalize_strava_sport_type` but the actual Strava webhook flow uses a SEPARATE mapping in `services_strava_ingest._STRAVA_SPORT_MAP`. Diagnosed by Claude Code + Sentry MCP on 2026-04-23 — Garmin→Strava synced activities (sport_type=WeightTraining) still appeared as OTHER in the calendar.
- **Root cause**: `core/tasks.py:1227` falls back from empty `type` to `tipo_deporte` (already normalized to "STRENGTH" by normalizer.py), then calls `_normalize_sport("STRENGTH")` which returned "OTHER" because "STRENGTH" was not a key in `_STRAVA_SPORT_MAP`.
- **Fix A**: Updated `"WALK": "OTHER"` → `"WALK": "WALK"` and `"SWIM": "SWIMMING"` → `"SWIM": "SWIM"` (align with business codes established in PR-182 normalizer).
- **Fix B**: Added passthrough entries for normalized business codes (STRENGTH, TRAIL, BIKE).
- **Fix C**: Added Garmin→Strava underscore aliases (WEIGHT_TRAINING→STRENGTH, TRAIL_RUN→TRAIL).
- **Fix D**: `mapper.py` prefers modern `sport_type` field over legacy `type` for stravalib Activity objects (Garmin-synced activities often leave `type` empty).
- **Architectural debt (Bug #45)**: unify `_STRAVA_SPORT_MAP` and `normalizer.py::_normalize_strava_sport_type` into a single source of truth — future PR.
- **2 new regression tests**: `test_strava_webhook_weight_training_maps_to_strength_via_ingest_flow` + `test_strava_ingest_accepts_normalized_business_codes_as_passthrough` in `core/tests_pr182_strava_sport_mapping.py`. 10/10 pass.
- Validation: `manage.py check` ✅ | 10/10 new tests ✅ | full suite ✅ | npm lint ✅ | npm build ✅
- Risk: LOW (dict entries + field preference, no tenancy/OAuth/model changes).

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
- **Queryset audit discipline (PR-185 lesson)**: Any future soft-delete field introduction requires a full `git grep CompletedActivity.objects` (and equivalent for the affected model) across ALL read paths — not just the write-path patch. PR-185 found 9 read sites needing `deleted_at__isnull=True` across views_pmc (×3), views_reports (×2), views_planning, services_analytics, services_pmc, services_reconciliation, views_athlete, views_p1 (×2). Two regression tripwire tests (T6/T7) added to `tests_pr185_strava_delete_webhook.py` to catch future regressions. Document in Constitution as mandatory step.
- **Bug #45**: Unify `_STRAVA_SPORT_MAP` and `normalizer.py::_normalize_strava_sport_type` into a single source of truth — future PR.
- **Bug #45**: Unify `_STRAVA_SPORT_MAP` and `normalizer.py::_normalize_strava_sport_type` into a single source of truth — future PR.
- **Next queue (confirmed order)**: PR-181 (weather enrichment Bug #63: populate weather_snapshot in /calendar-timeline/) → PR-182 (Bug bundle frontend: #29 notifications nav, #30 modal math, #32 intensity graph) → PR-179c (design system) → PR-187 (Bug #33 root cause: Alumno.entrenador_id upstream persistence skip_no_coach).
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

### PR-164a — Mobile Navigation + PWA ✅ 2026-04-05
- Bottom tabs (5 coach, 4 athlete), service worker, standalone PWA manifest

### PR-164b — Brand #00D4AA + Responsive + Logo real ✅ 2026-04-05
- Zero #F57C00 remaining; real Quantoryn SVG logo; flex-column layout; psychological hooks

### PR-165a — Team Invite + Role-Based Sidebar ✅ 2026-04-05
- TeamInvitation model: token, role (coach/staff only), email, 7-day expiry, idempotent accept
- Migration: 0107_pr165a_teaminvitation.py (migration 107)
- TeamInvitationViewSet: GET list (owner+coach) + POST create (owner only) — org-scoped
- TeamJoinView: GET /api/team-join/<token>/ (public preview) + POST (accept → JWT)
- Role-aware sidebar: coach hides Finanzas + Mi Organización; staff sees only Alumnos + Grupos
- Dynamic mobile bottom tabs by role (staff 3 tabs, coach/owner 5 tabs)
- RosterSection: 4th tab "Equipo" (owner only) — active members + pending invites + copy link
- InviteTeamModal: role selector + optional email + generated link with clipboard copy
- JoinTeamPage: /join/team/:token — public registration flow (new user or logged-in shortcut)
- 20 backend tests in core/tests_pr165a_team_invite.py — all pass
- Frontend: lint 0 errors, build success
- Risk: MEDIUM — RESOLVED
- Next: PR-165b — org profile, photo upload, athlete payment visibility, trial paywall

### PR-165b — Org Profile + Payment Visibility + Coach Card + Trial Paywall ✅ 2026-04-05
- Organization model: +8 profile fields (description, city, disciplines, contact_email, phone, instagram, website, founded_year)
- Migration: 0108_org_profile_fields.py
- OrgProfileView: GET (any member) + PATCH (owner/admin) at /api/p1/orgs/{id}/profile/
- MySubscriptionView: /api/me/subscription/?org_id= returns coach info + subscription + org branding
- AthleteSubscriptionListView: adds athlete_phone + trial_ends_at to subscription list
- CoachDashboard: dark gradient org header with logo placeholder, description, city/disciplines/year, "Editar perfil" button
- OrgProfileEditModal: MUI Dialog for editing org profile fields
- Finanzas: 4th KPI "En trial", trial filter tab, overdue/trial row colors + day counts, "Recordar" WhatsApp button
- AthleteDashboard: CoachInfoCard + CoachPlanCard (SubscriptionCard) + TrialBanner (<5 days) + TrialPaywall (expired)
- 17 backend tests in core/tests_pr165b_org_profile.py — all pass
- Frontend: lint 0 errors, build success
- Risk: MEDIUM — RESOLVED

### PR-165c — Coach/Staff Profiles + UX Polish + Backfill ✅ 2026-04-06
- CoachProfile page: reads/writes bio, specialties, certifications, years_experience, phone, birth_date, photo_url, instagram via /api/me/coach-profile/
- StaffProfile page: reads/writes staff_title, phone, birth_date, photo_url, instagram via /api/me/staff-profile/
- backfill_coaches management command added
- Frontend: lint 0 errors, build success
- Risk: LOW — RESOLVED

### PR-165d — Pre-launch blockers (12 bugs) ✅ 2026-04-06
- A.1: CoachBriefingView + TeamReadinessView scoped to AthleteCoachAssignment (was showing all org athletes)
- A.2: RegisterView checks email uniqueness before serializer (returns recovery hint)
- A.3: MyUserProfileView GET/PATCH /api/me/user/ (first_name, last_name)
- A.4: MyStaffProfileView GET/PATCH /api/me/staff-profile/
- A.5: CoachPricingPlanDetailView.delete() blocks if active subscriptions exist
- A.6: UserIdentityView returns first_name, last_name (was missing, caused avatar "F" bug)
- B.1: StaffDashboard for staff role in DashboardRouter
- B.2: OwnerProfile page (redirects to /coach-dashboard in 165e)
- B.3: Finanzas handleDeletePlan shows 400 error message
- B.4: RegistrationStep handles email_exists code with login link
- 7 new tests in core/tests_pr165d_prelaunch.py — all pass
- Fixed tests_pr128a_pmc + tests_pr148_compliance to create AthleteCoachAssignment
- Frontend: lint 0 errors, build success
- Risk: MEDIUM — RESOLVED

### PR-165e — Final Pre-Launch: Password Recovery + Tenancy + Sidebar + UX ✅ 2026-04-06
- Password recovery: PasswordResetToken model (SHA-256, single-use, 1h expiry), Resend backend
  ForgotPassword + ResetPassword pages, anti-enumeration 200, strength meter, Login link
- Group 2: AthleteRosterViewSet scoped to coach-assigned athletes (was returning all org athletes)
- Group 3: MyCoachProfileView.get() now returns phone, birth_date, photo_url, instagram
- Group 4: Dashboard activeOrg.org_name fix (was undefined)
- Group 5: Owner sidebar unified into CoachDashboard 3-tab (Organización / Mi Perfil / Equipo)
- Group 6: Wellness first-checkin retention toast "✨ ¡Listo! Tu coach acaba de recibirlo."
- Group 7: Spanish vos cleanup (TrainingDetailModal, JoinTeamPage, Teams)
- Migration: 0111_password_reset_token.py
- 9 new tests in core/tests_pr165e_final.py — all pass
- Frontend: lint 0 errors, build success
- Risk: MEDIUM — IN REVIEW (branch: pr-165e-final-prelaunch-v2)
- Next: PR-166 — Onboarding Experience (checklist + empty states)
- Post-merge: set RESEND_API_KEY in Railway, configure DKIM/SPF for noreply@quantoryn.com

### PR-167d — Hotfix: MP Webhook Reconciliation + Sentry org_id fix + Athlete Refresh UX ✅ 2026-04-15
- Root cause: `_create_mp_preapproval` returned only `{init_point}` — no `id` field → `mp_preapproval_id` stored as None → webhook lookup failed → subscription stayed "pending" forever
- Fix 1 (Sentry crash): `MySubscriptionView.get()` — `int(org_id)` with 400 on TypeError/ValueError (was 500 ValueError for `?org_id=undefined`)
- Fix 2 (webhook fallback): `athlete_webhook.process_athlete_subscription_webhook()` — when fast-path lookup fails, fetches preapproval from MP API using each OrgOAuthCredential(provider="mercadopago"), matches by `payer_email` + `preapproval_plan_id`, stamps real `mp_preapproval_id` on sub, applies STATUS_MAP. Logs `mp.athlete_webhook.reconciled`.
- Fix 3 (sync endpoint): `AthleteSubscriptionSyncView` POST `/api/billing/athlete-subscriptions/sync/` — owner/admin only; fetches MP status for all pending/overdue subs with `mp_preapproval_id` set; returns `{reconciled, errors}`
- Fix 4 (athlete UX): `AthleteDashboard` polls `/api/me/subscription/` every 10s (max 6 attempts) when redirected back from MP with `?mp_return=1`; shows "¡Suscripción activada!" toast on activation
- Fix 5 (callback): `PaymentCallback.jsx` adds `?mp_return=1` to all `/dashboard` redirects (approved + pending paths)
- Fix 6 (Finanzas): "Sincronizar con MercadoPago" button next to "Actualizar" — calls sync endpoint, toasts count
- Fix 7 (API): `syncAthleteSubscriptions()` added to `frontend/src/api/billing.js`
- 8 new tests in `tests_pr167d_my_subscription.py` + `tests_pr167d_webhook_reconcile.py` + `tests_pr167d_sync_endpoint.py` — all pass
- Django system check: 0 issues; Frontend lint: 0 errors; Frontend build: success (8m 13s)
- Post-deploy action: run POST /api/billing/athlete-subscriptions/sync/ to reconcile Natalia's test sub ($100 "Regalo")
- Risk: HIGH (billing critical path) — RESOLVED

### PR-167c — Subscription lifecycle: Pause + Cancel + Reactivate + Retention survey ✅ 2026-04-16
- Model: AthleteSubscription.Status.PAUSED added + 6 new nullable fields: paused_at, cancelled_at, pause_reason, pause_comment, cancellation_reason, cancellation_comment
- Migration 0114_pr167c_subscription_lifecycle.py
- Webhook: STATUS_MAP "paused" → "paused" (was "overdue") — corrects idempotency behavior
- 3 new MP helpers: pause_subscription, cancel_athlete_subscription, reactivate_subscription (all coach-token, Law 6 compliant)
- 4 new endpoints:
  - POST /api/athlete/subscription/pause/ — athlete pauses with retention survey
  - POST /api/athlete/subscription/cancel/ — athlete cancels with retention survey
  - POST /api/athlete/subscription/reactivate/ — paused→active (MP reactivate) or cancelled→pending (new preapproval)
  - POST /api/billing/athlete-subscriptions/<pk>/owner-action/ — owner pause/cancel/reactivate + notifies athlete
- AthleteMySubscriptionView now returns paused_at, cancelled_at, pause_reason, cancellation_reason
- Frontend:
  - SubscriptionActionModal.jsx (new) — retention survey modal for pause + cancel flows
  - SubscriptionCard.jsx — action buttons for active (Pausar/Cancelar), paused (Reactivar/Cancelar), cancelled (Volver a suscribirse)
  - Finanzas.jsx — owner action buttons per row + Pausados filter tab + ownerSubscriptionAction import
  - billing.js — 4 new API functions
- 28 new tests, all pass; adjacent billing tests (47 total) all pass
- Django check: 0 issues; lint: 0 errors; build: success
- Risk: MEDIUM | Branch: p2/pr167c-subscription-lifecycle | Commit: f998dfe

### PR-169 — MP Security & Reliability Bundle ✅ 2026-04-17
- Feature 1: `create_preapproval_plan()` raises ImproperlyConfigured if BACKEND_URL empty (non-test);
  `patch_mp_notification_urls` command — idempotent PUT on all active CoachPricingPlans; --verify mode
- Feature 2: `integrations/mercadopago/webhook_security.py` — HMAC-SHA256 x-signature verification;
  `AthleteSubscriptionWebhookView` returns 401 on invalid sig; passthrough when secret unconfigured (dev)
  `MERCADOPAGO_WEBHOOK_SECRET` added to settings.py
- Feature 3: `daily_mp_reconciliation` command — reconciles pending/overdue subs vs MP; logs orphans;
  notifies org owner on orphaned authorized preapproval
- Feature 4: `STATUS_MAP["overdue"] = "overdue"` — creates InternalMessages to both owner (urgent alert)
  and athlete (update card CTA); sub is never auto-cancelled; SubscriptionCard.jsx overdue message added
- Feature 5: `last_pre_charge_notification_sent_at` field on AthleteSubscription (migration 0115);
  `pre_charge_notifications` command — sends 3-day renewal reminder; idempotent (24h dedup guard)
- 13 new tests in core/tests_pr169_mp_security.py — all pass; 64 billing regression tests — all pass
- Migration: 0115_pr169_pre_charge_notification_field.py
- Django check: 0 issues; lint: 0 errors; build: success
- Branch: p2/pr169-mp-security-reliability | NOT YET PUSHED (waiting for Fernando)
- Post-deploy: add MERCADOPAGO_WEBHOOK_SECRET env var + run patch_mp_notification_urls + configure cron

## Test Baseline
~1444+ tests | CI: backend ✅ frontend ✅
