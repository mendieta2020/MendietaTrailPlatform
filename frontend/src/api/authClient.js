import client from './client';
import { tokenStore } from './tokenStore';
import { USE_COOKIE_AUTH } from './authMode';

export async function loginWithCredentials({ username, password }) {
  const response = await client.post('/api/token/', { username, password });
  tokenStore.setTokens({ access: response.data?.access, refresh: response.data?.refresh });
  return response;
}

export async function logoutSession() {
  tokenStore.clear();
  if (client.defaults?.headers?.common) {
    delete client.defaults.headers.common.Authorization;
    delete client.defaults.headers.common.authorization;
  }
  if (import.meta.env.DEV) {
    console.debug('[auth] cleared token store and axios defaults on logout');
  }
  if (USE_COOKIE_AUTH) {
    try {
      await client.post('/api/token/logout/');
    } catch (error) {
      // Silencioso: el logout de cookies es best-effort.
    }
  }
}

export async function fetchSession() {
  return client.get('/api/auth/session/');
}
