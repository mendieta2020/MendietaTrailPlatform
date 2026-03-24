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
