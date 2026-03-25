import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, MenuItem, CircularProgress, Alert, Collapse,
  Tooltip, Menu,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  DragHandle as DragHandleIcon,
  Repeat as RepeatIcon,
  KeyboardArrowUp as ArrowUpIcon,
  KeyboardArrowDown as ArrowDownIcon,
  FitnessCenter as FitnessCenterIcon,
} from '@mui/icons-material';
import { ChevronDown } from 'lucide-react';
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
  { value: 'warmup',        label: 'Calentamiento',    emoji: '🔥', color: '#fb923c' },
  { value: 'main',          label: 'Fondo / Base',      emoji: '🏃', color: '#3b82f6' },
  { value: 'drill',         label: 'Intensivo',         emoji: '⚡', color: '#8b5cf6' },
  { value: 'custom',        label: 'Tempo',             emoji: '💨', color: '#eab308' },
  { value: 'recovery_step', label: 'Recuperación',      emoji: '😮‍💨', color: '#94a3b8' },
  { value: 'cooldown',      label: 'Vuelta calma',      emoji: '🏁', color: '#84cc16' },
  { value: 'strength',      label: 'Fuerza',            emoji: '💪', color: '#c084fc' },
  { value: 'free',          label: 'Libre',             emoji: '🆓', color: '#64748b' },
];

const STEP_TYPE_MAP = Object.fromEntries(STEP_TYPES.map((s) => [s.value, s]));

// Zone definitions per discipline mode
const ZONES_RUN = [
  { value: 'Z1', label: 'Z1', name: 'Recuperación', color: '#94a3b8' },
  { value: 'Z2', label: 'Z2', name: 'Aeróbico',     color: '#22c55e' },
  { value: 'Z3', label: 'Z3', name: 'Tempo',         color: '#eab308' },
  { value: 'Z4', label: 'Z4', name: 'Umbral',        color: '#f97316' },
  { value: 'Z5', label: 'Z5', name: 'VO2max',        color: '#ef4444' },
];
const ZONES_BIKE = [
  { value: 'Z1', label: 'Z1', name: 'Rec. <70% FC',    color: '#94a3b8' },
  { value: 'Z2', label: 'Z2', name: 'Base 70-80% FC',  color: '#22c55e' },
  { value: 'Z3', label: 'Z3', name: 'Aeróbico 80-87%', color: '#eab308' },
  { value: 'Z4', label: 'Z4', name: 'Umbral 87-93%',   color: '#f97316' },
  { value: 'Z5', label: 'Z5', name: 'VO2 >93% FC',     color: '#ef4444' },
];
const ZONES_STRENGTH = [
  { value: 'Z1', label: 'Bajo',    name: 'Bajo / Técnico',   color: '#94a3b8' },
  { value: 'Z2', label: 'Medio',   name: 'Moderado',          color: '#22c55e' },
  { value: 'Z3', label: 'Alto',    name: 'Alta intensidad',   color: '#eab308' },
  { value: 'Z4', label: 'Máx',     name: 'Máxima carga',      color: '#f97316' },
];

function getZones(discipline) {
  if (discipline === 'bike') return ZONES_BIKE;
  if (discipline === 'strength' || discipline === 'mobility') return ZONES_STRENGTH;
  return ZONES_RUN; // trail, run, swim, other
}

// Keep ZONES as alias for backward compat
const ZONES = [...ZONES_RUN, { value: '', label: '—', name: 'Sin zona', color: '#cbd5e1' }];
const ZONE_MAP = Object.fromEntries(ZONES_RUN.map((z) => [z.value, z]));

// IF (Intensity Factor) por zona — base para cálculo de rTSS estimado
const IF_ZONE = { Z1: 0.63, Z2: 0.75, Z3: 0.85, Z4: 0.975, Z5: 1.10 };
const IF_DEFAULT = 0.70; // sin zona → aeróbico moderado

// ── Defaults ─────────────────────────────────────────────────────────────────

const emptyInterval = () => ({
  description: '',
  step_type: 'main',
  measure: 'tiempo',
  obj_unit: 'seg',        // UI unit: 'seg'|'min'|'m'|'km'|'rep'
  duration_seconds: '',
  distance_meters: '',
  zone: '',
  metric_type: 'free',
  target_label: '',
  recovery_seconds: '',
  repetitions: 1,
});

const emptyBlock = (order_index) => ({
  id: null,
  name: '',
  block_type: 'main',
  order_index,
  repetitions: 1,
  isRepeated: false,
  intervals: [emptyInterval()],
});

const INITIAL_FORM = {
  name: '',
  description: '',
  discipline: 'trail',
  session_type: 'other',
  difficulty: '',
  elevation_gain_min_m: '',
  elevation_gain_max_m: '',
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
    difficulty: workout.difficulty ?? '',
    elevation_gain_min_m: workout.elevation_gain_min_m ?? '',
    elevation_gain_max_m: workout.elevation_gain_max_m ?? '',
  };
  const blocks = (workout.blocks ?? []).map((b, bIdx) => {
    const intervals = (b.intervals ?? []).map((iv) => {
      const m = inferMeasure(iv);
      return {
        description: iv.description ?? '',
        step_type: 'main',
        measure: m,
        obj_unit: m === 'distancia' ? 'm' : 'seg',
        duration_seconds: iv.duration_seconds != null ? String(iv.duration_seconds) : '',
        distance_meters: iv.distance_meters != null ? String(iv.distance_meters) : '',
        zone: inferZone(iv),
        metric_type: iv.metric_type ?? 'free',
        target_label: iv.target_label ?? '',
        recovery_seconds: iv.recovery_seconds != null ? String(iv.recovery_seconds) : '',
        repetitions: iv.repetitions ?? 1,
      };
    });
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
    return dist_km * 360; // fallback 6:00/km
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
      if (iv.recovery_seconds) totalSeconds += Number(iv.recovery_seconds) * mult;
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

  const zoneSeconds = { Z1: 0, Z2: 0, Z3: 0, Z4: 0, Z5: 0 };
  let tssSum = 0;
  let weightedIF2 = 0;

  for (const block of blocks) {
    const br = Math.max(1, Number(block.repetitions) || 1);
    for (const iv of block.intervals) {
      const mult = br * Math.max(1, Number(iv.repetitions) || 1);
      const dur = estimateDurationS(iv, paceZones) * mult;
      const ifVal = IF_ZONE[iv.zone] ?? IF_DEFAULT;
      if (iv.zone && zoneSeconds[iv.zone] !== undefined) {
        zoneSeconds[iv.zone] += dur;
      }
      tssSum += (dur / 3600) * ifVal * ifVal * 100;
      weightedIF2 += dur * ifVal * ifVal;
    }
  }

  const domZone = Object.entries(zoneSeconds).sort((a, b) => b[1] - a[1])[0];
  const loadLabel = totalSeconds === 0 ? '—'
    : domZone?.[0] === 'Z5' ? 'Máxima'
    : domZone?.[0] === 'Z4' ? 'Alta'
    : domZone?.[0] === 'Z3' ? 'Moderada'
    : 'Recuperación / Base';

  // TSS estimado y IF ponderado
  const tssLabel = totalSeconds > 60 ? String(Math.round(tssSum)) : '—';
  const ifLabel = totalSeconds > 60 && weightedIF2 > 0
    ? Math.sqrt(weightedIF2 / totalSeconds).toFixed(2)
    : '—';

  return { totalSeconds, totalMeters, durationLabel, distanceLabel, loadLabel, tssLabel, ifLabel };
}

// ── Intensity Histogram ────────────────────────────────────────────────────────

function fmtSeconds(s) {
  if (!s || s === 0) return null;
  const m = Math.floor(s / 60);
  if (m === 0) return `${Math.round(s)}s`;
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
}

function IntensityHistogram({ blocks, paceZones }) {
  const zoneSecondsMap = { Z1: 0, Z2: 0, Z3: 0, Z4: 0, Z5: 0 };
  let total = 0;

  for (const block of blocks) {
    const br = Math.max(1, Number(block.repetitions) || 1);
    for (const iv of block.intervals) {
      const mult = br * Math.max(1, Number(iv.repetitions) || 1);
      const dur = estimateDurationS(iv, paceZones) * mult;
      if (iv.zone && zoneSecondsMap[iv.zone] !== undefined) {
        zoneSecondsMap[iv.zone] += dur;
      }
      total += dur;
    }
  }

  if (total === 0) return null;

  const maxVal = Math.max(...Object.values(zoneSecondsMap), 1);

  return (
    <div>
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
        Distribución de Intensidad
      </p>
      <div className="flex flex-col gap-2">
        {ZONES.filter((z) => z.value).map((z) => {
          const secs = zoneSecondsMap[z.value] ?? 0;
          const pct = total > 0 ? Math.round((secs / total) * 100) : 0;
          const barW = maxVal > 0 ? (secs / maxVal) * 100 : 0;
          const timeLabel = fmtSeconds(secs);
          return (
            <div key={z.value} className="flex items-center gap-2">
              {/* Zone label */}
              <div className="flex items-center gap-1 flex-shrink-0" style={{ width: 126 }}>
                <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: z.color }} />
                <span className="text-xs font-bold flex-shrink-0" style={{ color: z.color }}>{z.label}</span>
                <span className="text-xs text-slate-500">{z.name}</span>
              </div>
              {/* Bar track */}
              <div className="flex-1 bg-slate-100 rounded-full overflow-hidden" style={{ height: 14 }}>
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${barW}%`,
                    background: z.color,
                    opacity: secs > 0 ? 0.82 : 0,
                    minWidth: secs > 0 ? 4 : 0,
                  }}
                />
              </div>
              {/* Time */}
              <span
                className="text-xs font-semibold flex-shrink-0"
                style={{ width: 36, textAlign: 'right', color: secs > 0 ? '#475569' : '#cbd5e1' }}
              >
                {timeLabel ?? '—'}
              </span>
              {/* % */}
              <span
                className="text-xs flex-shrink-0"
                style={{ width: 28, color: secs > 0 ? '#94a3b8' : '#e2e8f0' }}
              >
                {secs > 0 ? `${pct}%` : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── PaceRangeBadge ────────────────────────────────────────────────────────────

function PaceRangeBadge({ zone, paceZones }) {
  if (!zone) return null;
  const zDef = ZONE_MAP[zone];
  const zData = paceZones?.zones?.[zone];
  if (!zDef) return null;
  return (
    <span
      className="text-xs font-semibold flex-shrink-0 px-1.5 py-0.5 rounded"
      style={{
        color: zDef.color,
        background: `${zDef.color}15`,
        border: `1px solid ${zDef.color}25`,
        whiteSpace: 'nowrap',
      }}
    >
      {zData ? `${zData.pace_min}–${zData.pace_max}` : `${zDef.label} ${zDef.name}`}
    </span>
  );
}

// ── StepTypeButton ────────────────────────────────────────────────────────────

function StepTypeButton({ value, onChange }) {
  const [anchor, setAnchor] = useState(null);
  const meta = STEP_TYPE_MAP[value] ?? STEP_TYPES[1];

  return (
    <>
      <button
        onClick={(e) => { e.stopPropagation(); setAnchor(e.currentTarget); }}
        className="flex items-center gap-1 pl-2 pr-1.5 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-opacity hover:opacity-90 border"
        style={{
          backgroundColor: `${meta.color}18`,
          color: meta.color,
          borderColor: `${meta.color}35`,
          minWidth: 128,
          maxWidth: 140,
        }}
      >
        <span style={{ flexShrink: 0 }}>{meta.emoji}</span>
        <span className="flex-1 text-left truncate">{meta.label}</span>
        <ChevronDown size={11} style={{ opacity: 0.55, flexShrink: 0 }} />
      </button>
      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        MenuListProps={{ dense: true }}
        PaperProps={{
          className: 'rounded-xl shadow-xl',
          sx: { mt: 0.5, minWidth: 180 },
        }}
      >
        {STEP_TYPES.map((t) => (
          <MenuItem
            key={t.value}
            selected={t.value === value}
            onClick={() => { onChange(t.value); setAnchor(null); }}
            sx={{ fontSize: '0.8rem', py: 0.75, gap: 1 }}
          >
            <span style={{ marginRight: 6 }}>{t.emoji}</span>
            <span style={{ color: t.color, fontWeight: 600 }}>{t.label}</span>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

// ── ZonePills ─────────────────────────────────────────────────────────────────

function ZonePills({ selected, onChange, paceZones, discipline }) {
  const zones = getZones(discipline);
  const activeZone = zones.find((z) => z.value === selected);
  const zData = selected && paceZones?.zones?.[selected];
  return (
    <div className="flex items-center gap-1 flex-shrink-0" style={{ minWidth: 130 }}>
      <select
        value={selected || ''}
        onChange={(e) => onChange(e.target.value)}
        style={{
          height: 28, borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
          border: `1px solid ${activeZone ? activeZone.color + '80' : '#e2e8f0'}`,
          background: activeZone ? activeZone.color + '18' : 'white',
          color: activeZone ? activeZone.color : '#94a3b8',
          paddingLeft: 6, paddingRight: 4, outline: 'none', flex: 1,
        }}
      >
        <option value="">Sin zona</option>
        {zones.filter((z) => z.value).map((z) => (
          <option key={z.value} value={z.value}>{z.label} {z.name}</option>
        ))}
      </select>
      {zData && (
        <span style={{ fontSize: 10, color: '#64748b', whiteSpace: 'nowrap' }}>
          {zData.pace_min}–{zData.pace_max}
        </span>
      )}
    </div>
  );
}

// ── MeasureInput ──────────────────────────────────────────────────────────────

const UNIT_OPTS = [
  { u: 'seg', label: 'seg' },
  { u: 'min', label: 'min' },
  { u: 'm',   label: 'm' },
  { u: 'km',  label: 'km' },
  { u: 'rep', label: 'rep' },
];

function MeasureInput({ iv, set }) {
  const unit = iv.obj_unit || (iv.measure === 'distancia' ? 'm' : 'seg');

  let displayVal = '';
  if (unit === 'seg') displayVal = iv.duration_seconds || '';
  else if (unit === 'min') {
    const s = Number(iv.duration_seconds);
    displayVal = s > 0 ? String(Math.round((s / 60) * 10) / 10) : '';
  } else if (unit === 'm') displayVal = iv.distance_meters || '';
  else if (unit === 'km') {
    const m = Number(iv.distance_meters);
    displayVal = m > 0 ? String(m / 1000) : '';
  } else if (unit === 'rep') displayVal = iv.repetitions > 1 ? String(iv.repetitions) : '';

  const handleChange = (val) => {
    if (unit === 'seg') set('duration_seconds', val);
    else if (unit === 'min') set('duration_seconds', String(Math.round(Number(val) * 60)));
    else if (unit === 'm') set('distance_meters', val);
    else if (unit === 'km') set('distance_meters', String(Math.round(Number(val) * 1000)));
    else if (unit === 'rep') set('repetitions', Number(val) || 1);
  };

  const handleUnitChange = (u) => {
    set('obj_unit', u);
    if (u === 'seg' || u === 'min') {
      set('measure', 'tiempo');
      set('distance_meters', '');
    } else if (u === 'm' || u === 'km') {
      set('measure', 'distancia');
      set('duration_seconds', '');
    } else if (u === 'rep') {
      set('measure', 'rep');
      set('duration_seconds', '');
      set('distance_meters', '');
    }
  };

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <input
        type="number" min={0}
        value={displayVal}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="—"
        className="text-center text-xs font-semibold border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-1 focus:border-amber-400"
        style={{ width: 54, height: 28 }}
      />
      <select
        value={unit}
        onChange={(e) => handleUnitChange(e.target.value)}
        style={{
          height: 28, borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
          border: '1px solid #e2e8f0', background: '#f8fafc', color: '#475569',
          paddingLeft: 4, paddingRight: 2, outline: 'none', width: 52,
        }}
      >
        {UNIT_OPTS.map(({ u, label }) => (
          <option key={u} value={u}>{label}</option>
        ))}
      </select>
    </div>
  );
}

// ── RecoveryInput ─────────────────────────────────────────────────────────────

function RecoveryInput({ value, onChange }) {
  const num = Number(value);
  // Auto-format: show "45 seg" for <60s, "1.5 min" for ≥60s
  let fmt = null;
  if (value && num > 0) {
    if (num < 60) fmt = `${num} seg`;
    else {
      const mins = num / 60;
      fmt = Number.isInteger(mins) ? `${mins} min` : `${Math.round(mins * 10) / 10} min`;
    }
  }
  return (
    <div className="flex items-center gap-1 flex-shrink-0" title="Recuperación (segundos)">
      <input
        type="number" min={0}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0"
        className="text-center text-xs font-semibold border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-1 focus:border-amber-400"
        style={{ width: 44, height: 26 }}
      />
      <span className="text-xs text-slate-400" style={{ minWidth: 40, whiteSpace: 'nowrap' }}>
        {fmt ?? 'rec'}
      </span>
    </div>
  );
}

// ── RowActions ────────────────────────────────────────────────────────────────

function RowActions({ onUp, onDown, onDelete, disableUp, disableDown }) {
  return (
    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" style={{ width: 72 }}>
      <Tooltip title="Subir">
        <span>
          <button
            onClick={onUp} disabled={disableUp}
            className="flex items-center justify-center rounded hover:bg-slate-200 disabled:opacity-20 transition-colors"
            style={{ width: 22, height: 22 }}
          >
            <ArrowUpIcon sx={{ fontSize: 14, color: '#64748b' }} />
          </button>
        </span>
      </Tooltip>
      <Tooltip title="Bajar">
        <span>
          <button
            onClick={onDown} disabled={disableDown}
            className="flex items-center justify-center rounded hover:bg-slate-200 disabled:opacity-20 transition-colors"
            style={{ width: 22, height: 22 }}
          >
            <ArrowDownIcon sx={{ fontSize: 14, color: '#64748b' }} />
          </button>
        </span>
      </Tooltip>
      <Tooltip title="Eliminar">
        <button
          onClick={onDelete}
          className="flex items-center justify-center rounded hover:bg-red-50 transition-colors"
          style={{ width: 22, height: 22 }}
        >
          <DeleteIcon sx={{ fontSize: 14, color: '#fca5a5' }} />
        </button>
      </Tooltip>
    </div>
  );
}

// ── SimpleStepRow ─────────────────────────────────────────────────────────────

function SimpleStepRow({ block, bIdx, iv, isFirst, isLast, paceZones, discipline, onSetBlock, onSetInterval, onMove, onRemove }) {
  const setBlock = (key, val) => onSetBlock(bIdx, key, val);
  const setIv = (key, val) => onSetInterval(bIdx, 0, key, val);

  const handleZone = (zone) => {
    setIv('zone', zone);
    setIv('metric_type', zone ? 'hr_zone' : 'free');
    setIv('target_label', zone || '');
  };

  const zoneColor = iv.zone ? ZONE_MAP[iv.zone]?.color : null;

  return (
    <div
      className="group flex items-center gap-2 px-3 py-2 hover:bg-amber-50 transition-colors border-b border-slate-100"
      style={{ borderLeft: `3px solid ${zoneColor ?? 'transparent'}` }}
    >
      <DragHandleIcon sx={{ color: '#cbd5e1', fontSize: 16, cursor: 'grab', flexShrink: 0 }} />

      <span className="text-xs font-bold text-slate-400 flex-shrink-0 text-center" style={{ width: 18 }}>
        {bIdx + 1}
      </span>

      <div className="flex-shrink-0">
        <StepTypeButton value={block.block_type} onChange={(v) => setBlock('block_type', v)} />
      </div>

      <input
        type="text"
        value={block.name}
        onChange={(e) => setBlock('name', e.target.value)}
        placeholder="Descripción del paso…"
        className="flex-1 min-w-0 px-2 text-sm text-slate-700 placeholder-slate-300 bg-transparent border border-transparent rounded-md focus:outline-none focus:border-slate-300 focus:bg-white transition-colors"
        style={{ height: 30 }}
      />

      <MeasureInput iv={iv} set={setIv} />

      <ZonePills selected={iv.zone} onChange={handleZone} paceZones={paceZones} discipline={discipline} />

      <PaceRangeBadge zone={iv.zone} paceZones={paceZones} />

      <RecoveryInput value={iv.recovery_seconds} onChange={(v) => setIv('recovery_seconds', v)} />

      <RowActions
        onUp={() => onMove(bIdx, -1)}
        onDown={() => onMove(bIdx, 1)}
        onDelete={() => onRemove(bIdx)}
        disableUp={isFirst}
        disableDown={isLast}
      />
    </div>
  );
}

// ── SubStepRow ────────────────────────────────────────────────────────────────

function SubStepRow({ iv, iIdx, bIdx, isOnly, paceZones, discipline, onSetValue, onRemove }) {
  const set = (key, val) => onSetValue(bIdx, iIdx, key, val);
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

  const handleZone = (zone) => {
    set('zone', zone);
    set('metric_type', zone ? 'hr_zone' : 'free');
    set('target_label', zone || '');
  };

  const zoneColor = iv.zone ? ZONE_MAP[iv.zone]?.color : null;

  return (
    <div
      className="group flex items-center gap-2 pr-3 py-1.5 hover:bg-amber-50 transition-colors border-b border-amber-100"
      style={{
        paddingLeft: 48,
        borderLeft: `3px solid ${zoneColor ?? '#fed7aa'}`,
      }}
    >
      <span className="text-xs font-bold text-amber-500 flex-shrink-0 text-center" style={{ width: 18 }}>
        {letters[iIdx] ?? iIdx + 1}
      </span>

      <div className="flex-shrink-0">
        <StepTypeButton value={iv.step_type} onChange={(v) => set('step_type', v)} />
      </div>

      <input
        type="text"
        value={iv.description}
        onChange={(e) => set('description', e.target.value)}
        placeholder="Descripción del sub-paso…"
        className="flex-1 min-w-0 px-2 text-sm text-slate-700 placeholder-slate-300 bg-transparent border border-transparent rounded-md focus:outline-none focus:border-slate-300 focus:bg-white transition-colors"
        style={{ height: 28 }}
      />

      <MeasureInput iv={iv} set={set} />

      <ZonePills selected={iv.zone} onChange={handleZone} paceZones={paceZones} discipline={discipline} />

      <PaceRangeBadge zone={iv.zone} paceZones={paceZones} />

      <RecoveryInput value={iv.recovery_seconds} onChange={(v) => set('recovery_seconds', v)} />

      <div className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" style={{ width: 72 }}>
        <Tooltip title="Eliminar sub-paso">
          <span>
            <button
              onClick={() => onRemove(bIdx, iIdx)}
              disabled={isOnly}
              className="flex items-center justify-center rounded hover:bg-red-50 disabled:opacity-20 transition-colors"
              style={{ width: 22, height: 22 }}
            >
              <DeleteIcon sx={{ fontSize: 14, color: '#fca5a5' }} />
            </button>
          </span>
        </Tooltip>
      </div>
    </div>
  );
}

// ── RepeatedBlockHeader ───────────────────────────────────────────────────────

function RepeatedBlockHeader({ block, bIdx, isFirst, isLast, onSetBlock, onMove, onRemove, onAddInterval }) {
  const setBlock = (key, val) => onSetBlock(bIdx, key, val);
  return (
    <div
      className="group flex items-center gap-2 px-3 py-2 border-b border-amber-200 transition-colors"
      style={{ background: '#fffbeb', borderLeft: '3px solid #f59e0b' }}
    >
      <DragHandleIcon sx={{ color: '#fbbf24', fontSize: 16, cursor: 'grab', flexShrink: 0 }} />

      <RepeatIcon sx={{ color: '#d97706', fontSize: 16, flexShrink: 0 }} />

      <div className="flex items-center gap-1 flex-shrink-0">
        <input
          type="number" min={2} max={50}
          value={block.repetitions}
          onChange={(e) => setBlock('repetitions', e.target.value)}
          className="text-center text-xs font-bold border border-amber-300 rounded-md bg-white text-amber-700 focus:outline-none focus:ring-1 focus:border-amber-500"
          style={{ width: 38, height: 26 }}
        />
        <span className="text-xs font-bold text-amber-700">×</span>
      </div>

      <input
        type="text"
        value={block.name}
        onChange={(e) => setBlock('name', e.target.value)}
        placeholder="Nombre del bloque (ej: Intervalos 4×1km)…"
        className="flex-1 min-w-0 px-2 text-sm font-semibold text-amber-800 placeholder-amber-300 bg-transparent border border-transparent rounded-md focus:outline-none focus:border-amber-300 focus:bg-white transition-colors"
        style={{ height: 28 }}
      />

      <Tooltip title="Agregar sub-paso">
        <button
          onClick={() => onAddInterval(bIdx)}
          className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium text-amber-700 hover:bg-amber-200 transition-colors flex-shrink-0"
          style={{ background: '#fef3c7' }}
        >
          <AddIcon sx={{ fontSize: 13 }} />
          paso
        </button>
      </Tooltip>

      <RowActions
        onUp={() => onMove(bIdx, -1)}
        onDown={() => onMove(bIdx, 1)}
        onDelete={() => onRemove(bIdx)}
        disableUp={isFirst}
        disableDown={isLast}
      />
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function WorkoutBuilder({ open, onClose, orgId, libraryId, onSaved, editWorkout, onUpdated }) {
  const isEditMode = !!editWorkout;
  const [form, setForm] = useState(INITIAL_FORM);
  const [blocks, setBlocks] = useState([emptyBlock(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [paceZones, setPaceZones] = useState(null);

  useEffect(() => {
    if (!open) return;
    getPaceZones()
      .then((res) => setPaceZones(res.data))
      .catch(() => setPaceZones(null));
  }, [open]);

  useEffect(() => {
    if (open && editWorkout) {
      const { form: f, blocks: b } = workoutToFormState(editWorkout);
      setForm(f); setBlocks(b); setError('');
    } else if (open && !editWorkout) {
      setForm(INITIAL_FORM); setBlocks([emptyBlock(1)]); setError('');
    }
  }, [open, editWorkout]);

  const totals = useMemo(() => computeTotals(blocks, paceZones), [blocks, paceZones]);

  const resetState = useCallback(() => {
    setForm(INITIAL_FORM); setBlocks([emptyBlock(1)]); setSaving(false); setError('');
  }, []);

  const handleClose = () => { resetState(); onClose(); };
  const setField = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  // Block operations
  const addSimpleStep = () => setBlocks((prev) => [...prev, emptyBlock(prev.length + 1)]);
  const addRepeatedBlock = () => setBlocks((prev) => [
    ...prev,
    { ...emptyBlock(prev.length + 1), isRepeated: true, repetitions: 4, intervals: [emptyInterval(), emptyInterval()] },
  ]);
  const removeBlock = (bIdx) => setBlocks((prev) =>
    prev.filter((_, i) => i !== bIdx).map((b, i) => ({ ...b, order_index: i + 1 }))
  );
  const moveBlock = (bIdx, dir) => setBlocks((prev) => {
    const next = [...prev];
    const target = bIdx + dir;
    if (target < 0 || target >= next.length) return prev;
    [next[bIdx], next[target]] = [next[target], next[bIdx]];
    return next.map((b, i) => ({ ...b, order_index: i + 1 }));
  });
  const setBlockField = (bIdx, key, value) =>
    setBlocks((prev) => prev.map((b, i) => i === bIdx ? { ...b, [key]: value } : b));

  const setIntervalValue = (bIdx, iIdx, key, value) =>
    setBlocks((prev) => prev.map((b, bi) => {
      if (bi !== bIdx) return b;
      return { ...b, intervals: b.intervals.map((iv, ii) => ii === iIdx ? { ...iv, [key]: value } : iv) };
    }));
  const addInterval = (bIdx) =>
    setBlocks((prev) => prev.map((b, i) => i !== bIdx ? b : { ...b, intervals: [...b.intervals, emptyInterval()] }));
  const removeInterval = (bIdx, iIdx) =>
    setBlocks((prev) => prev.map((b, i) =>
      i !== bIdx ? b : { ...b, intervals: b.intervals.filter((_, ii) => ii !== iIdx) }
    ));

  // Submit
  const handleSubmit = async () => {
    if (!form.name.trim()) { setError('El nombre del entrenamiento es obligatorio.'); return; }
    if (blocks.length === 0) { setError('Agrega al menos un paso.'); return; }
    setSaving(true); setError('');
    try {
      const workoutPayload = {
        name: form.name.trim(),
        description: form.description.trim(),
        discipline: form.discipline,
        session_type: form.session_type,
        ...(form.difficulty && { difficulty: form.difficulty }),
        ...(form.elevation_gain_min_m && { elevation_gain_min_m: Number(form.elevation_gain_min_m) }),
        ...(form.elevation_gain_max_m && { elevation_gain_max_m: Number(form.elevation_gain_max_m) }),
        ...(totals.totalSeconds > 0 && { estimated_duration_seconds: Math.round(totals.totalSeconds) }),
        ...(totals.totalMeters > 0 && { estimated_distance_meters: Math.round(totals.totalMeters) }),
      };

      let workoutId, workoutData;
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
          const hasZone = !!iv.zone;
          const ivPayload = {
            order_index: idx + 1,
            repetitions: Number(iv.repetitions) || 1,
            metric_type: hasZone ? 'hr_zone' : (iv.metric_type || 'free'),
            ...(iv.description.trim() && { description: iv.description.trim() }),
            ...(iv.measure === 'tiempo' && iv.duration_seconds && { duration_seconds: Number(iv.duration_seconds) }),
            ...(iv.measure === 'distancia' && iv.distance_meters && { distance_meters: Number(iv.distance_meters) }),
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
      if (!data) setError('Error al guardar el entrenamiento.');
      else if (typeof data === 'string') setError(data);
      else if (data.detail) setError(data.detail);
      else {
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
      {/* ── Header ── */}
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
              Quantoryn ·{' '}
              {paceZones
                ? paceZones.has_threshold
                  ? `Umbral ${paceZones.threshold_pace_display} personalizado`
                  : 'Zonas estimadas — configura umbral en tu perfil para mayor precisión'
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
          <div className="flex-1 overflow-y-auto" style={{ minWidth: 0 }}>

            {/* Section 1: General Info */}
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
                Información General
              </p>
              <div className="flex flex-col gap-3">
                <TextField
                  label="Nombre del entrenamiento *"
                  value={form.name}
                  onChange={setField('name')}
                  fullWidth size="small"
                  placeholder="Ej: Intervalos 4×1000m Z4"
                  sx={{
                    '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' },
                    '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' },
                  }}
                />
                <div className="grid grid-cols-2 gap-3">
                  <TextField
                    select label="Deporte" value={form.discipline} onChange={setField('discipline')} size="small"
                    sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' } }}
                  >
                    {SPORT_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                  </TextField>
                  <TextField
                    select label="Tipo de sesión" value={form.session_type} onChange={setField('session_type')} size="small"
                    sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' } }}
                  >
                    {SESSION_TYPE_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                  </TextField>
                </div>
                {/* Difficulty + D+ row */}
                <div className="grid grid-cols-2 gap-3">
                  <TextField
                    select label="Dificultad" value={form.difficulty} onChange={setField('difficulty')} size="small"
                    sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' } }}
                  >
                    <MenuItem value="">Sin definir</MenuItem>
                    <MenuItem value="easy">🟢 Fácil</MenuItem>
                    <MenuItem value="moderate">🟡 Moderado</MenuItem>
                    <MenuItem value="hard">🟠 Difícil</MenuItem>
                    <MenuItem value="very_hard">🔴 Muy difícil</MenuItem>
                  </TextField>
                  {/* D+ only for trail/run */}
                  {(form.discipline === 'trail' || form.discipline === 'run') ? (
                    <div className="flex gap-1 items-center">
                      <TextField
                        label="D+ mín (m)" type="number" size="small"
                        value={form.elevation_gain_min_m}
                        onChange={setField('elevation_gain_min_m')}
                        inputProps={{ min: 0, step: 50 }}
                        sx={{ flex: 1, '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' } }}
                      />
                      <span className="text-slate-400 text-sm flex-shrink-0">–</span>
                      <TextField
                        label="D+ máx (m)" type="number" size="small"
                        value={form.elevation_gain_max_m}
                        onChange={setField('elevation_gain_max_m')}
                        inputProps={{ min: 0, step: 50 }}
                        sx={{ flex: 1, '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' } }}
                      />
                    </div>
                  ) : (
                    <div /> /* empty cell to keep grid */
                  )}
                </div>
                <TextField
                  label="Notas para el atleta"
                  value={form.description} onChange={setField('description')}
                  fullWidth size="small" multiline minRows={3} maxRows={10}
                  placeholder="Objetivo del entrenamiento, instrucciones adicionales para el atleta…"
                  sx={{
                    '& .MuiOutlinedInput-root': { borderRadius: '8px', bgcolor: 'white' },
                    '& .MuiOutlinedInput-root.Mui-focused fieldset': { borderColor: '#f59e0b' },
                    '& textarea': { resize: 'vertical', minHeight: 60 },
                  }}
                />
                {/* Totals */}
                <div className="flex gap-4 px-3 py-2 bg-white rounded-lg border border-slate-200 flex-wrap">
                  <div>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">Duración est.</p>
                    <p className="text-sm font-bold text-slate-700">{totals.durationLabel}</p>
                  </div>
                  <div className="w-px bg-slate-200" />
                  <div>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">Distancia est.</p>
                    <p className="text-sm font-bold text-slate-700">{totals.distanceLabel}</p>
                  </div>
                  <div className="w-px bg-slate-200" />
                  <div>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">Carga</p>
                    <p className="text-sm font-bold text-slate-700">{totals.loadLabel}</p>
                  </div>
                  <div className="w-px bg-slate-200" />
                  <Tooltip title="Training Stress Score estimado (rTSS basado en zonas de ritmo)" arrow>
                    <div style={{ cursor: 'default' }}>
                      <p className="text-xs text-slate-400 uppercase tracking-wide">TSS ~</p>
                      <p className="text-sm font-bold text-blue-700">{totals.tssLabel}</p>
                    </div>
                  </Tooltip>
                  <div className="w-px bg-slate-200" />
                  <Tooltip title="Intensity Factor — ratio de intensidad promedio ponderado por zona (IF = √(NP²×t / t_total))" arrow>
                    <div style={{ cursor: 'default' }}>
                      <p className="text-xs text-slate-400 uppercase tracking-wide">IF</p>
                      <p className="text-sm font-bold text-indigo-700">{totals.ifLabel}</p>
                    </div>
                  </Tooltip>
                </div>
              </div>
            </div>

            {/* Section 2: Steps */}
            <div className="px-5 pt-4 pb-2 flex items-center justify-between">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                Pasos del entrenamiento
                <span className="ml-1.5 px-1.5 py-0.5 bg-slate-200 rounded text-slate-600">
                  {blocks.length}
                </span>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={addSimpleStep}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-50 transition-colors"
                >
                  <AddIcon sx={{ fontSize: 14 }} />
                  Agregar paso
                </button>
                <button
                  onClick={addRepeatedBlock}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-purple-700 border border-purple-300 rounded-lg hover:bg-purple-50 transition-colors"
                >
                  <RepeatIcon sx={{ fontSize: 14 }} />
                  Bloque repetido
                </button>
              </div>
            </div>

            {/* Column headers */}
            <div className="flex items-center gap-2 px-3 py-1.5 border-y border-slate-100 bg-slate-50">
              <div style={{ width: 16 }} />
              <div style={{ width: 18 }} />
              <div style={{ minWidth: 140, flex: '0 0 140px' }}
                className="text-xs font-semibold text-slate-400 uppercase tracking-wide">TIPO</div>
              <div className="flex-1 text-xs font-semibold text-slate-400 uppercase tracking-wide">DESCRIPCIÓN</div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide" style={{ width: 118 }}>OBJETIVO</div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide" style={{ width: 168 }}>
                {form.discipline === 'bike' ? 'ZONA FC' : form.discipline === 'strength' || form.discipline === 'mobility' ? 'CARGA' : 'ZONA RITMO'}
              </div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide" style={{ width: 80 }}>RECUP.</div>
              <div style={{ width: 72 }} />
            </div>

            {/* Steps list */}
            {blocks.length === 0 ? (
              <div className="py-16 text-center">
                <FitnessCenterIcon sx={{ fontSize: 40, color: '#cbd5e1' }} />
                <p className="text-sm font-semibold text-slate-500 mt-3">Sin pasos aún</p>
                <p className="text-xs text-slate-400 mt-1">Agrega un paso simple o un bloque de intervalos repetidos.</p>
              </div>
            ) : (
              <div className="border-b border-slate-100">
                {blocks.map((block, bIdx) => {
                  if (!block.isRepeated) {
                    const iv = block.intervals[0] ?? emptyInterval();
                    return (
                      <SimpleStepRow
                        key={bIdx}
                        block={block}
                        bIdx={bIdx}
                        iv={iv}
                        isFirst={bIdx === 0}
                        isLast={bIdx === blocks.length - 1}
                        paceZones={paceZones}
                        discipline={form.discipline}
                        onSetBlock={setBlockField}
                        onSetInterval={setIntervalValue}
                        onMove={moveBlock}
                        onRemove={removeBlock}
                      />
                    );
                  }
                  return (
                    <div key={bIdx}>
                      <RepeatedBlockHeader
                        block={block}
                        bIdx={bIdx}
                        isFirst={bIdx === 0}
                        isLast={bIdx === blocks.length - 1}
                        onSetBlock={setBlockField}
                        onMove={moveBlock}
                        onRemove={removeBlock}
                        onAddInterval={addInterval}
                      />
                      {block.intervals.map((iv, iIdx) => (
                        <SubStepRow
                          key={iIdx}
                          iv={iv}
                          iIdx={iIdx}
                          bIdx={bIdx}
                          isOnly={block.intervals.length === 1}
                          paceZones={paceZones}
                          discipline={form.discipline}
                          onSetValue={setIntervalValue}
                          onRemove={removeInterval}
                        />
                      ))}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Intensity histogram */}
            {blocks.length > 0 && (
              <div className="mx-5 my-4 px-4 py-3 bg-slate-50 rounded-xl border border-slate-200">
                <IntensityHistogram blocks={blocks} paceZones={paceZones} />
              </div>
            )}
          </div>

          {/* ── RIGHT: Zone reference panel ── */}
          <div
            className="flex-shrink-0 overflow-y-auto border-l border-slate-100 px-4 py-4 bg-slate-50"
            style={{ width: 210 }}
          >
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Zonas de Ritmo
            </p>
            {ZONES.filter((z) => z.value).map((z) => {
              const zData = paceZones?.zones?.[z.value];
              return (
                <div key={z.value} className="mb-3.5">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: z.color }} />
                    <span className="text-xs font-bold" style={{ color: z.color }}>{z.label}</span>
                    <span className="text-xs font-semibold text-slate-600">{z.name}</span>
                  </div>
                  <p className="text-xs text-slate-500 pl-4">
                    {zData ? `${zData.pace_min} – ${zData.pace_max}` : '—'}
                  </p>
                  {zData && <p className="text-xs text-slate-400 pl-4">{zData.description}</p>}
                </div>
              );
            })}
            {paceZones && !paceZones.has_threshold && (
              <Alert severity="info" sx={{ mt: 2, fontSize: '0.7rem', p: '4px 8px' }}>
                Configura tu ritmo umbral en el perfil para personalizar las zonas.
              </Alert>
            )}
          </div>
        </div>
      </DialogContent>

      {/* ── Footer ── */}
      <DialogActions sx={{
        px: 3, py: 2,
        borderTop: '1px solid',
        borderColor: 'grey.100',
        justifyContent: 'space-between',
      }}>
        <Button
          onClick={handleClose}
          disabled={saving}
          variant="outlined"
          sx={{ borderRadius: 2, textTransform: 'none', borderColor: '#e2e8f0', color: '#64748b' }}
        >
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={saving}
          variant="contained"
          sx={{
            borderRadius: 2,
            minWidth: 210,
            bgcolor: '#f59e0b',
            '&:hover': { bgcolor: '#d97706' },
            '&.Mui-disabled': { bgcolor: '#fed7aa' },
            textTransform: 'none',
            fontWeight: 600,
          }}
        >
          {saving
            ? <><CircularProgress size={16} color="inherit" sx={{ mr: 1 }} />Guardando…</>
            : (isEditMode ? 'Guardar cambios →' : 'Guardar entrenamiento →')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
