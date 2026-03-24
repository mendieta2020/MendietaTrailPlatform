import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, MenuItem, Box, Typography, Divider,
  IconButton, Chip, CircularProgress, Alert, Collapse,
  Paper, Tooltip,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  DragHandle as DragHandleIcon,
  FitnessCenter as FitnessCenterIcon,
  Repeat as RepeatIcon,
  KeyboardArrowUp as ArrowUpIcon,
  KeyboardArrowDown as ArrowDownIcon,
} from '@mui/icons-material';
import {
  createPlannedWorkout,
  updatePlannedWorkout,
  createWorkoutBlock,
  deleteWorkoutBlock,
  createWorkoutInterval,
} from '../api/p1';
import { getPaceZones } from '../api/workouts';

// ── Constants ────────────────────────────────────────────────────────────────

const SPORT_OPTIONS = [
  { value: 'trail',    label: 'Trail Running' },
  { value: 'run',      label: 'Running' },
  { value: 'bike',     label: 'Ciclismo' },
  { value: 'swim',     label: 'Natación' },
  { value: 'strength', label: 'Fuerza' },
  { value: 'mobility', label: 'Movilidad' },
  { value: 'other',    label: 'Otro' },
];

const SESSION_TYPE_OPTIONS = [
  { value: 'base',            label: 'Fondo' },
  { value: 'threshold',       label: 'Tempo' },
  { value: 'interval',        label: 'Intervalos' },
  { value: 'recovery',        label: 'Recuperación' },
  { value: 'long',            label: 'Largo' },
  { value: 'strength',        label: 'Fuerza' },
  { value: 'race_simulation', label: 'Test' },
  { value: 'other',           label: 'Libre' },
];

const STEP_TYPES = [
  { value: 'warmup',   label: 'Calentamiento', emoji: '🔥', color: '#fb923c' },
  { value: 'main',     label: 'Fondo / Base',  emoji: '🏃', color: '#3b82f6' },
  { value: 'drill',    label: 'Intensivo',      emoji: '⚡', color: '#8b5cf6' },
  { value: 'custom',   label: 'Tempo',          emoji: '💨', color: '#eab308' },
  { value: 'recovery_step', label: 'Recuperación', emoji: '😮‍💨', color: '#94a3b8' },
  { value: 'cooldown', label: 'Vuelta a la calma', emoji: '🏁', color: '#a3e635' },
  { value: 'strength', label: 'Fuerza',         emoji: '💪', color: '#c084fc' },
  { value: 'free',     label: 'Libre',          emoji: '🆓', color: '#64748b' },
];

// Map block_type → display config (for rendering existing data)
const STEP_TYPE_MAP = Object.fromEntries(STEP_TYPES.map((s) => [s.value, s]));

const ZONES = [
  { value: 'Z1', label: 'Z1', name: 'Recuperación', color: '#94a3b8' },
  { value: 'Z2', label: 'Z2', name: 'Aeróbico',     color: '#22c55e' },
  { value: 'Z3', label: 'Z3', name: 'Tempo',         color: '#eab308' },
  { value: 'Z4', label: 'Z4', name: 'Umbral',        color: '#f97316' },
  { value: 'Z5', label: 'Z5', name: 'VO2max',        color: '#ef4444' },
  { value: '',   label: 'Sin zona', name: 'Libre',   color: '#94a3b8' },
];

const ZONE_MAP = Object.fromEntries(ZONES.filter((z) => z.value).map((z) => [z.value, z]));

// ── Defaults ─────────────────────────────────────────────────────────────────

const emptyInterval = () => ({
  description: '',
  step_type: 'main',      // visual only — maps to block_type for sub-intervals display
  measure: 'tiempo',      // 'tiempo' | 'distancia'
  duration_seconds: '',
  distance_meters: '',
  zone: '',               // 'Z1'...'Z5' | ''
  metric_type: 'free',
  target_label: '',
  recovery_seconds: '',
  repetitions: 1,
});

// A "block" can be simple (repetitions=1, 1 interval) or repeated (repetitions>1, N intervals)
const emptyBlock = (order_index) => ({
  id: null,
  name: '',
  block_type: 'main',
  order_index,
  repetitions: 1,
  isRepeated: false,     // UI-only toggle: false = simple step, true = repeated block
  intervals: [emptyInterval()],
});

const INITIAL_FORM = {
  name: '',
  description: '',
  discipline: 'trail',
  session_type: 'other',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function inferMeasure(iv) {
  if (iv.distance_meters != null && iv.distance_meters !== '') return 'distancia';
  return 'tiempo';
}

function inferZone(iv) {
  if (!iv.metric_type || iv.metric_type === 'free') return '';
  if (iv.metric_type === 'hr_zone' && iv.target_label) {
    const z = iv.target_label.trim().toUpperCase();
    if (['Z1', 'Z2', 'Z3', 'Z4', 'Z5'].includes(z)) return z;
  }
  return '';
}

function workoutToFormState(workout) {
  const form = {
    name: workout.name ?? '',
    description: workout.description ?? '',
    discipline: workout.discipline ?? 'trail',
    session_type: workout.session_type ?? 'other',
  };
  const blocks = (workout.blocks ?? []).map((b, bIdx) => {
    const intervals = (b.intervals ?? []).map((iv) => ({
      description: iv.description ?? '',
      step_type: 'main',
      measure: inferMeasure(iv),
      duration_seconds: iv.duration_seconds != null ? String(iv.duration_seconds) : '',
      distance_meters: iv.distance_meters != null ? String(iv.distance_meters) : '',
      zone: inferZone(iv),
      metric_type: iv.metric_type ?? 'free',
      target_label: iv.target_label ?? '',
      recovery_seconds: iv.recovery_seconds != null ? String(iv.recovery_seconds) : '',
      repetitions: iv.repetitions ?? 1,
    }));
    const reps = b.repetitions ?? 1;
    return {
      id: b.id,
      name: b.name ?? '',
      block_type: b.block_type ?? 'main',
      order_index: b.order_index ?? bIdx + 1,
      repetitions: reps,
      isRepeated: reps > 1 || intervals.length > 1,
      intervals,
    };
  });
  return { form, blocks };
}

// ── Calculations ──────────────────────────────────────────────────────────────

function estimateDurationS(iv, paceZones) {
  if (iv.measure === 'tiempo' && iv.duration_seconds) {
    return Number(iv.duration_seconds);
  }
  if (iv.measure === 'distancia' && iv.distance_meters) {
    const dist_km = Number(iv.distance_meters) / 1000;
    if (iv.zone && paceZones?.zones?.[iv.zone]) {
      const zoneData = paceZones.zones[iv.zone];
      const midPace = (zoneData.pace_min_s + zoneData.pace_max_s) / 2;
      return midPace * dist_km;
    }
    return dist_km * 360; // fallback: 6:00/km
  }
  return 0;
}

function computeTotals(blocks, paceZones) {
  let totalSeconds = 0;
  let totalMeters = 0;

  for (const block of blocks) {
    const blockReps = Math.max(1, Number(block.repetitions) || 1);
    for (const iv of block.intervals) {
      const mult = blockReps * Math.max(1, Number(iv.repetitions) || 1);
      const durS = estimateDurationS(iv, paceZones);
      totalSeconds += durS * mult;
      if (iv.recovery_seconds) {
        totalSeconds += Number(iv.recovery_seconds) * mult;
      }
      if (iv.measure === 'distancia' && iv.distance_meters) {
        totalMeters += Number(iv.distance_meters) * mult;
      }
    }
  }

  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const durationLabel = totalSeconds === 0
    ? '—'
    : h > 0 ? `${h}h ${m}min` : `${m} min`;

  const distanceLabel = totalMeters === 0
    ? '—'
    : totalMeters >= 1000
      ? `${(totalMeters / 1000).toFixed(1)} km`
      : `${totalMeters} m`;

  // Dominant zone by duration
  const zoneSeconds = { Z1: 0, Z2: 0, Z3: 0, Z4: 0, Z5: 0 };
  for (const block of blocks) {
    const br = Math.max(1, Number(block.repetitions) || 1);
    for (const iv of block.intervals) {
      if (iv.zone && zoneSeconds[iv.zone] !== undefined) {
        const dur = estimateDurationS(iv, paceZones) * br * Math.max(1, Number(iv.repetitions) || 1);
        zoneSeconds[iv.zone] += dur;
      }
    }
  }
  const domZone = Object.entries(zoneSeconds).sort((a, b) => b[1] - a[1])[0];
  const loadLabel = totalSeconds === 0 ? '—'
    : domZone?.[0] === 'Z5' ? 'Máxima'
    : domZone?.[0] === 'Z4' ? 'Alta'
    : domZone?.[0] === 'Z3' ? 'Moderada'
    : 'Recuperación / Base';

  return { totalSeconds, totalMeters, durationLabel, distanceLabel, loadLabel };
}

// ── Intensity Bar ─────────────────────────────────────────────────────────────

function IntensityBar({ blocks, paceZones }) {
  const segments = [];
  let totalDur = 0;

  for (const block of blocks) {
    const br = Math.max(1, Number(block.repetitions) || 1);
    for (let r = 0; r < br; r++) {
      for (const iv of block.intervals) {
        const dur = Math.max(estimateDurationS(iv, paceZones), 60);
        totalDur += dur;
        const zone = ZONE_MAP[iv.zone];
        const color = zone?.color ?? '#e2e8f0';
        const label = iv.description || (zone ? `${zone.label} ${zone.name}` : 'Paso');
        segments.push({ dur, color, label, zoneName: zone?.name ?? 'Libre' });
      }
    }
  }

  if (segments.length === 0 || totalDur === 0) return null;

  return (
    <div>
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
        Perfil de Intensidad
      </p>
      <div className="flex h-8 rounded-lg overflow-hidden gap-px">
        {segments.map((seg, i) => (
          <Tooltip key={i} title={`${seg.label} · ${seg.zoneName}`} arrow placement="top">
            <div
              style={{
                flex: seg.dur / totalDur,
                backgroundColor: seg.color,
                minWidth: 4,
                opacity: 0.85,
                transition: 'opacity 0.15s',
                cursor: 'default',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.85'; }}
            />
          </Tooltip>
        ))}
      </div>
      {/* Zone legend */}
      <div className="flex flex-wrap gap-2 mt-2">
        {ZONES.filter((z) => z.value).map((z) => (
          <div key={z.value} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: z.color }} />
            <span className="text-xs text-slate-500">{z.label} {z.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Zone Selector Badge ────────────────────────────────────────────────────────

function ZoneBadge({ zone, paceZones }) {
  if (!zone) return null;
  const zDef = ZONE_MAP[zone];
  const zData = paceZones?.zones?.[zone];
  if (!zDef) return null;
  return (
    <div
      className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-semibold"
      style={{ backgroundColor: `${zDef.color}20`, color: zDef.color, border: `1px solid ${zDef.color}40` }}
    >
      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: zDef.color }} />
      {zDef.label} {zDef.name}
      {zData ? ` · ${zData.pace_min} – ${zData.pace_max}` : ''}
    </div>
  );
}

// ── Estimated Time Badge ───────────────────────────────────────────────────────

function EstTimeBadge({ iv, paceZones }) {
  if (iv.measure !== 'distancia' || !iv.distance_meters || !iv.zone) return null;
  const zData = paceZones?.zones?.[iv.zone];
  if (!zData) return null;
  const dist_km = Number(iv.distance_meters) / 1000;
  const minS = zData.pace_min_s * dist_km;
  const maxS = zData.pace_max_s * dist_km;
  const fmt = (s) => {
    const total = Math.round(s);
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
  };
  return (
    <span className="text-xs text-slate-400 italic">
      ~{fmt(minS)} – {fmt(maxS)} estimados
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function WorkoutBuilder({ open, onClose, orgId, libraryId, onSaved, editWorkout, onUpdated }) {
  const isEditMode = !!editWorkout;

  const [form, setForm] = useState(INITIAL_FORM);
  const [blocks, setBlocks] = useState([emptyBlock(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [paceZones, setPaceZones] = useState(null);

  // Load pace zones once on open
  useEffect(() => {
    if (!open) return;
    getPaceZones()
      .then((res) => setPaceZones(res.data))
      .catch(() => setPaceZones(null));
  }, [open]);

  // Load edit state
  useEffect(() => {
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

  const totals = useMemo(() => computeTotals(blocks, paceZones), [blocks, paceZones]);

  const resetState = useCallback(() => {
    setForm(INITIAL_FORM);
    setBlocks([emptyBlock(1)]);
    setSaving(false);
    setError('');
  }, []);

  const handleClose = () => { resetState(); onClose(); };
  const setField = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  // ── Block operations ────────────────────────────────────────────────────────

  const addSimpleStep = () =>
    setBlocks((prev) => [...prev, emptyBlock(prev.length + 1)]);

  const addRepeatedBlock = () =>
    setBlocks((prev) => [
      ...prev,
      {
        ...emptyBlock(prev.length + 1),
        isRepeated: true,
        repetitions: 4,
        intervals: [emptyInterval(), emptyInterval()],
      },
    ]);

  const removeBlock = (bIdx) =>
    setBlocks((prev) =>
      prev.filter((_, i) => i !== bIdx).map((b, i) => ({ ...b, order_index: i + 1 }))
    );

  const moveBlock = (bIdx, dir) =>
    setBlocks((prev) => {
      const next = [...prev];
      const target = bIdx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[bIdx], next[target]] = [next[target], next[bIdx]];
      return next.map((b, i) => ({ ...b, order_index: i + 1 }));
    });

  const setBlockField = (bIdx, key, value) =>
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, [key]: value } : b));

  // ── Interval operations ─────────────────────────────────────────────────────

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

  // ── Submit ──────────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('El nombre del entrenamiento es obligatorio.'); return; }
    if (blocks.length === 0) { setError('Agrega al menos un paso.'); return; }

    setSaving(true);
    setError('');

    try {
      const workoutPayload = {
        name: form.name.trim(),
        description: form.description.trim(),
        discipline: form.discipline,
        session_type: form.session_type,
        ...(totals.totalSeconds > 0 && {
          estimated_duration_seconds: Math.round(totals.totalSeconds),
        }),
        ...(totals.totalMeters > 0 && {
          estimated_distance_meters: Math.round(totals.totalMeters),
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
        const stepMeta = STEP_TYPE_MAP[block.block_type] ?? STEP_TYPES[1];
        const blockPayload = {
          name: block.name.trim() || stepMeta.label,
          block_type: block.block_type,
          order_index: block.order_index,
          repetitions: Number(block.repetitions) || 1,
        };
        const blockRes = await createWorkoutBlock(orgId, libraryId, workoutId, blockPayload);
        const blockId = blockRes.data.id;

        for (let idx = 0; idx < block.intervals.length; idx++) {
          const iv = block.intervals[idx];
          // Map zone → metric_type + target_label
          const hasZone = !!iv.zone;
          const ivPayload = {
            order_index: idx + 1,
            repetitions: Number(iv.repetitions) || 1,
            metric_type: hasZone ? 'hr_zone' : (iv.metric_type || 'free'),
            ...(iv.description.trim() && { description: iv.description.trim() }),
            ...(iv.measure === 'tiempo' && iv.duration_seconds && {
              duration_seconds: Number(iv.duration_seconds),
            }),
            ...(iv.measure === 'distancia' && iv.distance_meters && {
              distance_meters: Number(iv.distance_meters),
            }),
            target_label: hasZone ? iv.zone : (iv.target_label || ''),
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
      maxWidth="lg"
      fullWidth
      PaperProps={{
        className: 'rounded-2xl shadow-xl',
        sx: { maxHeight: '94vh', height: '94vh' },
      }}
    >
      {/* Header */}
      <DialogTitle sx={{ pb: 0 }}>
        <div className="flex items-center gap-3 pb-3 border-b border-slate-200">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-amber-500 flex-shrink-0">
            <FitnessCenterIcon sx={{ color: 'white', fontSize: 20 }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-lg font-bold text-slate-900 leading-tight">
              {isEditMode ? 'Editar Entrenamiento' : 'Nuevo Entrenamiento · Constructor Pro'}
            </p>
            <p className="text-xs text-slate-500">
              Quantoryn · {paceZones
                ? (paceZones.has_threshold
                  ? `Umbral ${paceZones.threshold_pace_display}`
                  : `Zonas estimadas (sin umbral personalizado)`)
                : 'Cargando zonas…'}
            </p>
          </div>
        </div>
      </DialogTitle>

      <DialogContent sx={{ p: 0, display: 'flex', flexDirection: 'column', flex: '1 1 0', minHeight: 0 }}>
        <Collapse in={!!error}>
          <Alert severity="error" sx={{ mx: 3, mt: 2 }} onClose={() => setError('')}>{error}</Alert>
        </Collapse>

        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* ── LEFT: Editor ── */}
          <div className="flex-1 overflow-y-auto px-5 py-4" style={{ minWidth: 0 }}>

            {/* ── Section 1: General Info ── */}
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Información General
            </p>

            <div className="flex flex-col gap-3 mb-5">
              <TextField
                label="Nombre del entrenamiento *"
                value={form.name}
                onChange={setField('name')}
                fullWidth
                size="small"
                placeholder="Ej: Intervalos 4×1000m Z4"
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' }, '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' } }}
              />

              <div className="grid grid-cols-2 gap-3">
                <TextField
                  select
                  label="Deporte *"
                  value={form.discipline}
                  onChange={setField('discipline')}
                  size="small"
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
                >
                  {SPORT_OPTIONS.map((o) => (
                    <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  label="Tipo de sesión"
                  value={form.session_type}
                  onChange={setField('session_type')}
                  size="small"
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
                >
                  {SESSION_TYPE_OPTIONS.map((o) => (
                    <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                  ))}
                </TextField>
              </div>

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

              {/* Auto-calculated totals row */}
              <div className="flex gap-4 px-3 py-2 bg-slate-50 rounded-lg border border-slate-200">
                <div>
                  <span className="text-xs text-slate-400 uppercase tracking-wide">Duración est.</span>
                  <p className="text-sm font-bold text-slate-700">{totals.durationLabel}</p>
                </div>
                <div className="w-px bg-slate-200" />
                <div>
                  <span className="text-xs text-slate-400 uppercase tracking-wide">Distancia est.</span>
                  <p className="text-sm font-bold text-slate-700">{totals.distanceLabel}</p>
                </div>
                <div className="w-px bg-slate-200" />
                <div>
                  <span className="text-xs text-slate-400 uppercase tracking-wide">Carga</span>
                  <p className="text-sm font-bold text-slate-700">{totals.loadLabel}</p>
                </div>
              </div>
            </div>

            <Divider sx={{ mb: 3 }} />

            {/* ── Section 2: Steps ── */}
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                Pasos del entrenamiento ({blocks.length})
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AddIcon sx={{ fontSize: 14 }} />}
                  onClick={addSimpleStep}
                  sx={{
                    borderColor: '#f59e0b',
                    color: '#d97706',
                    borderRadius: '8px',
                    fontSize: '0.75rem',
                    textTransform: 'none',
                    '&:hover': { borderColor: '#d97706', bgcolor: '#fffbeb' },
                  }}
                >
                  Agregar paso
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<RepeatIcon sx={{ fontSize: 14 }} />}
                  onClick={addRepeatedBlock}
                  sx={{
                    borderColor: '#8b5cf6',
                    color: '#7c3aed',
                    borderRadius: '8px',
                    fontSize: '0.75rem',
                    textTransform: 'none',
                    '&:hover': { borderColor: '#7c3aed', bgcolor: '#f5f3ff' },
                  }}
                >
                  Bloque repetido
                </Button>
              </div>
            </div>

            {/* Steps list */}
            <div className="flex flex-col gap-3">
              {blocks.map((block, bIdx) => {
                const isRepeated = block.isRepeated;
                return (
                  <Paper
                    key={bIdx}
                    elevation={1}
                    sx={{
                      borderRadius: '12px',
                      overflow: 'hidden',
                      border: isRepeated ? '1px solid #8b5cf630' : '1px solid #e2e8f0',
                    }}
                  >
                    {/* Block header */}
                    <div
                      className="flex items-center gap-2 px-3 py-2"
                      style={{ backgroundColor: isRepeated ? '#f5f3ff' : '#f8fafc' }}
                    >
                      {/* Drag handle */}
                      <DragHandleIcon fontSize="small" sx={{ color: '#cbd5e1', cursor: 'grab', flexShrink: 0 }} />

                      {/* Step number */}
                      <span className="text-xs font-bold text-slate-500 flex-shrink-0 w-5">
                        {bIdx + 1}
                      </span>

                      {isRepeated ? (
                        /* Repeated block header */
                        <>
                          <RepeatIcon sx={{ color: '#8b5cf6', fontSize: 16, flexShrink: 0 }} />
                          <span className="text-xs font-semibold text-purple-700 flex-shrink-0">
                            Repetir
                          </span>
                          <TextField
                            type="number"
                            value={block.repetitions}
                            onChange={(e) => setBlockField(bIdx, 'repetitions', e.target.value)}
                            size="small"
                            inputProps={{ min: 2, max: 50, style: { textAlign: 'center', fontWeight: 700, padding: '2px 4px', width: 36, fontSize: '0.8rem' } }}
                            sx={{
                              flexShrink: 0,
                              '& .MuiOutlinedInput-root': { borderRadius: '6px', '&.Mui-focused fieldset': { borderColor: '#8b5cf6' } },
                            }}
                          />
                          <span className="text-xs font-semibold text-purple-700">veces</span>
                          <TextField
                            value={block.name}
                            onChange={(e) => setBlockField(bIdx, 'name', e.target.value)}
                            placeholder="Nombre del bloque"
                            size="small"
                            variant="standard"
                            sx={{ flex: 1, '& input': { fontSize: '0.82rem', fontWeight: 500 } }}
                          />
                        </>
                      ) : (
                        /* Simple step header */
                        <>
                          <TextField
                            select
                            value={block.block_type}
                            onChange={(e) => setBlockField(bIdx, 'block_type', e.target.value)}
                            size="small"
                            variant="standard"
                            sx={{ minWidth: 140, '& .MuiInput-root': { fontSize: '0.82rem', fontWeight: 600 } }}
                          >
                            {STEP_TYPES.map((t) => (
                              <MenuItem key={t.value} value={t.value} sx={{ fontSize: '0.82rem' }}>
                                <span className="mr-1.5">{t.emoji}</span> {t.label}
                              </MenuItem>
                            ))}
                          </TextField>
                          <TextField
                            value={block.name}
                            onChange={(e) => setBlockField(bIdx, 'name', e.target.value)}
                            placeholder="Descripción opcional"
                            size="small"
                            variant="standard"
                            sx={{ flex: 1, '& input': { fontSize: '0.82rem' } }}
                          />
                        </>
                      )}

                      {/* Move up/down */}
                      <IconButton size="small" onClick={() => moveBlock(bIdx, -1)} disabled={bIdx === 0}
                        sx={{ p: 0.25, opacity: bIdx === 0 ? 0.3 : 0.6 }}>
                        <ArrowUpIcon sx={{ fontSize: 16 }} />
                      </IconButton>
                      <IconButton size="small" onClick={() => moveBlock(bIdx, 1)} disabled={bIdx === blocks.length - 1}
                        sx={{ p: 0.25, opacity: bIdx === blocks.length - 1 ? 0.3 : 0.6 }}>
                        <ArrowDownIcon sx={{ fontSize: 16 }} />
                      </IconButton>

                      <Tooltip title="Eliminar">
                        <IconButton size="small" onClick={() => removeBlock(bIdx)}
                          sx={{ p: 0.5, '&:hover': { color: '#ef4444' } }}>
                          <DeleteIcon sx={{ fontSize: 15, color: '#cbd5e1' }} />
                        </IconButton>
                      </Tooltip>
                    </div>

                    {/* Intervals */}
                    <div className="bg-white px-3 py-3 flex flex-col gap-2">
                      {block.intervals.map((iv, iIdx) => (
                        <IntervalRow
                          key={iIdx}
                          iv={iv}
                          iIdx={iIdx}
                          bIdx={bIdx}
                          isRepeated={isRepeated}
                          totalIntervals={block.intervals.length}
                          paceZones={paceZones}
                          onSetValue={setIntervalValue}
                          onRemove={removeInterval}
                        />
                      ))}

                      {isRepeated && (
                        <Button
                          variant="text"
                          size="small"
                          startIcon={<AddIcon sx={{ fontSize: 13 }} />}
                          onClick={() => addInterval(bIdx)}
                          sx={{
                            alignSelf: 'flex-start',
                            color: '#8b5cf6',
                            fontSize: '0.72rem',
                            textTransform: 'none',
                            '&:hover': { bgcolor: '#f5f3ff' },
                          }}
                        >
                          Agregar paso interno
                        </Button>
                      )}
                    </div>
                  </Paper>
                );
              })}
            </div>

            {/* ── Section 3: Intensity bar ── */}
            {blocks.length > 0 && (
              <div className="mt-5 px-3 py-3 bg-slate-50 rounded-xl border border-slate-200">
                <IntensityBar blocks={blocks} paceZones={paceZones} />
              </div>
            )}

          </div>

          {/* ── RIGHT: Zone reference panel ── */}
          <div
            className="w-60 flex-shrink-0 overflow-y-auto border-l border-slate-100 px-4 py-4 bg-slate-50"
            style={{ minWidth: 200 }}
          >
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Zonas de Ritmo
            </p>

            {ZONES.filter((z) => z.value).map((z) => {
              const zData = paceZones?.zones?.[z.value];
              return (
                <div key={z.value} className="mb-3">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <div
                      className="w-3 h-3 rounded-sm flex-shrink-0"
                      style={{ backgroundColor: z.color }}
                    />
                    <span className="text-xs font-bold" style={{ color: z.color }}>
                      {z.label}
                    </span>
                    <span className="text-xs font-semibold text-slate-600">{z.name}</span>
                  </div>
                  <p className="text-xs text-slate-500 pl-4">
                    {zData ? `${zData.pace_min} – ${zData.pace_max}` : '—'}
                  </p>
                  {zData && (
                    <p className="text-xs text-slate-400 pl-4">{zData.description}</p>
                  )}
                </div>
              );
            })}

            {paceZones && !paceZones.has_threshold && (
              <Alert severity="info" sx={{ mt: 2, fontSize: '0.7rem', p: '4px 8px' }}>
                Zonas estimadas. Configura tu ritmo umbral en el perfil para personalizarlas.
              </Alert>
            )}
          </div>
        </div>
      </DialogContent>

      {/* Footer */}
      <DialogActions
        sx={{
          px: 3, py: 2,
          borderTop: '1px solid',
          borderColor: 'grey.100',
          justifyContent: 'space-between',
        }}
      >
        <Button
          onClick={handleClose}
          disabled={saving}
          variant="outlined"
          sx={{ borderRadius: 2, textTransform: 'none' }}
        >
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={saving}
          variant="contained"
          sx={{
            borderRadius: 2,
            minWidth: 180,
            bgcolor: '#f59e0b',
            '&:hover': { bgcolor: '#d97706' },
            '&.Mui-disabled': { bgcolor: '#fed7aa' },
            textTransform: 'none',
            fontWeight: 600,
          }}
        >
          {saving
            ? <CircularProgress size={18} color="inherit" />
            : (isEditMode ? 'Guardar cambios →' : 'Guardar entrenamiento →')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── IntervalRow sub-component ─────────────────────────────────────────────────

function IntervalRow({ iv, iIdx, bIdx, isRepeated, totalIntervals, paceZones, onSetValue, onRemove }) {
  const set = (key, value) => onSetValue(bIdx, iIdx, key, value);
  const setE = (key) => (e) => set(key, e.target.value);

  const zoneColor = iv.zone ? ZONE_MAP[iv.zone]?.color : '#e2e8f0';
  const stepMeta = STEP_TYPE_MAP[iv.step_type] ?? STEP_TYPES[1];

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        borderColor: iv.zone ? `${zoneColor}40` : '#e2e8f0',
        borderLeftWidth: 3,
        borderLeftColor: iv.zone ? zoneColor : '#e2e8f0',
      }}
    >
      {/* Interval header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-50 border-b border-slate-100">
        <div className="flex items-center gap-2">
          {isRepeated && (
            <span className="text-xs font-bold text-slate-400">
              {iIdx + 1}.
            </span>
          )}
          {isRepeated ? (
            <TextField
              select
              value={iv.step_type}
              onChange={(e) => set('step_type', e.target.value)}
              size="small"
              variant="standard"
              sx={{ minWidth: 120, '& .MuiInput-root': { fontSize: '0.78rem', fontWeight: 600 } }}
            >
              {STEP_TYPES.map((t) => (
                <MenuItem key={t.value} value={t.value} sx={{ fontSize: '0.78rem' }}>
                  <span className="mr-1">{t.emoji}</span> {t.label}
                </MenuItem>
              ))}
            </TextField>
          ) : (
            <span className="text-xs font-semibold text-slate-500">
              {stepMeta.emoji} Paso {iIdx + 1}
            </span>
          )}
          {/* Repetitions (for simple steps only shown if explicitly set >1) */}
          <Tooltip title="Repetir este paso N veces" arrow>
            <div className="flex items-center gap-1">
              <TextField
                type="number"
                value={iv.repetitions}
                onChange={setE('repetitions')}
                size="small"
                inputProps={{ min: 1, max: 99, style: { textAlign: 'center', fontWeight: 700, padding: '1px 4px', width: 30, fontSize: '0.75rem' } }}
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '6px', '&.Mui-focused fieldset': { borderColor: '#f59e0b' } } }}
              />
              <span className="text-xs text-slate-400">×</span>
            </div>
          </Tooltip>
        </div>
        <Tooltip title="Eliminar paso">
          <span>
            <IconButton
              size="small"
              onClick={() => onRemove(bIdx, iIdx)}
              disabled={totalIntervals === 1 && !isRepeated}
            >
              <DeleteIcon
                fontSize="small"
                sx={{ color: (totalIntervals === 1 && !isRepeated) ? '#e2e8f0' : '#fca5a5', fontSize: 15 }}
              />
            </IconButton>
          </span>
        </Tooltip>
      </div>

      {/* Interval body */}
      <div className="px-3 pt-2.5 pb-3 bg-white">
        <div className="flex flex-col gap-2">

          {/* Row 1: description + measure + value */}
          <div className="flex gap-2 items-start">
            <TextField
              value={iv.description}
              onChange={setE('description')}
              size="small"
              label="Descripción"
              placeholder="Ej: 1000m al umbral…"
              sx={{
                flex: 1,
                '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.82rem' },
                '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' },
              }}
            />
            <TextField
              select
              value={iv.measure}
              onChange={(e) => {
                set('measure', e.target.value);
                if (e.target.value !== 'tiempo') set('duration_seconds', '');
                if (e.target.value !== 'distancia') set('distance_meters', '');
              }}
              size="small"
              label="Medida"
              sx={{ width: 110, '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.82rem' } }}
            >
              <MenuItem value="tiempo" sx={{ fontSize: '0.82rem' }}>⏱ Tiempo</MenuItem>
              <MenuItem value="distancia" sx={{ fontSize: '0.82rem' }}>📏 Distancia</MenuItem>
            </TextField>
            {iv.measure === 'tiempo' && (
              <TextField
                value={iv.duration_seconds}
                onChange={setE('duration_seconds')}
                size="small"
                type="number"
                label="Segundos"
                inputProps={{ min: 0 }}
                sx={{ width: 90, '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.82rem' }, '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' } }}
              />
            )}
            {iv.measure === 'distancia' && (
              <TextField
                value={iv.distance_meters}
                onChange={setE('distance_meters')}
                size="small"
                type="number"
                label="Metros"
                inputProps={{ min: 0 }}
                sx={{ width: 90, '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.82rem' }, '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' } }}
              />
            )}
          </div>

          {/* Row 2: Zone selector */}
          <div className="flex items-center gap-2 flex-wrap">
            <TextField
              select
              value={iv.zone}
              onChange={(e) => {
                set('zone', e.target.value);
                if (e.target.value) {
                  set('metric_type', 'hr_zone');
                  set('target_label', e.target.value);
                } else {
                  set('metric_type', 'free');
                  set('target_label', '');
                }
              }}
              size="small"
              label="Zona"
              sx={{ width: 130, '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.82rem' } }}
            >
              {ZONES.map((z) => (
                <MenuItem key={z.value} value={z.value} sx={{ fontSize: '0.82rem' }}>
                  {z.value && (
                    <span
                      className="inline-block w-2 h-2 rounded-full mr-1.5"
                      style={{ backgroundColor: z.color }}
                    />
                  )}
                  {z.label}{z.value ? ` ${z.name}` : ''}
                </MenuItem>
              ))}
            </TextField>

            <ZoneBadge zone={iv.zone} paceZones={paceZones} />
            <EstTimeBadge iv={iv} paceZones={paceZones} />
          </div>

          {/* Recovery */}
          <div className="flex items-center gap-2 mt-1">
            <div className="w-0.5 h-4 rounded-full bg-slate-200 flex-shrink-0" />
            <span className="text-xs text-slate-400 font-semibold uppercase tracking-wide flex-shrink-0">
              Recuperación
            </span>
            <TextField
              value={iv.recovery_seconds}
              onChange={setE('recovery_seconds')}
              size="small"
              type="number"
              label="Seg"
              inputProps={{ min: 0 }}
              sx={{ width: 80, '& .MuiOutlinedInput-root': { borderRadius: '8px', fontSize: '0.8rem' }, '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' } }}
            />
            {iv.recovery_seconds && Number(iv.recovery_seconds) > 0 && (
              <span className="text-xs text-slate-400">
                {Math.floor(Number(iv.recovery_seconds) / 60) > 0
                  ? `${Math.floor(Number(iv.recovery_seconds) / 60)} min `
                  : ''}
                {Number(iv.recovery_seconds) % 60 > 0
                  ? `${Number(iv.recovery_seconds) % 60} seg`
                  : ''}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
