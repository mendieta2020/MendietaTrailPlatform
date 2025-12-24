import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import client from '../client';
import { getAlerts } from './analytics';

describe('getAlerts', () => {
  let spy;

  beforeEach(() => {
    spy = vi.spyOn(client, 'get').mockResolvedValue({ data: { count: 0, next: null, previous: null, results: [] } });
  });

  afterEach(() => {
    spy?.mockRestore();
  });

  it('builds query params with optional filters', async () => {
    await getAlerts({ page: 2, pageSize: 20, alumnoId: 7, vistoPorCoach: false });

    expect(client.get).toHaveBeenCalledTimes(1);
    const [url, config] = client.get.mock.calls[0];
    expect(url).toBe('/api/analytics/alerts/');
    expect(config.params).toEqual({ page: 2, page_size: 20, alumno_id: 7, visto_por_coach: false });
  });

  it('omits undefined/null/empty optional params', async () => {
    await getAlerts({ page: 1, pageSize: 5, alumnoId: undefined, vistoPorCoach: undefined });

    const [, config] = client.get.mock.calls[0];
    expect(config.params).toEqual({ page: 1, page_size: 5 });
  });

  it('passes AbortSignal to axios', async () => {
    const ac = new AbortController();
    await getAlerts({ page: 1, pageSize: 5, signal: ac.signal });

    const [, config] = client.get.mock.calls[0];
    expect(config.signal).toBe(ac.signal);
  });
});

