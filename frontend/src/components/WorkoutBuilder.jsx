import React, { useState, useCallback, useMemo } from 'react';
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
  Timer as TimerIcon,
  Straighten as StraightenIcon,
  TouchApp as TouchAppIcon,
} from '@mui/icons-material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  createPlannedWorkout,
  updatePlannedWorkout,
  createWorkoutBlock,
  deleteWorkoutBlock,
  createWorkoutInterval,
} from '../api/p1';

// ── Constants ────────────────────────────────────────────────────────────────

const SPORT_OPTIONS = [
  { value: 'trail', label: 'Trail Running' },
  { value: 'run', label: 'Running' },
  { value: 'bike', label: 'Ciclismo' },
  { value: 'strength', label: 'Fuerza / Funcional' },
  { value: 'mobility', label: 'Movilidad' },
  { value: 'other', label: 'Otro' },
];

const SESSION_TYPE_OPTIONS = [
  { value: 'base', label: 'Base / Fácil' },
  { value: 'threshold', label: 'Umbral' },
  { value: 'interval', label: 'Intervalos' },
  { value: 'long', label: 'Largo' },
  { value: 'recovery', label: 'Recuperación' },
  { value: 'race_simulation', label: 'Simulación de Carrera' },
  { value: 'strength', label: 'Fuerza' },
  { value: 'other', label: 'Otro' },
];

const BLOCK_TYPES = [
  { value: 'warmup',   label: 'Calentamiento',    color: '#fb923c' },
  { value: 'main',     label: 'Bloque Principal', color: '#3b82f6' },
  { value: 'cooldown', label: 'Enfriamiento',     color: '#a3e635' },
  { value: 'drill',    label: 'Técnica / Drills', color: '#94a3b8' },
  { value: 'strength', label: 'Fuerza',           color: '#c084fc' },
  { value: 'custom',   label: 'Personalizado',    color: '#f59e0b' },
];

const METRIC_TYPES = [
  { value: 'rpe',     label: 'RPE (1–10)' },
  { value: 'hr_zone', label: 'Zona FC (Z1–Z5)' },
  { value: 'pace',    label: 'Ritmo (min/km)' },
  { value: 'power',   label: 'Vatios' },
  { value: 'free',    label: 'Libre' },
];

// "Fin de paso" — how the step ends
const STEP_END_OPTIONS = [
  { value: 'tiempo',    label: 'Tiempo',       icon: <TimerIcon fontSize="small" /> },
  { value: 'distancia', label: 'Distancia',    icon: <StraightenIcon fontSize="small" /> },
  { value: 'lap',       label: 'Lap Button',   icon: <TouchAppIcon fontSize="small" /> },
];

// ── Defaults ─────────────────────────────────────────────────────────────────

const emptyInterval = () => ({
  description: '',
  repetitions: 1,
  step_end_type: 'tiempo',
  duration_seconds: '',
  distance_meters: '',
  metric_type: 'rpe',
  target_label: '',
  recovery_seconds: '',
});

const emptyBlock = (order_index) => ({
  name: '',
  block_type: 'main',
  order_index,
  repetitions: 1,
  open: true,
  intervals: [emptyInterval()],
});

const INITIAL_FORM = {
  name: '',
  description: '',
  discipline: 'trail',
  session_type: 'other',
  estimated_duration_minutes: '',
  estimated_distance_km: '',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function inferStepEndType(iv) {
  if (iv.duration_seconds != null && iv.duration_seconds !== '') return 'tiempo';
  if (iv.distance_meters != null && iv.distance_meters !== '') return 'distancia';
  return 'tiempo';
}

function workoutToFormState(workout) {
  const form = {
    name: workout.name ?? '',
    description: workout.description ?? '',
    discipline: workout.discipline ?? 'trail',
    session_type: workout.session_type ?? 'other',
    estimated_duration_minutes: workout.estimated_duration_seconds
      ? String(Math.round(workout.estimated_duration_seconds / 60))
      : '',
    estimated_distance_km: workout.estimated_distance_meters
      ? String(workout.estimated_distance_meters / 1000)
      : '',
  };
  const blocks = (workout.blocks ?? []).map((b, bIdx) => ({
    id: b.id,
    name: b.name ?? '',
    block_type: b.block_type ?? 'main',
    order_index: b.order_index ?? bIdx + 1,
    repetitions: b.repetitions ?? 1,
    open: true,
    intervals: (b.intervals ?? []).map((iv) => ({
      description: iv.description ?? '',
      repetitions: iv.repetitions ?? 1,
      step_end_type: inferStepEndType(iv),
      duration_seconds: iv.duration_seconds != null ? String(iv.duration_seconds) : '',
      distance_meters: iv.distance_meters != null ? String(iv.distance_meters) : '',
      metric_type: iv.metric_type ?? 'rpe',
      target_label: iv.target_label ?? '',
      recovery_seconds: iv.recovery_seconds != null ? String(iv.recovery_seconds) : '',
    })),
  }));
  return { form, blocks };
}

// ── Calculator ────────────────────────────────────────────────────────────────

function computeTotals(blocks) {
  let totalSeconds = 0;
  let totalMeters = 0;

  for (const block of blocks) {
    const blockReps = Math.max(1, Number(block.repetitions) || 1);
    for (const iv of block.intervals) {
      const ivReps = Math.max(1, Number(iv.repetitions) || 1);
      const mult = blockReps * ivReps;

      if (iv.step_end_type === 'tiempo' && iv.duration_seconds) {
        totalSeconds += Number(iv.duration_seconds) * mult;
        if (iv.recovery_seconds) {
          totalSeconds += Number(iv.recovery_seconds) * mult;
        }
      } else if (iv.step_end_type === 'distancia' && iv.distance_meters) {
        totalMeters += Number(iv.distance_meters) * mult;
      }
    }
  }

  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const durationLabel = totalSeconds === 0
    ? '—'
    : h > 0
      ? `${h}h ${m}min`
      : `${m} min`;

  const distanceLabel = totalMeters === 0
    ? '—'
    : totalMeters >= 1000
      ? `${(totalMeters / 1000).toFixed(2)} km`
      : `${totalMeters} m`;

  return { totalSeconds, totalMeters, durationLabel, distanceLabel };
}

// ── Chart data ────────────────────────────────────────────────────────────────

function buildChartData(blocks) {
  const data = [];
  blocks.forEach((block, bIdx) => {
    const blockMeta = BLOCK_TYPES.find((t) => t.value === block.block_type) ?? BLOCK_TYPES[1];
    const blockReps = Math.max(1, Number(block.repetitions) || 1);

    block.intervals.forEach((iv, iIdx) => {
      const ivReps = Math.max(1, Number(iv.repetitions) || 1);
      let stepMinutes = 0;

      if (iv.step_end_type === 'tiempo' && iv.duration_seconds) {
        stepMinutes = Number(iv.duration_seconds) / 60;
      } else if (iv.step_end_type === 'distancia' && iv.distance_meters) {
        // rough 6 min/km pace proxy for visual height
        stepMinutes = (Number(iv.distance_meters) / 1000) * 6;
      } else {
        stepMinutes = 3; // lap button: fixed visual bar
      }

      const shortLabel =
        iv.description
          ? iv.description.slice(0, 10)
          : `${bIdx + 1}.${iIdx + 1}`;

      const repsSuffix = ivReps > 1 ? `×${ivReps}` : '';
      const blockRepsSuffix = blockReps > 1 ? ` [B×${blockReps}]` : '';

      data.push({
        name: `${shortLabel}${repsSuffix}${blockRepsSuffix}`,
        duration: parseFloat((stepMinutes * ivReps).toFixed(1)),
        fill: blockMeta.color,
        blockLabel: blockMeta.label,
        stepEnd: iv.step_end_type,
        target: iv.target_label,
        metric: iv.metric_type,
      });
    });
  });
  return data;
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-slate-900 text-slate-100 rounded-lg px-3 py-2 text-xs shadow-xl border border-slate-700">
      <p className="font-semibold text-amber-400 mb-1">{d.blockLabel}</p>
      <p>Paso: <span className="font-medium">{d.name}</span></p>
      <p>Duración visual: <span className="font-medium">{d.duration} min</span></p>
      {d.target && <p>Objetivo: <span className="font-medium">{d.target}</span></p>}
      <p className="text-slate-400 mt-1">Métrica: {d.metric}</p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function WorkoutBuilder({ open, onClose, orgId, libraryId, onSaved, editWorkout, onUpdated }) {
  const isEditMode = !!editWorkout;

  const [form, setForm] = useState(INITIAL_FORM);
  const [blocks, setBlocks] = useState([emptyBlock(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  React.useEffect(() => {
    if (open && editWorkout) {
      const { form: f, blocks: b } = workoutToFormState(editWorkout);
      setForm(f);
      setBlocks(b);
      setError('');
    } else if (open && !editWorkout) {
      setForm(INITIAL_FORM);
      setBlocks([emptyBlock(1)]);
      setError('');
    }
  }, [open, editWorkout]);

  const resetState = useCallback(() => {
    setForm(INITIAL_FORM);
    setBlocks([emptyBlock(1)]);
    setSaving(false);
    setError('');
  }, []);

  const handleClose = () => { resetState(); onClose(); };

  // ── Form helpers ────────────────────────────────────────────────────────────

  const setField = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const setBlockField = (bIdx, key) => (e) =>
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, [key]: e.target.value } : b));

  const toggleBlock = (bIdx) =>
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, open: !b.open } : b));

  const addBlock = () =>
    setBlocks((prev) => [...prev, emptyBlock(prev.length + 1)]);

  const removeBlock = (bIdx) =>
    setBlocks((prev) =>
      prev.filter((_, i) => i !== bIdx).map((b, i) => ({ ...b, order_index: i + 1 }))
    );

  const setIntervalField = (bIdx, iIdx, key) => (e) =>
    setBlocks((prev) =>
      prev.map((b, bi) => {
        if (bi !== bIdx) return b;
        return {
          ...b,
          intervals: b.intervals.map((iv, ii) =>
            ii === iIdx ? { ...iv, [key]: e.target.value } : iv
          ),
        };
      })
    );

  const setIntervalValue = (bIdx, iIdx, key, value) =>
    setBlocks((prev) =>
      prev.map((b, bi) => {
        if (bi !== bIdx) return b;
        return {
          ...b,
          intervals: b.intervals.map((iv, ii) =>
            ii === iIdx ? { ...iv, [key]: value } : iv
          ),
        };
      })
    );

  const addInterval = (bIdx) =>
    setBlocks((prev) =>
      prev.map((b, i) => i !== bIdx ? b : { ...b, intervals: [...b.intervals, emptyInterval()] })
    );

  const removeInterval = (bIdx, iIdx) =>
    setBlocks((prev) =>
      prev.map((b, i) =>
        i !== bIdx ? b : { ...b, intervals: b.intervals.filter((_, ii) => ii !== iIdx) }
      )
    );

  // ── Derived: totals + chart ─────────────────────────────────────────────────

  const totals = useMemo(() => computeTotals(blocks), [blocks]);
  const chartData = useMemo(() => buildChartData(blocks), [blocks]);

  // ── Submit ──────────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('El nombre del entrenamiento es obligatorio.'); return; }
    if (blocks.length === 0) { setError('Agrega al menos un bloque.'); return; }

    setSaving(true);
    setError('');

    try {
      const workoutPayload = {
        name: form.name.trim(),
        description: form.description.trim(),
        discipline: form.discipline,
        session_type: form.session_type,
        ...(form.estimated_duration_minutes && {
          estimated_duration_seconds: Math.round(Number(form.estimated_duration_minutes) * 60),
        }),
        ...(form.estimated_distance_km && {
          estimated_distance_meters: Number(form.estimated_distance_km) * 1000,
        }),
      };

      let workoutId;
      let workoutData;

      if (isEditMode) {
        const res = await updatePlannedWorkout(orgId, libraryId, editWorkout.id, workoutPayload);
        workoutId = editWorkout.id;
        workoutData = res.data;
        for (const existingBlock of editWorkout.blocks ?? []) {
          await deleteWorkoutBlock(orgId, libraryId, workoutId, existingBlock.id);
        }
      } else {
        const res = await createPlannedWorkout(orgId, libraryId, workoutPayload);
        workoutId = res.data.id;
        workoutData = res.data;
      }

      for (const block of blocks) {
        const blockPayload = {
          name: block.name.trim() || BLOCK_TYPES.find((t) => t.value === block.block_type)?.label,
          block_type: block.block_type,
          order_index: block.order_index,
          repetitions: Number(block.repetitions) || 1,
        };
        const blockRes = await createWorkoutBlock(orgId, libraryId, workoutId, blockPayload);
        const blockId = blockRes.data.id;

        for (let idx = 0; idx < block.intervals.length; idx++) {
          const iv = block.intervals[idx];
          const ivPayload = {
            order_index: idx + 1,
            repetitions: Number(iv.repetitions) || 1,
            metric_type: iv.metric_type,
            ...(iv.description.trim() && { description: iv.description.trim() }),
            ...(iv.step_end_type === 'tiempo' && iv.duration_seconds && {
              duration_seconds: Number(iv.duration_seconds),
            }),
            ...(iv.step_end_type === 'distancia' && iv.distance_meters && {
              distance_meters: Number(iv.distance_meters),
            }),
            ...(iv.target_label && { target_label: iv.target_label }),
            ...(iv.recovery_seconds && { recovery_seconds: Number(iv.recovery_seconds) }),
          };
          await createWorkoutInterval(orgId, libraryId, workoutId, blockId, ivPayload);
        }
      }

      if (isEditMode) { onUpdated?.(workoutData); }
      else { onSaved(workoutData); }
      handleClose();
    } catch (err) {
      const data = err?.response?.data;
      if (!data) {
        setError('Error al guardar el entrenamiento.');
      } else if (typeof data === 'string') {
        setError(data);
      } else if (data.detail) {
        setError(data.detail);
      } else {
        const firstKey = Object.keys(data)[0];
        const firstMsg = Array.isArray(data[firstKey]) ? data[firstKey][0] : String(data[firstKey]);
        setError(`${firstKey}: ${firstMsg}`);
      }
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="xl"
      fullWidth
      PaperProps={{ className: 'rounded-2xl shadow-xl', sx: { maxHeight: '92vh' } }}
    >
      {/* ── Header ── */}
      <DialogTitle sx={{ pb: 0 }}>
        <div className="flex items-center gap-2 pb-3 border-b border-slate-200">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-amber-500">
            <FitnessCenterIcon sx={{ color: 'white', fontSize: 20 }} />
          </div>
          <div>
            <p className="text-lg font-bold text-slate-900 leading-tight">
              {isEditMode ? 'Editar Entrenamiento' : 'Nuevo Entrenamiento'}
            </p>
            <p className="text-xs text-slate-500">Constructor Pro · Quantoryn</p>
          </div>
        </div>
      </DialogTitle>

      <DialogContent sx={{ p: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Collapse in={!!error}>
          <Alert severity="error" sx={{ mx: 3, mt: 2 }} onClose={() => setError('')}>{error}</Alert>
        </Collapse>

        {/* ── Two-column layout ── */}
        <div className="flex gap-0 flex-1 min-h-0" style={{ height: '100%' }}>

          {/* ── LEFT: Editor ── */}
          <div className="flex-1 overflow-y-auto px-6 py-5" style={{ minWidth: 0 }}>

            {/* Metadata */}
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Información General
            </p>

            <div className="flex flex-col gap-3 mb-5">
              <TextField
                label="Nombre del entrenamiento *"
                value={form.name}
                onChange={setField('name')}
                fullWidth
                size="small"
                placeholder="Ej: Fartlek 8×400m, Carrera larga en montaña…"
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' }, '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' } }}
              />
              <TextField
                label="Descripción / Notas para el atleta"
                value={form.description}
                onChange={setField('description')}
                fullWidth
                size="small"
                multiline
                rows={2}
                placeholder="Objetivo del entrenamiento, instrucciones adicionales…"
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
              />
              <div className="grid grid-cols-4 gap-3">
                <TextField select label="Deporte" value={form.discipline} onChange={setField('discipline')} size="small" fullWidth
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}>
                  {SPORT_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                </TextField>
                <TextField select label="Tipo de sesión" value={form.session_type} onChange={setField('session_type')} size="small" fullWidth
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}>
                  {SESSION_TYPE_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                </TextField>
                <TextField
                  label="Duración estimada (min)"
                  value={form.estimated_duration_minutes}
                  onChange={setField('estimated_duration_minutes')}
                  size="small"
                  type="number"
                  inputProps={{ min: 0 }}
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
                />
                <TextField
                  label="Distancia estimada (km)"
                  value={form.estimated_distance_km}
                  onChange={setField('estimated_distance_km')}
                  size="small"
                  type="number"
                  inputProps={{ min: 0, step: 0.1 }}
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
                />
              </div>
            </div>

            <Divider sx={{ mb: 3 }} />

            {/* Blocks header */}
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Bloques ({blocks.length})
              </p>
              <button
                onClick={addBlock}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-amber-600 border border-amber-400 rounded-lg hover:bg-amber-50 transition-colors"
              >
                <AddIcon sx={{ fontSize: 15 }} />
                Agregar bloque
              </button>
            </div>

            {/* Blocks list */}
            <div className="flex flex-col gap-3">
              {blocks.map((block, bIdx) => {
                const blockMeta = BLOCK_TYPES.find((t) => t.value === block.block_type) ?? BLOCK_TYPES[1];
                return (
                  <div
                    key={bIdx}
                    className="rounded-xl border overflow-hidden"
                    style={{ borderColor: block.open ? blockMeta.color + '60' : '#e2e8f0' }}
                  >
                    {/* Block header */}
                    <div
                      className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
                      style={{ backgroundColor: block.open ? blockMeta.color + '12' : 'transparent' }}
                      onClick={() => toggleBlock(bIdx)}
                    >
                      <DragHandleIcon fontSize="small" sx={{ color: '#94a3b8', flexShrink: 0 }} />

                      <span
                        className="text-xs font-bold px-2 py-0.5 rounded-md text-white flex-shrink-0"
                        style={{ backgroundColor: blockMeta.color }}
                      >
                        {blockMeta.label}
                      </span>

                      {/* Block name */}
                      <TextField
                        value={block.name}
                        onChange={setBlockField(bIdx, 'name')}
                        placeholder={`Bloque ${bIdx + 1}`}
                        size="small"
                        variant="standard"
                        onClick={(e) => e.stopPropagation()}
                        sx={{ flexGrow: 1, '& input': { fontWeight: 500, fontSize: '0.85rem' } }}
                      />

                      {/* Block type selector */}
                      <TextField
                        select
                        value={block.block_type}
                        onChange={setBlockField(bIdx, 'block_type')}
                        size="small"
                        variant="standard"
                        onClick={(e) => e.stopPropagation()}
                        sx={{ minWidth: 130 }}
                      >
                        {BLOCK_TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                      </TextField>

                      {/* Block repetitions */}
                      <div
                        className="flex items-center gap-1 flex-shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span className="text-xs text-slate-500 font-medium">Repetir</span>
                        <TextField
                          type="number"
                          value={block.repetitions}
                          onChange={(e) =>
                            setBlocks((prev) =>
                              prev.map((b, i) =>
                                i === bIdx ? { ...b, repetitions: e.target.value } : b
                              )
                            )
                          }
                          size="small"
                          inputProps={{ min: 1, max: 99, style: { textAlign: 'center', fontWeight: 600, padding: '4px 6px', width: 40 } }}
                          sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', '&.Mui-focused fieldset': { borderColor: '#f59e0b' } } }}
                        />
                        <span className="text-xs text-slate-500">×</span>
                      </div>

                      <Tooltip title="Eliminar bloque">
                        <IconButton
                          size="small"
                          onClick={(e) => { e.stopPropagation(); removeBlock(bIdx); }}
                        >
                          <DeleteIcon fontSize="small" sx={{ color: '#ef4444' }} />
                        </IconButton>
                      </Tooltip>

                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); toggleBlock(bIdx); }}>
                        {block.open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                      </IconButton>
                    </div>

                    {/* Block intervals */}
                    <Collapse in={block.open}>
                      <div className="px-3 py-3 bg-white flex flex-col gap-2">

                        {/* Interval column headers */}
                        <div className="grid gap-2 px-1 pb-1"
                          style={{ gridTemplateColumns: '2fr 60px 110px 1fr 1fr 1fr 36px' }}>
                          {[
                            'Descripción del paso',
                            'Reps',
                            'Fin de paso',
                            'Métrica',
                            'Objetivo',
                            'Descanso (seg)',
                            '',
                          ].map((h) => (
                            <p key={h} className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                              {h}
                            </p>
                          ))}
                        </div>

                        {block.intervals.map((iv, iIdx) => (
                          <div
                            key={iIdx}
                            className="grid gap-2 items-center"
                            style={{ gridTemplateColumns: '2fr 60px 110px 1fr 1fr 1fr 36px' }}
                          >
                            {/* Description */}
                            <TextField
                              value={iv.description}
                              onChange={setIntervalField(bIdx, iIdx, 'description')}
                              size="small"
                              placeholder="Intervalo, técnica…"
                              sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' } }}
                            />

                            {/* Repetitions */}
                            <TextField
                              value={iv.repetitions}
                              onChange={setIntervalField(bIdx, iIdx, 'repetitions')}
                              size="small"
                              type="number"
                              inputProps={{ min: 1 }}
                              sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' } }}
                            />

                            {/* Fin de paso — compound: selector + conditional input */}
                            <div className="flex flex-col gap-1">
                              <TextField
                                select
                                value={iv.step_end_type}
                                onChange={(e) => {
                                  setIntervalValue(bIdx, iIdx, 'step_end_type', e.target.value);
                                  // Clear the unused field
                                  if (e.target.value !== 'tiempo') setIntervalValue(bIdx, iIdx, 'duration_seconds', '');
                                  if (e.target.value !== 'distancia') setIntervalValue(bIdx, iIdx, 'distance_meters', '');
                                }}
                                size="small"
                                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.75rem' } }}
                              >
                                {STEP_END_OPTIONS.map((o) => (
                                  <MenuItem key={o.value} value={o.value} sx={{ fontSize: '0.8rem' }}>
                                    {o.label}
                                  </MenuItem>
                                ))}
                              </TextField>

                              {iv.step_end_type === 'tiempo' && (
                                <TextField
                                  value={iv.duration_seconds}
                                  onChange={setIntervalField(bIdx, iIdx, 'duration_seconds')}
                                  size="small"
                                  type="number"
                                  inputProps={{ min: 0 }}
                                  placeholder="seg"
                                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.75rem' } }}
                                />
                              )}
                              {iv.step_end_type === 'distancia' && (
                                <TextField
                                  value={iv.distance_meters}
                                  onChange={setIntervalField(bIdx, iIdx, 'distance_meters')}
                                  size="small"
                                  type="number"
                                  inputProps={{ min: 0 }}
                                  placeholder="metros"
                                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.75rem' } }}
                                />
                              )}
                              {iv.step_end_type === 'lap' && (
                                <p className="text-xs text-slate-400 italic px-1">Hasta lap</p>
                              )}
                            </div>

                            {/* Metric */}
                            <TextField
                              select
                              value={iv.metric_type}
                              onChange={setIntervalField(bIdx, iIdx, 'metric_type')}
                              size="small"
                              sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' } }}
                            >
                              {METRIC_TYPES.map((t) => (
                                <MenuItem key={t.value} value={t.value} sx={{ fontSize: '0.8rem' }}>
                                  {t.label}
                                </MenuItem>
                              ))}
                            </TextField>

                            {/* Target */}
                            <TextField
                              value={iv.target_label}
                              onChange={setIntervalField(bIdx, iIdx, 'target_label')}
                              size="small"
                              placeholder="Z3 / 7 / 4:30"
                              sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' } }}
                            />

                            {/* Recovery */}
                            <TextField
                              value={iv.recovery_seconds}
                              onChange={setIntervalField(bIdx, iIdx, 'recovery_seconds')}
                              size="small"
                              type="number"
                              inputProps={{ min: 0 }}
                              placeholder="90"
                              sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' } }}
                            />

                            {/* Delete */}
                            <Tooltip title="Eliminar paso">
                              <span>
                                <IconButton
                                  size="small"
                                  onClick={() => removeInterval(bIdx, iIdx)}
                                  disabled={block.intervals.length === 1}
                                >
                                  <DeleteIcon
                                    fontSize="small"
                                    sx={{ color: block.intervals.length === 1 ? '#cbd5e1' : '#ef4444' }}
                                  />
                                </IconButton>
                              </span>
                            </Tooltip>
                          </div>
                        ))}

                        <button
                          onClick={() => addInterval(bIdx)}
                          className="self-start flex items-center gap-1 text-xs text-slate-500 hover:text-amber-600 transition-colors mt-1"
                        >
                          <AddIcon sx={{ fontSize: 14 }} />
                          Agregar paso
                        </button>
                      </div>
                    </Collapse>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── RIGHT: Chart + Totals ── */}
          <div className="flex-shrink-0 flex flex-col gap-4 p-5 bg-slate-50 border-l border-slate-200 overflow-y-auto"
            style={{ width: 380 }}>

            {/* Calculator */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Calculadora Automática
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <TimerIcon sx={{ fontSize: 16, color: '#f59e0b' }} />
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Tiempo Total</p>
                  </div>
                  <p className="text-2xl font-bold text-slate-900">{totals.durationLabel}</p>
                  {totals.totalSeconds > 0 && (
                    <p className="text-xs text-slate-400 mt-0.5">{Math.round(totals.totalSeconds / 60)} min</p>
                  )}
                </div>
                <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <StraightenIcon sx={{ fontSize: 16, color: '#3b82f6' }} />
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Distancia</p>
                  </div>
                  <p className="text-2xl font-bold text-slate-900">{totals.distanceLabel}</p>
                  {totals.totalMeters > 0 && (
                    <p className="text-xs text-slate-400 mt-0.5">{totals.totalMeters} m</p>
                  )}
                </div>
              </div>
            </div>

            {/* Chart */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Perfil Visual del Entrenamiento
              </p>

              {chartData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 bg-white rounded-xl border border-slate-200">
                  <FitnessCenterIcon sx={{ fontSize: 36, color: '#cbd5e1' }} />
                  <p className="text-sm font-semibold text-slate-600 mt-3">Sin pasos aún</p>
                  <p className="text-xs text-slate-400 mt-1 text-center px-4">
                    Agrega bloques e intervalos para ver el perfil fisiológico.
                  </p>
                </div>
              ) : (
                <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-sm">
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart
                      data={chartData}
                      margin={{ top: 8, right: 8, left: -24, bottom: 40 }}
                      barCategoryGap="15%"
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        angle={-45}
                        textAnchor="end"
                        interval={0}
                        height={48}
                      />
                      <YAxis
                        tick={{ fontSize: 9, fill: '#94a3b8' }}
                        label={{
                          value: 'min',
                          angle: -90,
                          position: 'insideLeft',
                          offset: 10,
                          style: { fontSize: 9, fill: '#94a3b8' },
                        }}
                      />
                      <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: '#f8fafc' }} />
                      <Bar dataKey="duration" radius={[4, 4, 0, 0]}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>

                  {/* Legend */}
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 px-1">
                    {BLOCK_TYPES.filter((bt) =>
                      blocks.some((b) => b.block_type === bt.value)
                    ).map((bt) => (
                      <div key={bt.value} className="flex items-center gap-1">
                        <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: bt.color }} />
                        <span className="text-xs text-slate-500">{bt.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Block summary */}
            {blocks.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  Resumen de Bloques
                </p>
                <div className="flex flex-col gap-1.5">
                  {blocks.map((block, bIdx) => {
                    const blockMeta = BLOCK_TYPES.find((t) => t.value === block.block_type) ?? BLOCK_TYPES[1];
                    const reps = Number(block.repetitions) || 1;
                    const steps = block.intervals.length;
                    return (
                      <div
                        key={bIdx}
                        className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-slate-200 text-xs"
                      >
                        <div className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: blockMeta.color }} />
                        <span className="font-medium text-slate-700 flex-1 truncate">
                          {block.name || blockMeta.label}
                        </span>
                        {reps > 1 && (
                          <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded-md font-semibold">
                            ×{reps}
                          </span>
                        )}
                        <span className="text-slate-400">{steps} paso{steps !== 1 ? 's' : ''}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>

      <Divider />

      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <button
          onClick={handleClose}
          disabled={saving}
          className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          onClick={handleSubmit}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg transition-colors disabled:opacity-60 min-w-44"
        >
          {saving ? (
            <>
              <CircularProgress size={15} sx={{ color: 'white' }} />
              <span>Guardando…</span>
            </>
          ) : (
            <span>{isEditMode ? 'Actualizar entrenamiento' : 'Guardar entrenamiento'}</span>
          )}
        </button>
      </DialogActions>
    </Dialog>
  );
}
