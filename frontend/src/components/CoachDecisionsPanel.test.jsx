import React, { act } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createRoot } from 'react-dom/client';

import CoachDecisionsPanel from './CoachDecisionsPanel';

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

  it('renders weekly summary metrics', async () => {
    client.get.mockResolvedValueOnce({
      data: {
        week: '2026-W03',
        start_date: '2026-01-12',
        end_date: '2026-01-18',
        distance_km: 112,
        duration_minutes: 724,
        elevation_gain_m: 2797,
        elevation_loss_m: 300,
        elevation_total_m: 3097,
        kcal: 8500,
        sessions_count: 6,
        sessions_by_type: { RUN: 4, BIKE: 1, STRENGTH: 1 },
        compliance: {},
        alerts: [],
      },
    });

    await act(async () => {
      root.render(<CoachDecisionsPanel athleteId={7} />);
      await flushPromises();
    });

    expect(container.textContent).toContain('112 km');
    expect(container.textContent).toContain('12h 4m');
    expect(container.textContent).toContain('Elev -');
    expect(container.textContent).toContain('Sesiones');
    expect(container.textContent).toContain('RUN: 4');
  });

  it('renders zero state without error', async () => {
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

    expect(container.textContent).toContain('0 km');
    expect(container.textContent).toContain('0h 0m');
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
