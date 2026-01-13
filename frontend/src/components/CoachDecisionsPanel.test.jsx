import React, { act } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createRoot } from 'react-dom/client';

import CoachDecisionsPanel from './CoachDecisionsPanel';
import weekSummaryFixture from './__fixtures__/weekSummaryFixture';

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

import client from '../api/client';

function setupMatchMedia() {
  if (!window.matchMedia) {
    window.matchMedia = () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }
}

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('CoachDecisionsPanel', () => {
  let container;
  let root;

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    setupMatchMedia();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.clearAllMocks();
  });

  it('renders weekly summary metrics from totals payload', async () => {
    client.get.mockResolvedValueOnce({
      data: weekSummaryFixture,
    });

    await act(async () => {
      root.render(<CoachDecisionsPanel athleteId={7} />);
      await flushPromises();
    });

    expect(container.textContent).toContain('14.01 km');
    expect(container.textContent).toContain('1h 20m');
    expect(container.textContent).toContain('Elev -');
    expect(container.textContent).toContain('Sesiones');
    expect(container.textContent).toContain('RUN: 1');
    expect(container.textContent).toContain('866 kcal');
    expect(container.textContent).toContain('Trabajo por deporte');
    expect(container.textContent).toContain('Fuerza');
    expect(container.textContent).toContain('1h 30m');
    expect(container.textContent).toContain('600 kcal');
    expect(container.textContent).toContain('280');
  });

  it('renders without per_sport_totals data', async () => {
    const payload = { ...weekSummaryFixture };
    delete payload.per_sport_totals;
    client.get.mockResolvedValueOnce({
      data: payload,
    });

    await act(async () => {
      root.render(<CoachDecisionsPanel athleteId={7} />);
      await flushPromises();
    });

    expect(container.textContent).toContain('14.01 km');
    expect(container.textContent).not.toContain('Trabajo por deporte');
  });

  it('shows empty state for empty payloads', async () => {
    client.get.mockResolvedValueOnce({
      data: {
        week: '2026-W03',
        start_date: '2026-01-12',
        end_date: '2026-01-18',
        distance_km: 0,
        duration_minutes: 0,
        elevation_gain_m: 0,
        elevation_loss_m: 0,
        elevation_total_m: 0,
        kcal: 0,
        sessions_count: 0,
        sessions_by_type: {},
        compliance: {},
        alerts: [],
      },
    });

    await act(async () => {
      root.render(<CoachDecisionsPanel athleteId={7} />);
      await flushPromises();
    });

    expect(container.textContent).toContain('Sin datos para esta semana');
    expect(container.textContent).not.toContain('No se pudo cargar');
  });

  it('shows empty state for 404 responses', async () => {
    client.get.mockRejectedValueOnce({ response: { status: 404 } });

    await act(async () => {
      root.render(<CoachDecisionsPanel athleteId={7} />);
      await flushPromises();
    });

    expect(container.textContent).toContain('Sin datos para esta semana');
    expect(container.textContent).not.toContain('No se pudo cargar');
  });
});
