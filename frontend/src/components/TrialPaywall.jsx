import React from 'react';
import { Box, Typography, Paper, Button } from '@mui/material';

/**
 * Full-page overlay shown when the trial has expired and subscription is NOT active.
 * Blocks all interaction behind a blurred overlay.
 */
export default function TrialPaywall({ trialEndsAt, status, planName, planPrice, coachName, mpPreapprovalId }) {
  if (!trialEndsAt) return null;
  if (status === 'active') return null;

  const expired = new Date(trialEndsAt) < new Date();
  if (!expired) return null;

  const formattedPrice = planPrice
    ? new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(planPrice)
    : null;

  const handleActivate = async () => {
    if (mpPreapprovalId) {
      try {
        const { getPaymentLink } = await import('../api/athlete');
        const { data } = await getPaymentLink();
        if (data.init_point) { window.location.href = data.init_point; return; }
      } catch {
        // fall through
      }
    }
    window.alert('Contactá a tu coach para activar tu suscripción.');
  };

  return (
    <Box
      sx={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        bgcolor: 'rgba(15, 23, 42, 0.85)', backdropFilter: 'blur(8px)',
        zIndex: 1300, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
      }}
    >
      <Paper sx={{ p: 5, borderRadius: 4, maxWidth: 440, width: '100%', textAlign: 'center' }}>
        <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>💪</Typography>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
          Tu prueba gratuita terminó
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
          Tus datos y progreso están guardados. Activá tu plan para seguir recibiendo
          entrenamientos personalizados{coachName ? ` de ${coachName}` : ''}.
        </Typography>

        {planName && (
          <Box
            sx={{
              mb: 3, p: 2.5, borderRadius: 2,
              bgcolor: '#F8FAFC', border: '1px solid #E2E8F0',
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
              {planName}
            </Typography>
            {formattedPrice && (
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#00D4AA', mt: 0.5 }}>
                {formattedPrice}
                <Typography component="span" variant="caption" sx={{ color: '#94A3B8' }}>/mes</Typography>
              </Typography>
            )}
          </Box>
        )}

        <Button
          variant="contained"
          fullWidth
          onClick={handleActivate}
          sx={{
            bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00BF99' },
            py: 1.5, borderRadius: 2, textTransform: 'none', fontWeight: 700, fontSize: '1rem',
          }}
        >
          Activar suscripción con MercadoPago
        </Button>
        <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mt: 1.5 }}>
          Podés cancelar en cualquier momento
        </Typography>
      </Paper>
    </Box>
  );
}
