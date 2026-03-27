import client from './client';

const p1Base = (orgId) => `/api/p1/orgs/${orgId}`;

export const getTeams = (orgId) =>
  client.get(`${p1Base(orgId)}/teams/`);

export const getComplianceWeek = (orgId, teamId, week) =>
  client.get(`${p1Base(orgId)}/teams/${teamId}/compliance-week/`, { params: { week } });

export const addTeamMember = (orgId, teamId, athleteId) =>
  client.post(`${p1Base(orgId)}/teams/${teamId}/members/`, { athlete_id: athleteId });

export const removeTeamMember = (orgId, teamId, athleteId) =>
  client.delete(`${p1Base(orgId)}/teams/${teamId}/members/${athleteId}/`);
