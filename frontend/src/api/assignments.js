import client from './client';

const p1Base = (orgId) => `/api/p1/orgs/${orgId}`;

export function listAssignments(orgId, { athleteId, dateFrom, dateTo } = {}) {
  const params = {};
  if (athleteId) params.athlete_id = athleteId;
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  return client.get(`${p1Base(orgId)}/assignments/`, { params });
}
