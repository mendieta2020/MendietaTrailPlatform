import client from './client';

export function getDeviceStatus() {
  return client.get('/api/athlete/device-status/');
}

export function dismissDevicePreference(reason = 'no_device') {
  return client.post('/api/athlete/device-preference/dismiss/', { reason });
}

export function reactivateDevicePreference() {
  return client.post('/api/athlete/device-preference/reactivate/');
}

export function getNotifications() {
  return client.get('/api/athlete/notifications/');
}

export function markNotificationRead(id) {
  return client.post(`/api/athlete/notifications/${id}/mark-read/`);
}

// PR-153: Profile, injuries, availability, goals, payment
export function getAthleteProfile(orgId, athleteId) {
  return client.get(`/api/p1/orgs/${orgId}/profiles/${athleteId}/`);
}

export function updateAthleteProfile(orgId, athleteId, data) {
  return client.patch(`/api/p1/orgs/${orgId}/profiles/${athleteId}/`, data);
}

export function getInjuries(orgId, athleteId) {
  return client.get(`/api/p1/orgs/${orgId}/athletes/${athleteId}/injuries/`);
}

export function createInjury(orgId, athleteId, data) {
  return client.post(`/api/p1/orgs/${orgId}/athletes/${athleteId}/injuries/`, data);
}

export function updateInjury(orgId, athleteId, injuryId, data) {
  return client.patch(`/api/p1/orgs/${orgId}/athletes/${athleteId}/injuries/${injuryId}/`, data);
}

export function deleteInjury(orgId, athleteId, injuryId) {
  return client.delete(`/api/p1/orgs/${orgId}/athletes/${athleteId}/injuries/${injuryId}/`);
}

export function getAvailability(orgId, athleteId) {
  return client.get(`/api/p1/orgs/${orgId}/athletes/${athleteId}/availability/`);
}

export function getGoals(orgId) {
  return client.get(`/api/p1/orgs/${orgId}/goals/`);
}

export function createGoal(orgId, data) {
  return client.post(`/api/p1/orgs/${orgId}/goals/`, data);
}

export function deleteGoal(orgId, goalId) {
  return client.delete(`/api/p1/orgs/${orgId}/goals/${goalId}/`);
}

export function getPaymentLink() {
  return client.get('/api/athlete/payment-link/');
}
