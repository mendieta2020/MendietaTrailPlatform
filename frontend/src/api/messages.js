import client from './client';

const p1Base = (orgId) => `/api/p1/orgs/${orgId}`;

export const sendMessage = (orgId, data) =>
  client.post(`${p1Base(orgId)}/messages/`, data);

export const getMessages = (orgId) =>
  client.get(`${p1Base(orgId)}/messages/`);

export const markMessageRead = (orgId, messageId) =>
  client.patch(`${p1Base(orgId)}/messages/${messageId}/read/`);

export const getAthleteAlerts = (orgId, athleteId) =>
  client.get(`${p1Base(orgId)}/athletes/${athleteId}/alerts/`);

export const getSessionMessages = (orgId, assignmentId) =>
  client.get(`${p1Base(orgId)}/messages/?reference_id=${assignmentId}`);
