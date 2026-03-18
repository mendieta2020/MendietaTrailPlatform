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
