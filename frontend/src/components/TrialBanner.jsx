import React from 'react';
import { Box, Typography, Button, LinearProgress, Paper } from '@mui/material';

/**
 * Shows a yellow banner when trial has < 5 days remaining.
 * Hidden when trial is expired (TrialPaywall handles that case).
 * Hidden when subscription is active.
 */
export default function TrialBanner({ trialEndsAt, status }) {
  if (!trialEndsAt) return null;
  if (status === 'active') return null;

  const now = new Date();
  const end = new Date(trialEndsAt);
  const msRemaining = end - now;

  if (msRemaining <= 0) return null; // Expired — let TrialPaywall handle it

  const daysLeft = Math.ceil(msRemaining / (1000 * 60 * 60 * 24));
  if (daysLeft > 5) return null; // Only show warning when close

  const progress = ((7 - daysLeft) / 7) * 100;

  return (
    <Paper
      sx={{
        mb: 3, p: 2.5, borderRadius: 3,
        background: 'linear-gradient(135deg, #FEF3C7 0%, #FFFBEB 100%)',
        border: '1px solid #FCD34D',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 700, color: '#92400E' }}>
          ⏳ Tu prueba termina en {daysLeft} día{daysLeft !== 1 ? 's' : ''}
        </Typography>
        <Button
          variant="contained"
          size="small"
          onClick={async () => {
            try {
              const { getPaymentLink } = await import('../api/athlete');
              const { data } = await getPaymentLink();
              if (data.init_point) window.location.href = data.init_point;
            } catch {
              window.alert('Contactá a tu coach para activar tu plan.');
            }
          }}
          sx={{
            bgcolor: '#F59E0B', '&:hover': { bgcolor: '#D97706' },
            borderRadius: 2, textTransform: 'none', fontWeight: 600, fontSize: '0.8rem',
          }}
        >
          Activar plan →
        </Button>
      </Box>
      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{
          height: 6, borderRadius: 3,
          bgcolor: '#FDE68A',
          '& .MuiLinearProgress-bar': { bgcolor: '#F59E0B', borderRadius: 3 },
        }}
      />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
        <Typography variant="caption" sx={{ color: '#B45309' }}>Día 1</Typography>
        <Typography variant="caption" sx={{ color: '#B45309' }}>Día 7</Typography>
      </Box>
    </Paper>
  );
}
