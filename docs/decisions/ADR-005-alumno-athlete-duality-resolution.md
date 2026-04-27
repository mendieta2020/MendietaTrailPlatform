# ADR-005 — Alumno / Athlete duality: resolution strategy

**Status:** accepted (partial — full deprecation deferred to post-launch)  
**Date:** 2026-04-26  
**Deciders:** Lab (strategy), Antigravity (implementation)

---

## Context

Two overlapping models represent the "athlete user" identity:

| Model | Origin | Key FKs |
|-------|--------|---------|
| `Alumno` | Legacy (V1 coach app) | `usuario` (OneToOneField → User), `entrenador` |
| `Athlete` | P1 org-first model | `user` (ForeignKey → User), `organization` |

`WorkoutAssignment` uses `Athlete` FK. `OAuthCredential` and the Strava OAuth flow use
`Alumno`. The weather service reads `Athlete.location_lat/lon` but the city may only be
stored on `Alumno.ciudad`. This creates stale coordinates for weather forecasts.

Additionally, the coach calendar calls `/api/planning/athlete/{Athlete.pk}/plan-vs-real/`
but this endpoint did not exist — the Athlete ID was not routed to the plan-vs-real view.

## Decision

**Athlete is canonical. Alumno is a legacy mirror.** The following immediate fixes
are applied (PR-188e):

1. **Location sync signal (Athlete → Alumno):** `post_save` on `Athlete` mirrors
   `location_lat`, `location_lon`, `location_city` to the linked `Alumno` via
   `update_fields` (no recursion).

2. **City propagation (Alumno → Athlete):** When `Alumno.ciudad` changes and the
   linked `Athlete` has no `location_city`, copy the city to `Athlete` (triggering the
   existing `geocode_athlete_city` signal to populate coordinates).

3. **Migration:** `Alumno.location_lat` and `Alumno.location_lon` (`FloatField`,
   null=True) added so the mirror is structurally complete.

4. **Coach plan-vs-real endpoint:** `/api/planning/athlete/<athlete_id>/plan-vs-real/`
   created (`CoachAthletePlanVsRealView`). Queries use `Athlete` FK directly — no
   Alumno intermediary needed for `WorkoutAssignment` lookups.

## Deferred (post-launch)

- Full `Alumno` deprecation and migration of all legacy FKs to `Athlete`.
- Removal of `Alumno.strava_athlete_id` (superseded by `ExternalIdentity`).
- `Alumno.entrenador` → `AthleteCoachAssignment` migration.

Re-evaluate when: athlete count exceeds 500 in production, or a second provider
requires Alumno-free onboarding.

## Consequences

- `Alumno.location_lat/lon` added (migration 0118).
- Two new signals in `core/signals.py`; infinite-loop prevention via `update_fields`
  and `_skip_signal` guard (same pattern as existing Alumno signals).
- Coach calendar plan-vs-real loads correctly without 404.
