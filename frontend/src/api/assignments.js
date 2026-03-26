import client from './client';

const p1Base = (orgId) => `/api/p1/orgs/${orgId}`;

export function listAssignments(orgId, { athleteId, teamId, dateFrom, dateTo } = {}) {
  const params = {};
  if (athleteId) params.athlete_id = athleteId;
  if (teamId) params.team_id = teamId;
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  return client.get(`${p1Base(orgId)}/assignments/`, { params });
}

export function createAssignment(orgId, data) {
  return client.post(`${p1Base(orgId)}/assignments/`, data);
}

export function bulkAssignTeam(orgId, data) {
  return client.post(`${p1Base(orgId)}/assignments/bulk-assign-team/`, data);
}

export function updateAssignment(orgId, id, data) {
  return client.patch(`${p1Base(orgId)}/assignments/${id}/`, data);
}
