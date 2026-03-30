import client from './client';

export function getBillingStatus() {
  return client.get('/api/billing/status/');
}

export function getCoachPricingPlans() {
  return client.get('/api/billing/plans/');
}

export function createCoachPricingPlan(data) {
  return client.post('/api/billing/plans/', data);
}

export function createInvitation(coachPlanId, email) {
  return client.post('/api/billing/invitations/', { coach_plan: coachPlanId, email });
}

export function getInvitations() {
  return client.get('/api/billing/invitations/');
}

export function resendInvitation(token) {
  return client.post(`/api/billing/invitations/${token}/resend/`);
}

export function getAthleteSubscriptions() {
  return client.get('/api/billing/athlete-subscriptions/');
}

export function activateAthleteManually(subscriptionId) {
  return client.post(`/api/billing/athlete-subscriptions/${subscriptionId}/activate/`);
}

// PR-138: public invite page
export function getInvitation(token) {
  return client.get(`/api/billing/invitations/${token}/`);
}

export function acceptInvitation(token) {
  return client.post(`/api/billing/invitations/${token}/accept/`);
}

// PR-150: MP Connect + Universal invite link + Athlete subscription
export function getMPConnectUrl() {
  return client.get('/api/billing/mp/connect/');
}

export function disconnectMP() {
  return client.delete('/api/billing/mp/disconnect/');
}

export function getInviteLink() {
  return client.get('/api/billing/invite-link/');
}

export function regenerateInviteLink() {
  return client.post('/api/billing/invite-link/regenerate/');
}

export function getJoinDetail(slug) {
  return client.get(`/api/billing/join/${slug}/`);
}

export function getMySubscription() {
  return client.get('/api/athlete/subscription/');
}
