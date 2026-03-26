import { useState, useMemo } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Typography, Box, CircularProgress, List, ListItem, ListItemText,
} from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { format, startOfWeek, endOfWeek, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { deleteWeek } from '../api/assignments';

function weekStart(date) { return startOfWeek(date, { weekStartsOn: 1 }); }
function weekEnd(date) { return endOfWeek(date, { weekStartsOn: 1 }); }
function formatRange(from, to) {
  return `${format(from, 'dd MMM', { locale: es })} – ${format(to, 'dd MMM yyyy', { locale: es })}`;
}

export default function DeleteWeekModal({ open, onClose, event, orgId, athleteId, onSuccess }) {
  const [saving, setSaving] = useState(false);

  const sourceDate = useMemo(() => {
    if (!event) return new Date();
    return parseISO(event.resource?.scheduled_date ?? format(event.start, 'yyyy-MM-dd'));
  }, [event]);

  const from = weekStart(sourceDate);
  const to = weekEnd(sourceDate);

  if (!event) return null;

  const resolvedAthleteId = athleteId ?? event.resource?.athlete_id ?? event.resource?.athlete;

  const handleConfirm = async () => {
    setSaving(true);
    try {
      const res = await deleteWeek(orgId, {
        athlete_id: resolvedAthleteId,
        date_from: format(from, 'yyyy-MM-dd'),
        date_to: format(to, 'yyyy-MM-dd'),
      });
      onSuccess?.(res.data);
      onClose();
    } catch {
      // error handled by caller
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <DeleteSweepIcon sx={{ color: '#ef4444' }} />
        Eliminar semana
      </DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Typography variant="body2" sx={{ color: '#94a3b8', mb: 2 }}>
          Semana del {formatRange(from, to)}
        </Typography>

        <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Se eliminarán las sesiones planificadas
        </Typography>
        <Typography variant="body2" sx={{ color: '#94a3b8', mt: 0.5, mb: 2 }}>
          Las sesiones ya completadas quedarán protegidas.
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5, bgcolor: 'rgba(239,68,68,0.07)', borderRadius: 1, border: '1px solid rgba(239,68,68,0.2)' }}>
          <CheckCircleOutlineIcon sx={{ color: '#22c55e', fontSize: 18 }} />
          <Typography variant="body2" sx={{ color: '#94a3b8' }}>
            Las sesiones completadas <strong>no</strong> se eliminarán.
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" disabled={saving}>Cancelar</Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          disabled={saving}
          sx={{ bgcolor: '#ef4444', '&:hover': { bgcolor: '#dc2626' } }}
          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : null}
        >
          Eliminar semana
        </Button>
      </DialogActions>
    </Dialog>
  );
}
