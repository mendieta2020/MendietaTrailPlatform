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
