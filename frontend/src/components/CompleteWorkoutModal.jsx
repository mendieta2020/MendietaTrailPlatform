/**
 * CompleteWorkoutModal.jsx
 *
 * PR-145d: Modal for athlete to log actual execution data when marking
 * a workout as completed.
 *
 * Fields:
 *   - Actual duration (hours + minutes)
 *   - Actual distance (km)
 *   - Actual elevation gain D+ (optional)
 *   - RPE 1–5 (emoji selector)
 *   - Nota para el coach (athlete_notes) — optional free-text
 *     When non-empty, the backend sends it as an InternalMessage to the coach
 *     with a deep-link to this session.
 *
 * If the assignment already has actual_duration_seconds (e.g. from Strava),
 * those fields are pre-filled and disabled — only RPE + note are requested.
 *
 * Props:
 *   open       {boolean}
 *   onClose    {() => void}
 *   onSubmit   {(data: object) => Promise<void>}
 *   assignment {object} — WorkoutAssignment
 */

import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Typography, Button, TextField, CircularProgress,
} from '@mui/material';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

const RPE_OPTIONS = [
  { value: 1, emoji: '😴', label: 'Muy fácil' },
  { value: 2, emoji: '😐', label: 'Fácil' },
  { value: 3, emoji: '🙂', label: 'Moderado' },
  { value: 4, emoji: '💪', label: 'Duro' },
  { value: 5, emoji: '🔥', label: 'Máximo' },
];

function secsToHm(seconds) {
  if (!seconds) return { h: '', m: '' };
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return { h: h > 0 ? String(h) : '', m: m > 0 ? String(m) : '' };
}

function metersToKm(meters) {
  if (!meters) return '';
  return String((meters / 1000).toFixed(2));
}

export function CompleteWorkoutModal({ open, onClose, onSubmit, assignment }) {
  const hasDeviceData = Boolean(assignment?.actual_duration_seconds);

  const [hours, setHours] = useState('');
  const [minutes, setMinutes] = useState('');
  const [distanceKm, setDistanceKm] = useState('');
  const [elevationM, setElevationM] = useState('');
  const [rpe, setRpe] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Pre-fill when modal opens
  useEffect(() => {
    if (!open || !assignment) return;
    if (hasDeviceData) {
      const { h, m } = secsToHm(assignment.actual_duration_seconds);
      setHours(h);
      setMinutes(m);
      setDistanceKm(metersToKm(assignment.actual_distance_meters));
      setElevationM(assignment.actual_elevation_gain ? String(assignment.actual_elevation_gain) : '');
    } else {
      setHours('');
      setMinutes('');
      setDistanceKm('');
      setElevationM('');
    }
    setRpe(assignment.rpe ?? null);
    setNoteText(assignment.athlete_notes ?? '');
    setError('');
  }, [open, assignment, hasDeviceData]);

  const handleSubmit = async () => {
    setSaving(true);
    setError('');
    try {
      const h = parseInt(hours || '0', 10);
      const m = parseInt(minutes || '0', 10);
      const durationSecs = h * 3600 + m * 60;
      const distanceMeters = distanceKm ? Math.round(parseFloat(distanceKm) * 1000) : null;
      const elevation = elevationM ? parseInt(elevationM, 10) : null;

      await onSubmit({
        status: 'completed',
        actual_duration_seconds: durationSecs > 0 ? durationSecs : null,
        actual_distance_meters: distanceMeters || null,
        actual_elevation_gain: elevation,
        rpe: rpe,
        athlete_notes: noteText.trim() || '',
      });
      onClose();
    } catch {
      setError('Error al guardar. Intenta de nuevo.');
    } finally {
      setSaving(false);
    }
  };

  if (!assignment) return null;

  const pw = assignment.planned_workout;
  const title = pw?.name ?? 'Entrenamiento';
  let dateLabel = '';
  try {
    dateLabel = format(parseISO(assignment.scheduled_date), "d 'de' MMMM", { locale: es });
  } catch {
    dateLabel = assignment.scheduled_date ?? '';
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A' }}>
          ¿Cómo fue tu sesión?
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mt: 0.25 }}>
          {title} · {dateLabel}
        </Typography>
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        {/* Duration */}
        <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, display: 'block', mb: 0.5 }}>
          Tiempo real
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <TextField
            label="Horas"
            type="number"
            size="small"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            disabled={hasDeviceData}
            inputProps={{ min: 0, max: 24 }}
            sx={{ width: 90 }}
          />
          <TextField
            label="Minutos"
            type="number"
            size="small"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            disabled={hasDeviceData}
            inputProps={{ min: 0, max: 59 }}
            sx={{ width: 100 }}
          />
          {hasDeviceData && (
            <Typography variant="caption" sx={{ color: '#94A3B8', alignSelf: 'center', fontStyle: 'italic' }}>
              Desde dispositivo
            </Typography>
          )}
        </Box>

        {/* Distance */}
        <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, display: 'block', mb: 0.5 }}>
          Distancia real
        </Typography>
        <TextField
          label="km"
          type="number"
          size="small"
          fullWidth
          value={distanceKm}
          onChange={(e) => setDistanceKm(e.target.value)}
          disabled={hasDeviceData}
          inputProps={{ min: 0, step: 0.1 }}
          sx={{ mb: 2 }}
        />

        {/* Elevation */}
        <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, display: 'block', mb: 0.5 }}>
          D+ real <span style={{ fontWeight: 400, color: '#94A3B8' }}>(opcional)</span>
        </Typography>
        <TextField
          label="metros"
          type="number"
          size="small"
          fullWidth
          value={elevationM}
          onChange={(e) => setElevationM(e.target.value)}
          disabled={hasDeviceData}
          placeholder="Opcional"
          inputProps={{ min: 0 }}
          sx={{ mb: 2 }}
        />

        {/* RPE */}
        <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, display: 'block', mb: 1 }}>
          ¿Cómo te sentiste?
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
          {RPE_OPTIONS.map(({ value, emoji, label }) => (
            <Button
              key={value}
              variant={rpe === value ? 'contained' : 'outlined'}
              size="small"
              title={label}
              onClick={() => setRpe(rpe === value ? null : value)}
              sx={{
                minWidth: 44,
                height: 44,
                fontSize: '1.3rem',
                p: 0,
                borderColor: rpe === value ? '#f97316' : '#e2e8f0',
                bgcolor: rpe === value ? '#f97316' : 'transparent',
                '&:hover': { bgcolor: rpe === value ? '#ea6c0a' : '#f8fafc' },
              }}
            >
              {emoji}
            </Button>
          ))}
        </Box>

        {/* Note to coach */}
        <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, display: 'block', mt: 2, mb: 0.5 }}>
          Nota para tu coach <span style={{ fontWeight: 400, color: '#94A3B8' }}>(opcional)</span>
        </Typography>
        <TextField
          fullWidth
          multiline
          minRows={2}
          maxRows={4}
          size="small"
          placeholder="¿Algo que quieras contarle a tu coach sobre esta sesión?"
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          sx={{
            '& .MuiOutlinedInput-root': {
              fontSize: '0.83rem',
              borderRadius: 2,
              '&.Mui-focused fieldset': { borderColor: '#f97316' },
            },
          }}
        />

        {noteText.trim() && (
          <Typography variant="caption" sx={{ color: '#f97316', fontWeight: 600, display: 'block', mt: 0.5 }}>
            💬 Tu nota llegará al coach con un link directo a esta sesión
          </Typography>
        )}

        {error && (
          <Typography variant="caption" sx={{ color: '#dc2626', display: 'block', mt: 1 }}>
            {error}
          </Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} color="inherit" disabled={saving}>
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={saving}
          sx={{ bgcolor: '#f97316', '&:hover': { bgcolor: '#ea6c0a' } }}
          endIcon={saving ? <CircularProgress size={14} color="inherit" /> : null}
        >
          Guardar sesión →
        </Button>
      </DialogActions>
    </Dialog>
  );
}
