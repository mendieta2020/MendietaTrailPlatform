/**
 * PR-168a: VisibilityGate
 *
 * Wraps content that requires an active or limited subscription.
 * Renders a PaywallOverlay when the athlete's subscription status
 * blocks access.
 *
 * Props:
 *   requiredAccess: "full" | "limited" | "any"
 *     - "full"    → visible only for active/trial
 *     - "limited" → visible for active/trial/paused
 *     - "any"     → always visible (skips gate)
 *
 *   pausedLabel: string (optional) — badge shown for paused athletes on "limited" content
 *   paywallMessage: string (optional) — override default paywall subtitle
 */
import React, { useState, useEffect } from 'react';
import { Box, Typography, Button, CircularProgress } from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import { useSubscription } from '../context/SubscriptionContext';
import { reactivateMySubscription } from '../api/billing';

// Access matrix
// "full"    → active, trial only
// "limited" → active, trial, paused
// "any"     → no gate
const FULL_ACCESS_STATUSES = new Set(['active', 'trial', 'none']);
const LIMITED_ACCESS_STATUSES = new Set(['active', 'trial', 'paused', 'none']);

function canAccess(status, requiredAccess) {
  if (requiredAccess === 'any') return true;
  if (requiredAccess === 'limited') return LIMITED_ACCESS_STATUSES.has(status);
  // default: "full"
  return FULL_ACCESS_STATUSES.has(status);
}

const PaywallOverlay = ({ message }) => {
  const { refresh } = useSubscription();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Refresh subscription when user returns to tab (e.g. after completing MP payment)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        refresh();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [refresh]);

  const handleActivate = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await reactivateMySubscription();
      // Always refresh context so paywall updates immediately
      await refresh();
      if (data?.redirect_url) {
        window.open(data.redirect_url, '_blank');
      }
    } catch (err) {
      console.error('[PaywallOverlay] reactivate error:', err);
      setError('No se pudo generar el link de pago. Contactá a tu coach.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        position: 'relative',
        minHeight: 220,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 3,
        overflow: 'hidden',
        background: 'linear-gradient(135deg, rgba(15,23,42,0.92) 0%, rgba(30,41,59,0.88) 100%)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255,255,255,0.08)',
        p: 4,
      }}
    >
      <Box sx={{ textAlign: 'center', maxWidth: 340 }}>
        <Box
          sx={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            bgcolor: 'rgba(99,102,241,0.15)',
            border: '1px solid rgba(99,102,241,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 2,
          }}
        >
          <LockIcon sx={{ color: '#818CF8', fontSize: 28 }} />
        </Box>

        <Typography
          variant="subtitle1"
          sx={{ fontWeight: 700, color: '#F1F5F9', mb: 1 }}
        >
          Contenido exclusivo para suscriptores
        </Typography>

        <Typography
          variant="body2"
          sx={{ color: '#94A3B8', mb: 3, lineHeight: 1.6 }}
        >
          {message || 'Activá tu plan para acceder a entrenamientos, progreso y más.'}
        </Typography>

        <Button
          variant="contained"
          size="small"
          onClick={handleActivate}
          disabled={loading}
          sx={{
            bgcolor: '#6366F1',
            '&:hover': { bgcolor: '#4F46E5' },
            borderRadius: 2,
            textTransform: 'none',
            fontWeight: 700,
            px: 3,
            py: 1,
            minWidth: 140,
          }}
        >
          {loading ? <CircularProgress size={16} sx={{ color: 'white' }} /> : 'Activá tu plan'}
        </Button>

        {error && (
          <Typography variant="caption" sx={{ color: '#FCA5A5', mt: 1.5, display: 'block' }}>
            {error}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

const PausedBadge = ({ label }) => (
  <Box
    sx={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 0.5,
      px: 1.5,
      py: 0.5,
      borderRadius: 2,
      bgcolor: '#FEF3C7',
      border: '1px solid #FDE68A',
      mb: 1.5,
    }}
  >
    <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600 }}>
      {label || '⏸️ Suscripción pausada — solo lectura'}
    </Typography>
  </Box>
);

const VisibilityGate = ({
  requiredAccess = 'full',
  children,
  pausedLabel,
  paywallMessage,
}) => {
  const { subscriptionStatus } = useSubscription();

  // While loading or for non-athletes, always render children (no gate)
  if (subscriptionStatus === 'loading' || subscriptionStatus === 'unknown') {
    return children;
  }

  if (!canAccess(subscriptionStatus, requiredAccess)) {
    return <PaywallOverlay message={paywallMessage} />;
  }

  // Paused + limited access: render children with a read-only badge
  if (subscriptionStatus === 'paused' && requiredAccess === 'limited') {
    return (
      <Box>
        <PausedBadge label={pausedLabel} />
        {children}
      </Box>
    );
  }

  return children;
};

export default VisibilityGate;
