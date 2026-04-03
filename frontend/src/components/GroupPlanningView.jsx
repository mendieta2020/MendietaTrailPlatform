/**
 * GroupPlanningView — PR-158 hotfix
 *
 * Group-level week planning surface shown when the coach clicks a week
 * header in MacroView. Replaces the DnDCalendar in Calendar.jsx for group
 * context, avoiding the chaos of 50 athletes' assignments mixed together.
 *
 * Layout:
 *   HistorialPanel (6-week history above)
 *   7 day drop zones (drag workouts from Library sidebar)
 *   WeeklyLoadEstimate (representative athlete TSS + phase)
 *   TSS estimate + "Asignar a grupo" button
 *
 * Props:
 *   orgId                     — organization ID
 *   weekStart                 — Monday of the week being planned (YYYY-MM-DD)
 *   teamId                    — team filter (number | null)
 *   onBack                    — callback to dismiss planning mode
 *   draggingWorkoutRef        — ref shared with Library sidebar (drag source)
 *   onAssigned                — callback() after successful assignment
 *   representativeMembershipId — membership_id of first team athlete for TSS estimate
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  CircularProgress,
  Alert,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import CloseIcon from '@mui/icons-material/Close';
import { getGroupWeekTemplate } from '../api/planning';
import { bulkAssignTeam } from '../api/assignments';
import HistorialPanel from './HistorialPanel';
import WeeklyLoadEstimate from './WeeklyLoadEstimate';
import WorkoutCoachDrawer from './WorkoutCoachDrawer';

const MONTHS_SHORT = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const DAY_LABELS_ES = ['LUN','MAR','MIÉ','JUE','VIE','SÁB','DOM'];

function weekLabel(weekStart) {
  const d = new Date(weekStart + 'T12:00:00');
  const end = new Date(d);
  end.setDate(end.getDate() + 6);
  const copy = new Date(weekStart + 'T12:00:00');
  const dow = copy.getUTCDay() || 7;
  copy.setUTCDate(copy.getUTCDate() + 4 - dow);
  const yearStart = new Date(Date.UTC(copy.getUTCFullYear(), 0, 1));
  const wNum = Math.ceil(((copy - yearStart) / 86400000 + 1) / 7);
  return `W${wNum} — ${d.getDate()} ${MONTHS_SHORT[d.getMonth()]} al ${end.getDate()} ${MONTHS_SHORT[end.getMonth()]}`;
}

function SportChip({ sport }) {
  const colors = {
    TRAIL: '#F57C00', RUNNING: '#3b82f6', CYCLING: '#16a34a',
    SWIM: '#06b6d4', STRENGTH: '#8b5cf6', OTHER: '#64748b',
  };
  const color = colors[sport] || colors.OTHER;
  return (
    <Chip
      label={sport}
      size="small"
      sx={{
        height: 16,
        fontSize: '0.58rem',
        fontWeight: 700,
        bgcolor: `${color}22`,
        color,
        border: `1px solid ${color}44`,
        '& .MuiChip-label': { px: 0.5 },
      }}
    />
  );
}

function addWeeksDays(dateStr, n) {
  const d = new Date(dateStr + 'T12:00:00');
  d.setDate(d.getDate() + n * 7);
  return d.toISOString().slice(0, 10);
}

function isoWeekNum(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const dow = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dow);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

export default function GroupPlanningView({
  orgId,
  weekStart,
  teamId,
  onBack,
  onNavigateWeek,
  draggingWorkoutRef,
  onAssigned,
  representativeMembershipId,
}) {
  const [template, setTemplate] = useState(null);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [dragOver, setDragOver] = useState(null);
  const [pending, setPending] = useState({});  // { "YYYY-MM-DD": [workout, ...] }
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(null);
  // Increments after each successful assign to trigger WeeklyLoadEstimate refresh
  const [assignTrigger, setAssignTrigger] = useState(0);
  // WorkoutCoachDrawer — shows workout detail on card click
  const [drawerWorkout, setDrawerWorkout] = useState(null);

  const fetchTemplate = useCallback(() => {
    if (!orgId || !weekStart) return;
    let cancelled = false;
    setLoadingTemplate(true);
    getGroupWeekTemplate(orgId, { weekStart, teamId: teamId || undefined })
      .then((res) => {
        if (!cancelled) { setTemplate(res.data); setLoadingTemplate(false); }
      })
      .catch(() => {
        if (!cancelled) { setLoadingTemplate(false); }
      });
    return () => { cancelled = true; };
  }, [orgId, weekStart, teamId]);

  useEffect(() => {
    const cancel = fetchTemplate();
    return cancel;
  }, [fetchTemplate]);

  const handleDragOver = (date) => (e) => {
    e.preventDefault();
    setDragOver(date);
  };

  const handleDragLeave = () => setDragOver(null);

  const handleDrop = (date) => (e) => {
    e.preventDefault();
    setDragOver(null);
    const workout = draggingWorkoutRef.current;
    if (!workout) return;
    draggingWorkoutRef.current = null;
    setPending((prev) => ({
      ...prev,
      [date]: [...(prev[date] || []), {
        planned_workout_id: workout.id,
        title: workout.name,
        sport: workout.discipline ? workout.discipline.toUpperCase() : 'OTHER',
        duration_min: workout.estimated_duration_seconds
          ? Math.round(workout.estimated_duration_seconds / 60) : null,
        distance_km: workout.estimated_distance_meters
          ? Math.round(workout.estimated_distance_meters / 100) / 10 : null,
        planned_tss: workout.planned_tss || null,
      }],
    }));
  };

  const removePending = (date, idx) => {
    setPending((prev) => {
      const updated = [...(prev[date] || [])];
      updated.splice(idx, 1);
      if (updated.length === 0) {
        const next = { ...prev };
        delete next[date];
        return next;
      }
      return { ...prev, [date]: updated };
    });
  };

  const pendingCount = Object.values(pending).reduce((sum, arr) => sum + arr.length, 0);

  const pendingTss = Object.values(pending).flat().reduce((sum, wo) => {
    if (wo.planned_tss) return sum + wo.planned_tss;
    if (wo.duration_min) return sum + (wo.duration_min / 60) * 50;
    return sum;
  }, 0);

  const handleAssign = async () => {
    const tasks = [];
    for (const [date, workouts] of Object.entries(pending)) {
      for (const wo of workouts) {
        tasks.push({ planned_workout_id: wo.planned_workout_id, date });
      }
    }
    if (tasks.length === 0) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      for (const { planned_workout_id, date } of tasks) {
        await bulkAssignTeam(orgId, {
          planned_workout_id,
          team_id: teamId || null,
          scheduled_date: date,
        });
      }
      setPending({});
      setSaveSuccess(`${tasks.length} entrenamiento(s) asignado(s) al grupo.`);
      setAssignTrigger((t) => t + 1);
      // Fix 1: Direct re-fetch avoids cancel-function interference with useEffect.
      // fetchTemplate() shares a `cancelled` variable with the useEffect — calling
      // it here could race with the effect cleanup. Instead we call the API directly.
      getGroupWeekTemplate(orgId, { weekStart, teamId: teamId || undefined })
        .then((res) => { setTemplate(res.data); })
        .catch(() => {});
      if (onAssigned) onAssigned();
    } catch {
      setSaveError('Error al asignar. Intenta de nuevo.');
    } finally {
      setSaving(false);
    }
  };

  // Build synthetic event for WorkoutCoachDrawer
  const drawerEvent = drawerWorkout ? {
    id: `gpv-${drawerWorkout.planned_workout_id}`,
    title: drawerWorkout.title,
    resource: {
      id: null,
      planned_workout: {
        id: drawerWorkout.planned_workout_id,
        name: drawerWorkout.title,
        discipline: drawerWorkout.sport ? drawerWorkout.sport.toLowerCase() : 'other',
        estimated_duration_seconds: drawerWorkout.duration_min
          ? drawerWorkout.duration_min * 60 : null,
        estimated_distance_meters: drawerWorkout.distance_km
          ? drawerWorkout.distance_km * 1000 : null,
        planned_tss: drawerWorkout.planned_tss,
      },
      status: 'planned',
      compliance_color: 'gray',
    },
  } : null;

  const days = template?.days ?? [];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, height: '100%' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
        <Tooltip title="Volver al Planificador">
          <IconButton size="small" onClick={onBack} sx={{ color: '#94a3b8' }}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#e2e8f0' }}>
          Planificador de grupo —{' '}
          <span style={{ color: '#F57C00' }}>{weekStart ? weekLabel(weekStart) : ''}</span>
        </Typography>
        {template?.team_name && (
          <Chip
            label={template.team_name}
            size="small"
            sx={{ fontSize: '0.67rem', bgcolor: '#1e293b', color: '#94a3b8', border: '1px solid #334155' }}
          />
        )}
        {/* Week navigation */}
        {onNavigateWeek && weekStart && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 'auto' }}>
            <Tooltip title={`Semana anterior (W${isoWeekNum(addWeeksDays(weekStart, -1))})`}>
              <IconButton
                size="small"
                onClick={() => onNavigateWeek(addWeeksDays(weekStart, -1))}
                sx={{ color: '#94a3b8', '&:hover': { color: '#F57C00' } }}
              >
                <ArrowBackIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.7rem', px: 0.5 }}>
              W{isoWeekNum(weekStart)}
            </Typography>
            <Tooltip title={`Semana siguiente (W${isoWeekNum(addWeeksDays(weekStart, 1))})`}>
              <IconButton
                size="small"
                onClick={() => onNavigateWeek(addWeeksDays(weekStart, 1))}
                sx={{ color: '#94a3b8', '&:hover': { color: '#F57C00' } }}
              >
                <ArrowBackIcon fontSize="small" sx={{ transform: 'rotate(180deg)' }} />
              </IconButton>
            </Tooltip>
          </Box>
        )}
      </Box>

      {/* Historial Panel */}
      <HistorialPanel
        orgId={orgId}
        teamId={teamId}
        targetWeek={weekStart}
        onCopyWeek={null}
      />

      {/* Loading template */}
      {loadingTemplate && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
          <CircularProgress size={20} sx={{ color: '#F57C00' }} />
        </Box>
      )}

      {/* Day grid */}
      {!loadingTemplate && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, 1fr)',
            gap: 1,
            flex: 1,
            minHeight: 0,
          }}
        >
          {(days.length > 0 ? days : DAY_LABELS_ES.map((_, i) => {
            const d = new Date(weekStart + 'T12:00:00');
            d.setDate(d.getDate() + i);
            return { date: d.toISOString().slice(0, 10), day: DAY_LABELS_ES[i], workouts: [] };
          })).map((day, i) => {
            const pendingForDay = pending[day.date] || [];
            const isOver = dragOver === day.date;
            return (
              <Box
                key={day.date}
                onDragOver={handleDragOver(day.date)}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop(day.date)}
                sx={{
                  border: isOver
                    ? '2px dashed #F57C00'
                    : '1px solid rgba(255,255,255,0.08)',
                  borderRadius: 1.5,
                  bgcolor: isOver ? 'rgba(245,124,0,0.06)' : '#0f1621',
                  p: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.5,
                  minHeight: 120,
                  transition: 'border-color 0.15s, background-color 0.15s',
                  overflowY: 'auto',
                }}
              >
                {/* Day header */}
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 700,
                    color: '#64748b',
                    fontSize: '0.65rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    pb: 0.5,
                    borderBottom: '1px solid rgba(255,255,255,0.06)',
                    mb: 0.25,
                  }}
                >
                  {DAY_LABELS_ES[i]}
                </Typography>

                {/* Existing template workouts — click to view in drawer */}
                {day.workouts.map((wo, j) => (
                  <Box
                    key={j}
                    onClick={() => setDrawerWorkout(wo)}
                    sx={{
                      bgcolor: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.07)',
                      borderRadius: 1,
                      px: 0.75,
                      py: 0.5,
                      cursor: 'pointer',
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.08)', borderColor: 'rgba(255,255,255,0.15)' },
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        color: '#cbd5e1',
                        fontSize: '0.67rem',
                        display: 'block',
                        lineHeight: 1.3,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {wo.title}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25, flexWrap: 'wrap' }}>
                      <SportChip sport={wo.sport} />
                      {wo.distance_km && (
                        <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.6rem' }}>
                          {wo.distance_km}km
                        </Typography>
                      )}
                    </Box>
                  </Box>
                ))}

                {/* Pending workouts (to be assigned) */}
                {pendingForDay.map((wo, j) => (
                  <Box
                    key={`p-${j}`}
                    onClick={() => setDrawerWorkout(wo)}
                    sx={{
                      bgcolor: 'rgba(245,124,0,0.08)',
                      border: '1px dashed #F57C00',
                      borderRadius: 1,
                      px: 0.75,
                      py: 0.5,
                      position: 'relative',
                      cursor: 'pointer',
                      '&:hover': { bgcolor: 'rgba(245,124,0,0.14)' },
                    }}
                  >
                    <IconButton
                      size="small"
                      onClick={(e) => { e.stopPropagation(); removePending(day.date, j); }}
                      sx={{
                        position: 'absolute',
                        top: 2,
                        right: 2,
                        p: 0.1,
                        color: '#F57C00',
                      }}
                    >
                      <CloseIcon sx={{ fontSize: 11 }} />
                    </IconButton>
                    <Typography
                      variant="caption"
                      sx={{
                        color: '#fdba74',
                        fontSize: '0.67rem',
                        display: 'block',
                        lineHeight: 1.3,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        pr: 1.5,
                      }}
                    >
                      {wo.title}
                    </Typography>
                    <SportChip sport={wo.sport} />
                  </Box>
                ))}

                {/* Drop hint */}
                {day.workouts.length === 0 && pendingForDay.length === 0 && (
                  <Box
                    sx={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#2d3748',
                    }}
                  >
                    <AddCircleOutlineIcon sx={{ fontSize: 18 }} />
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      )}

      {/* Fix 2: WeeklyLoadEstimate — representative athlete TSS + phase */}
      {representativeMembershipId && (
        <WeeklyLoadEstimate
          membershipId={representativeMembershipId}
          weekStart={weekStart}
          trigger={assignTrigger}
        />
      )}

      {/* Footer: TSS estimate + assign button */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          pt: 1,
          borderTop: '1px solid rgba(255,255,255,0.06)',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {pendingTss > 0 && (
            <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.67rem' }}>
              TSS pendiente:{' '}
              <strong style={{ color: '#F57C00' }}>{Math.round(pendingTss)}</strong>
            </Typography>
          )}
          {pendingCount > 0 && (
            <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.67rem' }}>
              {pendingCount} entrenamiento(s) por asignar
            </Typography>
          )}
        </Box>

        <Box sx={{ display: 'flex', gap: 1 }}>
          {saveSuccess && (
            <Typography variant="caption" sx={{ color: '#22c55e', alignSelf: 'center', fontSize: '0.67rem' }}>
              {saveSuccess}
            </Typography>
          )}
          {saveError && (
            <Alert severity="error" sx={{ py: 0.25, fontSize: '0.67rem' }}>{saveError}</Alert>
          )}
          <Button
            variant="contained"
            size="small"
            onClick={handleAssign}
            disabled={pendingCount === 0 || saving}
            startIcon={saving ? <CircularProgress size={12} sx={{ color: 'inherit' }} /> : null}
            sx={{
              bgcolor: '#F57C00',
              color: '#fff',
              fontWeight: 700,
              fontSize: '0.72rem',
              '&:hover': { bgcolor: '#e65c00' },
              '&:disabled': { bgcolor: '#374151', color: '#6b7280' },
            }}
          >
            Asignar a grupo
          </Button>
        </Box>
      </Box>

      {/* Fix 3: WorkoutCoachDrawer for workout card detail view */}
      <WorkoutCoachDrawer
        key={drawerEvent?.id ?? 'none'}
        event={drawerEvent}
        orgId={orgId}
        onClose={() => setDrawerWorkout(null)}
        onSaved={() => {}}
        onMarkComplete={() => {}}
      />
    </Box>
  );
}
