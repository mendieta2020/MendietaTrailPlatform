/* eslint-disable react-refresh/only-export-components */
/**
 * PR-168a: SubscriptionContext
 *
 * Single source of truth for the athlete's subscription status.
 * Fetches /api/athlete/subscription/ and computes an effective
 * subscriptionStatus string used by VisibilityGate.
 *
 * Status values:
 *   "active"        — paid subscription, full access
 *   "trial"         — trial period still valid, full access
 *   "paused"        — paused, limited access
 *   "cancelled"     — cancelled, hard paywall
 *   "trial_expired" — trial ended without active sub, hard paywall
 *   "none"          — no subscription record, hard paywall
 *   "loading"       — data not yet fetched
 *   "unknown"       — not an athlete or fetch error (no gate applied)
 */
import { createContext, useState, useEffect, useContext, useCallback } from 'react';
import { getMySubscription } from '../api/billing';
import { useAuth } from './AuthContext';

const SubscriptionContext = createContext(null);

/**
 * Derive the effective visibility status from /api/athlete/subscription/ response.
 */
function deriveStatus(data) {
  if (!data) return 'unknown';
  if (!data.has_subscription) return 'none';

  const { status, trial_active, trial_ends_at } = data;

  if (status === 'active') return 'active';
  if (status === 'paused') return 'paused';
  if (status === 'cancelled') return 'cancelled';

  // pending / overdue / suspended — check trial
  if (trial_active) return 'trial';

  // trial_ends_at in the past or absent
  if (trial_ends_at && new Date(trial_ends_at) > new Date()) return 'trial';

  return 'trial_expired';
}

export const SubscriptionProvider = ({ children }) => {
  const { user } = useAuth();
  const isAthlete = user?.role === 'athlete';

  // Non-athletes start as 'unknown' (no gate); athletes start as 'loading'
  const [subscriptionData, setSubscriptionData] = useState(null);
  const [subscriptionStatus, setSubscriptionStatus] = useState(
    isAthlete ? 'loading' : 'unknown'
  );

  // Exposed so callers can force a refresh (e.g. after MP payment return)
  const refresh = useCallback(() => {
    if (!isAthlete) return;
    return getMySubscription()
      .then(({ data }) => {
        setSubscriptionData(data);
        setSubscriptionStatus(deriveStatus(data));
      })
      .catch(() => {
        setSubscriptionStatus('unknown');
      });
  }, [isAthlete]);

  useEffect(() => {
    if (!isAthlete) return;
    let cancelled = false;
    getMySubscription()
      .then(({ data }) => {
        if (cancelled) return;
        setSubscriptionData(data);
        setSubscriptionStatus(deriveStatus(data));
      })
      .catch(() => {
        if (!cancelled) setSubscriptionStatus('unknown');
      });
    return () => { cancelled = true; };
  }, [isAthlete]);

  const value = {
    subscriptionStatus,
    subscriptionData,
    refresh,
    // Convenience booleans
    isActive: subscriptionStatus === 'active' || subscriptionStatus === 'trial',
    isPaused: subscriptionStatus === 'paused',
    isPaywalled: ['cancelled', 'trial_expired', 'none'].includes(subscriptionStatus),
  };

  return (
    <SubscriptionContext.Provider value={value}>
      {children}
    </SubscriptionContext.Provider>
  );
};

export const useSubscription = () => {
  const ctx = useContext(SubscriptionContext);
  if (!ctx) throw new Error('useSubscription must be used inside SubscriptionProvider');
  return ctx;
};
