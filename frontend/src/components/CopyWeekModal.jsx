import { useState, useMemo } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, FormControl, InputLabel, Select, MenuItem,
  Typography, Box, IconButton, CircularProgress,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { format, startOfWeek, endOfWeek, addWeeks, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { copyWeek } from '../api/assignments';

function weekStart(date) {
  return startOfWeek(date, { weekStartsOn: 1 });
}
function weekEnd(date) {
  return endOfWeek(date, { weekStartsOn: 1 });
}

export default function CopyWeekModal({ open, onClose, sourceEvent, athletes, orgId, onSuccess }) {
  const [targetAthleteId, setTargetAthleteId] = useState('same');
  const [targetWeekOffset, setTargetWeekOffset] = useState(1);
  const [saving, setSaving] = useState(false);

  const sourceDate = useMemo(() => {
    if (!sourceEvent) return new Date();
    return parseISO(sourceEvent.resource?.scheduled_date ?? format(sourceEvent.start, 'yyyy-MM-dd'));
  }, [sourceEvent]);

  const srcFrom = weekStart(sourceDate);
  const srcTo = weekEnd(sourceDate);

  const targetBase = addWeeks(weekStart(sourceDate), targetWeekOffset);
  const targetEnd = weekEnd(targetBase);

  const formatRange = (from, to) =>
    `${format(from, 'dd MMM', { locale: es })} – ${format(to, 'dd MMM yyyy', { locale: es })}`;

  if (!sourceEvent) return null;

  const handleConfirm = async () => {
    setSaving(true);
    try {
      const resolvedAthleteId =
        targetAthleteId === 'same'
          ? (sourceEvent.resource?.athlete_id ?? sourceEvent.resource?.athlete)
          : Number(targetAthleteId);

      const sourceAthleteId =
        sourceEvent.resource?.athlete_id ?? sourceEvent.resource?.athlete;

      await copyWeek(orgId, {
        source_athlete_id: sourceAthleteId,
        source_date_from: format(srcFrom, 'yyyy-MM-dd'),
        source_date_to: format(srcTo, 'yyyy-MM-dd'),
        target_athlete_id: resolvedAthleteId,
        target_week_start: format(targetBase, 'yyyy-MM-dd'),
      });

      onSuccess?.({ targetAthleteId: resolvedAthleteId, targetWeekStart: format(targetBase, 'yyyy-MM-dd') });
      onClose();
    } catch {
      // error handled by caller
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Copiar semana</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <Box sx={{ bgcolor: 'rgba(245,124,0,0.08)', borderRadius: 1, px: 2, py: 1 }}>
          <Typography variant="caption" sx={{ color: '#94a3b8' }}>Origen</Typography>
          <Typography variant="body2" fontWeight={600}>
            {formatRange(srcFrom, srcTo)}
          </Typography>
        </Box>

        <FormControl size="small" fullWidth>
          <InputLabel>Destino — Atleta</InputLabel>
          <Select
            value={targetAthleteId}
            label="Destino — Atleta"
            onChange={(e) => setTargetAthleteId(e.target.value)}
          >
            <MenuItem value="same">Mismo atleta</MenuItem>
            {(athletes ?? []).map((a) => {
              const name = [a.first_name, a.last_name].filter(Boolean).join(' ')
                || a.email?.split('@')[0]
                || `Atleta #${a.id}`;
              return <MenuItem key={a.id} value={a.id}>{name}</MenuItem>;
            })}
          </Select>
        </FormControl>

        <Box>
          <Typography variant="caption" sx={{ color: '#94a3b8', mb: 0.5, display: 'block' }}>
            Destino — Semana
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <IconButton size="small" onClick={() => setTargetWeekOffset((n) => n - 1)}>
              <ChevronLeftIcon />
            </IconButton>
            <Typography variant="body2" sx={{ flex: 1, textAlign: 'center', fontWeight: 600 }}>
              {formatRange(targetBase, targetEnd)}
            </Typography>
            <IconButton size="small" onClick={() => setTargetWeekOffset((n) => n + 1)}>
              <ChevronRightIcon />
            </IconButton>
          </Box>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" disabled={saving}>Cancelar</Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          disabled={saving}
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65c00' } }}
          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : null}
        >
          Pegar semana
        </Button>
      </DialogActions>
    </Dialog>
  );
}
