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
import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Typography, Chip, Button, Divider, Tooltip, Tabs, Tab,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import IconButton from '@mui/material/IconButton';
import { MiniWorkoutProfile } from '../MiniWorkoutProfile';
import { weatherBadgeProps } from '../../hooks/useWeatherIcon';
import { sportLabel, sportColor, fmtDuration, fmtDistance } from '../../utils/calendarHelpers';
import MarkdownRenderer from '../MarkdownRenderer';
import { getSessionMessages, sendMessage } from '../../api/messages';
import { useOrg } from '../../context/OrgContext';

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

// Fix 5: hierarchical block viewer with "Repetir × N" grouping
function BlockGroupList({ blocks }) {
  if (!blocks?.length) return null;

  const totalDistM = blocks.reduce((sum, b) => {
    const reps = b.repetitions ?? 1;
    const blockDist = (b.intervals ?? []).reduce((s, iv) => s + (iv.distance_meters ?? 0), 0);
    return sum + blockDist * reps;
  }, 0);
  const totalDurS = blocks.reduce((sum, b) => {
    const reps = b.repetitions ?? 1;
    const blockDur = (b.intervals ?? []).reduce((s, iv) => s + (iv.duration_seconds ?? 0), 0);
    return sum + blockDur * reps;
  }, 0);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      {blocks.map((block, bi) => {
        const reps = block.repetitions ?? 1;
        const isRepeat = reps > 1;
        const intervals = block.intervals ?? [];
        const blockDistM = intervals.reduce((s, iv) => s + (iv.distance_meters ?? 0), 0);

        return (
          <Box key={bi}>
            {isRepeat ? (
              <Box sx={{ border: '1px solid #bfdbfe', borderRadius: 1.5, overflow: 'hidden' }}>
                <Box sx={{ px: 1, py: 0.4, bgcolor: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography sx={{ fontSize: '0.62rem', fontWeight: 700, color: '#1d4ed8' }}>
                    Repetir × {reps}
                  </Typography>
                  {blockDistM > 0 && (
                    <Typography sx={{ fontSize: '0.58rem', color: '#3b82f6' }}>
                      {fmtDistance(blockDistM * reps)} trabajo
                    </Typography>
                  )}
                </Box>
                <Box sx={{ px: 0.5, py: 0.4, display: 'flex', flexDirection: 'column', gap: 0.3 }}>
                  {intervals.map((iv, ii) => <IntervalRow key={ii} iv={iv} />)}
                </Box>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
                {intervals.map((iv, ii) => (
                  <IntervalRow key={ii} iv={iv} blockName={block.name || block.block_type} />
                ))}
              </Box>
            )}
          </Box>
        );
      })}
      {/* Total volume row */}
      {(totalDistM > 0 || totalDurS > 0) && (
        <Box sx={{ borderTop: '1px solid #e2e8f0', pt: 0.5, display: 'flex', gap: 2 }}>
          {totalDistM > 0 && (
            <Typography sx={{ fontSize: '0.62rem', color: '#64748b' }}>
              📏 Total: {fmtDistance(totalDistM)}
            </Typography>
          )}
          {totalDurS > 0 && (
            <Typography sx={{ fontSize: '0.62rem', color: '#64748b' }}>
              ~{fmtDuration(totalDurS)} estimado
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}

function IntervalRow({ iv, blockName }) {
  const duration = iv.duration_seconds ? fmtDuration(iv.duration_seconds) : null;
  const distance = iv.distance_meters ? fmtDistance(iv.distance_meters) : null;
  const label = iv.target_label || null;
  const reps = iv.repetitions > 1 ? `${iv.repetitions}×` : null;
  const metric = [reps, distance, duration, label].filter(Boolean).join(' · ');
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1, py: 0.3, borderRadius: 1, bgcolor: '#f8fafc' }}>
      {blockName && (
        <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: '#94a3b8', minWidth: 52, flexShrink: 0 }}>
          {blockName}
        </Typography>
      )}
      <Typography sx={{ fontSize: '0.65rem', color: '#1e293b' }}>
        {metric || (iv.description || '—')}
      </Typography>
    </Box>
  );
}

// Legacy flat step list (kept for fallback when blocks not available)
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
  const fillPct = Math.min(pct, 100);
  const color = pct > 150 ? '#7c3aed' : pct > 120 ? '#3b82f6' : pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
        <Typography sx={{ fontSize: '0.65rem', color: '#64748b' }}>Cumplimiento</Typography>
        <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color }}>{pct}%</Typography>
      </Box>
      <Box sx={{ height: 6, borderRadius: 3, bgcolor: '#e2e8f0', overflow: 'hidden' }}>
        <Box sx={{ height: '100%', width: `${fillPct}%`, bgcolor: color, borderRadius: 3, transition: 'width 0.3s' }} />
      </Box>
    </Box>
  );
}

const fmtPace = (s) => {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, '0')}/km`;
};

// ── SessionConversation ───────────────────────────────────────────────────────

function SessionConversation({ assignmentId, orgId, role }) {
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!assignmentId || !orgId) return;
    getSessionMessages(orgId, assignmentId)
      .then((r) => setMsgs(Array.isArray(r.data) ? r.data : []))
      .catch(() => {});
  }, [assignmentId, orgId]);

  const handleSend = async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await sendMessage(orgId, {
        content: text.trim(),
        alert_type: 'session_comment',
        reference_id: assignmentId,
      });
      const r = await getSessionMessages(orgId, assignmentId);
      setMsgs(Array.isArray(r.data) ? r.data : []);
      setText('');
    } catch { /* graceful */ } finally {
      setSending(false);
    }
  };

  if (!assignmentId || !orgId) return null;
  return (
    <>
      <Divider sx={{ my: 1.5 }} />
      <SectionLabel>💬 Conversación</SectionLabel>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mb: 1.5 }}>
        {msgs.map((m) => (
          <Box key={m.id} sx={{
            p: 1, borderRadius: 1.5, border: '1px solid #e2e8f0',
            bgcolor: m.is_coach_message ? '#f0fdf4' : '#f8fafc',
          }}>
            <Typography sx={{ fontSize: '0.62rem', color: '#94a3b8', mb: 0.25 }}>
              {m.sender_name}
            </Typography>
            <Typography sx={{ fontSize: '0.74rem', color: '#1e293b' }}>{m.content}</Typography>
          </Box>
        ))}
        {msgs.length === 0 && (
          <Typography sx={{ fontSize: '0.72rem', color: '#94a3b8' }}>Sin mensajes aún.</Typography>
        )}
      </Box>
      <Box sx={{ display: 'flex', gap: 1 }}>
        <Box component="input"
          sx={{ flex: 1, fontSize: '0.74rem', p: '6px 10px',
            border: '1px solid #e2e8f0', borderRadius: 2, outline: 'none',
            '&:focus': { borderColor: '#059669' } }}
          placeholder={role === 'coach' ? 'Responder al atleta...' : 'Responder al coach...'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
        />
        <Button size="small" variant="contained" disabled={sending || !text.trim()}
          onClick={handleSend}
          sx={{ bgcolor: '#059669', '&:hover': { bgcolor: '#047857' },
            fontSize: '0.7rem', px: 1.5, minWidth: 0 }}>→</Button>
      </Box>
    </>
  );
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export default function WorkoutModal({ open, onClose, payload, role = 'athlete' }) {
  const [activeTab, setActiveTab] = useState(0);
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.id;

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
  // Fix 2: strip "(personalizado)" suffix from displayed title
  const rawTitle = isFree
    ? sportLabel(discipline)
    : (pw?.name ?? assignment?.planned_workout_title ?? 'Entrenamiento');
  const title = rawTitle.replace(/ \(personalizado\)$/i, '');

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

  // Real metrics — from Strava activity if paired, else from manual completion data on assignment
  const realDurationMin = act?.duration_min
    ?? (act?.duration_s != null ? Math.round(act.duration_s / 60) : null)
    ?? (act?.actual_duration_seconds != null ? Math.round(act.actual_duration_seconds / 60) : null)
    ?? (assignment?.actual_duration_seconds != null ? Math.round(assignment.actual_duration_seconds / 60) : null);
  const realDistanceKm = act?.distance_km
    ?? (act?.distance_m != null ? (act.distance_m / 1000).toFixed(1) : null)
    ?? (act?.actual_distance_meters != null ? (act.actual_distance_meters / 1000).toFixed(1) : null)
    ?? (assignment?.actual_distance_meters != null ? (assignment.actual_distance_meters / 1000).toFixed(1) : null);
  const realElevation = act?.elevation_m ?? act?.elevation_gain_m ?? act?.actual_elevation_gain
    ?? assignment?.actual_elevation_gain ?? null;

  const compliancePct = reconciliation?.compliance_pct ?? assignment?.compliance_pct ?? null;
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

      {/* Tab bar — only show Análisis if there's a real activity */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}>
        <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)}
          sx={{ minHeight: 36 }} textColor="inherit"
          TabIndicatorProps={{ style: { backgroundColor: '#059669' } }}>
          <Tab label="Resumen" sx={{ fontSize: '0.72rem', minHeight: 36, textTransform: 'none' }} />
          <Tab label="Análisis" disabled={!act && !assignment?.actual_duration_seconds && !assignment?.actual_distance_meters}
            sx={{ fontSize: '0.72rem', minHeight: 36, textTransform: 'none' }} />
        </Tabs>
      </Box>

      <DialogContent sx={{ px: 2.5, py: 2, overflowY: 'auto' }}>
        {/* ── Tab 1: Análisis ── */}
        {activeTab === 1 && (act || assignment?.actual_duration_seconds) && (
          <Box sx={{ pt: 1 }}>
            {!act && (assignment?.actual_duration_seconds || assignment?.actual_distance_meters) && (
              <Box sx={{ display:'flex', gap:1.5, flexWrap:'wrap', mb:2 }}>
                {assignment.actual_duration_seconds && <MetricChip label="Duración" value={`${Math.round(assignment.actual_duration_seconds/60)}min`} color="#16a34a"/>}
                {assignment.actual_distance_meters && <MetricChip label="Distancia" value={`${(assignment.actual_distance_meters/1000).toFixed(1)}km`} color="#16a34a"/>}
                {assignment.actual_elevation_gain && <MetricChip label="D+" value={`${assignment.actual_elevation_gain}m`} color="#16a34a"/>}
                <Typography sx={{fontSize:'0.72rem',color:'#94a3b8',alignSelf:'center',ml:1}}>
                  Análisis completo disponible al sincronizar con Strava.
                </Typography>
              </Box>
            )}
            {act && (
              <>
                <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap', mb: 2 }}>
                  {act.avg_hr && <MetricChip label="FC prom" value={`${act.avg_hr}bpm`} />}
                  {act.max_hr && <MetricChip label="FC máx" value={`${act.max_hr}bpm`} />}
                  {act.avg_pace_s_km && <MetricChip label="Ritmo" value={fmtPace(act.avg_pace_s_km)} />}
                  {(act.elevation_gain_m ?? act.actual_elevation_gain) != null && (
                    <MetricChip label="D+" value={`${Math.round(act.elevation_gain_m ?? act.actual_elevation_gain)}m`} />
                  )}
                  {act.calories && <MetricChip label="Calorías" value={`${Math.round(act.calories)}kcal`} />}
                  {act?.canonical_load && (
                    <Tooltip title="Training Stress Score (TSS): carga del entrenamiento. 100 = 1 hora al máximo esfuerzo." arrow>
                      <Box><MetricChip label="TSS ①" value={String(Math.round(act.canonical_load))} color="#7c3aed"/></Box>
                    </Tooltip>
                  )}
                </Box>
                {(act.splits ?? []).length > 0 ? (
                  <>
                    <SectionLabel>Splits</SectionLabel>
                    <Box sx={{ overflowX: 'auto', mb: 1.5 }}>
                      <table style={{ width: '100%', fontSize: '0.7rem', borderCollapse: 'collapse' }}>
                        <thead><tr>
                          {['#', 'Dist', 'Tiempo', 'Ritmo', 'FC', 'D+'].map((h) => (
                            <th key={h} style={{ textAlign: 'left', padding: '4px 6px', color: '#94a3b8', fontWeight: 600 }}>{h}</th>
                          ))}
                        </tr></thead>
                        <tbody>
                          {act.splits.map((s, i) => (
                            <tr key={i} style={{ borderTop: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '4px 6px' }}>{i + 1}</td>
                              <td style={{ padding: '4px 6px' }}>{s.km != null ? `${s.km}km` : '—'}</td>
                              <td style={{ padding: '4px 6px' }}>{s.time_s ? fmtDuration(s.time_s) : '—'}</td>
                              <td style={{ padding: '4px 6px' }}>{s.pace_s_km ? fmtPace(s.pace_s_km) : '—'}</td>
                              <td style={{ padding: '4px 6px' }}>{s.avg_hr ? Math.round(s.avg_hr) : '—'}</td>
                              <td style={{ padding: '4px 6px' }}>{s.elevation_diff_m != null ? `${Math.round(s.elevation_diff_m)}m` : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Box>
                  </>
                ) : (
                  <Typography sx={{ fontSize: '0.75rem', color: '#94a3b8', textAlign: 'center', py: 2 }}>
                    {act ? 'Splits no disponibles para esta actividad' : 'Análisis completo disponible cuando la actividad se sincronice con Strava.'}
                  </Typography>
                )}
              </>
            )}
          </Box>
        )}

        {/* ── Tab 0: Resumen ── */}
        {activeTab === 0 && (
          <>
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

            {/* Fix 5: hierarchical block view (preferred); flat steps as fallback */}
            {blocks.length > 0 && (
              <>
                <SectionLabel>📋 Pasos</SectionLabel>
                <Box sx={{ mb: 1.5 }}>
                  <BlockGroupList blocks={blocks} />
                </Box>
              </>
            )}
            {blocks.length === 0 && intensitySteps.length > 0 && (
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

        {/* ── Case 1 + manually completed: show athlete's own session data ── */}
        {caseNum === 1 && assignment?.status === 'completed' && (realDurationMin || realDistanceKm || athleteRpe != null) && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <SectionLabel>✅ Tu sesión</SectionLabel>
            {(realDurationMin || realDistanceKm || realElevation) && (
              <Box sx={{ display: 'flex', gap: 2, mb: 1.5, flexWrap: 'wrap' }}>
                <MetricChip label="Duración" value={realDurationMin ? `${realDurationMin}min` : null} color="#16a34a" />
                <MetricChip label="Distancia" value={realDistanceKm ? `${realDistanceKm}km` : null} color="#16a34a" />
                {realElevation && <MetricChip label="D+" value={`${realElevation}m`} color="#16a34a" />}
              </Box>
            )}
            <ComplianceBar pct={compliancePct} />
            {(athleteRpe != null || athleteNotes) && (
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
              {act.avg_hr && <MetricChip label="FC prom" value={`${act.avg_hr}bpm`} color="#16a34a" />}
              {act.max_hr && <MetricChip label="FC máx" value={`${act.max_hr}bpm`} color="#16a34a" />}
              {act.canonical_load && (
                <Tooltip title="Training Stress Score (TSS): carga del entrenamiento. 100 = 1h al máximo esfuerzo." arrow>
                  <Box><MetricChip label="TSS ①" value={String(Math.round(act.canonical_load))} color="#7c3aed" /></Box>
                </Tooltip>
              )}
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
          </>
        )}
        {assignment?.id && orgId && (
          <SessionConversation assignmentId={assignment.id} orgId={orgId} role={role} />
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
