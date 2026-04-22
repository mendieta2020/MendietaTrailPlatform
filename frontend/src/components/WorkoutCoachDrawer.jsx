/**
 * WorkoutCoachDrawer.jsx — PR-145g
 *
 * Coach drawer: opens on single-click of any calendar event.
 * Width: 480px | Anchor: right
 *
 * Information hierarchy (top → bottom):
 *   1. Header — sport color band + status badge + name + athlete/date
 *   2. Metric chips — duration, distance, D+, TSS, IF, weather
 *   3. Mini workout profile (SVG)
 *   4. Athlete note + RPE (FIRST per retention research)
 *   5. Planned vs Real table + zone bar (completed only)
 *   6. Coach instructions
 *   7. Coach comment box (always visible for coach/owner)
 *   8. Sticky footer — Edit + Mark Complete buttons
 */

import React, { useState } from 'react';
import {
  Drawer, Box, Typography, IconButton, Divider, Chip, Button,
  TextField, Tooltip, CircularProgress, useTheme, useMediaQuery,
} from '@mui/material';
import { Close, ArrowBack } from '@mui/icons-material';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { MiniWorkoutProfile } from './MiniWorkoutProfile';
import { addCoachComment, cloneAssignmentWorkout } from '../api/assignments';
import WorkoutAssignmentEditModal from './WorkoutAssignmentEditModal';

// ── Constants ─────────────────────────────────────────────────────────────────

const SPORT_COLOR = {
  trail:    '#f97316',
  run:      '#22c55e',
  bike:     '#3b82f6',
  cycling:  '#3b82f6',
  strength: '#a855f7',
  mobility: '#06b6d4',
  swim:     '#0ea5e9',
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

const COMPLIANCE_BADGE = {
  green:  { label: '✓ Cumplido',        bg: '#f0fdf4', color: '#16a34a', border: '#bbf7d0' },
  blue:   { label: '↑ Superó el plan',  bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' },
  yellow: { label: '⚡ Parcial',          bg: '#fefce8', color: '#ca8a04', border: '#fde68a' },
  red:    { label: '✗ No completó',     bg: '#fef2f2', color: '#dc2626', border: '#fecaca' },
  gray:   { label: '○ Planificado',     bg: '#f8fafc', color: '#64748b', border: '#e2e8f0' },
};

const RPE_EMOJI = { 1: '😴', 2: '😐', 3: '🙂', 4: '💪', 5: '🔥' };

const ZONE_COLORS = {
  Z1: '#94A3B8', Z2: '#60A5FA', Z3: '#34D399', Z4: '#FBBF24', Z5: '#F87171',
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
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${meters} m`;
}

function fmtDateLong(dateStr) {
  if (!dateStr) return '';
  try {
    return format(parseISO(dateStr), "EEEE d 'de' MMMM", { locale: es });
  } catch {
    return dateStr;
  }
}

// ── MetricChip ────────────────────────────────────────────────────────────────

function MetricChip({ icon, value, label, highlight }) {
  if (!value) return null;
  return (
    <Box
      sx={{
        display: 'flex', alignItems: 'center', gap: 0.5,
        px: 1.5, py: 0.75,
        bgcolor: highlight ? '#fff7ed' : '#f8fafc',
        border: `1px solid ${highlight ? '#fed7aa' : '#e2e8f0'}`,
        borderRadius: 2,
        minWidth: 72,
        flexShrink: 0,
      }}
    >
      <Typography variant="caption" sx={{ fontSize: '1rem', lineHeight: 1 }}>{icon}</Typography>
      <Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: '#1e293b', display: 'block', lineHeight: 1 }}>{value}</Typography>
        {label && (
          <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.6rem' }}>{label}</Typography>
        )}
      </Box>
    </Box>
  );
}

// ── ZoneBar ───────────────────────────────────────────────────────────────────

function ZoneBar({ zones }) {
  const total = Object.values(zones).reduce((s, v) => s + v, 0);
  if (!total) return null;

  const segments = Object.entries(zones)
    .filter(([, secs]) => secs > 0)
    .map(([zone, secs]) => ({
      zone,
      pct: (secs / total) * 100,
      label: `${zone}: ${fmtDuration(secs)} (${Math.round((secs / total) * 100)}%)`,
    }));

  if (!segments.length) return null;

  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
        Distribución de zonas
      </Typography>
      <Box sx={{ display: 'flex', height: 18, borderRadius: 1, overflow: 'hidden', width: '100%' }}>
        {segments.map(({ zone, pct, label }) => (
          <Tooltip key={zone} title={label} arrow>
            <Box
              sx={{
                width: `${pct}%`,
                bgcolor: ZONE_COLORS[zone] ?? '#94a3b8',
                cursor: 'default',
                transition: 'opacity 0.15s',
                '&:hover': { opacity: 0.8 },
              }}
            />
          </Tooltip>
        ))}
      </Box>
      <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
        {segments.map(({ zone }) => (
          <Box key={zone} sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: ZONE_COLORS[zone] ?? '#94a3b8' }} />
            <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem' }}>{zone}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── WorkoutCoachDrawer ─────────────────────────────────────────────────────────

export default function WorkoutCoachDrawer({
  event,
  orgId,
  onClose,
  onSaved,
  onMarkComplete,
}) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const open = !!event;
  const assignment = event?.resource ?? null;
  const pw = assignment?.planned_workout ?? null;

  const discipline = pw?.discipline ?? 'other';
  const color = SPORT_COLOR[discipline] ?? '#94a3b8';
  const isCompleted = assignment?.status === 'completed';

  const complianceKey = isCompleted ? (assignment?.compliance_color ?? 'gray') : 'gray';
  const badge = COMPLIANCE_BADGE[complianceKey] ?? COMPLIANCE_BADGE.gray;

  // Athlete name from event or assignment
  const athleteLabel = (() => {
    const a = assignment?.athlete_name ?? assignment?.athlete ?? '';
    return a || null;
  })();

  // ── Coach comment state ────────────────────────────────────────────────────
  // Reset when switching assignments (Plantilla reuses same instance; Calendar
  // remounts via key — this derived-state pattern covers both without useEffect).
  const [prevAssignmentId, setPrevAssignmentId] = useState(assignment?.id);
  const [commentText, setCommentText] = useState(assignment?.coach_comment ?? '');
  const [commentStatus, setCommentStatus] = useState(null); // null | 'saving' | 'saved' | 'error'

  if (assignment?.id !== prevAssignmentId) {
    setPrevAssignmentId(assignment?.id);
    setCommentText(assignment?.coach_comment ?? '');
    setCommentStatus(null);
  }

  const handleSendComment = async () => {
    if (!orgId || !assignment?.id) return;
    setCommentStatus('saving');
    try {
      await addCoachComment(orgId, assignment.id, commentText);
      setCommentStatus('saved');
      setTimeout(() => setCommentStatus(null), 3000);
    } catch {
      setCommentStatus('error');
    }
  };

  // ── FIX 3: Inline edit modal state ────────────────────────────────────────
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editWorkout, setEditWorkout] = useState(null);
  const [editLoading, setEditLoading] = useState(false);

  const handleOpenEdit = async () => {
    if (!assignment?.id || !pw) return;
    let workoutData = pw;
    if (!pw.is_assignment_snapshot) {
      setEditLoading(true);
      try {
        const res = await cloneAssignmentWorkout(orgId, assignment.id);
        workoutData = res.data.planned_workout ?? res.data;
      } catch {
        setEditLoading(false);
        return;
      }
      setEditLoading(false);
    }
    setEditWorkout(workoutData);
    setEditModalOpen(true);
  };

  const handleEditSaved = (updatedWorkout) => {
    // Notify Calendar to update the event and refresh selectedEvent —
    // the drawer stays open; Calendar's onSaved handles the rest.
    onSaved?.(updatedWorkout);
  };

  // ── Weather chip ──────────────────────────────────────────────────────────
  const weather = assignment?.weather_snapshot ?? null;
  const weatherLabel = weather
    ? `${Math.round(weather.temp_c ?? weather.temp ?? 0)}°C ${weather.description ?? ''}`
    : null;

  // ── Planned vs real ───────────────────────────────────────────────────────
  const plannedDuration = fmtDuration(pw?.estimated_duration_seconds);
  const plannedDistance = fmtDistance(pw?.estimated_distance_meters);
  const plannedElevation = pw?.elevation_gain_min_m ? `${pw.elevation_gain_min_m}m` : null;

  const realDuration = isCompleted ? fmtDuration(assignment?.actual_duration_seconds) : null;
  const realDistance = isCompleted ? fmtDistance(assignment?.actual_distance_meters) : null;
  const realElevation = isCompleted && assignment?.actual_elevation_gain
    ? `${assignment.actual_elevation_gain}m`
    : null;

  const showPlanVsReal = isCompleted && (realDuration || realDistance || realElevation);

  // Zone data (only if present in completed activity)
  const zones = assignment?.zone_distribution ?? null;
  const hasZones = zones && Object.values(zones).some((v) => v > 0);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 480 },
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      {/* ── 1. HEADER ───────────────────────────────────────────────────── */}
      <Box
        sx={{
          px: 3, pt: 3, pb: 2,
          borderBottom: '1px solid #e2e8f0',
          borderLeft: `5px solid ${color}`,
          bgcolor: '#fafafa',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ flex: 1, mr: 1 }}>
            {/* Status badge */}
            <Box
              sx={{
                display: 'inline-flex', alignItems: 'center',
                px: 1, py: 0.25, borderRadius: 1.5, mb: 0.75,
                bgcolor: badge.bg, border: `1px solid ${badge.border}`,
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 700, color: badge.color, fontSize: '0.65rem' }}>
                {badge.label}
              </Typography>
            </Box>

            {/* Workout name */}
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#1e293b', lineHeight: 1.3, fontSize: '1.05rem' }}>
              {pw?.name ?? event?.title ?? 'Entrenamiento'}
            </Typography>

            {/* Sport label */}
            <Typography variant="caption" sx={{ color, fontWeight: 700, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: 0.4 }}>
              {SPORT_LABEL[discipline] ?? discipline}
            </Typography>

            {/* Athlete + date */}
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
              {athleteLabel && (
                <Typography variant="caption" sx={{ color: '#475569', fontWeight: 500 }}>
                  {athleteLabel}
                </Typography>
              )}
              {assignment?.scheduled_date && (
                <Typography variant="caption" sx={{ color: '#94a3b8', textTransform: 'capitalize' }}>
                  {fmtDateLong(assignment.scheduled_date)}
                </Typography>
              )}
            </Box>
          </Box>

          <IconButton size="small" onClick={onClose} sx={{ color: '#94a3b8', mt: -0.5 }}>
            {isMobile ? <ArrowBack fontSize="small" /> : <Close fontSize="small" />}
          </IconButton>
        </Box>
      </Box>

      {/* ── Scrollable body ─────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 3, py: 2 }}>

        {/* ── 2. METRIC CHIPS (plan values) ───────────────────────────── */}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'nowrap', overflowX: 'auto', pb: 0.5, mb: 2 }}>
          <MetricChip icon="⏱" value={fmtDuration(pw?.estimated_duration_seconds)} label="Plan" />
          <MetricChip icon="📍" value={fmtDistance(pw?.estimated_distance_meters)} label="Plan" />
          {pw?.elevation_gain_min_m > 0 && (
            <MetricChip icon="⛰" value={`${pw.elevation_gain_min_m}m`} label="D+" />
          )}
          {pw?.planned_tss > 0 && (
            <MetricChip icon="🔥" value={`TSS ${pw.planned_tss}`} label="Carga" />
          )}
          {weatherLabel && (
            <MetricChip icon="🌤" value={weatherLabel} label="Clima" highlight />
          )}
        </Box>

        {/* ── 3. MINI PROFILE ─────────────────────────────────────────── */}
        {pw?.blocks?.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <MiniWorkoutProfile
              blocks={pw.blocks}
              estimatedDuration={pw.estimated_duration_seconds}
            />
          </Box>
        )}

        {/* ── FIX 2: WORKOUT STEPS ────────────────────────────────────── */}
        {pw?.blocks?.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
              Pasos del entrenamiento
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              {pw.blocks.map((block, bi) => {
                const typeLabel =
                  block.block_type === 'warmup'   ? '🔆 Calentamiento' :
                  block.block_type === 'cooldown' ? '❄️ Vuelta a la calma' :
                  block.block_type === 'repeat'   ? `🔁 ${block.repeat_count ?? 1}× Repetición` :
                  block.name ?? '▶ Principal';
                return (
                  <Box key={bi} sx={{ pl: 1.5, borderLeft: `3px solid ${color}55`, py: 0.25 }}>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#475569', display: 'block', fontSize: '0.75rem' }}>
                      {typeLabel}
                    </Typography>
                    {block.intervals?.map((iv, ii) => {
                      const parts = [];
                      if (iv.target_label) parts.push(iv.target_label);
                      if (iv.value_seconds) parts.push(fmtDuration(iv.value_seconds));
                      if (iv.distance_meters) parts.push(fmtDistance(iv.distance_meters));
                      if (iv.description) parts.push(iv.description);
                      return (
                        <Typography key={ii} variant="caption" sx={{ color: '#64748b', display: 'block', fontSize: '0.72rem', pl: 0.5 }}>
                          · {parts.length ? parts.join(' — ') : 'Intervalo'}
                        </Typography>
                      );
                    })}
                  </Box>
                );
              })}
            </Box>
          </Box>
        )}

        <Divider sx={{ mb: 2 }} />

        {/* ── 4. ATHLETE NOTE (FIRST — retention research) ─────────────── */}
        {isCompleted && (
          <Box sx={{ mb: 2.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
              Nota del atleta
            </Typography>
            <Box
              sx={{
                p: 1.5, borderRadius: 2,
                bgcolor: assignment?.athlete_notes ? '#f0f9ff' : '#f8fafc',
                border: `1px solid ${assignment?.athlete_notes ? '#bae6fd' : '#e2e8f0'}`,
              }}
            >
              {/* RPE */}
              {assignment?.rpe && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography sx={{ fontSize: '1.5rem', lineHeight: 1 }}>
                    {RPE_EMOJI[assignment.rpe] ?? '🏃'}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: '#1e293b' }}>
                    RPE {assignment.rpe}/5
                  </Typography>
                </Box>
              )}
              {/* Notes */}
              {assignment?.athlete_notes ? (
                <Typography variant="body2" sx={{ color: '#334155', fontSize: '0.82rem', whiteSpace: 'pre-wrap', mt: assignment?.rpe ? 0.5 : 0 }}>
                  {assignment.athlete_notes}
                </Typography>
              ) : (
                <Typography variant="body2" sx={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>
                  El atleta no dejó nota
                </Typography>
              )}
            </Box>
          </Box>
        )}

        {/* ── 5. PLAN vs REAL ──────────────────────────────────────────── */}
        {showPlanVsReal && (
          <Box sx={{ mb: 2.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
              Planificado vs Real
            </Typography>
            <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
              <Box component="thead">
                <Box component="tr">
                  {['Métrica', 'Planificado', 'Real'].map((h) => (
                    <Box component="th" key={h} sx={{ py: 0.75, px: 1, textAlign: h === 'Métrica' ? 'left' : 'center', color: '#94a3b8', fontWeight: 700, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: 0.3, borderBottom: '1px solid #e2e8f0' }}>
                      {h}
                    </Box>
                  ))}
                </Box>
              </Box>
              <Box component="tbody">
                {[
                  { label: 'Tiempo',    plan: plannedDuration,  real: realDuration },
                  { label: 'Distancia', plan: plannedDistance,  real: realDistance },
                  { label: 'D+',        plan: plannedElevation, real: realElevation },
                ]
                  .filter(({ plan, real }) => plan || real)
                  .map(({ label, plan, real }) => (
                    <Box component="tr" key={label} sx={{ '&:last-child td': { borderBottom: 'none' } }}>
                      <Box component="td" sx={{ py: 0.75, px: 1, color: '#475569', fontWeight: 500, borderBottom: '1px solid #f1f5f9' }}>
                        {label}
                      </Box>
                      <Box component="td" sx={{ py: 0.75, px: 1, textAlign: 'center', color: '#64748b', borderBottom: '1px solid #f1f5f9' }}>
                        {plan ?? '—'}
                      </Box>
                      <Box component="td" sx={{ py: 0.75, px: 1, textAlign: 'center', fontWeight: 700, color: '#1e293b', borderBottom: '1px solid #f1f5f9' }}>
                        {real ?? '—'}
                      </Box>
                    </Box>
                  ))}
              </Box>
            </Box>

            {/* Zone bar — only if zone data available */}
            {hasZones && <ZoneBar zones={zones} />}
          </Box>
        )}

        {/* ── 6. COACH INSTRUCTIONS ──────────────────────────────────── */}
        {(assignment?.coach_notes || pw?.description) && (
          <Box sx={{ mb: 2.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
              Instrucciones
            </Typography>
            <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: '#fffbeb', border: '1px solid #fde68a' }}>
              <Typography variant="body2" sx={{ color: '#78350f', fontSize: '0.8rem', whiteSpace: 'pre-wrap' }}>
                {assignment?.coach_notes || pw?.description}
              </Typography>
            </Box>
          </Box>
        )}

        {/* ── 7. COACH COMMENT ───────────────────────────────────────── */}
        <Box sx={{ mb: 1 }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.3, display: 'block', mb: 0.75 }}>
            Tu comentario
          </Typography>
          <TextField
            multiline
            minRows={2}
            maxRows={5}
            fullWidth
            size="small"
            placeholder="Deja un comentario para el atleta…"
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            sx={{ mb: 1 }}
          />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-end' }}>
            {commentStatus === 'saved' && (
              <Typography variant="caption" sx={{ color: '#16a34a', fontWeight: 600 }}>✓ Comentario enviado</Typography>
            )}
            {commentStatus === 'error' && (
              <Typography variant="caption" sx={{ color: '#dc2626' }}>No se pudo enviar el comentario</Typography>
            )}
            <Button
              size="small"
              variant="contained"
              disabled={commentStatus === 'saving'}
              onClick={handleSendComment}
              sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 600, bgcolor: '#1e293b', '&:hover': { bgcolor: '#334155' } }}
            >
              {commentStatus === 'saving' ? (
                <CircularProgress size={14} sx={{ color: '#fff' }} />
              ) : (
                'Enviar →'
              )}
            </Button>
          </Box>
        </Box>
      </Box>

      {/* ── 8. STICKY FOOTER ──────────────────────────────────────────────── */}
      <Box
        sx={{
          px: 3, py: 2,
          borderTop: '1px solid #e2e8f0',
          bgcolor: '#fafafa',
          display: 'flex',
          gap: 1,
        }}
      >
        <Button
          variant="outlined"
          size="small"
          onClick={handleOpenEdit}
          disabled={editLoading}
          sx={{ flex: 1, borderRadius: 2, textTransform: 'none', fontWeight: 600, borderColor: '#e2e8f0', color: '#475569' }}
        >
          {editLoading ? <CircularProgress size={14} /> : '✏ Editar sesión'}
        </Button>
        {!isCompleted && (
          <Button
            variant="contained"
            size="small"
            onClick={() => { onMarkComplete?.(assignment); onClose(); }}
            sx={{ flex: 1, borderRadius: 2, textTransform: 'none', fontWeight: 600, bgcolor: color, '&:hover': { bgcolor: color, filter: 'brightness(0.92)' } }}
          >
            ✓ Marcar completado
          </Button>
        )}
      </Box>
      {/* FIX 3: Inline edit modal */}
      {editModalOpen && (
        <WorkoutAssignmentEditModal
          open={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          assignmentId={assignment?.id}
          orgId={orgId}
          initialWorkout={editWorkout}
          onSaved={handleEditSaved}
        />
      )}
    </Drawer>
  );
}
