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
