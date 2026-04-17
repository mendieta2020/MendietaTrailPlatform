import React, { useState } from 'react';
import { Box, Typography, Paper, Chip, Button, CircularProgress } from '@mui/material';
import { CreditCard } from '@mui/icons-material';
import SubscriptionActionModal from './SubscriptionActionModal';

const STATUS_LABEL = {
  active:    'Al día',
  pending:   'Pendiente',
  overdue:   'Vencido',
  paused:    'Pausado',
  cancelled: 'Cancelado',
  suspended: 'Suspendido',
};

const STATUS_COLOR = {
  active:    { bg: '#DCFCE7', text: '#166534' },
  pending:   { bg: '#FEF3C7', text: '#92400E' },
  overdue:   { bg: '#FEE2E2', text: '#991B1B' },
  paused:    { bg: '#FEF3C7', text: '#92400E' },
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

export default function SubscriptionCard({ subscription, orgName, onUpdatePayment, onChangePlan, onPause, onCancel, onReactivate }) {
  const [modal, setModal] = useState(null); // 'pause' | 'cancel' | null
  const [reactivateLoading, setReactivateLoading] = useState(false);
  const [reactivateError, setReactivateError] = useState('');
  const [reactivateSuccess, setReactivateSuccess] = useState('');
  if (!subscription) return null;

  const handleReactivate = async () => {
    if (!onReactivate) return;
    setReactivateLoading(true);
    setReactivateError('');
    setReactivateSuccess('');
    try {
      const result = await onReactivate();
      if (result?.redirect_url) {
        setReactivateSuccess('Abriendo MercadoPago...');
        window.open(result.redirect_url, '_blank');
      }
    } catch (err) {
      console.error('[SubscriptionCard] reactivate error:', err);
      setReactivateError('No se pudo generar el link de pago. Contactá a tu coach.');
    } finally {
      setReactivateLoading(false);
    }
  };

  const { status, plan_name, plan_price, next_payment_at, mp_preapproval_id, trial_ends_at, paused_at, cancelled_at } = subscription;

  // BUG-9 fix: determine trial state so we don't pressure day-1 users with "Actualizar pago"
  const now = new Date();
  const trialEnd = trial_ends_at ? new Date(trial_ends_at) : null;
  const trialActive = trialEnd && trialEnd > now;
  const trialDaysLeft = trialActive
    ? Math.ceil((trialEnd - now) / (1000 * 60 * 60 * 24))
    : 0;

  // Effective status for display: show trial state instead of "pending" while trial is active
  const displayStatus = (status === 'pending' && trialActive) ? 'trial' : status;
  const trialStatusLabel =
    trialDaysLeft >= 5 ? `Trial activo — ${trialDaysLeft} días` :
    trialDaysLeft >= 3 ? 'Trial termina pronto' :
    trialDaysLeft >= 1 ? 'Último día de trial' :
    STATUS_LABEL[status] || status;
  const trialStatusColors =
    trialDaysLeft >= 5 ? { bg: '#DCFCE7', text: '#166534' } :
    trialDaysLeft >= 3 ? { bg: '#FEF3C7', text: '#92400E' } :
    { bg: '#FEE2E2', text: '#991B1B' };

  const colors = displayStatus === 'trial' ? trialStatusColors : (STATUS_COLOR[status] || STATUS_COLOR.pending);
  const statusLabel = displayStatus === 'trial' ? trialStatusLabel : (STATUS_LABEL[status] || status);
  const nextPayment = formatDate(next_payment_at);

  const handleUpdatePayment = () => {
    if (onUpdatePayment) { onUpdatePayment(); return; }
    window.alert('Contactá a tu coach para actualizar el método de pago.');
  };

  const handlePauseConfirm = async (payload) => {
    if (onPause) await onPause(payload);
    setModal(null);
  };

  const handleCancelConfirm = async (payload) => {
    if (onCancel) await onCancel(payload);
    setModal(null);
  };

  const pausedDate = paused_at ? formatDate(paused_at) : null;
  const cancelledDate = cancelled_at ? formatDate(cancelled_at) : null;

  return (
    <>
      {modal && (
        <SubscriptionActionModal
          action={modal}
          planName={plan_name}
          onConfirm={modal === 'pause' ? handlePauseConfirm : handleCancelConfirm}
          onClose={() => setModal(null)}
        />
      )}
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
                label={statusLabel}
                size="small"
                sx={{ bgcolor: colors.bg, color: colors.text, fontWeight: 600, height: 20, fontSize: '0.7rem', mt: 0.25 }}
              />
            </Box>
          </Box>

          {/* Paused state message */}
          {status === 'paused' && (
            <Typography variant="caption" sx={{ color: '#92400E', display: 'block', mb: 1.5 }}>
              Tu suscripción está pausada{pausedDate ? ` desde el ${pausedDate}` : ''}. Podés reactivarla cuando quieras.
            </Typography>
          )}

          {/* Cancelled state message */}
          {status === 'cancelled' && (
            <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 1.5 }}>
              Tu suscripción fue cancelada{cancelledDate ? ` el ${cancelledDate}` : ''}.
            </Typography>
          )}

          {/* Bottom row */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              {status === 'active' && nextPayment && (
                <Typography variant="caption" sx={{ color: '#64748B' }}>
                  Próximo pago: {nextPayment}
                </Typography>
              )}
              {mp_preapproval_id && status === 'active' && (
                <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                  Método: MercadoPago
                </Typography>
              )}
            </Box>

            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
              {/* Active state CTAs */}
              {status === 'active' && (
                <>
                  {onChangePlan && (
                    <Button size="small" variant="text" onClick={onChangePlan}
                      sx={{ color: '#6366F1', textTransform: 'none', fontWeight: 600, fontSize: '0.75rem', '&:hover': { bgcolor: 'rgba(99,102,241,0.06)' } }}>
                      Cambiar plan
                    </Button>
                  )}
                  {onPause && (
                    <Button size="small" variant="text" onClick={() => setModal('pause')}
                      sx={{ color: '#94A3B8', textTransform: 'none', fontSize: '0.72rem', '&:hover': { color: '#64748B' } }}>
                      Pausar
                    </Button>
                  )}
                  {onCancel && (
                    <Button size="small" variant="text" onClick={() => setModal('cancel')}
                      sx={{ color: '#94A3B8', textTransform: 'none', fontSize: '0.72rem', '&:hover': { color: '#EF4444' } }}>
                      Cancelar
                    </Button>
                  )}
                </>
              )}

              {/* Paused state CTAs */}
              {status === 'paused' && (
                <>
                  {onReactivate && (
                    <Button size="small" variant="contained" onClick={handleReactivate}
                      disabled={reactivateLoading}
                      sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00B899' }, textTransform: 'none', fontWeight: 700, fontSize: '0.75rem', borderRadius: 2, minWidth: 100 }}>
                      {reactivateLoading ? <CircularProgress size={14} sx={{ color: 'white' }} /> : 'Reactivar'}
                    </Button>
                  )}
                  {onCancel && (
                    <Button size="small" variant="text" onClick={() => setModal('cancel')}
                      sx={{ color: '#94A3B8', textTransform: 'none', fontSize: '0.72rem', '&:hover': { color: '#EF4444' } }}>
                      Cancelar suscripción
                    </Button>
                  )}
                </>
              )}

              {/* Cancelled state CTA */}
              {status === 'cancelled' && onReactivate && (
                <Button size="small" variant="contained" onClick={handleReactivate}
                  disabled={reactivateLoading}
                  sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00B899' }, textTransform: 'none', fontWeight: 700, fontSize: '0.75rem', borderRadius: 2, minWidth: 140 }}>
                  {reactivateLoading ? <CircularProgress size={14} sx={{ color: 'white' }} /> : 'Volver a suscribirse'}
                </Button>
              )}

              {/* Legacy payment CTAs */}
              {status === 'overdue' && (
                <Button size="small" variant="outlined" onClick={handleUpdatePayment}
                  sx={{ color: '#F59E0B', borderColor: '#F59E0B', textTransform: 'none', fontWeight: 600, fontSize: '0.75rem', '&:hover': { borderColor: '#D97706', bgcolor: 'rgba(245,158,11,0.04)' } }}>
                  Actualizar pago
                </Button>
              )}
              {status === 'pending' && trialActive && trialDaysLeft >= 3 && trialDaysLeft < 5 && (
                <Button size="small" variant="outlined" onClick={handleUpdatePayment}
                  sx={{ color: '#F59E0B', borderColor: '#F59E0B', textTransform: 'none', fontWeight: 600, fontSize: '0.75rem', '&:hover': { borderColor: '#D97706', bgcolor: 'rgba(245,158,11,0.04)' } }}>
                  Ver planes
                </Button>
              )}
              {status === 'pending' && trialActive && trialDaysLeft < 3 && (
                <Button size="small" variant="contained" onClick={handleUpdatePayment}
                  sx={{ bgcolor: '#EF4444', '&:hover': { bgcolor: '#DC2626' }, textTransform: 'none', fontWeight: 600, fontSize: '0.75rem' }}>
                  Activar plan →
                </Button>
              )}
              {status === 'pending' && !trialActive && (
                <Button size="small" variant="outlined" onClick={handleUpdatePayment}
                  sx={{ color: '#F59E0B', borderColor: '#F59E0B', textTransform: 'none', fontWeight: 600, fontSize: '0.75rem', '&:hover': { borderColor: '#D97706', bgcolor: 'rgba(245,158,11,0.04)' } }}>
                  Actualizar pago
                </Button>
              )}
            </Box>
          </Box>
          {reactivateError && (
            <Typography variant="caption" sx={{ color: '#EF4444', display: 'block', px: 2.5, pb: 1.5 }}>
              {reactivateError}
            </Typography>
          )}
          {reactivateSuccess && (
            <Typography variant="caption" sx={{ color: '#00D4AA', display: 'block', px: 2.5, pb: 1.5 }}>
              {reactivateSuccess}
            </Typography>
          )}
        </Box>
      </Paper>
    </>
  );
}
