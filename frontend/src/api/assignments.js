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

export function moveAssignment(orgId, id, newDate) {
  return client.patch(`${p1Base(orgId)}/assignments/${id}/`, { scheduled_date: newDate });
}

export function deleteAssignment(orgId, id) {
  return client.delete(`${p1Base(orgId)}/assignments/${id}/`);
}

export function cloneAssignmentWorkout(orgId, id) {
  return client.post(`${p1Base(orgId)}/assignments/${id}/clone-workout/`);
}

export function updateAssignmentSnapshot(orgId, assignmentId, data) {
  return client.patch(`${p1Base(orgId)}/assignments/${assignmentId}/update-snapshot/`, data);
}

export function copyWeek(orgId, payload) {
  return client.post(`${p1Base(orgId)}/assignments/copy-week/`, payload);
}

export function deleteWeek(orgId, payload) {
  return client.post(`${p1Base(orgId)}/assignments/delete-week/`, payload);
}

export function addCoachComment(orgId, assignmentId, comment) {
  return client.patch(
    `${p1Base(orgId)}/assignments/${assignmentId}/coach-comment/`,
    { coach_comment: comment }
  );
}

export function bulkCreateAssignments(orgId, data) {
  return client.post(`${p1Base(orgId)}/assignments/bulk-create/`, data);
}

export function getAssignment(orgId, id) {
  return client.get(`${p1Base(orgId)}/assignments/${id}/`);
}

export function getCalendarTimeline(orgId, { startDate, endDate, athleteId } = {}) {
  const params = { start_date: startDate, end_date: endDate };
  if (athleteId) params.athlete_id = athleteId;
  return client.get(`${p1Base(orgId)}/calendar-timeline/`, { params });
}
