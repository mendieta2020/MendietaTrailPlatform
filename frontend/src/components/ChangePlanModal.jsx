import React, { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Box, Typography, CircularProgress, Radio,
  RadioGroup, FormControlLabel, Chip,
} from '@mui/material';
import { getAvailablePlans, changePlan } from '../api/billing';

function formatARS(value) {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency', currency: 'ARS', maximumFractionDigits: 0,
  }).format(value);
}

export default function ChangePlanModal({ open, onClose, onPlanChanged }) {
  const [plans, setPlans] = useState([]);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError('');
    setSelectedId(null);
    getAvailablePlans()
      .then(({ data }) => {
        setPlans(data.plans || []);
        setCurrentPlan(data.current_plan || null);
      })
      .catch(() => setError('No se pudieron cargar los planes.'))
      .finally(() => setLoading(false));
  }, [open]);

  const selectedPlan = plans.find(p => p.id === selectedId);
  const priceDiff = selectedPlan && currentPlan
    ? parseFloat(selectedPlan.price_ars) - parseFloat(currentPlan.price_ars)
    : null;

  const handleConfirm = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    setError('');
    try {
      const { data } = await changePlan(selectedId);
      onPlanChanged(data);
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error al cambiar el plan.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ fontWeight: 700, color: '#0F172A', pb: 0.5 }}>
        Cambiar tu plan
      </DialogTitle>

      {currentPlan && (
        <Box sx={{ px: 3, pb: 1 }}>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Tu plan actual: <strong>{currentPlan.name}</strong> ({formatARS(currentPlan.price_ars)}/mes)
          </Typography>
        </Box>
      )}

      <DialogContent sx={{ pt: 1 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={28} />
          </Box>
        ) : error ? (
          <Typography color="error" variant="body2">{error}</Typography>
        ) : (
          <RadioGroup
            value={selectedId ?? ''}
            onChange={(e) => setSelectedId(Number(e.target.value))}
          >
            {plans.map(plan => (
              <Box
                key={plan.id}
                onClick={() => !plan.is_current && setSelectedId(plan.id)}
                sx={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  p: 1.5, mb: 1, borderRadius: 2, border: '1px solid',
                  borderColor: selectedId === plan.id ? '#6366F1' : '#E2E8F0',
                  bgcolor: selectedId === plan.id ? 'rgba(99,102,241,0.04)' : '#FAFAFA',
                  cursor: plan.is_current ? 'default' : 'pointer',
                  opacity: plan.is_current ? 0.6 : 1,
                  transition: 'border-color 0.15s, background-color 0.15s',
                }}
              >
                <FormControlLabel
                  value={plan.id}
                  disabled={plan.is_current}
                  control={<Radio size="small" sx={{ color: '#6366F1', '&.Mui-checked': { color: '#6366F1' } }} />}
                  label={
                    <Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#1E293B' }}>
                          {plan.name}
                        </Typography>
                        {plan.is_current && (
                          <Chip label="Tu plan" size="small" sx={{ height: 18, fontSize: '0.65rem', bgcolor: '#E0E7FF', color: '#4338CA', fontWeight: 600 }} />
                        )}
                      </Box>
                      {plan.description && (
                        <Typography variant="caption" sx={{ color: '#64748B' }}>
                          {plan.description}
                        </Typography>
                      )}
                    </Box>
                  }
                  sx={{ m: 0, flex: 1 }}
                />
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B', whiteSpace: 'nowrap', ml: 1 }}>
                  {formatARS(plan.price_ars)}/mes
                </Typography>
              </Box>
            ))}
          </RadioGroup>
        )}

        {priceDiff !== null && priceDiff !== 0 && (
          <Box sx={{
            mt: 1.5, p: 1.5, borderRadius: 2,
            bgcolor: priceDiff < 0 ? '#F0FDF4' : '#FFF7ED',
            border: '1px solid', borderColor: priceDiff < 0 ? '#BBF7D0' : '#FED7AA',
          }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: priceDiff < 0 ? '#166534' : '#9A3412' }}>
              {priceDiff < 0
                ? `Ahorrás ${formatARS(Math.abs(priceDiff))}/mes`
                : `+${formatARS(priceDiff)}/mes`}
            </Typography>
          </Box>
        )}

        {error && !loading && (
          <Typography color="error" variant="body2" sx={{ mt: 1 }}>{error}</Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button onClick={onClose} variant="outlined" sx={{ textTransform: 'none', borderRadius: 2, color: '#64748B', borderColor: '#CBD5E1' }}>
          Cancelar
        </Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          disabled={!selectedId || submitting}
          sx={{ textTransform: 'none', borderRadius: 2, bgcolor: '#6366F1', '&:hover': { bgcolor: '#4F46E5' }, fontWeight: 600 }}
        >
          {submitting ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Confirmar cambio'}
        </Button>
      </DialogActions>

      <Box sx={{ px: 3, pb: 2 }}>
        <Typography variant="caption" sx={{ color: '#94A3B8' }}>
          El cambio se aplica inmediatamente.
        </Typography>
      </Box>
    </Dialog>
  );
}
