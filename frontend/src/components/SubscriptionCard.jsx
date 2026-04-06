import React from 'react';
import { Box, Typography, Paper, Chip, Button } from '@mui/material';
import { CreditCard } from '@mui/icons-material';

const STATUS_LABEL = {
  active: 'Al día',
  pending: 'Pendiente',
  overdue: 'Vencido',
  cancelled: 'Cancelado',
  suspended: 'Suspendido',
};

const STATUS_COLOR = {
  active:    { bg: '#DCFCE7', text: '#166534' },
  pending:   { bg: '#FEF3C7', text: '#92400E' },
  overdue:   { bg: '#FEE2E2', text: '#991B1B' },
  cancelled: { bg: '#F1F5F9', text: '#64748B' },
  suspended: { bg: '#F1F5F9', text: '#64748B' },
};

function formatARS(value) {
  if (!value) return '—';
  return new Intl.NumberFormat('es-AR', {
    style: 'currency', currency: 'ARS', maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function SubscriptionCard({ subscription, orgName, onUpdatePayment }) {
  if (!subscription) return null;

  const { status, plan_name, plan_price, next_payment_at, mp_preapproval_id } = subscription;
  const colors = STATUS_COLOR[status] || STATUS_COLOR.pending;
  const nextPayment = formatDate(next_payment_at);

  const handleUpdatePayment = () => {
    if (onUpdatePayment) { onUpdatePayment(); return; }
    window.alert('Contactá a tu coach para actualizar el método de pago.');
  };

  return (
    <Paper
      sx={{
        mb: 2, borderRadius: 3,
        border: '1px solid', borderColor: 'divider',
        borderLeft: '4px solid #00D4AA',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
      }}
    >
      <Box sx={{ p: 2.5 }}>
        {/* Top row: plan + status */}
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1.5 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.25 }}>
              <CreditCard sx={{ color: '#00D4AA', fontSize: 18 }} />
              <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
                {plan_name || 'Mi suscripción'}
              </Typography>
            </Box>
            {orgName && (
              <Typography variant="caption" sx={{ color: '#64748B', pl: 3.25 }}>
                {orgName}
              </Typography>
            )}
          </Box>
          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
              {formatARS(plan_price)}
              <Typography component="span" variant="caption" sx={{ color: '#94A3B8' }}>/mes</Typography>
            </Typography>
            <Chip
              label={STATUS_LABEL[status] || status}
              size="small"
              sx={{ bgcolor: colors.bg, color: colors.text, fontWeight: 600, height: 20, fontSize: '0.7rem', mt: 0.25 }}
            />
          </Box>
        </Box>

        {/* Bottom row */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', gap: 2 }}>
            {nextPayment && (
              <Typography variant="caption" sx={{ color: '#64748B' }}>
                Próximo pago: {nextPayment}
              </Typography>
            )}
            {mp_preapproval_id && (
              <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                Método: MercadoPago
              </Typography>
            )}
          </Box>
          {(status === 'overdue' || status === 'pending') && (
            <Button
              size="small"
              variant="outlined"
              onClick={handleUpdatePayment}
              sx={{
                color: '#F59E0B', borderColor: '#F59E0B', textTransform: 'none',
                fontWeight: 600, fontSize: '0.75rem',
                '&:hover': { borderColor: '#D97706', bgcolor: 'rgba(245,158,11,0.04)' },
              }}
            >
              Actualizar pago
            </Button>
          )}
        </Box>
      </Box>
    </Paper>
  );
}
