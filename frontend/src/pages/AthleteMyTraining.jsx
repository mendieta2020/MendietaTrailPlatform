import React, { useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import {
  Box, Typography, Paper, IconButton, Chip, CircularProgress, Alert,
} from '@mui/material';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';
import {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek,
  addMonths, subMonths, eachDayOfInterval, isSameMonth, isSameDay, format,
} from 'date-fns';
import { es } from 'date-fns/locale';
import AthleteLayout from '../components/AthleteLayout';
import WorkoutDetailDrawer from '../components/WorkoutDetailDrawer';
import { CompleteWorkoutModal } from '../components/CompleteWorkoutModal';
import { MiniWorkoutProfile } from '../components/MiniWorkoutProfile';
import { weatherChip } from '../hooks/useWeatherIcon';
import { useAuth } from '../context/AuthContext';
import { listAssignments, updateAssignment } from '../api/assignments';
import client from '../api/client';

// ── Sport colors ──────────────────────────────────────────────────────────────

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
  trail:    'Trail',
  run:      'Running',
  bike:     'Ciclismo',
  cycling:  'Ciclismo',
  strength: 'Fuerza',
  mobility: 'Movilidad',
  swim:     'Natación',
  other:    'Otro',
};

function sportColor(discipline) {
  return SPORT_COLOR[discipline] ?? '#94a3b8';
}

function sportLabel(discipline) {
  return SPORT_LABEL[discipline] ?? discipline ?? 'Otro';
}

// ── Duration formatting ───────────────────────────────────────────────────────

function fmtDuration(seconds) {
  if (!seconds) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h${m > 0 ? ` ${m}min` : ''}`;
  return `${m}min`;
}

function fmtDistance(meters) {
  if (!meters) return null;
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}km`;
  return `${meters}m`;
}

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  planned:   { label: 'Planificado', color: '#64748b', bg: '#f1f5f9' },
  completed: { label: 'Completado',  color: '#16a34a', bg: '#f0fdf4' },
  skipped:   { label: 'Saltado',     color: '#d97706', bg: '#fffbeb' },
  canceled:  { label: 'Cancelado',   color: '#dc2626', bg: '#fef2f2' },
  moved:     { label: 'Movido',      color: '#7c3aed', bg: '#f5f3ff' },
};

// ── Compliance dot ─────────────────────────────────────────────────────────────

const COMPLIANCE_DOT = {
  green:  '#22C55E',
  yellow: '#EAB308',
  red:    '#EF4444',
  blue:   '#3B82F6',
  gray:   null,
};

const RPE_EMOJI = { 1: '😴', 2: '😐', 3: '🙂', 4: '💪', 5: '🔥' };

// ── WorkoutDayCard — dual-state ─────────────────────────────────────────────────

function WorkoutDayCard({ assignment, onClick, onCompleteClick }) {
  const pw = assignment.planned_workout;
  const discipline = pw?.discipline ?? 'other';
  const color = sportColor(discipline);
  const isCompleted = assignment.status === 'completed';

  // Metrics: prefer actual data when completed
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

  const dotColor = COMPLIANCE_DOT[assignment.compliance_color];
  const chip = weatherChip(assignment.weather_snapshot);
  const blocks = pw?.blocks ?? [];

  const handleClick = (e) => {
    e.stopPropagation();
    onClick(assignment);
  };

  const handleCompleteClick = (e) => {
    e.stopPropagation();
    onCompleteClick(assignment);
  };

  return (
    <Paper
      onClick={handleClick}
      sx={{
        borderRadius: 2,
        boxShadow: 'none',
        border: `1px solid #e2e8f0`,
        borderLeftColor: color,
        borderLeftWidth: 3,
        borderLeftStyle: 'solid',
        cursor: 'pointer',
        bgcolor: isCompleted ? '#f0fdf4' : 'white',
        transition: 'box-shadow 0.15s',
        '&:hover': { boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
        mb: 0.5,
        p: 1,
        minWidth: 0,
      }}
    >
      {/* Row 1: Sport label + weather + compliance dot */}
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
          {isCompleted && dotColor && (
            <Box
              title={`Compliance: ${assignment.compliance_color}`}
              sx={{
                width: 8, height: 8, borderRadius: '50%',
                bgcolor: dotColor, flexShrink: 0,
              }}
            />
          )}
          {isCompleted && !dotColor && (
            <span style={{ fontSize: 10, color: '#16a34a', fontWeight: 700 }}>✓</span>
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

      {/* Row 4: Mini workout profile bar */}
      <MiniWorkoutProfile
        blocks={blocks}
        estimatedDuration={pw?.estimated_duration_seconds}
      />

      {/* Row 5: Status + RPE */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.5 }}>
        {isCompleted ? (
          <Typography variant="caption" sx={{ color: '#16a34a', fontSize: '0.6rem', fontWeight: 600 }}>
            ✓ Completado
          </Typography>
        ) : (
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

// ── WeekSummaryRow ────────────────────────────────────────────────────────────

function WeekSummaryRow({ weekAssignments, pmcData }) {
  if (weekAssignments.length === 0) return null;

  const done = weekAssignments.filter((a) => a.status === 'completed').length;
  const total = weekAssignments.length;
  const totalKm = weekAssignments.reduce((s, a) => {
    return s + ((a.planned_workout?.estimated_distance_meters ?? 0) / 1000);
  }, 0);
  const totalDPlus = weekAssignments.reduce((s, a) => {
    return s + (a.planned_workout?.elevation_gain_min_m ?? 0);
  }, 0);
  const totalTSS = weekAssignments.reduce((s, a) => s + (a.planned_workout?.planned_tss ?? 0), 0);

  const parts = [`${done} de ${total} entrenamientos`];
  if (totalKm > 0.1) parts.push(`${totalKm.toFixed(1)}km`);
  if (totalDPlus > 0) parts.push(`${Math.round(totalDPlus)}m D+`);
  if (totalTSS > 0) parts.push(`TSS: ${Math.round(totalTSS)}`);

  const tsbVal = pmcData?.tsb;
  const tsbColor = tsbVal == null ? '#94a3b8'
    : tsbVal > 0 ? '#16a34a'
    : tsbVal < -20 ? '#dc2626'
    : '#d97706';

  return (
    <Box
      sx={{
        gridColumn: '1 / -1',
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
      <Typography variant="caption" sx={{ color: '#475569', fontSize: '0.7rem', fontWeight: 500 }}>
        {parts.join(' · ')}
      </Typography>
      {pmcData && (
        <Box sx={{ display: 'flex', gap: 1 }}>
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildCalendarWeeks(currentDate) {
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 1 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start: calStart, end: calEnd });

  const weeks = [];
  for (let i = 0; i < days.length; i += 7) {
    weeks.push(days.slice(i, i + 7));
  }
  return weeks;
}

const DAY_HEADERS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];

// ── Main Component ─────────────────────────────────────────────────────────────

const AthleteMyTraining = () => {
  const { user } = useAuth();
  const orgId = user?.memberships?.[0]?.org_id;

  const [currentDate, setCurrentDate] = useState(new Date());
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pmcData, setPmcData] = useState(null);
  const [selectedAssignment, setSelectedAssignment] = useState(null);
  const [completeModalOpen, setCompleteModalOpen] = useState(false);
  const [completeTarget, setCompleteTarget] = useState(null);

  const fetchData = useCallback(async () => {
    if (!orgId) { setLoading(false); return; }
    setLoading(true);
    setError('');
    try {
      const dateFrom = format(startOfMonth(currentDate), 'yyyy-MM-dd');
      const dateTo = format(endOfMonth(currentDate), 'yyyy-MM-dd');
      const res = await listAssignments(orgId, { dateFrom, dateTo });
      const data = res.data?.results ?? res.data ?? [];
      setAssignments(Array.isArray(data) ? data : []);
    } catch (err) {
      setError('Error cargando el calendario. Intenta de nuevo.');
      console.error('[AthleteMyTraining] fetch assignments error:', err);
    } finally {
      setLoading(false);
    }
  }, [orgId, currentDate]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    client.get('/api/athlete/pmc/')
      .then((res) => setPmcData(res.data))
      .catch(() => setPmcData(null));
  }, []);

  const handlePrevMonth = () => setCurrentDate((d) => subMonths(d, 1));
  const handleNextMonth = () => setCurrentDate((d) => addMonths(d, 1));

  const handleMarkComplete = async (assignment) => {
    if (!orgId) return;
    try {
      const res = await updateAssignment(orgId, assignment.id, { status: 'completed' });
      setAssignments((prev) => prev.map((a) => a.id === assignment.id ? res.data : a));
      if (selectedAssignment?.id === assignment.id) {
        setSelectedAssignment(res.data);
      }
    } catch (err) {
      console.error('[AthleteMyTraining] mark complete error:', err);
    }
  };

  const handleOpenCompleteModal = (assignment) => {
    setCompleteTarget(assignment);
    setCompleteModalOpen(true);
  };

  const handleCompleteSubmit = async (data) => {
    if (!orgId || !completeTarget) return;
    const res = await updateAssignment(orgId, completeTarget.id, data);
    setAssignments((prev) => prev.map((a) => a.id === completeTarget.id ? res.data : a));
    if (selectedAssignment?.id === completeTarget.id) {
      setSelectedAssignment(res.data);
    }
  };

  const role = user?.memberships?.[0]?.role;
  if (role && role !== 'athlete') {
    return <Navigate to="/dashboard" replace />;
  }

  const weeks = buildCalendarWeeks(currentDate);

  const assignmentsByDate = {};
  for (const a of assignments) {
    const key = a.scheduled_date;
    if (!assignmentsByDate[key]) assignmentsByDate[key] = [];
    assignmentsByDate[key].push(a);
  }

  return (
    <AthleteLayout user={user}>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Mi Entrenamiento</Typography>
          <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>Calendario de sesiones asignadas</Typography>
        </Box>

        {/* Month navigation */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconButton size="small" onClick={handlePrevMonth} sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
            <ChevronLeft fontSize="small" />
          </IconButton>
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 600, color: '#1e293b', minWidth: 140, textAlign: 'center', textTransform: 'capitalize' }}
          >
            {format(currentDate, 'MMMM yyyy', { locale: es })}
          </Typography>
          <IconButton size="small" onClick={handleNextMonth} sx={{ bgcolor: '#f1f5f9', '&:hover': { bgcolor: '#e2e8f0' } }}>
            <ChevronRight fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
          <CircularProgress sx={{ color: '#f97316' }} />
        </Box>
      ) : (
        <Paper sx={{ borderRadius: 3, overflow: 'hidden', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
          {/* Day-of-week headers */}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, 1fr)',
              bgcolor: '#f8fafc',
              borderBottom: '1px solid #e2e8f0',
            }}
          >
            {DAY_HEADERS.map((d) => (
              <Box key={d} sx={{ py: 1, textAlign: 'center' }}>
                <Typography variant="caption" sx={{ fontWeight: 700, color: '#94a3b8', fontSize: '0.65rem', letterSpacing: 0.5 }}>
                  {d}
                </Typography>
              </Box>
            ))}
          </Box>

          {/* Weeks */}
          {weeks.map((week, wIdx) => {
            const weekDateKeys = week.map((d) => format(d, 'yyyy-MM-dd'));
            const weekAssignments = weekDateKeys.flatMap((k) => assignmentsByDate[k] ?? []);

            return (
              <React.Fragment key={wIdx}>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(7, 1fr)',
                    borderBottom: weekAssignments.length > 0 ? 'none' : '1px solid #e2e8f0',
                  }}
                >
                  {week.map((day, dIdx) => {
                    const dateKey = format(day, 'yyyy-MM-dd');
                    const dayAssignments = assignmentsByDate[dateKey] ?? [];
                    const isToday = isSameDay(day, new Date());
                    const inMonth = isSameMonth(day, currentDate);

                    return (
                      <Box
                        key={dIdx}
                        sx={{
                          minHeight: 80,
                          p: 0.75,
                          borderRight: dIdx < 6 ? '1px solid #e2e8f0' : 'none',
                          bgcolor: inMonth ? 'white' : '#f8fafc',
                          position: 'relative',
                        }}
                      >
                        {/* Day number */}
                        <Box
                          sx={{
                            width: 22, height: 22,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            borderRadius: '50%',
                            bgcolor: isToday ? '#f97316' : 'transparent',
                            mb: 0.5,
                          }}
                        >
                          <Typography
                            variant="caption"
                            sx={{
                              fontWeight: isToday ? 700 : 400,
                              color: isToday ? 'white' : inMonth ? '#374151' : '#cbd5e1',
                              fontSize: '0.7rem',
                            }}
                          >
                            {format(day, 'd')}
                          </Typography>
                        </Box>

                        {/* Assignment cards */}
                        {dayAssignments.map((a) => (
                          <WorkoutDayCard
                            key={a.id}
                            assignment={a}
                            onClick={setSelectedAssignment}
                            onCompleteClick={handleOpenCompleteModal}
                          />
                        ))}
                      </Box>
                    );
                  })}
                </Box>

                {/* Week summary row */}
                <WeekSummaryRow weekAssignments={weekAssignments} pmcData={pmcData} />
              </React.Fragment>
            );
          })}
        </Paper>
      )}

      {/* Workout detail drawer */}
      <WorkoutDetailDrawer
        assignment={selectedAssignment}
        onClose={() => setSelectedAssignment(null)}
        onMarkComplete={handleMarkComplete}
      />

      {/* Complete workout modal */}
      <CompleteWorkoutModal
        open={completeModalOpen}
        onClose={() => { setCompleteModalOpen(false); setCompleteTarget(null); }}
        onSubmit={handleCompleteSubmit}
        assignment={completeTarget}
      />
    </AthleteLayout>
  );
};

export default AthleteMyTraining;
