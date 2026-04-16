import React, { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Typography, Box, Radio, RadioGroup,
  FormControlLabel, TextField, Divider,
} from '@mui/material';

const PAUSE_OPTIONS = [
  { value: 'injury',   label: '🤕 Estoy lesionado/a' },
  { value: 'vacation', label: '🏖️ Me voy de vacaciones' },
  { value: 'financial',label: '💰 Razones económicas' },
  { value: 'time',     label: '⏰ No tengo tiempo' },
  { value: 'other',    label: 'Otro motivo' },
];

const CANCEL_OPTIONS = [
  { value: 'price',      label: '💰 El precio es muy alto' },
  { value: 'injury',     label: '🤕 Estoy lesionado/a' },
  { value: 'time',       label: '⏰ No tengo tiempo' },
  { value: 'other_coach',label: '🏃 Cambié de entrenador' },
  { value: 'not_using',  label: '📱 No uso la app' },
  { value: 'other',      label: 'Otro motivo' },
];

export default function SubscriptionActionModal({ action, planName, onConfirm, onClose }) {
  const [reason, setReason] = useState('');
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const isPause = action === 'pause';
  const options = isPause ? PAUSE_OPTIONS : CANCEL_OPTIONS;
  const title = isPause ? '¿Por qué querés pausar?' : '¿Por qué querés cancelar?';
  const confirmLabel = isPause ? 'Pausar suscripción' : 'Cancelar suscripción';
  const confirmColor = isPause ? '#F59E0B' : '#EF4444';
  const confirmHover = isPause ? '#D97706' : '#DC2626';

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await onConfirm({ reason, comment });
      setConfirmed(true);
    } catch {
      // parent handles error display
    } finally {
      setLoading(false);
    }
  };

  if (confirmed) {
    return (
      <Dialog open onClose={onClose} PaperProps={{ sx: { borderRadius: 3, maxWidth: 420 } }}>
        <DialogContent sx={{ textAlign: 'center', py: 4, px: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
            {isPause ? '⏸️ Suscripción pausada' : '✅ Suscripción cancelada'}
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>
            Entendemos. Siempre podés volver cuando quieras.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ justifyContent: 'center', pb: 3 }}>
          <Button onClick={onClose} variant="contained" sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00B899' }, textTransform: 'none', borderRadius: 2 }}>
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <Dialog open onClose={onClose} PaperProps={{ sx: { borderRadius: 3, maxWidth: 440, width: '100%' } }}>
      <DialogTitle sx={{ fontWeight: 700, color: '#1E293B', pb: 1 }}>
        {title}
      </DialogTitle>
      {planName && (
        <Box sx={{ px: 3, pb: 1 }}>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            Plan: <strong>{planName}</strong>
          </Typography>
        </Box>
      )}
      <Divider />
      <DialogContent sx={{ pt: 2 }}>
        <RadioGroup value={reason} onChange={(e) => setReason(e.target.value)}>
          {options.map((opt) => (
            <FormControlLabel
              key={opt.value}
              value={opt.value}
              control={<Radio size="small" sx={{ color: '#94A3B8', '&.Mui-checked': { color: '#6366F1' } }} />}
              label={<Typography variant="body2" sx={{ color: '#1E293B' }}>{opt.label}</Typography>}
              sx={{ mb: 0.5 }}
            />
          ))}
        </RadioGroup>
        {reason === 'other' && (
          <TextField
            multiline
            rows={2}
            fullWidth
            placeholder="Contanos un poco más (opcional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            size="small"
            sx={{ mt: 1.5 }}
            inputProps={{ maxLength: 300 }}
          />
        )}
      </DialogContent>
      <Divider />
      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <Button
          onClick={onClose}
          variant="text"
          sx={{ color: '#64748B', textTransform: 'none', fontWeight: 600 }}
          disabled={loading}
        >
          Volver
        </Button>
        <Button
          onClick={handleConfirm}
          disabled={!reason || loading}
          variant="contained"
          sx={{
            bgcolor: confirmColor,
            '&:hover': { bgcolor: confirmHover },
            textTransform: 'none',
            fontWeight: 700,
            borderRadius: 2,
          }}
        >
          {loading ? 'Procesando...' : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
