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
