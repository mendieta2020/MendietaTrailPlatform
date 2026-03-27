import { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, FormControl, InputLabel, Select, MenuItem, TextField,
  Typography, Box,
} from '@mui/material';

export default function DuplicateSessionModal({ open, onClose, assignment, athletes, onConfirm }) {
  const [targetAthleteId, setTargetAthleteId] = useState('same');
  const [targetDate, setTargetDate] = useState('');

  if (!assignment) return null;

  const workoutName = assignment.planned_workout?.name ?? assignment.title ?? 'Entrenamiento';

  const handleConfirm = () => {
    const athleteId = targetAthleteId === 'same' ? assignment.resource?.athlete_id : Number(targetAthleteId);
    onConfirm({ targetAthleteId: athleteId, targetDate });
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Duplicar sesión</DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
        <Box sx={{ bgcolor: 'rgba(245,124,0,0.08)', borderRadius: 1, px: 2, py: 1 }}>
          <Typography variant="body2" sx={{ color: '#F57C00', fontWeight: 600 }}>
            {workoutName}
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
              return (
                <MenuItem key={a.id} value={a.id}>{name}</MenuItem>
              );
            })}
          </Select>
        </FormControl>

        <TextField
          label="Destino — Fecha"
          type="date"
          size="small"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          fullWidth
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit">Cancelar</Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          disabled={!targetDate}
          sx={{ bgcolor: '#F57C00', '&:hover': { bgcolor: '#e65c00' } }}
        >
          Duplicar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
