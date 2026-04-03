import client from './client'

export const getAthletePMC = (days = 90) =>
  client.get(`/api/athlete/pmc/?days=${days}`)

export const getHRProfile = () =>
  client.get('/api/athlete/hr-profile/')

export const updateHRProfile = (data) =>
  client.put('/api/athlete/hr-profile/', data)

export const getCoachAthletePMC = (membershipId, days = 90) =>
  client.get(`/api/coach/athletes/${membershipId}/pmc/?days=${days}`)

export const getTeamReadiness = () =>
  client.get('/api/coach/team-readiness/')

export const getTrainingVolume = (membershipId, { metric = 'distance', sport = 'all', precision = 'weekly', days = 90 } = {}) =>
  client.get(`/api/coach/athletes/${membershipId}/training-volume/`, { params: { metric, sport, precision, days } })

export const getAthleteWellness = (membershipId, days = 30) =>
  client.get(`/api/coach/athletes/${membershipId}/wellness/`, { params: { days } })

export const getAthleteCompliance = (membershipId, { days = 90, precision = 'weekly' } = {}) =>
  client.get(`/api/coach/athletes/${membershipId}/compliance/`, { params: { days, precision } })

// PR-159: Athlete Card — coach reads profile, injuries, goals, notes
export const getCoachAthleteProfile = (membershipId) =>
  client.get(`/api/coach/athletes/${membershipId}/profile/`)

export const patchCoachAthleteProfile = (membershipId, data) =>
  client.patch(`/api/coach/athletes/${membershipId}/profile/`, data)

export const getCoachAthleteInjuries = (membershipId) =>
  client.get(`/api/coach/athletes/${membershipId}/card-injuries/`)

export const createCoachAthleteInjury = (membershipId, data) =>
  client.post(`/api/coach/athletes/${membershipId}/card-injuries/`, data)

export const getCoachAthleteGoals = (membershipId) =>
  client.get(`/api/coach/athletes/${membershipId}/card-goals/`)

export const getCoachAthleteNotes = (membershipId) =>
  client.get(`/api/coach/athletes/${membershipId}/notes/`)

export const updateCoachAthleteNotes = (membershipId, notes) =>
  client.put(`/api/coach/athletes/${membershipId}/notes/`, { notes })

// PR-156: Athlete self-serve progress endpoints
export const getAthleteGoals = () =>
  client.get('/api/athlete/goals/')

export const getAthleteWeeklySummary = () =>
  client.get('/api/athlete/weekly-summary/')

export const getAthleteWellnessToday = () =>
  client.get('/api/athlete/wellness/today/')
