import MockAdapter from 'axios-mock-adapter';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';

import client from './client';
import { loginWithCredentials, logoutSession } from './authClient';
import { tokenStore } from './tokenStore';

describe('auth client logout/login edge cases', () => {
  let mockClient;

  beforeEach(() => {
    tokenStore.clear();
    mockClient = new MockAdapter(client);
    delete client.defaults.headers.common.Authorization;
    delete client.defaults.headers.common.authorization;
  });

  afterEach(() => {
    mockClient.restore();
    tokenStore.clear();
    delete client.defaults.headers.common.Authorization;
    delete client.defaults.headers.common.authorization;
  });

  it('clears tokens and axios Authorization defaults on logout', async () => {
    tokenStore.setTokens({ access: 'stale_access', refresh: 'stale_refresh' });
    client.defaults.headers.common.Authorization = 'Bearer stale_access';

    await logoutSession();

    expect(tokenStore.getAccessToken()).toBe(null);
    expect(tokenStore.getRefreshToken()).toBe(null);
    expect(client.defaults.headers.common.Authorization).toBeUndefined();
  });

  it('does not include Authorization for /api/token/ requests', async () => {
    tokenStore.setTokens({ access: 'stale_access', refresh: 'stale_refresh' });
    client.defaults.headers.common.Authorization = 'Bearer stale_access';
    let sentAuthorization;

    mockClient.onPost('/api/token/').reply((config) => {
      sentAuthorization = config.headers?.Authorization || config.headers?.authorization;
      return [200, { access: 'new_access', refresh: 'new_refresh' }];
    });

    await loginWithCredentials({ username: 'coach', password: 'secret' });

    expect(sentAuthorization).toBeUndefined();
  });

  it('allows logout → login without hard reload', async () => {
    tokenStore.setTokens({ access: 'stale_access', refresh: 'stale_refresh' });
    client.defaults.headers.common.Authorization = 'Bearer stale_access';

    mockClient.onPost('/api/token/').reply((config) => {
      if (config.headers?.Authorization || config.headers?.authorization) {
        return [400, { detail: 'auth_header_not_allowed' }];
      }
      return [200, { access: 'new_access', refresh: 'new_refresh' }];
    });

    await logoutSession();
    const response = await loginWithCredentials({ username: 'coach', password: 'secret' });

    expect(response.status).toBe(200);
    expect(tokenStore.getAccessToken()).toBe('new_access');
    expect(tokenStore.getRefreshToken()).toBe('new_refresh');
  });
});
