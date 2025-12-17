import MockAdapter from 'axios-mock-adapter';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import client, { __internal } from './client';
import { tokenStore } from './tokenStore';
import { subscribeOnLogout } from './authEvents';

describe('api client jwt refresh flow', () => {
  let mockClient;
  let mockRefresh;

  beforeEach(() => {
    tokenStore.clear();
    mockClient = new MockAdapter(client);
    mockRefresh = new MockAdapter(__internal.refreshClient);
  });

  afterEach(() => {
    mockClient.restore();
    mockRefresh.restore();
    tokenStore.clear();
  });

  it('refreshes access token on 401 and retries request', async () => {
    tokenStore.setTokens({ access: 'expired_access', refresh: 'valid_refresh' });

    mockClient
      .onGet('/api/analytics/alerts/')
      .replyOnce(401, { detail: 'token_not_valid' })
      .onGet('/api/analytics/alerts/')
      .reply(200, { count: 1, next: null, previous: null, results: [{ id: 1, mensaje: 'ok' }] });

    mockRefresh
      .onPost('/api/token/refresh/')
      .reply(200, { access: 'new_access', refresh: 'rotated_refresh' });

    const resp = await client.get('/api/analytics/alerts/', { params: { page: 1, page_size: 20 } });

    expect(resp.status).toBe(200);
    expect(resp.data.count).toBe(1);
    expect(tokenStore.getAccessToken()).toBe('new_access');
    expect(tokenStore.getRefreshToken()).toBe('rotated_refresh');
    expect(mockRefresh.history.post.length).toBe(1);
  });

  it('queues concurrent 401s and refreshes only once', async () => {
    tokenStore.setTokens({ access: 'expired_access', refresh: 'valid_refresh' });

    mockRefresh
      .onPost('/api/token/refresh/')
      .reply(200, { access: 'new_access', refresh: 'rotated_refresh' });

    mockClient.onGet('/api/analytics/alerts/').reply((config) => {
      const auth = config.headers?.Authorization;
      if (auth === 'Bearer new_access') {
        return [200, { count: 2, next: null, previous: null, results: [{ id: 1 }, { id: 2 }] }];
      }
      return [401, { detail: 'token_not_valid' }];
    });

    const p1 = client.get('/api/analytics/alerts/', { params: { page: 1, page_size: 20 } });
    const p2 = client.get('/api/analytics/alerts/', { params: { page: 2, page_size: 20 } });

    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1.status).toBe(200);
    expect(r2.status).toBe(200);
    expect(mockRefresh.history.post.length).toBe(1);
  });

  it('clears tokens and emits logout on refresh failure', async () => {
    tokenStore.setTokens({ access: 'expired_access', refresh: 'bad_refresh' });

    const onLogout = vi.fn();
    const unsub = subscribeOnLogout(onLogout);

    mockRefresh.onPost('/api/token/refresh/').reply(401, { detail: 'token_not_valid' });
    mockClient.onGet('/api/analytics/alerts/').reply(401, { detail: 'token_not_valid' });

    await expect(client.get('/api/analytics/alerts/', { params: { page: 1, page_size: 20 } })).rejects.toBeTruthy();

    expect(tokenStore.getAccessToken()).toBe(null);
    expect(tokenStore.getRefreshToken()).toBe(null);
    expect(onLogout).toHaveBeenCalled();
    expect(onLogout.mock.calls[0][0]).toMatchObject({ reason: 'refresh_failed' });

    unsub();
  });
});
