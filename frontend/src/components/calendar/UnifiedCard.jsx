/**
 * UnifiedCard.jsx — Unified plan + real card for calendar day cells (PR-179b)
 *
 * Replaces separate WorkoutCard + ActivityPill rendering.
 * One card per assignment; free activities (no plan) render as variant F.
 *
 * Variants:
 *   A — Plan future pending
 *   B — Plan + Real on-plan (80–110%)
 *   C — Plan + Real under (<80%)
 *   D — Plan + Real over (>150% — alert)
 *   E — Plan past missed
 *   F — Free activity (no plan)
 *   G — Rest / no data (rendered by CalendarGrid directly, not here)
 *
 * Props:
 *   assignment    — WorkoutAssignment object (null for variant F)
 *   activity      — CompletedActivity from timeline (null if no real data)
 *   reconciliation — reconciliation entry { compliance_pct, status } (null if none)
 *   planDetails   — enriched plan entry from timeline { weather, description, intensity_steps, ... }
 *   freeActivity  — CompletedActivity for free-activity cards (no plan)
 *   isPast        — boolean
 *   role          — 'coach' | 'athlete'
 *   onClick       — (payload) => void  (opens WorkoutModal)
 *   onContextMenu — (x, y, assignment) => void  [coach only]
 *   onDragStart   — (e, assignment) => void  [coach only]
 *   onDragEnd     — (e) => void  [coach only]
 */
import React from 'react';
import { Box, Paper, Typography, Tooltip } from '@mui/material';
import { ChatBubbleOutline } from '@mui/icons-material';
import { weatherBadgeProps } from '../../hooks/useWeatherIcon';
import {
  sportColor, sportLabel, fmtDuration, fmtDistance, computeCompliancePct,
} from '../../utils/calendarHelpers';

// ── Compliance variant resolver ───────────────────────────────────────────────

function resolveVariant(assignment, activity, reconciliation, isPast) {
  if (!assignment) return 'F'; // free activity
  const hasReal = !!activity;
  if (!hasReal) return isPast ? 'E' : 'A';

  const pct = reconciliation?.compliance_pct ?? computeCompliancePct(assignment);
  if (pct == null) return 'B';
  if (pct > 150)   return 'D';
  if (pct >= 80)   return 'B';
  return 'C';
}

const VARIANT_BORDER = {
  A: '#94a3b8', // pending — gray
  B: '#22c55e', // on plan — green
  C: '#f59e0b', // under — amber
  D: '#7c3aed', // over — purple alert
  E: '#ef4444', // missed — red
  F: '#e2e8f0', // free — neutral (Bug #67: libre no debe heredar sport color)
};

const VARIANT_BG = {
  A: '#ffffff',
  B: '#f0fdf4',
  C: '#fffbeb',
  D: '#faf5ff',
  E: '#fef2f2',
  F: '#f8fafc', // free — neutral gray
};

const VARIANT_EMOJI = { A: null, B: '✅', C: '⚠️', D: '🔥', E: '❌', F: '🏃' };

// ── WeatherBadge ──────────────────────────────────────────────────────────────

function WeatherBadge({ weather }) {
  const props = weatherBadgeProps(weather);
  if (!props) return null;
  return (
    <Tooltip
      title={props.alert ?? ''}
      placement="top"
      disableHoverListener={!props.alert}
    >
      <Typography
        component="span"
        sx={{
          fontSize: '0.6rem',
          color: props.alert ? '#dc2626' : '#475569',
          fontWeight: props.alert ? 700 : 400,
          cursor: props.alert ? 'help' : 'default',
          whiteSpace: 'nowrap',
        }}
      >
        {props.icon} {props.label}
        {props.alert && ' ⚡'}
      </Typography>
    </Tooltip>
  );
}

// ── ComplianceBadge ── prominent bottom strip with semantic label ─────────────

function resolveComplianceLabel(pct) {
  if (pct == null) return null;
  if (pct >= 80 && pct <= 120) return { label: 'Óptimo',  color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' };
  if ((pct >= 50 && pct < 80) || (pct > 120 && pct <= 150)) return { label: 'Revisar', color: '#d97706', bg: '#fffbeb', border: '#fde68a' };
  return { label: 'Alerta', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' };
}

function ComplianceBadge({ pct, variant }) {
  if (pct == null || variant === 'A' || variant === 'E' || variant === 'F') return null;
  const meta = resolveComplianceLabel(pct);
  if (!meta) return null;
  return (
    <Box
      sx={{
        mt: 0.5,
        px: 0.75, py: 0.25,
        borderRadius: 1,
        bgcolor: meta.bg,
        border: `1px solid ${meta.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}
    >
      <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color: meta.color, lineHeight: 1.3 }}>
        {meta.label}
      </Typography>
      <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color: meta.color, lineHeight: 1.3 }}>
        {pct}%
      </Typography>
    </Box>
  );
}

// ── MetricRow ─────────────────────────────────────────────────────────────────

function MetricRow({ prefix, duration, distance, elevation, color }) {
  const parts = [duration, distance, elevation ? `D+${elevation}m` : null].filter(Boolean);
  if (!parts.length) return null;
  return (
    <Typography
      variant="caption"
      sx={{ fontSize: '0.62rem', color: color ?? '#64748b', lineHeight: 1.3, display: 'block' }}
    >
      {prefix && <span style={{ marginRight: 3 }}>{prefix}</span>}
      {parts.join(' · ')}
    </Typography>
  );
}

// ── UnifiedCard ───────────────────────────────────────────────────────────────

export default function UnifiedCard({
  assignment,
  activity,
  reconciliation,
  planDetails,
  freeActivity,
  isPast = false,
  role = 'athlete',
  onClick,
  onCompleteClick,
  onContextMenu,
  onDragStart,
  onDragEnd,
}) {
  const isFreeVariant = !assignment && !!freeActivity;
  const act = isFreeVariant ? freeActivity : activity;
  const variant = resolveVariant(assignment, act, reconciliation, isPast);

  const pw = assignment?.planned_workout ?? null;
  const discipline = pw?.discipline ?? act?.sport ?? 'other';
  const color = sportColor(discipline);
  const borderColor = VARIANT_BORDER[variant];

  // weather: prefer enriched plan data from timeline, fall back to assignment snapshot
  const weather = planDetails?.weather ?? assignment?.weather_snapshot ?? null;

  // plan metrics
  const planDuration = fmtDuration(pw?.estimated_duration_seconds);
  const planDistance = fmtDistance(pw?.estimated_distance_meters);
  const planElevation = pw?.elevation_gain_min_m ?? null;

  // real metrics
  const realDuration = act ? fmtDuration(act.duration_s ?? act.actual_duration_seconds) : null;
  const realDistance = act ? fmtDistance(
    act.distance_m != null ? act.distance_m * 1000 : act.actual_distance_meters
  ) : null;
  const realElevation = act?.elevation_gain_m ?? act?.actual_elevation_gain ?? null;

  const compliancePct = reconciliation?.compliance_pct ?? (
    assignment && act ? computeCompliancePct(assignment) : null
  );

  const hasComment = !!assignment?.coach_comment || !!planDetails?.coach_notes;
  const variantEmoji = VARIANT_EMOJI[variant];

  const handleClick = (e) => {
    e.stopPropagation();
    onClick?.({ assignment, activity: act, reconciliation, planDetails, freeActivity });
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
    if (role !== 'coach' || !assignment) return;
    e.dataTransfer.setData('cardAssignmentId', String(assignment.id));
    e.dataTransfer.effectAllowed = 'move';
    onDragStart?.(e, assignment);
  };

  const handleDragEnd = (e) => {
    if (role !== 'coach') return;
    onDragEnd?.(e);
  };

  // Fix 6: show Strava activity name for libre cards when available
  const freeTitle = freeActivity?.name?.trim()
    ? freeActivity.name.trim()
    : (sportLabel(discipline) + ' — libre');

  // Fix 2: strip " (personalizado)" from display; detect via is_assignment_snapshot
  const isCustomized = pw?.is_assignment_snapshot === true;
  const rawTitle = isFreeVariant
    ? freeTitle
    : (pw?.name ?? assignment?.planned_workout_title ?? '');
  const title = rawTitle.replace(/ \(personalizado\)$/i, '');

  return (
    <Paper
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      draggable={role === 'coach' && !!assignment}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      sx={{
        borderRadius: 2,
        boxShadow: 'none',
        border: '1px solid #e2e8f0',
        borderLeftColor: isFreeVariant ? VARIANT_BORDER.F : color,
        borderLeftWidth: 3,
        borderLeftStyle: 'solid',
        borderTopColor: borderColor,
        borderTopWidth: variant !== 'A' ? 2 : 1,
        cursor: 'pointer',
        bgcolor: VARIANT_BG[variant],
        transition: 'box-shadow 0.15s',
        '&:hover': { boxShadow: '0 2px 8px rgba(0,0,0,0.1)' },
        mb: 0.5,
        p: 1,
        minWidth: 0,
        userSelect: 'none',
      }}
    >
      {/* Row 1: sport label + weather + compliance pill + comment + custom icon */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4, minWidth: 0 }}>
          {variantEmoji && !isFreeVariant && (
            <Typography component="span" sx={{ fontSize: '0.65rem', lineHeight: 1 }}>
              {variantEmoji}
            </Typography>
          )}
          <Typography
            variant="caption"
            noWrap
            sx={{
              fontWeight: 700,
              color: isFreeVariant ? '#94a3b8' : color,
              fontSize: '0.65rem',
              textTransform: 'uppercase',
              letterSpacing: 0.3,
            }}
          >
            {sportLabel(discipline)}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
          <WeatherBadge weather={weather} />
          {/* Fix 7: compliance pill — top-right, shown for completed sessions */}
          {!isFreeVariant && variant !== 'A' && variant !== 'E' && compliancePct != null && (
            <Box sx={{
              px: 0.5, py: 0.1, borderRadius: 0.75, lineHeight: 1.4, flexShrink: 0,
              fontSize: '0.58rem', fontWeight: 700,
              ...(compliancePct <= 69
                ? { bgcolor: '#fef2f2', color: '#ef4444' }
                : compliancePct <= 110
                  ? { bgcolor: '#f0fdf4', color: '#16a34a' }
                  : compliancePct <= 150
                    ? { bgcolor: '#eff6ff', color: '#3b82f6' }
                    : { bgcolor: '#faf5ff', color: '#7c3aed' }),
            }}>
              {compliancePct}%
            </Box>
          )}
          {!isFreeVariant && variant !== 'A' && variant !== 'E' && compliancePct == null && (
            <Typography component="span" sx={{ fontSize: '0.6rem', color: '#16a34a', fontWeight: 700 }}>✓</Typography>
          )}
          {/* Fix 2: pencil icon for individually customized sessions */}
          {isCustomized && (
            <Typography component="span" sx={{ fontSize: '0.6rem', color: '#94a3b8' }} title="Sesión personalizada">✏️</Typography>
          )}
          {hasComment && (
            <Tooltip
              title={(planDetails?.coach_notes || assignment?.coach_comment || '').slice(0, 60)}
              placement="top"
            >
              <ChatBubbleOutline sx={{ fontSize: 10, color: '#64748b' }} />
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Row 2: workout name */}
      {title && (
        <Typography
          variant="caption"
          noWrap
          sx={{ fontWeight: 600, color: '#1e293b', fontSize: '0.68rem', display: 'block', mb: 0.2 }}
        >
          {title}
        </Typography>
      )}

      {/* Row 3: plan metrics */}
      {!isFreeVariant && (planDuration || planDistance) && (
        <MetricRow
          prefix="🎯"
          duration={planDuration}
          distance={planDistance}
          elevation={planElevation}
          color="#64748b"
        />
      )}

      {/* Row 4: real metrics (when paired or free) */}
      {act && (realDuration || realDistance) && (
        <MetricRow
          prefix={isFreeVariant ? null : variantEmoji}
          duration={realDuration}
          distance={realDistance}
          elevation={realElevation}
          color={isFreeVariant ? '#94a3b8' : VARIANT_BORDER[variant]}
        />
      )}

      {/* Row 5: free activity tag — neutral */}
      {isFreeVariant && (
        <Typography
          variant="caption"
          sx={{ fontSize: '0.58rem', color: '#94a3b8', fontWeight: 500, display: 'block' }}
        >
          Actividad libre
        </Typography>
      )}

      {/* Row 6: athlete RPE emoji */}
      {planDetails?.rpe != null && !isFreeVariant && (
        <Typography
          component="span"
          sx={{ fontSize: '0.65rem', lineHeight: 1.3 }}
          title={`RPE: ${planDetails.rpe}/5`}
        >
          {['', '😴', '😐', '🙂', '💪', '🔥'][planDetails.rpe] ?? ''}
        </Typography>
      )}

      {/* Row 7: compliance badge — prominent bottom strip */}
      <ComplianceBadge pct={compliancePct} variant={variant} />

      {/* Row 8: athlete-only "Marcar completado" — only when no real data yet */}
      {role === 'athlete' && !isFreeVariant && !act && assignment && (
        <Typography
          variant="caption"
          onClick={handleCompleteClick}
          sx={{
            display: 'block',
            mt: 0.5,
            color: '#64748b', fontSize: '0.6rem', fontWeight: 500,
            cursor: 'pointer', textDecoration: 'underline',
            '&:hover': { color: '#f97316' },
          }}
        >
          Marcar completado
        </Typography>
      )}
    </Paper>
  );
}
