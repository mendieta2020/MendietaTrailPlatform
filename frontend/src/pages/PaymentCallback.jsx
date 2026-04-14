import React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Paper, Button, CircularProgress } from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

/**
 * Landing page after MercadoPago payment flow.
 * Handles ?status=approved|pending|failure query param.
 * Registered at /payment/callback (public — no auth required).
 */
export default function PaymentCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const status = params.get('status') || 'pending';

  if (status === 'approved') {
    return (
      <Box sx={overlay}>
        <Paper sx={card}>
          <CheckCircleOutlineIcon sx={{ fontSize: 56, color: '#00D4AA', mb: 2 }} />
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
            ¡Pago confirmado!
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
            Tu suscripción está activa. Ya podés ver tus entrenamientos y comunicarte con tu coach.
          </Typography>
          <Button
            variant="contained"
            fullWidth
            onClick={() => navigate('/dashboard')}
            sx={ctaGreen}
          >
            Ir a entrenar →
          </Button>
        </Paper>
      </Box>
    );
  }

  if (status === 'failure') {
    return (
      <Box sx={overlay}>
        <Paper sx={card}>
          <ErrorOutlineIcon sx={{ fontSize: 56, color: '#EF4444', mb: 2 }} />
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
            El pago no se pudo procesar
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
            Verificá los datos de tu tarjeta o método de pago e intentá de nuevo.
          </Typography>
          <Button
            variant="contained"
            fullWidth
            onClick={() => navigate('/dashboard')}
            sx={ctaRed}
          >
            Reintentar
          </Button>
        </Paper>
      </Box>
    );
  }

  // status === 'pending' or unknown
  return (
    <Box sx={overlay}>
      <Paper sx={card}>
        <HourglassEmptyIcon sx={{ fontSize: 56, color: '#F59E0B', mb: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
          Pago en proceso
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mb: 1 }}>
          Tu pago está siendo procesado. Te avisamos cuando esté listo.
        </Typography>
        <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mb: 3 }}>
          Esto puede tardar unos minutos. No cierres esta pantalla.
        </Typography>
        <CircularProgress size={24} sx={{ color: '#F59E0B', mb: 2 }} />
        <Button
          variant="outlined"
          fullWidth
          onClick={() => navigate('/dashboard')}
          sx={{ borderColor: '#CBD5E1', color: '#64748B', textTransform: 'none', borderRadius: 2, fontWeight: 600 }}
        >
          Volver al dashboard
        </Button>
      </Paper>
    </Box>
  );
}

const overlay = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  bgcolor: '#F8FAFC',
  p: 2,
};

const card = {
  p: 5,
  borderRadius: 4,
  maxWidth: 420,
  width: '100%',
  textAlign: 'center',
  boxShadow: '0 4px 24px 0 rgba(0,0,0,0.08)',
};

const ctaGreen = {
  bgcolor: '#00D4AA',
  '&:hover': { bgcolor: '#00BF99' },
  py: 1.5,
  borderRadius: 2,
  textTransform: 'none',
  fontWeight: 700,
  fontSize: '1rem',
};

const ctaRed = {
  bgcolor: '#EF4444',
  '&:hover': { bgcolor: '#DC2626' },
  py: 1.5,
  borderRadius: 2,
  textTransform: 'none',
  fontWeight: 700,
  fontSize: '1rem',
};
