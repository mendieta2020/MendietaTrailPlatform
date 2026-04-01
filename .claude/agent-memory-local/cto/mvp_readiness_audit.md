---
name: MVP Readiness Audit
description: Radiografia completa del estado del producto al 2026-03-24 — que esta listo para testing interno y que falta
type: project
---

# MVP Readiness Audit — 2026-03-24

## Contexto
Fernando quiere testing interno (coach + atletas reales) en 1-2 meses.
Competidor actual de referencia: Trainer Plan (LATAM).
Timeline: testing interno -> beta externa -> lanzamiento mercado.

## Seccion por seccion

### LISTO PARA TESTING INTERNO (funcional)
1. Roster/Alumnos — muestra CTL real, badges de suscripcion, device status
2. Calendario — drag & drop desde libreria, assignment lifecycle
3. Grupos/Teams — CRUD completo, team detail
4. Conexiones — Strava + Suunto activos, Garmin/Coros/Polar/Wahoo "proximamente"
5. PMC Engine — TRIMP cascade, CTL/ATL/TSB, DailyLoad computando con datos reales
6. Athlete Dashboard — home personalizado, clima, today workout, onboarding checklist
7. Billing backend — OrganizationSubscription, CoachPricingPlan, AthleteSubscription, MP webhooks
8. Invitaciones — token-based invite, accept flow, MP redirect
9. Finanzas (owner/admin) — KPIs, plans, subscriptions table, invitations
10. Multi-tenant — organization-scoped everything, ~1329 tests

### EN PROCESO (PR-128b en branch)
- AthleteProgress (Mi Progreso) — error "No se pudieron cargar datos" → fix en PR-128b
- CoachAnalytics — error "No se pudieron cargar datos del equipo" → fix en PR-128b
- CoachAthletePMC — individual athlete PMC view → depende de PR-128b

### DEBIL / NECESITA TRABAJO
1. Dashboard Inicio (coach) — KPIs hardcodeados ("Objetivo: $1M", "68 CTL", "Riesgo Lesion: 0"), pmcData=[], pagosData=[]
2. Libreria — workout creator existe pero UI plana, no profesional
3. Mi Organizacion (CoachDashboard) — basico, no claro que aporta
4. Finanzas local — error esperado sin MP real configurado
5. require_plan gates — Free bloquea PMC, deberia permitirlo (business_strategy.md)

### NO EXISTE AUN
1. Historical backfill (PR-129) — no hay forma de traer actividades pasadas
2. Modal de upgrade atleta #6 (PR-142)
3. Plan vs Real reconciliation UI — backend existe, frontend no
4. Workout delivery a dispositivo (Suunto push existe, UI parcial)
5. Landing page con onboarding real (registro coach -> org -> trial)

## Proximos 5 PRs priorizados (ver radiografia principal)
PR-128b merge, PR-142, PR-143, PR-144, PR-129
