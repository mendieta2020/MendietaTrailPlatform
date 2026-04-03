/**
 * frontend/src/api/planning.js — PR-158
 *
 * API client functions for Planificador Pro:
 * - Workout history (day-by-day grid)
 * - Group workout history
 * - Copy week
 * - Estimated weekly load
 * - Plan vs Real
 */
import client from './client'

/**
 * GET /api/coach/athletes/<membershipId>/workout-history/
 * Day-by-day workout history grid for a single athlete.
 */
export const getWorkoutHistory = (membershipId, { weeks = 6, targetWeek } = {}) =>
  client.get(`/api/coach/athletes/${membershipId}/workout-history/`, {
    params: { weeks, target_week: targetWeek },
  })

/**
 * GET /api/p1/orgs/<orgId>/group-workout-history/
 * Day-by-day workout history grid for a group/team.
 */
export const getGroupWorkoutHistory = (orgId, { weeks = 6, targetWeek, teamId } = {}) =>
  client.get(`/api/p1/orgs/${orgId}/group-workout-history/`, {
    params: { weeks, target_week: targetWeek, team_id: teamId },
  })

/**
 * POST /api/p1/orgs/<orgId>/copy-week/
 * Copy all workout assignments from source week to target week.
 */
export const copyWeek = (orgId, { sourceWeekStart, targetWeekStart, teamId, athleteIds }) =>
  client.post(`/api/p1/orgs/${orgId}/copy-week/`, {
    source_week_start: sourceWeekStart,
    target_week_start: targetWeekStart,
    team_id: teamId ?? null,
    athlete_ids: athleteIds ?? null,
  })

/**
 * GET /api/coach/athletes/<membershipId>/estimated-weekly-load/
 * Planned TSS + phase recommendation for a target week.
 */
export const getEstimatedWeeklyLoad = (membershipId, { weekStart } = {}) =>
  client.get(`/api/coach/athletes/${membershipId}/estimated-weekly-load/`, {
    params: { week_start: weekStart },
  })

/**
 * GET /api/athlete/plan-vs-real/
 * Athlete's weekly plan vs real compliance summary.
 */
export const getPlanVsReal = ({ weekStart } = {}) =>
  client.get('/api/athlete/plan-vs-real/', {
    params: { week_start: weekStart },
  })

/**
 * GET /api/p1/orgs/<orgId>/group-week-template/
 * Current planned workouts for a team's week (deduplicated template).
 * Used by GroupPlanningView.
 */
export const getGroupWeekTemplate = (orgId, { weekStart, teamId } = {}) =>
  client.get(`/api/p1/orgs/${orgId}/group-week-template/`, {
    params: { week_start: weekStart, team_id: teamId },
  })
