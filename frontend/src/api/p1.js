import client from './client';

const p1Base = (orgId) => `/api/p1/orgs/${orgId}`;

export function listCoaches(orgId) {
  return client.get(`${p1Base(orgId)}/coaches/`);
}

export function listAthletes(orgId) {
  return client.get(`${p1Base(orgId)}/roster/athletes/`);
}

export function listTeams(orgId) {
  return client.get(`${p1Base(orgId)}/teams/`);
}

export function createTeam(orgId, data) {
  return client.post(`${p1Base(orgId)}/teams/`, data);
}

export function getAthlete(orgId, id) {
  return client.get(`${p1Base(orgId)}/roster/athletes/${id}/`);
}

export function listMemberships(orgId) {
  return client.get(`${p1Base(orgId)}/memberships/`);
}

export function listExternalIdentities(orgId) {
  return client.get(`${p1Base(orgId)}/external-identities/`);
}

export function createExternalIdentity(orgId, data) {
  return client.post(`${p1Base(orgId)}/external-identities/`, data);
}

export function deleteExternalIdentity(orgId, id) {
  return client.delete(`${p1Base(orgId)}/external-identities/${id}/`);
}

// ── Workout Libraries ─────────────────────────────────────────────────────────

export function listLibraries(orgId) {
  return client.get(`${p1Base(orgId)}/libraries/`);
}

export function createLibrary(orgId, data) {
  return client.post(`${p1Base(orgId)}/libraries/`, data);
}

export function updateLibrary(orgId, libId, data) {
  return client.patch(`${p1Base(orgId)}/libraries/${libId}/`, data);
}

export function deleteLibrary(orgId, libId) {
  return client.delete(`${p1Base(orgId)}/libraries/${libId}/`);
}

// ── Planned Workouts ──────────────────────────────────────────────────────────

export function listPlannedWorkouts(orgId, libId) {
  return client.get(`${p1Base(orgId)}/libraries/${libId}/workouts/`);
}

export function getPlannedWorkout(orgId, libId, workoutId) {
  return client.get(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/`);
}

export function createPlannedWorkout(orgId, libId, data) {
  return client.post(`${p1Base(orgId)}/libraries/${libId}/workouts/`, data);
}

export function updatePlannedWorkout(orgId, libId, workoutId, data) {
  return client.patch(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/`, data);
}

export function deletePlannedWorkout(orgId, libId, workoutId) {
  return client.delete(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/`);
}

// ── Workout Blocks ────────────────────────────────────────────────────────────

export function createWorkoutBlock(orgId, libId, workoutId, data) {
  return client.post(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/`, data);
}

export function updateWorkoutBlock(orgId, libId, workoutId, blockId, data) {
  return client.patch(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/${blockId}/`, data);
}

export function deleteWorkoutBlock(orgId, libId, workoutId, blockId) {
  return client.delete(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/${blockId}/`);
}

// ── Workout Intervals ─────────────────────────────────────────────────────────

export function createWorkoutInterval(orgId, libId, workoutId, blockId, data) {
  return client.post(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/${blockId}/intervals/`, data);
}

export function updateWorkoutInterval(orgId, libId, workoutId, blockId, intervalId, data) {
  return client.patch(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/${blockId}/intervals/${intervalId}/`, data);
}

export function deleteWorkoutInterval(orgId, libId, workoutId, blockId, intervalId) {
  return client.delete(`${p1Base(orgId)}/libraries/${libId}/workouts/${workoutId}/blocks/${blockId}/intervals/${intervalId}/`);
}

// ── Dashboard Analytics (PR-149) ──────────────────────────────────────────────

export function getDashboardAnalytics(orgId) {
  return client.get(`${p1Base(orgId)}/dashboard-analytics/`);
}

// ── Athlete Availability (PR-153) ─────────────────────────────────────────────

export function getAthleteAvailability(orgId, athleteId) {
  return client.get(`${p1Base(orgId)}/athletes/${athleteId}/availability/`);
}

// ── Wellness Check-In (PR-154) ────────────────────────────────────────────────

export function submitWellnessCheckIn(orgId, athleteId, data) {
  return client.post(`${p1Base(orgId)}/athletes/${athleteId}/wellness/`, data);
}

export function getWellnessHistory(orgId, athleteId, days = 7) {
  return client.get(`${p1Base(orgId)}/athletes/${athleteId}/wellness/?days=${days}`);
}

export function dismissWellnessPrompt(orgId, athleteId) {
  return client.post(`${p1Base(orgId)}/athletes/${athleteId}/wellness/dismiss/`);
}

// ── TrainingWeek — Macro View (PR-155) ────────────────────────────────────────

export function getTrainingWeeks(orgId, weekStart, teamId = null) {
  const params = new URLSearchParams({ week_start: weekStart });
  if (teamId) params.append('team_id', teamId);
  return client.get(`${p1Base(orgId)}/training-weeks/?${params}`);
}

export function upsertTrainingWeek(orgId, data) {
  return client.post(`${p1Base(orgId)}/training-weeks/`, data);
}

// Client-side phase suggestion based on recent weeks
export function suggestPhase(recentPhases, hasRaceThisWeek, hasActiveInjury) {
  if (hasActiveInjury) return 'lesion';
  if (hasRaceThisWeek) return 'carrera';
  const recent = (recentPhases || []).slice(-3);
  const cargaCount = recent.filter((p) => p === 'carga').length;
  if (cargaCount >= 2) return 'descarga';
  return null;
}

// ── Athlete Profile (PR-116) ──────────────────────────────────────────────────

export function getAthleteProfile(orgId, athleteId) {
  return client.get(`${p1Base(orgId)}/profiles/${athleteId}/`);
}
