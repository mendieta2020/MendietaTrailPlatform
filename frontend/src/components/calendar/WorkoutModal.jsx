/**
 * WorkoutModal.jsx — Expanded workout detail modal (PR-179b)
 *
 * Cases:
 *   1 — Plan only (future pending or past missed): description, steps, intensity graph
 *   2 — Plan + Real paired: plan + real metrics, compliance, intensity graph, athlete sentiment
 *   3 — Free activity (no plan): sport + metrics + "Actividad libre" info
 *
 * IMPORTANT: No "Ver en Strava" link. No "Agregar al reloj" button.
 * Law 3: PlannedWorkout and CompletedActivity are displayed side-by-side but
 *         never merged — they remain distinct objects in the UI and backend.
 */
import React from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Typography, Chip, Button, Divider, Tooltip,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import IconButton from '@mui/material/IconButton';
import { MiniWorkoutProfile } from '../MiniWorkoutProfile';
import { weatherBadgeProps } from '../../hooks/useWeatherIcon';
import { sportLabel, sportColor, fmtDuration, fmtDistance } from '../../utils/calendarHelpers';
import MarkdownRenderer from '../MarkdownRenderer';

const RPE_EMOJI = { 1: '😴', 2: '😐', 3: '🙂', 4: '💪', 5: '🔥' };

// ── Helpers ───────────────────────────────────────────────────────────────────

function MetricChip({ label, value, color }) {
  if (!value) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 52 }}>
      <Typography sx={{ fontSize: '0.95rem', fontWeight: 700, color: color ?? '#1e293b', lineHeight: 1.2 }}>
        {value}
      </Typography>
      <Typography sx={{ fontSize: '0.6rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.4 }}>
        {label}
      </Typography>
    </Box>
  );
}

function SectionLabel({ children }) {
  return (
    <Typography
      sx={{
        fontSize: '0.65rem', fontWeight: 700, color: '#94a3b8',
        textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.75,
      }}
    >
      {children}
    </Typography>
  );
}

function WeatherRow({ weather }) {
  const props = weatherBadgeProps(weather);
  if (!props) return null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
      <Typography sx={{ fontSize: '1.1rem' }}>{props.icon}</Typography>
      <Box>
        <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: props.alert ? '#dc2626' : '#475569' }}>
          {props.label}
          {props.alert && ` — ${props.alert}`}
        </Typography>
      </Box>
    </Box>
  );
}

function IntensityStepsList({ steps }) {
  if (!steps?.length) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4 }}>
      {steps.map((s, i) => {
        const duration = s.duration_sec ? fmtDuration(s.duration_sec) : null;
        const distance = s.distance_m ? fmtDistance(s.distance_m) : null;
        const metric = [
          s.repetitions > 1 ? `${s.repetitions}×` : null,
          duration,
          distance,
          s.intensity_label || null,
        ].filter(Boolean).join(' ');
        return (
          <Box
            key={i}
            sx={{
              display: 'flex', alignItems: 'center', gap: 1,
              px: 1, py: 0.4,
              borderRadius: 1,
              bgcolor: s.block_type === 'main' ? '#f0fdf4' : '#f8fafc',
              border: '1px solid',
              borderColor: s.block_type === 'main' ? '#bbf7d0' : '#e2e8f0',
            }}
          >
            <Typography sx={{ fontSize: '0.62rem', fontWeight: 700, color: '#64748b', minWidth: 56 }}>
              {s.block_name || s.block_type}
            </Typography>
            <Typography sx={{ fontSize: '0.68rem', color: '#1e293b', fontWeight: 500 }}>
              {metric || s.description || '—'}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

function ComplianceBar({ pct }) {
  if (pct == null) return null;
  const capped = Math.min(pct, 200);
  const color = pct > 150 ? '#7c3aed' : pct >= 80 ? '#22c55e' : '#f59e0b';
  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
        <Typography sx={{ fontSize: '0.65rem', color: '#64748b' }}>Cumplimiento</Typography>
        <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color }}>{pct}%</Typography>
      </Box>
      <Box sx={{ height: 6, borderRadius: 3, bgcolor: '#e2e8f0', overflow: 'hidden' }}>
        <Box sx={{ height: '100%', width: `${Math.min(capped / 2, 100)}%`, bgcolor: color, borderRadius: 3, transition: 'width 0.3s' }} />
      </Box>
    </Box>
  );
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export default function WorkoutModal({ open, onClose, payload, role = 'athlete' }) {
  if (!payload) return null;

  const { assignment, activity, reconciliation, planDetails, freeActivity } = payload;
  const isFree = !assignment && !!freeActivity;
  const act = isFree ? freeActivity : activity;
  const pw = assignment?.planned_workout ?? null;

  // Determine case
  let caseNum = 1;
  if (isFree) caseNum = 3;
  else if (act) caseNum = 2;

  const discipline = pw?.discipline ?? act?.sport ?? 'other';
  const color = sportColor(discipline);
  const title = isFree
    ? sportLabel(discipline)
    : (pw?.name ?? assignment?.planned_workout_title ?? 'Entrenamiento');

  const dateStr = isFree
    ? (act?.date ?? '')
    : (planDetails?.date ?? assignment?.scheduled_date ?? '');

  const weather = planDetails?.weather ?? assignment?.weather_snapshot ?? null;

  // Plan metrics (from planDetails if available, fall back to planned_workout)
  const planDurationMin = planDetails?.estimated_duration_min
    ?? (pw?.estimated_duration_seconds ? Math.round(pw.estimated_duration_seconds / 60) : null);
  const planDistanceKm = planDetails?.estimated_distance_km
    ?? (pw?.estimated_distance_meters ? (pw.estimated_distance_meters / 1000).toFixed(1) : null);
  const planElevation = planDetails?.estimated_elevation_m ?? pw?.elevation_gain_min_m ?? null;

  // Real metrics
  const realDurationMin = act?.duration_min
    ?? (act?.duration_s != null ? Math.round(act.duration_s / 60) : null)
    ?? (act?.actual_duration_seconds != null ? Math.round(act.actual_duration_seconds / 60) : null);
  const realDistanceKm = act?.distance_km
    ?? (act?.distance_m != null ? (act.distance_m / 1000).toFixed(1) : null)
    ?? (act?.actual_distance_meters != null ? (act.actual_distance_meters / 1000).toFixed(1) : null);
  const realElevation = act?.elevation_m ?? act?.elevation_gain_m ?? act?.actual_elevation_gain ?? null;

  const compliancePct = reconciliation?.compliance_pct ?? null;
  const athleteRpe = planDetails?.rpe ?? assignment?.rpe ?? null;
  const athleteNotes = planDetails?.athlete_notes ?? assignment?.athlete_notes ?? '';
  const coachNotes = planDetails?.coach_notes ?? assignment?.coach_notes ?? '';
  const description = planDetails?.description ?? pw?.description ?? '';
  const intensitySteps = planDetails?.intensity_steps ?? [];
  const blocks = pw?.blocks ?? [];

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3, maxHeight: '90vh' } }}
    >
      {/* Header */}
      <DialogTitle
        sx={{
          pb: 1,
          borderBottom: `3px solid ${color}`,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 1,
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {sportLabel(discipline)}
            {isFree && (
              <Chip
                label="Libre"
                size="small"
                sx={{ ml: 1, height: 16, fontSize: '0.55rem', bgcolor: '#fff7ed', color: '#92400e', border: '1px solid #fde68a' }}
              />
            )}
          </Typography>
          <Typography sx={{ fontWeight: 700, fontSize: '1rem', color: '#0f172a', mt: 0.25, lineHeight: 1.25 }}>
            {title}
          </Typography>
          {dateStr && (
            <Typography sx={{ fontSize: '0.7rem', color: '#64748b', mt: 0.2 }}>
              {dateStr}
            </Typography>
          )}
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ mt: -0.5, flexShrink: 0 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ px: 2.5, py: 2, overflowY: 'auto' }}>
        {/* Weather row */}
        <WeatherRow weather={weather} />

        {/* ── Case 3: Free activity ── */}
        {caseNum === 3 && (
          <>
            <Box sx={{ display: 'flex', gap: 2, mb: 1.5 }}>
              <MetricChip label="Duración" value={realDurationMin ? `${realDurationMin}min` : null} />
              <MetricChip label="Distancia" value={realDistanceKm ? `${realDistanceKm}km` : null} />
              {realElevation && <MetricChip label="D+" value={`${realElevation}m`} />}
            </Box>
            <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: '#fff7ed', border: '1px solid #fed7aa' }}>
              <Typography sx={{ fontSize: '0.75rem', color: '#92400e' }}>
                Esta actividad no era parte del plan. Aporta al PMC y al balance de carga semanal.
              </Typography>
            </Box>
          </>
        )}

        {/* ── Case 1 & 2: Plan section ── */}
        {caseNum !== 3 && (
          <>
            <SectionLabel>Plan</SectionLabel>
            <Box sx={{ display: 'flex', gap: 2, mb: 1.5, flexWrap: 'wrap' }}>
              <MetricChip label="Duración" value={planDurationMin ? `${planDurationMin}min` : null} />
              <MetricChip label="Distancia" value={planDistanceKm ? `${planDistanceKm}km` : null} />
              {planElevation && <MetricChip label="D+" value={`${planElevation}m`} />}
            </Box>

            {/* Coach description */}
            {description && (
              <>
                <SectionLabel>📖 Descripción</SectionLabel>
                <Box sx={{ mb: 1.5, p: 1, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                  <MarkdownRenderer content={description} />
                </Box>
              </>
            )}

            {/* Intensity steps list */}
            {intensitySteps.length > 0 && (
              <>
                <SectionLabel>📋 Pasos</SectionLabel>
                <Box sx={{ mb: 1.5 }}>
                  <IntensityStepsList steps={intensitySteps} />
                </Box>
              </>
            )}

            {/* Intensity profile graph (from planned_workout blocks) */}
            {blocks.length > 0 && (
              <>
                <SectionLabel>📊 Perfil de intensidad</SectionLabel>
                <Box sx={{ mb: 1.5, px: 0.5 }}>
                  <MiniWorkoutProfile
                    blocks={blocks}
                    estimatedDuration={pw?.estimated_duration_seconds}
                  />
                </Box>
              </>
            )}

            {/* Coach notes (shared, both roles see this) */}
            {coachNotes && (
              <>
                <SectionLabel>💬 Nota del entrenador</SectionLabel>
                <Box sx={{ mb: 1.5, p: 1, bgcolor: '#eff6ff', borderRadius: 1.5, border: '1px solid #bfdbfe' }}>
                  <Typography sx={{ fontSize: '0.75rem', color: '#1e40af' }}>{coachNotes}</Typography>
                </Box>
              </>
            )}
          </>
        )}

        {/* ── Case 2 additions: real data section ── */}
        {caseNum === 2 && act && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <SectionLabel>✅ Tu actividad</SectionLabel>
            <Box sx={{ display: 'flex', gap: 2, mb: 1.5, flexWrap: 'wrap' }}>
              <MetricChip label="Duración" value={realDurationMin ? `${realDurationMin}min` : null} color="#16a34a" />
              <MetricChip label="Distancia" value={realDistanceKm ? `${realDistanceKm}km` : null} color="#16a34a" />
              {realElevation && <MetricChip label="D+" value={`${realElevation}m`} color="#16a34a" />}
            </Box>

            <ComplianceBar pct={compliancePct} />

            {/* Athlete sentiment */}
            {(athleteRpe != null || athleteNotes) && (
              <>
                <SectionLabel>💭 Sensaciones del atleta</SectionLabel>
                <Box sx={{ p: 1, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0', mb: 1 }}>
                  {athleteRpe != null && (
                    <Typography sx={{ fontSize: '0.8rem', mb: 0.5 }}>
                      {RPE_EMOJI[athleteRpe] ?? ''} RPE {athleteRpe}/5
                    </Typography>
                  )}
                  {athleteNotes && (
                    <Typography sx={{ fontSize: '0.75rem', color: '#475569', fontStyle: 'italic' }}>
                      "{athleteNotes}"
                    </Typography>
                  )}
                </Box>
              </>
            )}

            {/* Coach-only: legacy coach_comment quick note */}
            {role === 'coach' && payload?.assignment?.coach_comment && (
              <>
                <SectionLabel>📝 Comentario rápido (privado)</SectionLabel>
                <Box sx={{ p: 1, bgcolor: '#fefce8', borderRadius: 1.5, border: '1px solid #fde68a', mb: 1 }}>
                  <Typography sx={{ fontSize: '0.75rem', color: '#854d0e' }}>
                    {payload.assignment.coach_comment}
                  </Typography>
                </Box>
              </>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 2.5, pb: 2 }}>
        <Button
          onClick={onClose}
          variant="text"
          sx={{ textTransform: 'none', color: '#64748b', fontWeight: 600 }}
        >
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
