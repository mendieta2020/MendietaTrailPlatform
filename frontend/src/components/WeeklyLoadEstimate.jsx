/**
 * WeeklyLoadEstimate — PR-158
 *
 * Displays planned TSS + phase recommendation for the week being planned.
 * Color-coded: green (within range), amber (10-20% over), red (>20% over).
 *
 * Props:
 *   membershipId  — athlete membership ID (for individual athlete context)
 *   weekStart     — Monday of target week (YYYY-MM-DD)
 *   trigger       — increments each time data should be re-fetched (after
 *                   adding/removing a workout)
 */
import React, { useState, useEffect } from 'react';
import { Box, Typography, Chip, CircularProgress } from '@mui/material';
import { getEstimatedWeeklyLoad } from '../api/planning';

function statusColor(status) {
  if (status === 'over')  return '#ef4444';
  if (status === 'under') return '#f59e0b';
  return '#22c55e';
}

function statusBg(status) {
  if (status === 'over')  return 'rgba(239,68,68,0.08)';
  if (status === 'under') return 'rgba(245,158,11,0.08)';
  return 'rgba(34,197,94,0.08)';
}

const PHASE_LABEL = {
  carga: 'CARGA',
  descarga: 'DESCARGA',
  carrera: 'CARRERA',
  descanso: 'DESCANSO',
  lesion: 'LESIÓN',
};

const PHASE_COLOR = {
  carga: '#f97316',
  descarga: '#22c55e',
  carrera: '#ef4444',
  descanso: '#3b82f6',
  lesion: '#6b7280',
};

export default function WeeklyLoadEstimate({ membershipId, weekStart, trigger }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!membershipId || !weekStart) return;
    let cancelled = false;
    getEstimatedWeeklyLoad(membershipId, { weekStart })
      .then((res) => { if (!cancelled) { setData(res.data); setLoading(false); } })
      .catch(() => { if (!cancelled) { setData(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [membershipId, weekStart, trigger]);

  if (!membershipId) return null;

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.75 }}>
        <CircularProgress size={14} sx={{ color: '#00D4AA' }} />
        <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
          Calculando carga estimada…
        </Typography>
      </Box>
    );
  }

  if (!data) return null;

  const {
    planned_tss, planned_sessions, planned_distance_km, planned_duration_min,
    current_phase, recommended_tss_range, load_status, load_message,
  } = data;

  const phaseLabel = current_phase ? PHASE_LABEL[current_phase] : null;
  const phaseColor = current_phase ? PHASE_COLOR[current_phase] : '#94a3b8';
  const color = statusColor(load_status);
  const bg = statusBg(load_status);

  const durationH = Math.floor(planned_duration_min / 60);
  const durationM = planned_duration_min % 60;
  const durationStr = durationH > 0
    ? `${durationH}h${durationM > 0 ? ` ${durationM}min` : ''}`
    : `${durationM}min`;

  return (
    <Box
      sx={{
        mt: 1,
        px: 2,
        py: 1,
        borderRadius: 1.5,
        bgcolor: bg,
        border: `1px solid ${color}33`,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
        {/* TSS badge */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
            TSS estimado:
          </Typography>
          <Typography
            variant="caption"
            sx={{ fontWeight: 700, color, fontSize: '0.75rem' }}
          >
            {Math.round(planned_tss)}
          </Typography>
        </Box>

        {/* Phase chip */}
        {phaseLabel && (
          <Chip
            label={phaseLabel}
            size="small"
            sx={{
              height: 18,
              fontSize: '0.6rem',
              fontWeight: 700,
              bgcolor: `${phaseColor}22`,
              color: phaseColor,
              border: `1px solid ${phaseColor}44`,
              '& .MuiChip-label': { px: 0.75 },
            }}
          />
        )}

        {/* Recommended range */}
        {recommended_tss_range && (
          <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
            Recomendado: {Math.round(recommended_tss_range.min)}–{Math.round(recommended_tss_range.max)} TSS
          </Typography>
        )}

        {/* Summary */}
        {planned_sessions > 0 && (
          <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
            {planned_sessions} ses · {planned_distance_km}km · {durationStr}
          </Typography>
        )}
      </Box>

      {/* Alert message */}
      {load_message && (
        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 0.5, color, fontSize: '0.67rem', fontWeight: 500 }}
        >
          {load_status === 'over' ? '⚠ ' : load_status === 'under' ? '↓ ' : ''}{load_message}
        </Typography>
      )}
    </Box>
  );
}
