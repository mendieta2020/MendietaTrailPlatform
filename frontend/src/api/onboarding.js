import client from './client';

export function registerWithEmail(data) {
  return client.post('/api/auth/register/', data);
}

export function registerWithGoogle(credential) {
  return client.post('/api/auth/google/', { credential });
}

export function completeOnboarding(data) {
  return client.post('/api/onboarding/complete/', data);
}

// PR-165e: Password recovery
export function requestPasswordReset(email) {
  return client.post('/api/auth/password-reset/request/', { email });
}

export function confirmPasswordReset(token, new_password) {
  return client.post('/api/auth/password-reset/confirm/', { token, new_password });
}
