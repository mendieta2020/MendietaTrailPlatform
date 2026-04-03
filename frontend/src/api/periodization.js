/**
 * frontend/src/api/periodization.js — PR-157
 *
 * API client functions for the auto-periodization feature.
 */
import client from './client'

/**
 * POST /api/coach/athletes/<membershipId>/auto-periodize/
 * Trigger auto-periodize for a single athlete.
 */
export const autoPeriodizeAthlete = (membershipId, { cycle_pattern = '3:1', weeks_back = 12 } = {}) =>
  client.post(`/api/coach/athletes/${membershipId}/auto-periodize/`, { cycle_pattern, weeks_back })

/**
 * POST /api/p1/orgs/<orgId>/auto-periodize-group/
 * Auto-periodize all athletes in a team (or entire org).
 */
export const autoPeriodizeGroup = (orgId, { team_id, default_cycle = '3:1' } = {}) =>
  client.post(`/api/p1/orgs/${orgId}/auto-periodize-group/`, { team_id, default_cycle })

/**
 * GET /api/coach/athletes/<membershipId>/recent-workouts/?weeks=6
 * Returns last N weeks of workout names + consecutive repetition warnings.
 */
export const getRecentWorkouts = (membershipId, weeks = 6) =>
  client.get(`/api/coach/athletes/${membershipId}/recent-workouts/`, { params: { weeks } })

/**
 * GET /api/athlete/training-phases/?weeks=12
 * Athlete's own training phases for the next N weeks (for Mi Progreso timeline).
 */
export const getAthleteTrainingPhases = (weeks = 12) =>
  client.get('/api/athlete/training-phases/', { params: { weeks } })

/**
 * GET /api/p1/orgs/<orgId>/athletes/<athleteId>/training-phases/?from=&to=
 * Coach reads an athlete's phases for a date range (Calendar badge).
 */
export const getCoachAthleteTrainingPhases = (orgId, athleteId, from, to) =>
  client.get(`/api/p1/orgs/${orgId}/athletes/${athleteId}/training-phases/`, {
    params: { from, to },
  })
