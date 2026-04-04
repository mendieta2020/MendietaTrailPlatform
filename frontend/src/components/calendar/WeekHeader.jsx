/**
 * WeekHeader.jsx — Week summary row with Plan vs Real bar + phase badge (PR-163)
 *
 * Props:
 *   planVsReal       — { planned, actual, compliance_pct } | null
 *   weekAssignments  — raw assignment array for this week
 *   pmcData          — { ctl, atl, tsb } | null
 *   trainingPhase    — 'carga' | 'descarga' | 'carrera' | 'descanso' | 'lesion' | null
 */
import React from 'react';
import { Box, Typography, Chip } from '@mui/material';
import { TRAINING_PHASE_CONFIG } from '../../utils/calendarHelpers';

function PlanVsRealBar({ planVsReal }) {
  if (!planVsReal?.planned || planVsReal.planned.sessions === 0) return null;
  const { planned, actual, compliance_pct } = planVsReal;
  const pct = compliance_pct ?? 0;
  const barColor = pct >= 90 ? '#16a34a' : pct >= 70 ? '#d97706' : '#dc2626';

  return (
    <Box sx={{ px: 2, pt: 0.5, pb: 0.25, bgcolor: '#f0fdf4', borderBottom: '1px solid #e2e8f0' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.25 }}>
        <Typography variant="caption" sx={{ color: '#374151', fontSize: '0.67rem', fontWeight: 600 }}>Plan:</Typography>
        <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
          {planned.sessions} ses · {planned.distance_km}km · {planned.duration_min}min
          {planned.elevation_m > 0 ? ` · D+${planned.elevation_m}m` : ''}
        </Typography>
        <Typography variant="caption" sx={{ color: '#374151', fontSize: '0.67rem', fontWeight: 600 }}>Real:</Typography>
        <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
          {actual.sessions} ses · {actual.distance_km}km · {actual.duration_min}min
          {actual.elevation_m > 0 ? ` · D+${actual.elevation_m}m` : ''}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ flex: 1, height: 4, borderRadius: 2, bgcolor: '#e2e8f0', overflow: 'hidden' }}>
          <Box sx={{ height: '100%', width: `${Math.min(100, pct)}%`, bgcolor: barColor, borderRadius: 2, transition: 'width 0.4s ease' }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: barColor, fontSize: '0.67rem', minWidth: 34 }}>
          {pct}%
        </Typography>
      </Box>
    </Box>
  );
}

function WeekSummaryRow({ weekAssignments, pmcData, trainingPhase }) {
  if (weekAssignments.length === 0 && !trainingPhase && !pmcData) return null;

  const done = weekAssignments.filter((a) => a.status === 'completed').length;
  const total = weekAssignments.length;
  const totalKm = weekAssignments.reduce((s, a) => s + ((a.planned_workout?.estimated_distance_meters ?? 0) / 1000), 0);
  const totalDPlus = weekAssignments.reduce((s, a) => s + (a.planned_workout?.elevation_gain_min_m ?? 0), 0);
  const totalTSS = weekAssignments.reduce((s, a) => s + (a.planned_workout?.planned_tss ?? 0), 0);

  const parts = total > 0 ? [`${done} de ${total} entrenamientos`] : [];
  if (totalKm > 0.1) parts.push(`${totalKm.toFixed(1)}km`);
  if (totalDPlus > 0) parts.push(`${Math.round(totalDPlus)}m D+`);
  if (totalTSS > 0) parts.push(`TSS: ${Math.round(totalTSS)}`);

  const tsbVal = pmcData?.tsb;
  const tsbColor = tsbVal == null ? '#94a3b8' : tsbVal > 0 ? '#16a34a' : tsbVal < -20 ? '#dc2626' : '#d97706';

  const phaseMeta = trainingPhase ? TRAINING_PHASE_CONFIG[trainingPhase] : null;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 2, py: 0.75,
        bgcolor: '#f8fafc',
        borderTop: '1px solid #e2e8f0',
        borderBottom: '1px solid #e2e8f0',
        flexWrap: 'wrap',
        gap: 1,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {phaseMeta && (
          <Box
            sx={{
              display: 'flex', alignItems: 'center', gap: 0.4,
              px: 0.75, py: 0.15,
              borderRadius: 1,
              bgcolor: `${phaseMeta.color}18`,
              border: `1px solid ${phaseMeta.color}44`,
            }}
          >
            <Typography sx={{ fontSize: '0.58rem' }}>{phaseMeta.emoji}</Typography>
            <Typography sx={{ fontSize: '0.58rem', fontWeight: 700, color: phaseMeta.color, letterSpacing: 0.3 }}>
              {phaseMeta.label}
            </Typography>
          </Box>
        )}
        {parts.length > 0 && (
          <Typography variant="caption" sx={{ color: '#475569', fontSize: '0.7rem', fontWeight: 500 }}>
            {parts.join(' · ')}
          </Typography>
        )}
      </Box>
      {pmcData && (
        <Box sx={{ display: 'flex', gap: 0.75 }}>
          <Chip
            label={`CTL ${pmcData.ctl?.toFixed(0) ?? '—'}`}
            size="small"
            sx={{ height: 18, fontSize: '0.6rem', bgcolor: '#dbeafe', color: '#1d4ed8', fontWeight: 600, '& .MuiChip-label': { px: 0.75 } }}
          />
          <Chip
            label={`ATL ${pmcData.atl?.toFixed(0) ?? '—'}`}
            size="small"
            sx={{ height: 18, fontSize: '0.6rem', bgcolor: '#fce7f3', color: '#9d174d', fontWeight: 600, '& .MuiChip-label': { px: 0.75 } }}
          />
          <Chip
            label={`Forma ${tsbVal != null ? tsbVal.toFixed(0) : '—'}`}
            size="small"
            sx={{ height: 18, fontSize: '0.6rem', bgcolor: '#f1f5f9', color: tsbColor, fontWeight: 700, '& .MuiChip-label': { px: 0.75 } }}
          />
        </Box>
      )}
    </Box>
  );
}

export default function WeekHeader({ planVsReal, weekAssignments, pmcData, trainingPhase }) {
  const hasPvr = planVsReal?.planned?.sessions > 0;
  const hasSummary = weekAssignments.length > 0 || trainingPhase || pmcData;
  if (!hasPvr && !hasSummary) return null;

  return (
    <>
      {hasPvr && <PlanVsRealBar planVsReal={planVsReal} />}
      {hasSummary && (
        <WeekSummaryRow weekAssignments={weekAssignments} pmcData={pmcData} trainingPhase={trainingPhase} />
      )}
    </>
  );
}
