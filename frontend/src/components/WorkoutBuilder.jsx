import React, { useState, useCallback } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, MenuItem, Box, Typography, Divider,
  IconButton, Chip, CircularProgress, Alert, Collapse,
  Paper, Tooltip,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  DragHandle as DragHandleIcon,
  FitnessCenter as FitnessCenterIcon,
} from '@mui/icons-material';
import {
  createPlannedWorkout,
  createWorkoutBlock,
  createWorkoutInterval,
} from '../api/p1';

const SPORT_OPTIONS = [
  { value: 'TRAIL', label: 'Trail Running' },
  { value: 'RUN', label: 'Running' },
  { value: 'BIKE', label: 'Ciclismo' },
  { value: 'WALK', label: 'Caminata' },
  { value: 'STRENGTH', label: 'Fuerza / Funcional' },
  { value: 'OTHER', label: 'Otro' },
];

const DIFFICULTY_OPTIONS = [
  { value: 'EASY', label: 'Fácil', color: '#22c55e' },
  { value: 'MODERATE', label: 'Moderado', color: '#f59e0b' },
  { value: 'HARD', label: 'Difícil', color: '#ef4444' },
  { value: 'VERY_HARD', label: 'Muy Difícil', color: '#7c3aed' },
];

const BLOCK_TYPES = [
  { value: 'WARMUP', label: 'Calentamiento', color: '#fb923c' },
  { value: 'ACTIVE', label: 'Bloque Principal', color: '#3b82f6' },
  { value: 'COOLDOWN', label: 'Enfriamiento', color: '#a3e635' },
  { value: 'REST', label: 'Descanso', color: '#94a3b8' },
  { value: 'TRANSITION', label: 'Transición', color: '#c084fc' },
];

const INTENSITY_TYPES = [
  { value: 'RPE', label: 'RPE (1–10)' },
  { value: 'HR_ZONE', label: 'Zona FC (Z1–Z5)' },
  { value: 'PACE', label: 'Ritmo (min/km)' },
  { value: 'POWER', label: 'Vatios' },
  { value: 'OPEN', label: 'Libre' },
];

const emptyInterval = () => ({
  name: '',
  duration_seconds: '',
  distance_meters: '',
  intensity_type: 'RPE',
  intensity_value: '',
  rest_duration_seconds: '',
  repetitions: 1,
});

const emptyBlock = (order) => ({
  name: '',
  block_type: 'ACTIVE',
  order,
  open: true,
  intervals: [emptyInterval()],
});

const INITIAL_FORM = {
  name: '',
  description: '',
  sport_type: 'TRAIL',
  difficulty: 'MODERATE',
  estimated_duration_minutes: '',
  estimated_distance_km: '',
  notes: '',
};

export default function WorkoutBuilder({ open, onClose, orgId, libraryId, onSaved }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [blocks, setBlocks] = useState([emptyBlock(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const resetState = useCallback(() => {
    setForm(INITIAL_FORM);
    setBlocks([emptyBlock(1)]);
    setSaving(false);
    setError('');
  }, []);

  const handleClose = () => {
    resetState();
    onClose();
  };

  // ── Form field helpers ──────────────────────────────────────────────────────

  const setField = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const setBlockField = (bIdx, key) => (e) => {
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, [key]: e.target.value } : b));
  };

  const toggleBlock = (bIdx) => {
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, open: !b.open } : b));
  };

  const addBlock = () => {
    setBlocks((prev) => [...prev, emptyBlock(prev.length + 1)]);
  };

  const removeBlock = (bIdx) => {
    setBlocks((prev) => prev.filter((_, i) => i !== bIdx).map((b, i) => ({ ...b, order: i + 1 })));
  };

  const setIntervalField = (bIdx, iIdx, key) => (e) => {
    setBlocks((prev) => prev.map((b, bi) => {
      if (bi !== bIdx) return b;
      return {
        ...b,
        intervals: b.intervals.map((iv, ii) => ii === iIdx ? { ...iv, [key]: e.target.value } : iv),
      };
    }));
  };

  const addInterval = (bIdx) => {
    setBlocks((prev) => prev.map((b, i) => i !== bIdx ? b : { ...b, intervals: [...b.intervals, emptyInterval()] }));
  };

  const removeInterval = (bIdx, iIdx) => {
    setBlocks((prev) => prev.map((b, i) => i !== bIdx ? b : { ...b, intervals: b.intervals.filter((_, ii) => ii !== iIdx) }));
  };

  // ── Submit ──────────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('El nombre del entrenamiento es obligatorio.'); return; }
    if (blocks.length === 0) { setError('Agrega al menos un bloque.'); return; }

    setSaving(true);
    setError('');

    try {
      // 1. Create the PlannedWorkout
      const workoutPayload = {
        name: form.name.trim(),
        description: form.description.trim(),
        sport_type: form.sport_type,
        difficulty: form.difficulty,
        notes: form.notes.trim(),
        ...(form.estimated_duration_minutes && { estimated_duration_minutes: Number(form.estimated_duration_minutes) }),
        ...(form.estimated_distance_km && { estimated_distance_km: Number(form.estimated_distance_km) }),
      };
      const workoutRes = await createPlannedWorkout(orgId, libraryId, workoutPayload);
      const workoutId = workoutRes.data.id;

      // 2. Create blocks + intervals sequentially
      for (const block of blocks) {
        const blockPayload = {
          name: block.name.trim() || BLOCK_TYPES.find((t) => t.value === block.block_type)?.label,
          block_type: block.block_type,
          order: block.order,
        };
        const blockRes = await createWorkoutBlock(orgId, libraryId, workoutId, blockPayload);
        const blockId = blockRes.data.id;

        for (let order = 0; order < block.intervals.length; order++) {
          const iv = block.intervals[order];
          const ivPayload = {
            order: order + 1,
            ...(iv.name.trim() && { name: iv.name.trim() }),
            ...(iv.duration_seconds && { duration_seconds: Number(iv.duration_seconds) }),
            ...(iv.distance_meters && { distance_meters: Number(iv.distance_meters) }),
            intensity_type: iv.intensity_type,
            ...(iv.intensity_value && { intensity_value: iv.intensity_value }),
            ...(iv.rest_duration_seconds && { rest_duration_seconds: Number(iv.rest_duration_seconds) }),
            repetitions: Number(iv.repetitions) || 1,
          };
          await createWorkoutInterval(orgId, libraryId, workoutId, blockId, ivPayload);
        }
      }

      onSaved(workoutRes.data);
      handleClose();
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.response?.data?.name?.[0] || 'Error al guardar el entrenamiento.';
      setError(detail);
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pb: 1 }}>
        <FitnessCenterIcon sx={{ color: '#F57C00' }} />
        <Typography variant="h6" fontWeight={700}>Nuevo Entrenamiento</Typography>
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ pt: 3 }}>
        <Collapse in={!!error}>
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>
        </Collapse>

        {/* ── Section 1: Workout Metadata ── */}
        <Typography variant="subtitle2" color="text.secondary" fontWeight={600} gutterBottom>
          INFORMACIÓN GENERAL
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mb: 3 }}>
          <TextField
            label="Nombre del entrenamiento *"
            value={form.name}
            onChange={setField('name')}
            fullWidth
            size="small"
            placeholder="Ej: Fartlek 8×400m, Carrera larga en montaña…"
          />
          <TextField
            label="Descripción"
            value={form.description}
            onChange={setField('description')}
            fullWidth
            size="small"
            multiline
            rows={2}
            placeholder="Objetivo del entrenamiento…"
          />

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <TextField select label="Deporte" value={form.sport_type} onChange={setField('sport_type')} size="small" fullWidth>
              {SPORT_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </TextField>
            <TextField select label="Dificultad" value={form.difficulty} onChange={setField('difficulty')} size="small" fullWidth>
              {DIFFICULTY_OPTIONS.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: o.color }} />
                    {o.label}
                  </Box>
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Duración estimada (min)"
              value={form.estimated_duration_minutes}
              onChange={setField('estimated_duration_minutes')}
              size="small"
              type="number"
              inputProps={{ min: 0 }}
            />
            <TextField
              label="Distancia estimada (km)"
              value={form.estimated_distance_km}
              onChange={setField('estimated_distance_km')}
              size="small"
              type="number"
              inputProps={{ min: 0, step: 0.1 }}
            />
          </Box>
          <TextField
            label="Notas para el atleta"
            value={form.notes}
            onChange={setField('notes')}
            fullWidth
            size="small"
            multiline
            rows={2}
            placeholder="Instrucciones adicionales, equipo necesario…"
          />
        </Box>

        <Divider sx={{ mb: 3 }} />

        {/* ── Section 2: Blocks ── */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="subtitle2" color="text.secondary" fontWeight={600}>
            BLOQUES ({blocks.length})
          </Typography>
          <Button startIcon={<AddIcon />} size="small" variant="outlined" onClick={addBlock} sx={{ borderRadius: 2 }}>
            Agregar bloque
          </Button>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {blocks.map((block, bIdx) => {
            const blockMeta = BLOCK_TYPES.find((t) => t.value === block.block_type);
            return (
              <Paper
                key={bIdx}
                variant="outlined"
                sx={{ borderRadius: 2, borderColor: block.open ? blockMeta?.color : 'divider', overflow: 'hidden' }}
              >
                {/* Block header */}
                <Box sx={{
                  display: 'flex', alignItems: 'center', gap: 1, px: 2, py: 1.5,
                  bgcolor: block.open ? `${blockMeta?.color}15` : 'transparent',
                  cursor: 'pointer',
                }} onClick={() => toggleBlock(bIdx)}>
                  <DragHandleIcon fontSize="small" sx={{ color: 'text.disabled' }} />
                  <Chip
                    label={blockMeta?.label}
                    size="small"
                    sx={{ bgcolor: blockMeta?.color, color: 'white', fontWeight: 600, fontSize: '0.7rem' }}
                  />
                  <TextField
                    value={block.name}
                    onChange={setBlockField(bIdx, 'name')}
                    placeholder={`Bloque ${bIdx + 1}`}
                    size="small"
                    variant="standard"
                    onClick={(e) => e.stopPropagation()}
                    sx={{ flexGrow: 1, '& input': { fontWeight: 500 } }}
                  />
                  <TextField
                    select
                    value={block.block_type}
                    onChange={setBlockField(bIdx, 'block_type')}
                    size="small"
                    variant="standard"
                    onClick={(e) => e.stopPropagation()}
                    sx={{ minWidth: 140 }}
                  >
                    {BLOCK_TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                  </TextField>
                  <Tooltip title="Eliminar bloque">
                    <IconButton size="small" onClick={(e) => { e.stopPropagation(); removeBlock(bIdx); }}>
                      <DeleteIcon fontSize="small" sx={{ color: '#ef4444' }} />
                    </IconButton>
                  </Tooltip>
                  <IconButton size="small">{block.open ? <ExpandLessIcon /> : <ExpandMoreIcon />}</IconButton>
                </Box>

                {/* Block intervals */}
                <Collapse in={block.open}>
                  <Box sx={{ px: 2, py: 1.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>

                    {/* Interval header */}
                    <Box sx={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 40px', gap: 1, px: 0.5 }}>
                      {['Nombre / Descripción', 'Duración (seg)', 'Distancia (m)', 'Tipo intensidad', 'Valor', 'Descanso (seg)', ''].map((h) => (
                        <Typography key={h} variant="caption" color="text.secondary" fontWeight={600} sx={{ textTransform: 'uppercase', fontSize: '0.65rem' }}>
                          {h}
                        </Typography>
                      ))}
                    </Box>

                    {block.intervals.map((iv, iIdx) => (
                      <Box key={iIdx} sx={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 40px', gap: 1, alignItems: 'center' }}>
                        <TextField value={iv.name} onChange={setIntervalField(bIdx, iIdx, 'name')} size="small" placeholder="Intervalo…" />
                        <TextField value={iv.duration_seconds} onChange={setIntervalField(bIdx, iIdx, 'duration_seconds')} size="small" type="number" inputProps={{ min: 0 }} placeholder="300" />
                        <TextField value={iv.distance_meters} onChange={setIntervalField(bIdx, iIdx, 'distance_meters')} size="small" type="number" inputProps={{ min: 0 }} placeholder="400" />
                        <TextField select value={iv.intensity_type} onChange={setIntervalField(bIdx, iIdx, 'intensity_type')} size="small">
                          {INTENSITY_TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                        </TextField>
                        <TextField value={iv.intensity_value} onChange={setIntervalField(bIdx, iIdx, 'intensity_value')} size="small" placeholder="Z3 / 7" />
                        <TextField value={iv.rest_duration_seconds} onChange={setIntervalField(bIdx, iIdx, 'rest_duration_seconds')} size="small" type="number" inputProps={{ min: 0 }} placeholder="90" />
                        <Tooltip title="Eliminar intervalo">
                          <span>
                            <IconButton size="small" onClick={() => removeInterval(bIdx, iIdx)} disabled={block.intervals.length === 1}>
                              <DeleteIcon fontSize="small" sx={{ color: block.intervals.length === 1 ? 'text.disabled' : '#ef4444' }} />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Box>
                    ))}

                    <Button
                      startIcon={<AddIcon />}
                      size="small"
                      onClick={() => addInterval(bIdx)}
                      sx={{ alignSelf: 'flex-start', color: 'text.secondary' }}
                    >
                      Agregar intervalo
                    </Button>
                  </Box>
                </Collapse>
              </Paper>
            );
          })}
        </Box>
      </DialogContent>

      <Divider />

      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <Button onClick={handleClose} disabled={saving} variant="outlined" sx={{ borderRadius: 2 }}>
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={saving}
          variant="contained"
          sx={{ borderRadius: 2, minWidth: 140 }}
        >
          {saving ? <CircularProgress size={20} color="inherit" /> : 'Guardar entrenamiento'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
