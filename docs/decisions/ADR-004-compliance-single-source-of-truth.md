# ADR-004 — Compliance: backend as single source of truth (cap 150 %)

**Status:** accepted  
**Date:** 2026-04-26  
**Deciders:** Lab (strategy), Antigravity (implementation)

---

## Context

`WorkoutAssignment` stores athlete-reported execution data (`actual_duration_seconds`,
`actual_distance_meters`). The compliance percentage (plan vs real) was being
calculated redundantly in three places:

1. `core/compliance.py` — `calcular_porcentaje_cumplimiento()` (Alumno-era logic, cap 120 %)
2. `calendarHelpers.js` — `computeCompliancePct()` (frontend, no cap)
3. `WorkoutCoachDrawer.jsx` — inline math

The frontend-only calculation had no cap, producing values >120 % with no UX tier for
"over-achieved". Railway logs showed the two calculations diverging for the same session.

## Decision

1. **Backend is the single source of truth.** `WorkoutAssignmentSerializer` and
   `WorkoutAssignmentAthleteSerializer` expose a read-only `compliance_pct` field
   computed by `_compute_assignment_compliance_pct()`.

2. **Cap raised from 120 % to 150 %.** Values >150 % return sentinel `151` (rendered
   as "⚠️ Exceso" in `getComplianceStyle()`).

3. **Frontend prefers backend value.** `computeCompliancePct(assignment)` checks
   `assignment.compliance_pct != null` first; falls back to local calculation only
   when backend value is absent (e.g., offline or older API response).

4. **Tiers** (unchanged in `getComplianceStyle`):
   - ≤30 %  → Muy parcial (red)
   - ≤70 %  → Parcial (amber)
   - ≤110 % → Completado (green)
   - ≤150 % → Sobre-cumplido (blue)
   - >150 % → ⚠️ Exceso (purple)

## Consequences

- `compliance_pct` field added to `_ASSIGNMENT_FIELDS` (read-only on both serializers).
- Old `calcular_porcentaje_cumplimiento()` cap updated to 150 % with sentinel 151.
- The `WorkoutCoachDrawer` inline math is a tech-debt item; it will read the backend
  field once the component is refactored.
- No migration required (computed field, not stored).
