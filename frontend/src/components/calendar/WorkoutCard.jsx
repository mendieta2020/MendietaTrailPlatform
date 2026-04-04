/**
 * WorkoutCard.jsx — Shared workout card for athlete + coach month grid (PR-163)
 *
 * Props:
 *   assignment  — raw assignment object from API
 *   role        — 'athlete' | 'coach'
 *   isToday     — boolean: day cell is today (orange left accent)
 *   isPast      — boolean: day is in the past (red tint for unfinished)
 *   onClick     — (assignment) => void
 *   onCompleteClick — (assignment) => void  [athlete only]
 *   onContextMenu   — (x, y, assignment) => void  [coach only]
 *   onDragStart     — (e, assignment) => void  [coach only]
 *   onDragEnd       — (e) => void  [coach only]
 */
import React from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { Tooltip } from '@mui/material';
import { ChatBubbleOutline } from '@mui/icons-material';
import { MiniWorkoutProfile } from '../MiniWorkoutProfile';
import { weatherChip } from '../../hooks/useWeatherIcon';
import {
  sportColor, sportLabel, fmtDuration, fmtDistance,
  computeCompliancePct, getComplianceStyle,
} from '../../utils/calendarHelpers';

const RPE_EMOJI = { 1: '😴', 2: '😐', 3: '🙂', 4: '💪', 5: '🔥' };

export default function WorkoutCard({
  assignment,
  role = 'athlete',
  isPast = false,
  onClick,
  onCompleteClick,
  onContextMenu,
  onDragStart,
  onDragEnd,
}) {
  const pw = assignment.planned_workout;
  const discipline = pw?.discipline ?? 'other';
  const color = sportColor(discipline);
  const isCompleted = assignment.status === 'completed';

  // Metrics: prefer actual when completed
  const hasDuration = isCompleted && assignment.actual_duration_seconds != null;
  const hasDistance = isCompleted && assignment.actual_distance_meters != null;
  const hasElevation = isCompleted && assignment.actual_elevation_gain != null;

  const duration = hasDuration
    ? fmtDuration(assignment.actual_duration_seconds)
    : fmtDuration(pw?.estimated_duration_seconds);
  const distance = hasDistance
    ? fmtDistance(assignment.actual_distance_meters)
    : fmtDistance(pw?.estimated_distance_meters);
  const dplus = hasElevation
    ? assignment.actual_elevation_gain
    : pw?.elevation_gain_min_m;

  const metricsLabel = isCompleted && (hasDuration || hasDistance || hasElevation)
    ? `Real: ${[duration, distance, dplus ? `${dplus}m D+` : null].filter(Boolean).join(' · ')}`
    : [duration, distance, dplus ? `${dplus}m D+` : null].filter(Boolean).join(' · ') || '—';

  const pct = isCompleted ? computeCompliancePct(assignment) : null;
  const complianceStyle = getComplianceStyle(pct, isPast, isCompleted);
  const chip = weatherChip(assignment.weather_snapshot);
  const blocks = pw?.blocks ?? [];
  const hasComment = !!assignment.coach_comment;

  const handleClick = (e) => {
    e.stopPropagation();
    onClick?.(assignment);
  };

  const handleCompleteClick = (e) => {
    e.stopPropagation();
    onCompleteClick?.(assignment);
  };

  const handleContextMenu = (e) => {
    if (role !== 'coach') return;
    e.preventDefault();
    e.stopPropagation();
    onContextMenu?.(e.clientX, e.clientY, assignment);
  };

  const handleDragStart = (e) => {
    if (role !== 'coach') return;
    e.dataTransfer.setData('cardAssignmentId', String(assignment.id));
    e.dataTransfer.effectAllowed = 'move';
    onDragStart?.(e, assignment);
  };

  const handleDragEnd = (e) => {
    if (role !== 'coach') return;
    onDragEnd?.(e);
  };

  return (
    <Paper
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      draggable={role === 'coach'}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      sx={{
        borderRadius: 2,
        boxShadow: 'none',
        border: '1px solid #e2e8f0',
        borderLeftColor: color,
        borderLeftWidth: 3,
        borderLeftStyle: 'solid',
        cursor: 'pointer',
        bgcolor: complianceStyle.bgColor,
        transition: 'box-shadow 0.15s',
        '&:hover': { boxShadow: '0 2px 8px rgba(0,0,0,0.1)' },
        mb: 0.5,
        p: 1,
        minWidth: 0,
        userSelect: 'none',
      }}
    >
      {/* Row 1: Sport label + weather + compliance badge + comment icon */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.25 }}>
        <Typography
          variant="caption"
          sx={{ fontWeight: 700, color, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: 0.3 }}
        >
          {sportLabel(discipline)}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {chip && (
            <Typography variant="caption" sx={{ fontSize: '0.6rem', color: '#475569' }}>
              {chip}
            </Typography>
          )}
          {hasComment && (
            <Tooltip title={assignment.coach_comment.slice(0, 50) + (assignment.coach_comment.length > 50 ? '…' : '')} placement="top">
              <ChatBubbleOutline sx={{ fontSize: 10, color: '#64748b' }} />
            </Tooltip>
          )}
          {isCompleted && pct != null && (
            <Box
              title={`Compliance: ${pct}%`}
              sx={{
                px: 0.5, py: 0.1,
                borderRadius: 0.75,
                bgcolor: `${complianceStyle.dotColor}22`,
                border: `1px solid ${complianceStyle.dotColor}44`,
                fontSize: '0.58rem',
                fontWeight: 700,
                color: complianceStyle.dotColor,
                lineHeight: 1.4,
                flexShrink: 0,
              }}
            >
              {pct}%
            </Box>
          )}
          {isCompleted && pct == null && (
            <Box
              sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: complianceStyle.dotColor, flexShrink: 0 }}
            />
          )}
        </Box>
      </Box>

      {/* Row 2: Workout name */}
      <Typography
        variant="body2"
        sx={{ fontWeight: 600, color: '#1e293b', fontSize: '0.75rem', lineHeight: 1.3, mb: 0.25 }}
        noWrap
      >
        {pw?.name ?? 'Entrenamiento'}
      </Typography>

      {/* Row 3: Metrics */}
      <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', display: 'block' }}>
        {metricsLabel}
      </Typography>

      {/* Row 4: Mini workout profile */}
      <MiniWorkoutProfile blocks={blocks} estimatedDuration={pw?.estimated_duration_seconds} />

      {/* Row 5: Status + RPE */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.5 }}>
        {isCompleted ? (
          <Typography variant="caption" sx={{ color: '#16a34a', fontSize: '0.6rem', fontWeight: 600 }}>
            ✓ {complianceStyle.label}
          </Typography>
        ) : role === 'athlete' ? (
          <Typography
            variant="caption"
            onClick={handleCompleteClick}
            sx={{
              color: '#64748b', fontSize: '0.6rem', fontWeight: 500,
              cursor: 'pointer', textDecoration: 'underline',
              '&:hover': { color: '#f97316' },
            }}
          >
            Marcar completado
          </Typography>
        ) : (
          <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.6rem' }}>
            {complianceStyle.label}
          </Typography>
        )}
        {isCompleted && assignment.rpe != null && (
          <Typography variant="caption" sx={{ fontSize: '0.65rem' }} title={`RPE ${assignment.rpe}/5`}>
            {RPE_EMOJI[assignment.rpe] ?? ''} {assignment.rpe}/5
          </Typography>
        )}
      </Box>
    </Paper>
  );
}
