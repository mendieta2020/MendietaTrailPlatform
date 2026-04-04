import React from 'react';
import {
  Drawer, Box, Typography, IconButton, Divider, Chip, Button,
  useMediaQuery, useTheme,
} from '@mui/material';
import { Close, StickyNote2, ArrowBack } from '@mui/icons-material';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

// ── Sport colors / labels (mirrors AthleteMyTraining) ─────────────────────────

const SPORT_COLOR = {
  trail:    '#f97316',
  run:      '#22c55e',
  bike:     '#3b82f6',
  cycling:  '#3b82f6',
  strength: '#a855f7',
  mobility: '#06b6d4',
  other:    '#94a3b8',
};

const SPORT_LABEL = {
  trail:    'Trail Running',
  run:      'Running',
  bike:     'Ciclismo',
  cycling:  'Ciclismo',
  strength: 'Fuerza',
  mobility: 'Movilidad',
  swim:     'Natación',
  other:    'Otro',
};

const DIFFICULTY_LABEL = {
  easy:      '🟢 Fácil',
  moderate:  '🟡 Moderado',
  hard:      '🟠 Difícil',
  very_hard: '🔴 Muy difícil',
};

const BLOCK_TYPE_COLOR = {
  warmup:   '#fb923c',
  main:     '#3b82f6',
  drill:    '#8b5cf6',
  custom:   '#eab308',
  recovery_step: '#94a3b8',
  cooldown: '#84cc16',
  strength: '#c084fc',
  repeat:   '#f59e0b',
  free:     '#64748b',
};

const BLOCK_TYPE_LABEL = {
  warmup:   'Calentamiento',
  main:     'Fondo / Base',
  drill:    'Intensivo',
  custom:   'Tempo',
  recovery_step: 'Recuperación',
  cooldown: 'Vuelta calma',
  strength: 'Fuerza',
  repeat:   'Bloque repetido',
  free:     'Libre',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(seconds) {
  if (!seconds) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m > 0 ? m + 'min' : ''}`.trim();
  return `${m}min`;
}

function fmtDistance(meters) {
  if (!meters) return null;
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}km`;
  return `${meters}m`;
}

function fmtDateLong(dateStr) {
  if (!dateStr) return '';
  try {
    return format(parseISO(dateStr), "EEEE d 'de' MMMM", { locale: es });
  } catch {
    return dateStr;
  }
}

function fmtIntervalDuration(iv) {
  if (iv.duration_seconds) {
    return fmtDuration(iv.duration_seconds);
  }
  if (iv.distance_meters) {
    return fmtDistance(iv.distance_meters);
  }
  if (iv.target_label) return iv.target_label;
  return null;
}

// ── Metric chip ───────────────────────────────────────────────────────────────

function MetricChip({ icon, value, label }) {
  if (!value) return null;
  return (
    <Box
      sx={{
        display: 'flex', alignItems: 'center', gap: 0.5,
        px: 1.5, py: 0.75, bgcolor: '#f8fafc',
        border: '1px solid #e2e8f0', borderRadius: 2,
        minWidth: 80,
      }}
    >
      <Typography variant="caption" sx={{ fontSize: '1rem', lineHeight: 1 }}>{icon}</Typography>
      <Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: '#1e293b', display: 'block', lineHeight: 1 }}>{value}</Typography>
        <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.6rem' }}>{label}</Typography>
      </Box>
    </Box>
  );
}

// ── Step row ─────────────────────────────────────────────────────────────────

function IntervalRow({ iv, index, isStrength }) {
  const duration = fmtIntervalDuration(iv);
  const zone = iv.target_label && ['Z1','Z2','Z3','Z4','Z5'].includes(iv.target_label.trim().toUpperCase())
    ? iv.target_label.trim().toUpperCase()
    : null;

  const zoneColors = { Z1: '#94a3b8', Z2: '#22c55e', Z3: '#eab308', Z4: '#f97316', Z5: '#ef4444' };

  if (isStrength) {
    // Fuerza: show target_label as sets×reps@weight
    const label = iv.target_label || [
      iv.repetitions > 1 ? `${iv.repetitions} series` : null,
      iv.target_value_low ? `${iv.target_value_low} reps` : null,
      iv.target_value_high ? `@ ${iv.target_value_high}kg` : null,
    ].filter(Boolean).join(' · ');

    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, py: 1, borderBottom: '1px solid #f1f5f9' }}>
        <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, minWidth: 16 }}>{String.fromCharCode(64 + index + 1)}</Typography>
        <Box sx={{ flex: 1 }}>
          {iv.description && (
            <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b', fontSize: '0.8rem' }}>{iv.description}</Typography>
          )}
          {label && (
            <Typography variant="caption" sx={{ color: '#475569' }}>{label}</Typography>
          )}
          {iv.recovery_seconds > 0 && (
            <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block' }}>
              Descanso: {iv.recovery_seconds < 60 ? `${iv.recovery_seconds}s` : `${Math.round(iv.recovery_seconds / 60)}min`}
            </Typography>
          )}
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, py: 1, borderBottom: '1px solid #f1f5f9' }}>
      <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, minWidth: 16 }}>{String.fromCharCode(64 + index + 1)}</Typography>
      <Box sx={{ flex: 1 }}>
        {iv.description && (
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b', fontSize: '0.8rem' }}>{iv.description}</Typography>
        )}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 0.25 }}>
          {duration && (
            <Typography variant="caption" sx={{ color: '#475569' }}>{duration}</Typography>
          )}
          {zone && (
            <Box component="span" sx={{ px: 0.75, py: 0.1, borderRadius: 1, bgcolor: `${zoneColors[zone]}18`, color: zoneColors[zone], fontSize: '0.65rem', fontWeight: 700 }}>
              {zone}
            </Box>
          )}
          {iv.recovery_seconds > 0 && (
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>
              rec {iv.recovery_seconds < 60 ? `${iv.recovery_seconds}s` : `${Math.round(iv.recovery_seconds / 60)}min`}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
}

function BlockSection({ block, isStrength }) {
  const color = BLOCK_TYPE_COLOR[block.block_type] ?? '#94a3b8';
  const label = BLOCK_TYPE_LABEL[block.block_type] ?? block.block_type;
  const reps = block.repetitions > 1 ? block.repetitions : null;

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <Box sx={{ width: 3, height: 16, borderRadius: 2, bgcolor: color }} />
        <Typography variant="caption" sx={{ fontWeight: 700, color, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: 0.3 }}>
          {reps ? `${reps}× ` : ''}{block.name || label}
        </Typography>
      </Box>
      {(block.intervals ?? []).map((iv, iIdx) => (
        <IntervalRow key={iIdx} iv={iv} index={iIdx} isStrength={isStrength} />
      ))}
    </Box>
  );
}

// ── WorkoutDetailDrawer ────────────────────────────────────────────────────────

export default function WorkoutDetailDrawer({ assignment, onClose, onMarkComplete }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const open = !!assignment;

  const pw = assignment?.planned_workout;
  const discipline = pw?.discipline ?? 'other';
  const color = SPORT_COLOR[discipline] ?? '#94a3b8';
  const isStrength = discipline === 'strength' || discipline === 'mobility';
  const isCompleted = assignment?.status === 'completed';

  const duration = fmtDuration(pw?.estimated_duration_seconds);
  const distance = fmtDistance(pw?.estimated_distance_meters);
  const dplus = pw?.elevation_gain_min_m;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: isMobile ? '100%' : 480,
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 3, pt: 3, pb: 2,
          borderBottom: '1px solid #e2e8f0',
          borderLeft: `4px solid ${color}`,
          bgcolor: '#fafafa',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ flex: 1, mr: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#1e293b', lineHeight: 1.3 }}>
              {pw?.name ?? 'Entrenamiento'}
            </Typography>
            <Typography
              variant="caption"
              sx={{ color, fontWeight: 700, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: 0.4 }}
            >
              {SPORT_LABEL[discipline] ?? discipline}
            </Typography>
          </Box>
          <IconButton size="small" onClick={onClose} sx={{ color: '#94a3b8' }}>
            {isMobile ? <ArrowBack fontSize="small" /> : <Close fontSize="small" />}
          </IconButton>
        </Box>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          {assignment?.scheduled_date && (
            <Typography variant="caption" sx={{ color: '#64748b', textTransform: 'capitalize' }}>
              {fmtDateLong(assignment.scheduled_date)}
            </Typography>
          )}
          {pw?.difficulty && (
            <Chip
              label={DIFFICULTY_LABEL[pw.difficulty] ?? pw.difficulty}
              size="small"
              sx={{ height: 20, fontSize: '0.65rem', '& .MuiChip-label': { px: 0.75 } }}
            />
          )}
        </Box>
      </Box>

      {/* Scrollable body */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 3, py: 2 }}>

        {/* Metric chips */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2.5 }}>
          <MetricChip icon="⏱" value={duration} label="Duración" />
          <MetricChip icon="📍" value={distance} label="Distancia" />
          {dplus > 0 && <MetricChip icon="⛰" value={`${dplus}m`} label="D+" />}
          {pw?.planned_tss > 0 && <MetricChip icon="💪" value={`TSS: ${pw.planned_tss}`} label="Carga est." />}
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Coach notes */}
        {assignment?.coach_notes && (
          <Box
            sx={{
              mb: 2.5, p: 1.5, borderRadius: 2,
              bgcolor: '#fffbeb', border: '1px solid #fde68a',
            }}
          >
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
              <StickyNote2 sx={{ color: '#d97706', fontSize: 16, mt: 0.1 }} />
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 700, color: '#d97706', display: 'block', mb: 0.25 }}>
                  Notas del coach
                </Typography>
                <Typography variant="body2" sx={{ color: '#78350f', fontSize: '0.8rem', whiteSpace: 'pre-wrap' }}>
                  {assignment.coach_notes}
                </Typography>
              </Box>
            </Box>
          </Box>
        )}

        {/* Description / workout notes */}
        {pw?.description && (
          <Box sx={{ mb: 2.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
              Objetivo
            </Typography>
            <Typography variant="body2" sx={{ color: '#475569', fontSize: '0.8rem', whiteSpace: 'pre-wrap' }}>
              {pw.description}
            </Typography>
          </Box>
        )}

        {/* Workout steps */}
        {pw?.blocks && pw.blocks.length > 0 && (
          <Box>
            <Typography
              variant="caption"
              sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 1.5 }}
            >
              Pasos del entrenamiento
              <Box component="span" sx={{ ml: 1, px: 1, py: 0.15, bgcolor: '#f1f5f9', borderRadius: 1, color: '#64748b', fontSize: '0.6rem' }}>
                {pw.blocks.length}
              </Box>
            </Typography>
            {pw.blocks.map((block, bIdx) => (
              <BlockSection key={block.id ?? bIdx} block={block} isStrength={isStrength} />
            ))}
          </Box>
        )}
      </Box>

      {/* Footer actions */}
      <Box
        sx={{
          px: 3, py: 2,
          borderTop: '1px solid #e2e8f0',
          bgcolor: '#fafafa',
        }}
      >
        {isCompleted ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box
              sx={{
                px: 2, py: 1, borderRadius: 2, bgcolor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                display: 'flex', alignItems: 'center', gap: 0.75,
              }}
            >
              <Typography variant="body2" sx={{ color: '#16a34a', fontWeight: 700 }}>
                ✓ Completado
              </Typography>
            </Box>
          </Box>
        ) : (
          <Button
            fullWidth
            variant="contained"
            onClick={() => onMarkComplete(assignment)}
            sx={{
              borderRadius: 2,
              bgcolor: color,
              '&:hover': { bgcolor: color, filter: 'brightness(0.92)' },
              textTransform: 'none',
              fontWeight: 600,
            }}
          >
            Marcar como completado
          </Button>
        )}
      </Box>
    </Drawer>
  );
}
