import React, { useState, useEffect, useReducer, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, dateFnsLocalizer } from 'react-big-calendar';
import withDragAndDrop from 'react-big-calendar/lib/addons/dragAndDrop';
import {
  format,
  parse,
  startOfWeek,
  getDay,
  startOfMonth,
  endOfMonth,
  parseISO,
} from 'date-fns';
import { es } from 'date-fns/locale';
import 'react-big-calendar/lib/css/react-big-calendar.css';
import 'react-big-calendar/lib/addons/dragAndDrop/styles.css';

import {
  Box,
  Paper,
  Typography,
  Select,
  MenuItem,
  ListSubheader,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  IconButton,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  ToggleButton,
  ToggleButtonGroup,
  TextField,
  Grid,
  Fab,
  SwipeableDrawer,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import { Users, BookOpen } from 'lucide-react';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { listAthletes, listTeams, listLibraries, listPlannedWorkouts, getAthleteAvailability, getAthleteProfile, listAthleteGoals } from '../api/p1';
import { getCoachAthleteTrainingPhases } from '../api/periodization';
import {
  listAssignments, createAssignment, bulkAssignTeam,
  moveAssignment, deleteAssignment, cloneAssignmentWorkout,
} from '../api/assignments';
import UndoToast from '../components/UndoToast';
import CalendarContextMenu from '../components/CalendarContextMenu';
import DuplicateSessionModal from '../components/DuplicateSessionModal';
import CopyWeekModal from '../components/CopyWeekModal';
import DeleteWeekModal from '../components/DeleteWeekModal';
import WorkoutCoachDrawer from '../components/WorkoutCoachDrawer';
import MacroView from '../components/MacroView';
import HistorialPanel from '../components/HistorialPanel';
import WeeklyLoadEstimate from '../components/WeeklyLoadEstimate';
import GroupPlanningView from '../components/GroupPlanningView';
import { copyWeek, getCoachAthletePlanVsReal } from '../api/planning';
import { updateGoal } from '../api/athlete';
import { getCoachAthletePMC } from '../api/pmc';
import CalendarGrid from '../components/calendar/CalendarGrid';
import AthleteSearchSelector from '../components/calendar/AthleteSearchSelector';
import CoachWeekOverview from '../components/calendar/CoachWeekOverview';

const DnDCalendar = withDragAndDrop(Calendar);

const locales = { es };

// PR-145d: compliance border-left color mapping (module-level constant)
const COMPLIANCE_HEX = {
  green:  '#22C55E',
  yellow: '#EAB308',
  red:    '#EF4444',
  blue:   '#3B82F6',
  gray:   '#94A3B8',
};

// PR-154: Menstrual cycle phase helpers
const MENSTRUAL_PHASES = [
  { name: 'Menstrual',  color: '#EF4444', tip: 'Fase menstrual — escuchá a tu cuerpo' },
  { name: 'Folicular',  color: '#00D4AA', tip: 'Fase folicular — ideal para alta intensidad' },
  { name: 'Ovulación',  color: '#F59E0B', tip: 'Ovulación — pico de energía' },
  { name: 'Lútea',      color: '#F97316', tip: 'Fase lútea — reducir intensidad' },
];

function getMenstrualPhaseForDate(dateObj, lastPeriodDate, cycleDays) {
  if (!lastPeriodDate || !cycleDays) return null;
  const last = new Date(lastPeriodDate);
  const daysSince = Math.floor((dateObj - last) / 86400000);
  const dayInCycle = ((daysSince % cycleDays) + cycleDays) % cycleDays;
  if (dayInCycle <= 4)  return MENSTRUAL_PHASES[0];
  if (dayInCycle <= 12) return MENSTRUAL_PHASES[1];
  if (dayInCycle <= 14) return MENSTRUAL_PHASES[2];
  return MENSTRUAL_PHASES[3];
}

// Convert day-of-week index (0=Mon…6=Sun, matching AthleteAvailability.day_of_week)
// to JS getDay() (0=Sun…6=Sat)
function jsWeekdayToAvailIndex(jsDay) {
  // js: 0=Sun,1=Mon,...,6=Sat → avail: 0=Mon,...,6=Sun
  return jsDay === 0 ? 6 : jsDay - 1;
}

// PR-157: Training phase color strip helpers
const TRAINING_PHASE_COLORS = {
  carga:    { color: '#F97316', label: 'Carga' },
  descarga: { color: '#22c55e', label: 'Descarga' },
  carrera:  { color: '#ef4444', label: 'Carrera' },
  descanso: { color: '#3b82f6', label: 'Descanso' },
  lesion:   { color: '#6b7280', label: 'Lesión' },
};

function getMonday(dateObj) {
  const d = new Date(dateObj);
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return format(d, 'yyyy-MM-dd');
}
const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: (date) => startOfWeek(date, { weekStartsOn: 1 }),
  getDay,
  locales,
});


// ── Reducers ──────────────────────────────────────────────────────────────────

function fetchReducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':
      return { ...state, loading: true, error: null, data: [] };
    case 'FETCH_SUCCESS':
      return { data: action.data, loading: false, error: null };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    case 'CLEAR':
      return { data: [], loading: false, error: null };
    case 'ADD_EVENT':
      return { ...state, data: [...state.data, action.event] };
    case 'REMOVE_EVENT':
      return { ...state, data: state.data.filter((e) => e.id !== action.id) };
    case 'MOVE_EVENT':
      return {
        ...state,
        data: state.data.map((e) =>
          e.id === action.id
            ? {
                ...e,
                scheduled_date: action.newDate,
                start: parseISO(action.newDate),
                end: parseISO(action.newDate),
                resource: { ...e.resource, scheduled_date: action.newDate },
              }
            : e
        ),
      };
    case 'UPDATE_EVENT':
      return {
        ...state,
        data: state.data.map((e) =>
          e.id === action.id ? { ...e, ...action.updates } : e
        ),
      };
    default:
      return state;
  }
}

// ── Draggable workout card ────────────────────────────────────────────────────

function WorkoutCard({ workout, onDragStart, onDragEnd }) {
  const [isDragging, setIsDragging] = React.useState(false);

  const handleDragStart = (e) => {
    e.dataTransfer.effectAllowed = 'copy';
    onDragStart(workout);
    setIsDragging(true);
  };

  const handleDragEnd = () => {
    onDragEnd();
    setIsDragging(false);
  };

  return (
    <Box
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      sx={{
        p: 1.5,
        mb: 1,
        borderRadius: 1.5,
        bgcolor: isDragging ? 'rgba(0, 212, 170, 0.12)' : '#1c2230',
        border: '1px solid',
        borderColor: isDragging ? '#00D4AA' : 'rgba(255,255,255,0.07)',
        cursor: 'grab',
        transition: 'border-color 0.15s, background-color 0.15s',
        opacity: isDragging ? 0.45 : 1,
        '&:hover': {
          borderColor: '#00D4AA',
          bgcolor: 'rgba(0, 212, 170, 0.07)',
        },
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: '#00D4AA', fontWeight: 600, display: 'block', lineHeight: 1 }}
      >
        <FitnessCenterIcon sx={{ fontSize: 10, mr: 0.5, verticalAlign: 'middle' }} />
        arrastrar
      </Typography>
      <Typography variant="body2" sx={{ color: '#e2e8f0', fontWeight: 500, mt: 0.4 }}>
        {workout.name}
      </Typography>
      {workout.description && (
        <Typography
          variant="caption"
          sx={{ color: '#718096', display: 'block', mt: 0.25 }}
          noWrap
        >
          {workout.description}
        </Typography>
      )}
    </Box>
  );
}

// ── Library sidebar ───────────────────────────────────────────────────────────

function LibrarySidebar({ orgId, onDragStart, onDragEnd }) {
  const [libState, libDispatch] = useReducer(fetchReducer, {
    data: [],
    loading: false,
    error: null,
  });
  const [workoutsByLib, setWorkoutsByLib] = useState({});
  const [loadingWorkouts, setLoadingWorkouts] = useState({});

  useEffect(() => {
    if (!orgId) return;
    libDispatch({ type: 'FETCH_START' });
    listLibraries(orgId)
      .then((res) =>
        libDispatch({ type: 'FETCH_SUCCESS', data: res.data?.results ?? res.data ?? [] })
      )
      .catch(() =>
        libDispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar las librerías.' })
      );
  }, [orgId]);

  const handleExpand = useCallback(
    (libId) => {
      if (workoutsByLib[libId] !== undefined) return;
      setLoadingWorkouts((prev) => ({ ...prev, [libId]: true }));
      listPlannedWorkouts(orgId, libId)
        .then((res) =>
          setWorkoutsByLib((prev) => ({
            ...prev,
            [libId]: res.data?.results ?? res.data ?? [],
          }))
        )
        .finally(() =>
          setLoadingWorkouts((prev) => ({ ...prev, [libId]: false }))
        );
    },
    [orgId, workoutsByLib]
  );

  if (libState.loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
        <CircularProgress size={22} sx={{ color: '#00D4AA' }} />
      </Box>
    );
  }

  if (!libState.data.length) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 4, textAlign: 'center', px: 1 }}>
        <BookOpen style={{ width: 28, height: 28, color: '#4a5568', marginBottom: 8 }} />
        <Typography variant="caption" sx={{ color: '#718096', display: 'block', fontWeight: 600 }}>
          Sin librerías
        </Typography>
        <Typography variant="caption" sx={{ color: '#4a5568', display: 'block', mt: 0.5, lineHeight: 1.4 }}>
          Crea entrenamientos en Librería para arrastrarlos aquí.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {libState.data.map((lib) => (
        <Accordion
          key={lib.id}
          disableGutters
          elevation={0}
          onChange={(_, expanded) => {
            if (expanded) handleExpand(lib.id);
          }}
          sx={{
            bgcolor: 'transparent',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '8px !important',
            mb: 1,
            '&:before': { display: 'none' },
            overflow: 'hidden',
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon sx={{ color: '#718096', fontSize: 16 }} />}
            sx={{
              px: 1.5,
              minHeight: 36,
              '& .MuiAccordionSummary-content': { my: 0.5 },
            }}
          >
            <Typography
              variant="caption"
              sx={{
                color: '#a0aec0',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              {lib.name}
            </Typography>
          </AccordionSummary>

          <AccordionDetails sx={{ p: 1, pt: 0 }}>
            {loadingWorkouts[lib.id] ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 1 }}>
                <CircularProgress size={16} sx={{ color: '#00D4AA' }} />
              </Box>
            ) : (workoutsByLib[lib.id] ?? []).length === 0 ? (
              <Typography variant="caption" sx={{ color: '#4a5568' }}>
                Sin entrenamientos
              </Typography>
            ) : (
              (workoutsByLib[lib.id] ?? []).map((wo) => (
                <WorkoutCard
                  key={wo.id}
                  workout={wo}
                  onDragStart={onDragStart}
                  onDragEnd={onDragEnd}
                />
              ))
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function toEvents(assignments) {
  return assignments.map((a) => {
    const day = parseISO(a.effective_date ?? a.scheduled_date);
    return {
      id: a.id,
      title: a.planned_workout_title ?? 'Entrenamiento',
      start: day,
      end: day,
      allDay: true,
      // PR-145d: map compliance + planned workout fields to top-level
      compliance_color: a.compliance_color,
      actual_duration_seconds: a.actual_duration_seconds,
      actual_distance_meters: a.actual_distance_meters,
      rpe: a.rpe,
      planned_workout: a.planned_workout,
      resource: a,
    };
  });
}

// ── Helpers ── (formatDuration is also used by CoachEventComponent)
function formatDuration(seconds) {
  if (!seconds) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m > 0 ? `${m}min` : ''}`.trim();
  return `${m}min`;
}

// ── Coach event component ─────────────────────────────────────────────────────

function CoachEventComponent({ event, onContextMenu }) {
  const pw = event.planned_workout;
  const duration = pw?.estimated_duration_seconds
    ? formatDuration(pw.estimated_duration_seconds)
    : null;
  const distance = pw?.estimated_distance_meters
    ? `${(pw.estimated_distance_meters / 1000).toFixed(1)}km`
    : null;
  const isCompleted = event.status === 'completed' || event.compliance_color === 'green';

  return (
    <div
      style={{ fontSize: '11px', lineHeight: '1.2', overflow: 'hidden', height: '100%' }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (onContextMenu) onContextMenu(e.clientX, e.clientY, event);
      }}
    >
      <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'flex', alignItems: 'center', gap: '3px' }}>
        {isCompleted && <span style={{ fontSize: '10px' }}>✅</span>}
        {event.title}
      </div>
      {(duration || distance) && (
        <div style={{ opacity: 0.85 }}>
          {[duration, distance].filter(Boolean).join(' · ')}
        </div>
      )}
    </div>
  );
}

// ── PR-161: Goal edit dialog ──────────────────────────────────────────────────

function GoalEditDialog({ goal, orgId, onClose, onSaved }) {
  const [form, setForm] = React.useState({
    title:                 goal.title ?? '',
    target_date:           goal.target_date ?? '',
    priority:              goal.priority ?? 'B',
    status:                goal.status ?? 'active',
    target_distance_km:    goal.target_distance_km ?? '',
    target_elevation_gain_m: goal.target_elevation_gain_m ?? '',
  });
  const [saving, setSaving] = React.useState(false);
  const [error,  setError]  = React.useState(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      const patch = {
        title:    form.title,
        priority: form.priority,
        status:   form.status,
        target_date: form.target_date || null,
        target_distance_km:       form.target_distance_km === '' ? null : Number(form.target_distance_km),
        target_elevation_gain_m:  form.target_elevation_gain_m === '' ? null : Number(form.target_elevation_gain_m),
      };
      const { data: updated } = await updateGoal(orgId, goal.id, patch);
      onSaved(updated);
    } catch {
      setError('No se pudo guardar el objetivo.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontWeight: 700, fontSize: '1rem' }}>
        🏆 Editar Objetivo
      </DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
        <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
          <Grid item xs={12}>
            <TextField label="Nombre" size="small" fullWidth value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          </Grid>
          <Grid item xs={12}>
            <TextField label="Fecha objetivo" type="date" size="small" fullWidth InputLabelProps={{ shrink: true }} value={form.target_date} onChange={e => setForm(f => ({ ...f, target_date: e.target.value }))} />
          </Grid>
          <Grid item xs={6}>
            <FormControl size="small" fullWidth>
              <InputLabel>Prioridad</InputLabel>
              <Select label="Prioridad" value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                <MenuItem value="A">A — Principal</MenuItem>
                <MenuItem value="B">B — Secundario</MenuItem>
                <MenuItem value="C">C — Desarrollo</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6}>
            <FormControl size="small" fullWidth>
              <InputLabel>Estado</InputLabel>
              <Select label="Estado" value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                <MenuItem value="active">Activo</MenuItem>
                <MenuItem value="completed">Completado</MenuItem>
                <MenuItem value="cancelled">Cancelado</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6}>
            <TextField label="Distancia (km)" type="number" size="small" fullWidth value={form.target_distance_km} onChange={e => setForm(f => ({ ...f, target_distance_km: e.target.value }))} />
          </Grid>
          <Grid item xs={6}>
            <TextField label="Elevación (m)" type="number" size="small" fullWidth value={form.target_elevation_gain_m} onChange={e => setForm(f => ({ ...f, target_elevation_gain_m: e.target.value }))} />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button variant="text" onClick={onClose} sx={{ textTransform: 'none', color: '#64748B' }}>Cancelar</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          sx={{ textTransform: 'none', bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00BF99' } }}
        >
          {saving ? <CircularProgress size={14} sx={{ color: '#fff' }} /> : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

// ── Target selector helpers ──────────────────────────────────────────────────
// selectedTarget is either '' (nothing selected) or a string like:
//   'a:42'  → individual athlete with id=42
//   't:7'   → team with id=7

function parseTarget(value) {
  if (!value) return null;
  const [type, id] = value.split(':');
  return { type, id: Number(id) };
}

export default function CalendarPage() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id ?? null;
  const navigate = useNavigate();
  const [libDrawerOpen, setLibDrawerOpen] = useState(false);

  // Athletes + Teams
  const [athleteState, athleteDispatch] = useReducer(fetchReducer, {
    data: [],
    loading: false,
    error: null,
  });
  const [teamState, teamDispatch] = useReducer(fetchReducer, {
    data: [],
    loading: false,
    error: null,
  });

  // Unified selection: '' | 'a:<id>' | 't:<id>'
  // PR-145g: restore last selected athlete from sessionStorage
  const [selectedTarget, setSelectedTarget] = useState(() => {
    return sessionStorage.getItem('calendarSelectedTarget') ?? '';
  });

  // PR-145g: drawer state
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Calendar events
  const [eventsState, eventsDispatch] = useReducer(fetchReducer, {
    data: [],
    loading: false,
    error: null,
  });

  // UI
  const [currentDate, setCurrentDate] = useState(new Date());
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  // PR-155: calendar view: 'calendar' | 'macro'
  const [calendarView, setCalendarView] = useState('calendar');
  // PR-158: react-big-calendar view mode: 'month' | 'week'
  const [calViewMode, setCalViewMode] = useState('month');
  // PR-158: trigger to re-fetch load estimate after assignment changes
  const [loadTrigger, setLoadTrigger] = useState(0);
  // PR-158 hotfix: group planning mode — { weekStart, teamId } | null
  const [planningWeek, setPlanningWeek] = useState(null);

  // PR-145f: undo toast
  const [undoToast, setUndoToast] = useState(null);

  // PR-145f: context menu
  const [contextMenu, setContextMenu] = useState(null); // { x, y, event }

  // PR-145f: modals
  const [duplicating, setDuplicating] = useState(null);
  const [copyingWeek, setCopyingWeek] = useState(null);
  const [deletingWeek, setDeletingWeek] = useState(null);

  // PR-154: Athlete availability + menstrual cycle
  const [athleteAvailability, setAthleteAvailability] = useState([]); // AthleteAvailability[]
  const [athleteProfile, setAthleteProfile] = useState(null);
  // Blocked-day drop confirmation dialog
  const [blockedDropPending, setBlockedDropPending] = useState(null); // { callback } | null

  // PR-157: Training phase map — { 'YYYY-MM-DD': 'carga' | ... } keyed by Monday
  const [trainingPhaseMap, setTrainingPhaseMap] = useState({});
  // PR-157 hotfix: goal events (race dates) for individual athlete calendar view
  const [goalEvents, setGoalEvents] = useState([]);
  // PR-161: selected goal for edit dialog
  const [selectedGoal, setSelectedGoal] = useState(null); // { id, title, target_date, priority, status, target_distance_km, target_elevation_gain_m }

  // PR-163 QA: coach PMC + plan-vs-real for month grid (Fix 4 + 5)
  const [coachPmcData, setCoachPmcData] = useState(null);
  const [coachPlanVsRealMap, setCoachPlanVsRealMap] = useState({});

  const showUndo = useCallback((message, onUndo) => {
    setUndoToast({ message, onUndo });
  }, []);

  // Ref to track currently dragged workout (synchronous, avoids stale closures)
  const draggingWorkoutRef = useRef(null);

  // ── Load athletes ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!orgId) return;
    athleteDispatch({ type: 'FETCH_START' });
    listAthletes(orgId)
      .then((res) =>
        athleteDispatch({ type: 'FETCH_SUCCESS', data: res.data?.results ?? res.data ?? [] })
      )
      .catch(() =>
        athleteDispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar los atletas.' })
      );
  }, [orgId]);

  // PR-154: Load availability + profile when an individual athlete is selected.
  // setState is only called inside async callbacks or the cleanup function (not
  // synchronously in the effect body) to avoid the react-hooks/set-state-in-effect rule.
  useEffect(() => {
    const target = parseTarget(selectedTarget);
    if (!orgId || !target || target.type !== 'a') return;

    let cancelled = false;
    const athleteId = target.id;

    getAthleteAvailability(orgId, athleteId)
      .then((res) => { if (!cancelled) setAthleteAvailability(res.data?.results ?? res.data ?? []); })
      .catch(() => { if (!cancelled) setAthleteAvailability([]); });
    getAthleteProfile(orgId, athleteId)
      .then((res) => { if (!cancelled) setAthleteProfile(res.data); })
      .catch(() => { if (!cancelled) setAthleteProfile(null); });

    return () => {
      cancelled = true;
      setAthleteAvailability([]);
      setAthleteProfile(null);
    };
  }, [orgId, selectedTarget]);

  // PR-157 hotfix: load athlete goals as calendar events when individual athlete selected.
  // setState only in async callbacks (never synchronously in effect body).
  useEffect(() => {
    const target = parseTarget(selectedTarget);
    let cancelled = false;
    if (!orgId || !target || target.type !== 'a') {
      return () => {
        if (!cancelled) setGoalEvents([]);
        cancelled = true;
      };
    }
    listAthleteGoals(orgId, target.id)
      .then((res) => {
        if (!cancelled) {
          const goals = res.data?.results ?? res.data ?? [];
          const events = goals
            .filter((g) => g.target_date || g.target_event_date)
            .map((g) => {
              const dateStr = g.target_date || g.target_event_date;
              const day = parseISO(dateStr);
              const subparts = [
                g.target_distance_km ? `${g.target_distance_km}km` : null,
                g.target_elevation_gain_m ? `D+${g.target_elevation_gain_m}m` : null,
              ].filter(Boolean).join(' · ');
              return {
                id: `goal-${g.id}`,
                title: subparts ? `🏆 ${g.title} — ${subparts}` : `🏆 ${g.title}`,
                start: day,
                end: day,
                allDay: true,
                isGoal: true,
                resource: { type: 'goal', goal: g },
              };
            });
          setGoalEvents(events);
        }
      })
      .catch(() => { if (!cancelled) setGoalEvents([]); });
    return () => {
      cancelled = true;
      setGoalEvents([]);
    };
  }, [orgId, selectedTarget]);

  // PR-157: Load training phases when individual athlete selected (for calendar badge).
  // setState is only called inside async callbacks or the cleanup function (not
  // synchronously in the effect body) to avoid the react-hooks/set-state-in-effect rule.
  useEffect(() => {
    const target = parseTarget(selectedTarget);
    let cancelled = false;
    if (!orgId || !target || target.type !== 'a') {
      return () => {
        if (!cancelled) setTrainingPhaseMap({});
        cancelled = true;
      };
    }
    const athleteId = target.id;
    const from = format(startOfMonth(currentDate), 'yyyy-MM-dd');
    const to = format(endOfMonth(currentDate), 'yyyy-MM-dd');
    getCoachAthleteTrainingPhases(orgId, athleteId, from, to)
      .then((res) => {
        if (!cancelled) {
          const map = {};
          (res.data?.phases ?? []).forEach((p) => { map[p.week_start] = p.phase; });
          setTrainingPhaseMap(map);
        }
      })
      .catch(() => { if (!cancelled) setTrainingPhaseMap({}); });
    return () => {
      cancelled = true;
      setTrainingPhaseMap({});
    };
  }, [orgId, selectedTarget, currentDate]);

  // PR-163 QA Fix 4: Load PMC data for coach month grid when individual athlete selected
  useEffect(() => {
    const target = parseTarget(selectedTarget);
    let cancelled = false;
    if (!orgId || !target || target.type !== 'a') {
      setCoachPmcData(null);
      return;
    }
    const athlete = athleteState.data.find((a) => a.id === target.id);
    const membershipId = athlete?.membership_id;
    if (!membershipId) { setCoachPmcData(null); return; }
    getCoachAthletePMC(membershipId)
      .then((res) => {
        if (cancelled) return;
        console.log('[Calendar] coachPmcData raw:', res.data);
        // API returns { current: { ctl, atl, tsb, ... }, history: [...] }
        const current = res.data?.current;
        if (current?.ctl != null) {
          setCoachPmcData({ ctl: current.ctl, atl: current.atl, tsb: current.tsb });
        } else {
          // Fallback: flat array or { ctl } direct
          const entries = Array.isArray(res.data) ? res.data : (res.data?.entries ?? []);
          if (entries.length > 0) {
            const latest = entries[entries.length - 1];
            setCoachPmcData({ ctl: latest.ctl, atl: latest.atl, tsb: latest.tsb });
          } else if (!Array.isArray(res.data) && res.data?.ctl != null) {
            setCoachPmcData({ ctl: res.data.ctl, atl: res.data.atl, tsb: res.data.tsb });
          } else {
            setCoachPmcData(null);
          }
        }
      })
      .catch(() => { if (!cancelled) setCoachPmcData(null); });
    return () => { cancelled = true; };
  }, [orgId, selectedTarget, athleteState.data]);

  // PR-163 QA Fix 5: Load plan-vs-real per week for coach month grid when individual athlete selected
  useEffect(() => {
    const target = parseTarget(selectedTarget);
    let cancelled = false;
    if (!orgId || !target || target.type !== 'a') {
      setCoachPlanVsRealMap({});
      return;
    }
    const athleteId = target.id;
    const monthStart = startOfMonth(currentDate);
    const calStart = startOfWeek(monthStart, { weekStartsOn: 1 });
    const mondays = [];
    let d = new Date(calStart);
    while (d <= endOfMonth(currentDate)) {
      mondays.push(format(d, 'yyyy-MM-dd'));
      d = new Date(d);
      d.setDate(d.getDate() + 7);
    }
    Promise.all(
      mondays.map((wk) =>
        getCoachAthletePlanVsReal(athleteId, { weekStart: wk })
          .then((res) => ({ wk, data: res.data }))
          .catch(() => ({ wk, data: null }))
      )
    ).then((results) => {
      if (cancelled) return;
      const map = {};
      results.forEach(({ wk, data }) => { if (data) map[wk] = data; });
      setCoachPlanVsRealMap(map);
    });
    return () => { cancelled = true; setCoachPlanVsRealMap({}); };
  }, [orgId, selectedTarget, currentDate]);

  // ── Load teams ────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!orgId) return;
    teamDispatch({ type: 'FETCH_START' });
    listTeams(orgId)
      .then((res) =>
        teamDispatch({ type: 'FETCH_SUCCESS', data: res.data?.results ?? res.data ?? [] })
      )
      .catch(() =>
        teamDispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar los grupos.' })
      );
  }, [orgId]);

  // ── Load assignments for current month ────────────────────────────────────

  const dateFrom = format(startOfMonth(currentDate), 'yyyy-MM-dd');
  const dateTo = format(endOfMonth(currentDate), 'yyyy-MM-dd');

  useEffect(() => {
    const target = parseTarget(selectedTarget);
    if (!orgId || !target) {
      eventsDispatch({ type: 'CLEAR' });
      return;
    }
    eventsDispatch({ type: 'FETCH_START' });
    const params =
      target.type === 't'
        ? { teamId: target.id, dateFrom, dateTo }
        : { athleteId: target.id, dateFrom, dateTo };
    listAssignments(orgId, params)
      .then((res) => {
        const data = res.data?.results ?? res.data ?? [];
        eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(data) });
      })
      .catch(() =>
        eventsDispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar los entrenamientos.' })
      );
  }, [orgId, selectedTarget, dateFrom, dateTo]);

  // Deep-link from MessagesDrawer:
  // Step 1 (mount-only) — navigate to the right month so the correct events are fetched.
  // Step 2 (data-watch) — once events load, find and open the target assignment drawer.
  // Both setState calls are conditional one-shots driven by sessionStorage flags;
  // they cannot loop. The rule suppression is intentional and safe here.
  useEffect(() => {
    const assignmentDate = sessionStorage.getItem('calendarOpenAssignmentDate');
    if (!assignmentDate) return;
    const targetDate = new Date(assignmentDate + 'T00:00:00');
    sessionStorage.removeItem('calendarOpenAssignmentDate');
    setCurrentDate(targetDate);
  }, []); // intentionally mount-only

  useEffect(() => {
    const assignmentId = sessionStorage.getItem('calendarOpenAssignment');
    if (!assignmentId || eventsState.loading || eventsState.data.length === 0) return;
    const targetId = parseInt(assignmentId, 10);
    const event = eventsState.data.find((e) => e.id === targetId);
    if (event) {
      sessionStorage.removeItem('calendarOpenAssignment');
      setSelectedEvent(event);
    }
  }, [eventsState.data, eventsState.loading]);

  // ── Drag handlers ─────────────────────────────────────────────────────────

  const handleDragStart = useCallback((workout) => {
    draggingWorkoutRef.current = workout;
  }, []);

  const handleDragEnd = useCallback(() => {
    draggingWorkoutRef.current = null;
  }, []);

  // Called by react-big-calendar to get a preview event while dragging over slots
  const dragFromOutsideItem = useCallback(() => {
    const w = draggingWorkoutRef.current;
    if (!w) return null;
    return { title: w.name, allDay: true };
  }, []);

  // PR-154: Check if a date is blocked for the currently selected individual athlete
  const isDateBlocked = useCallback((dateObj) => {
    const target = parseTarget(selectedTarget);
    if (!target || target.type !== 'a') return null; // teams: no block
    const dayIndex = jsWeekdayToAvailIndex(dateObj.getDay());
    const avail = athleteAvailability.find((a) => a.day_of_week === dayIndex);
    if (avail && !avail.is_available) return avail;
    return null;
  }, [selectedTarget, athleteAvailability]);

  // Called when a sidebar workout is dropped onto a calendar slot
  const handleDropFromOutside = useCallback(
    ({ start }) => {
      const workout = draggingWorkoutRef.current;
      draggingWorkoutRef.current = null;
      const target = parseTarget(selectedTarget);
      if (!workout || !orgId) return;
      if (!target) {
        setSaveError('Seleccioná un atleta o grupo antes de arrastrar el entrenamiento.');
        setSaving(false);
        return;
      }

      // PR-154: Blocked day intercept
      const blockedAvail = isDateBlocked(start);
      if (blockedAvail) {
        const athleteObj = athleteState.data.find((a) => a.id === target.id);
        const athleteName = athleteObj
          ? `${athleteObj.first_name || ''} ${athleteObj.last_name || ''}`.trim()
          : 'El atleta';
        const dayName = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][blockedAvail.day_of_week] ?? '';
        setBlockedDropPending({
          message: `⚠️ ${athleteName} no está disponible los ${dayName}${blockedAvail.reason ? ` (${blockedAvail.reason})` : ''}.`,
          workout,
          target,
          start,
        });
        return;
      }

      const scheduledDate = format(start, 'yyyy-MM-dd');
      setSaving(true);
      setSaveError(null);

      if (target.type === 't') {
        // Bulk team assignment
        bulkAssignTeam(orgId, {
          planned_workout_id: workout.id,
          team_id: target.id,
          scheduled_date: scheduledDate,
        })
          .then((res) => {
            const assignments = res.data?.assignments ?? [];
            assignments.forEach((a) => {
              const day = parseISO(a.effective_date ?? a.scheduled_date);
              eventsDispatch({
                type: 'ADD_EVENT',
                event: {
                  id: a.id,
                  title: a.planned_workout_title ?? workout.name,
                  start: day,
                  end: day,
                  allDay: true,
                  compliance_color: a.compliance_color,
                  actual_duration_seconds: a.actual_duration_seconds,
                  actual_distance_meters: a.actual_distance_meters,
                  rpe: a.rpe,
                  planned_workout: a.planned_workout,
                  resource: a,
                },
              });
            });
          })
          .then(() => setLoadTrigger((n) => n + 1))
          .catch((err) => {
            const detail = err.response?.data
              ? JSON.stringify(err.response.data)
              : err.message;
            console.error('[Calendar] bulkAssignTeam failed:', detail);
            setSaveError(
              `Error al asignar el entrenamiento al grupo: ${detail ?? 'Intenta de nuevo.'}`
            );
          })
          .finally(() => setSaving(false));
      } else {
        // Individual athlete assignment
        createAssignment(orgId, {
          planned_workout_id: workout.id,
          athlete_id: target.id,
          scheduled_date: scheduledDate,
        })
          .then((res) => {
            const a = res.data;
            const day = parseISO(a.effective_date ?? a.scheduled_date);
            eventsDispatch({
              type: 'ADD_EVENT',
              event: {
                id: a.id,
                title: a.planned_workout_title ?? workout.name,
                start: day,
                end: day,
                allDay: true,
                compliance_color: a.compliance_color,
                actual_duration_seconds: a.actual_duration_seconds,
                actual_distance_meters: a.actual_distance_meters,
                rpe: a.rpe,
                planned_workout: a.planned_workout,
                resource: a,
              },
            });
          })
          .then(() => setLoadTrigger((n) => n + 1))
          .catch((err) => {
            const detail = err.response?.data
              ? JSON.stringify(err.response.data)
              : err.message;
            console.error('[Calendar] createAssignment failed:', detail);
            setSaveError(
              `Error al asignar el entrenamiento: ${detail ?? 'Intenta de nuevo.'}`
            );
          })
          .finally(() => setSaving(false));
      }
    },
    [orgId, selectedTarget, isDateBlocked, athleteState.data]
  );

  // PR-154: Confirm drop on blocked day
  const handleConfirmBlockedDrop = useCallback(() => {
    if (!blockedDropPending) return;
    const { workout, target, start } = blockedDropPending;
    setBlockedDropPending(null);
    const scheduledDate = format(start, 'yyyy-MM-dd');
    setSaving(true);
    setSaveError(null);
    const refetch = () => {
      const params = target.type === 't'
        ? { teamId: target.id, dateFrom, dateTo }
        : { athleteId: target.id, dateFrom, dateTo };
      listAssignments(orgId, params)
        .then((res) => {
          const data = res.data?.results ?? res.data ?? [];
          eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(data) });
        })
        .catch(() => {});
    };
    if (target.type === 't') {
      bulkAssignTeam(orgId, {
        planned_workout_id: workout.id,
        team_id: target.id,
        scheduled_date: scheduledDate,
      })
        .then(() => refetch())
        .catch(() => setSaveError('Error al asignar el entrenamiento al grupo.'))
        .finally(() => setSaving(false));
    } else {
      createAssignment(orgId, {
        planned_workout_id: workout.id,
        athlete_id: target.id,
        scheduled_date: scheduledDate,
      })
        .then(() => refetch())
        .catch(() => setSaveError('Error al asignar el entrenamiento.'))
        .finally(() => setSaving(false));
    }
  }, [blockedDropPending, orgId, dateFrom, dateTo]);

  // ── PR-145f: Drag existing events (move) ──────────────────────────────────

  const handleEventDrop = useCallback(
    async ({ event, start }) => {
      // Goals cannot be moved via drag (PR-163)
      if (event.isGoal) return;

      const newDate = format(start, 'yyyy-MM-dd');
      const oldDate = event.resource?.scheduled_date ?? format(event.start, 'yyyy-MM-dd');
      if (newDate === oldDate) return;

      eventsDispatch({ type: 'MOVE_EVENT', id: event.id, newDate });

      try {
        await moveAssignment(orgId, event.id, newDate);
        showUndo(
          `${event.title} → ${format(start, 'EEEE d MMM', { locale: es })}`,
          async () => {
            await moveAssignment(orgId, event.id, oldDate);
            eventsDispatch({ type: 'MOVE_EVENT', id: event.id, newDate: oldDate });
          }
        );
      } catch (err) {
        console.error('[Calendar] handleEventDrop error:', err);
        eventsDispatch({ type: 'MOVE_EVENT', id: event.id, newDate: oldDate });
        setSaveError('No se pudo mover la sesión.');
      }
    },
    [orgId, showUndo]
  );

  // ── PR-163: Grid card move (custom month view) ────────────────────────────

  const handleGridCardMove = useCallback(
    async (assignmentId, newDate) => {
      const event = eventsState.data.find((e) => e.id === assignmentId);
      if (!event) return;
      const oldDate = event.resource?.scheduled_date ?? format(event.start, 'yyyy-MM-dd');
      if (newDate === oldDate) return;
      eventsDispatch({ type: 'MOVE_EVENT', id: assignmentId, newDate });
      try {
        await moveAssignment(orgId, assignmentId, newDate);
        showUndo(
          `${event.title} → ${newDate}`,
          async () => {
            await moveAssignment(orgId, assignmentId, oldDate);
            eventsDispatch({ type: 'MOVE_EVENT', id: assignmentId, newDate: oldDate });
          }
        );
      } catch (err) {
        console.error('[Calendar] handleGridCardMove error:', err.response?.data ?? err);
        eventsDispatch({ type: 'MOVE_EVENT', id: assignmentId, newDate: oldDate });
        const errMsg = err.response?.status === 400
          ? 'No se pudo mover: ya existe un entrenamiento similar en ese día.'
          : 'No se pudo mover la sesión.';
        setSaveError(errMsg);
      }
    },
    [orgId, eventsState.data, showUndo]
  );

  // ── PR-163: Library drop on custom grid date ──────────────────────────────

  const handleLibraryDropOnDate = useCallback(
    (dateKey) => {
      // Reuse existing drop logic by simulating a date start
      handleDropFromOutside({ start: parseISO(dateKey) });
    },
    [handleDropFromOutside]
  );

  // ── PR-145f: Context menu opener ───────────────────────────────────────────

  const handleContextMenu = useCallback((x, y, event) => {
    setContextMenu({ x, y, event });
  }, []);

  // ── PR-145f: Delete individual session ────────────────────────────────────

  const handleDeleteEvent = useCallback(
    async (event) => {
      eventsDispatch({ type: 'REMOVE_EVENT', id: event.id });
      try {
        await deleteAssignment(orgId, event.id);
        showUndo(
          `"${event.title}" eliminado`,
          async () => {
            const res = await createAssignment(orgId, {
              planned_workout_id: event.planned_workout?.id,
              athlete_id: event.resource?.athlete_id ?? event.resource?.athlete,
              scheduled_date: event.resource?.scheduled_date ?? format(event.start, 'yyyy-MM-dd'),
            });
            const a = res.data;
            const day = parseISO(a.effective_date ?? a.scheduled_date);
            eventsDispatch({
              type: 'ADD_EVENT',
              event: {
                id: a.id,
                title: a.planned_workout_title ?? event.title,
                start: day, end: day, allDay: true,
                compliance_color: a.compliance_color,
                actual_duration_seconds: a.actual_duration_seconds,
                actual_distance_meters: a.actual_distance_meters,
                rpe: a.rpe,
                planned_workout: a.planned_workout,
                resource: a,
              },
            });
          }
        );
      } catch (err) {
        eventsDispatch({ type: 'ADD_EVENT', event });
        setSaveError(err?.response?.data?.detail || 'No se pudo eliminar la sesión.');
      }
    },
    [orgId, showUndo]
  );

  // ── PR-145f: Edit session (clone then navigate to WorkoutBuilder) ──────────

  const handleEditEvent = useCallback(
    async (event) => {
      const pw = event.planned_workout;
      if (!pw) return;

      let workoutData = pw;

      // If not yet a snapshot, clone first so the library original is untouched
      if (!pw.is_assignment_snapshot) {
        try {
          const res = await cloneAssignmentWorkout(orgId, event.id);
          workoutData = res.data.planned_workout ?? res.data;
          eventsDispatch({
            type: 'UPDATE_EVENT',
            id: event.id,
            updates: { planned_workout: workoutData },
          });
        } catch {
          setSaveError('No se pudo preparar la edición.');
          return;
        }
      }

      // Store full workout + assignmentId in sessionStorage so WorkoutLibraryPage
      // can hydrate the builder and route the save to update-snapshot endpoint.
      sessionStorage.setItem(
        'calendarEditWorkout',
        JSON.stringify({ workout: workoutData, assignmentId: event.id }),
      );
      navigate(`/library?editWorkout=${workoutData.id}`);
    },
    [orgId, navigate]
  );

  // ── PR-145f: Duplicate session ─────────────────────────────────────────────

  const handleDuplicate = useCallback(
    async ({ targetAthleteId, targetDate }) => {
      if (!duplicating) return;
      try {
        const res = await createAssignment(orgId, {
          planned_workout_id: duplicating.planned_workout?.id,
          athlete_id: targetAthleteId,
          scheduled_date: targetDate,
        });
        const a = res.data;
        const day = parseISO(a.effective_date ?? a.scheduled_date);
        // Only add to calendar if same athlete currently selected
        const target = parseTarget(selectedTarget);
        if (target?.type === 'a' && target.id === targetAthleteId) {
          eventsDispatch({
            type: 'ADD_EVENT',
            event: {
              id: a.id,
              title: a.planned_workout_title ?? duplicating.title,
              start: day, end: day, allDay: true,
              compliance_color: a.compliance_color,
              actual_duration_seconds: a.actual_duration_seconds,
              actual_distance_meters: a.actual_distance_meters,
              rpe: a.rpe,
              planned_workout: a.planned_workout,
              resource: a,
            },
          });
        }
      } catch {
        setSaveError('No se pudo duplicar la sesión.');
      }
    },
    [orgId, duplicating, selectedTarget]
  );

  // ── PR-145f: Copy week success ─────────────────────────────────────────────

  const handleCopyWeekSuccess = useCallback(
    ({ targetAthleteId, targetWeekStart }) => {
      const target = parseTarget(selectedTarget);
      if (target?.type === 'a' && target.id === targetAthleteId) {
        // Reload events for this athlete (simple approach: trigger re-fetch)
        eventsDispatch({ type: 'FETCH_START' });
        listAssignments(orgId, { athleteId: target.id, dateFrom, dateTo })
          .then((res) => {
            const data = res.data?.results ?? res.data ?? [];
            eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(data) });
          })
          .catch(() => eventsDispatch({ type: 'FETCH_ERROR', error: 'No se pudo recargar.' }));
      }
      showUndo(`Semana copiada a partir de ${targetWeekStart}`, null);
    },
    [orgId, selectedTarget, dateFrom, dateTo, showUndo]
  );

  // ── PR-145f: Delete week success ──────────────────────────────────────────

  const handleDeleteWeekSuccess = useCallback(
    (data) => {
      // Reload events
      const target = parseTarget(selectedTarget);
      if (!target) return;
      eventsDispatch({ type: 'FETCH_START' });
      const params = target.type === 't'
        ? { teamId: target.id, dateFrom, dateTo }
        : { athleteId: target.id, dateFrom, dateTo };
      listAssignments(orgId, params)
        .then((res) => {
          const evData = res.data?.results ?? res.data ?? [];
          eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(evData) });
        })
        .catch(() => eventsDispatch({ type: 'FETCH_ERROR', error: 'No se pudo recargar.' }));
      showUndo(`${data?.deleted ?? 0} sesiones eliminadas`, null);
    },
    [orgId, selectedTarget, dateFrom, dateTo, showUndo]
  );

  // ── PR-158: Navigate from Planificador week header ────────────────────────
  // teamId is non-null when the coach has a team filter selected in MacroView.
  // For teams: open GroupPlanningView (avoids mixing all athletes' events).
  // For individuals: fall back to Calendar/Week view (unchanged behaviour).

  const handleNavigateToWeek = useCallback((weekStart, teamId = null) => {
    if (!teamId) {
      // No group selected — warn the coach and stay in MacroView
      setSaveError('Seleccioná un grupo en el filtro del Planificador antes de planificar la semana del grupo.');
      setTimeout(() => setSaveError(null), 4000);
      return;
    }
    // Group context → open dedicated planning view
    setPlanningWeek({ weekStart, teamId });
    setCalendarView('calendar');
  }, []);

  // ── PR-158: Copy week from historial panel ────────────────────────────────

  const handleHistorialCopy = useCallback(
    async (sourceWeek) => {
      if (!orgId) return;
      const target = parseTarget(selectedTarget);
      const teamId = target?.type === 't' ? target.id : null;
      const targetWeekStart = format(currentDate, 'yyyy-MM-dd');
      setSaving(true);
      setSaveError(null);
      try {
        await copyWeek(orgId, {
          sourceWeekStart: sourceWeek,
          targetWeekStart,
          teamId: teamId || undefined,
        });
        // Reload events
        const params = target?.type === 't'
          ? { teamId: target.id, dateFrom, dateTo }
          : target?.type === 'a' ? { athleteId: target.id, dateFrom, dateTo } : null;
        if (params) {
          const res = await listAssignments(orgId, params);
          const data = res.data?.results ?? res.data ?? [];
          eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(data) });
        }
        setLoadTrigger((n) => n + 1);
        showUndo(`Semana ${sourceWeek} copiada`, null);
      } catch (err) {
        setSaveError(err?.response?.data?.detail || 'No se pudo copiar la semana.');
      } finally {
        setSaving(false);
      }
    },
    [orgId, selectedTarget, currentDate, dateFrom, dateTo, showUndo]
  );

  // ── Calendar styling ──────────────────────────────────────────────────────

  const eventPropGetter = useCallback(
    (event) => {
      // PR-160: goal events — gold trophy badge style
      if (event.isGoal) {
        return {
          style: {
            background: 'linear-gradient(135deg, #FFD700 0%, #F97316 100%)',
            borderRadius: '6px',
            color: '#7c2d12',
            fontWeight: 800,
            fontSize: '0.7rem',
            border: '1px solid #F59E0B',
            cursor: 'default',
          },
        };
      }

      // PR-145d: compliance fields mapped directly to event object in toEvents/ADD_EVENT
      const complianceColor = event.compliance_color;
      const borderColor = complianceColor
        ? (COMPLIANCE_HEX[complianceColor] ?? '#94A3B8')
        : '#94A3B8';

      // Build tooltip for completed events with actual data
      let title = event.title ?? '';
      const durationSecs = event.actual_duration_seconds;
      const distanceMeters = event.actual_distance_meters;
      const rpe = event.rpe;

      if (durationSecs || distanceMeters || rpe) {
        const parts = [];
        if (durationSecs) {
          const h = Math.floor(durationSecs / 3600);
          const m = Math.floor((durationSecs % 3600) / 60);
          parts.push(h > 0 ? `${h}h ${m}min` : `${m}min`);
        }
        if (distanceMeters) {
          parts.push(`${(distanceMeters / 1000).toFixed(1)}km`);
        }
        if (rpe) {
          parts.push(`RPE: ${rpe}/5`);
        }
        title = `Real: ${parts.join(' · ')}`;
      }

      return {
        title,
        style: {
          backgroundColor: '#00D4AA',
          borderRadius: '5px',
          borderLeft: `3px solid ${borderColor}`,
          paddingLeft: '6px',
          color: '#fff',
          fontSize: '0.72rem',
          padding: '2px 5px 2px 6px',
          fontWeight: 500,
        },
      };
    },
    []
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Layout>
      <>
        {/* ── Header ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            mb: 2,
            flexWrap: 'wrap',
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h5" fontWeight={700}>
              Calendario de Temporada
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Arrastra entrenamientos desde la librería al día que desees.
            </Typography>
          </Box>

          {/* PR-155: view toggle — Calendario / Macro */}
          <ToggleButtonGroup
            size="small"
            exclusive
            value={calendarView}
            onChange={(_, v) => { if (v) setCalendarView(v); }}
          >
            <ToggleButton value="calendar" sx={{ px: 2, textTransform: 'none', fontWeight: 600 }}>
              Calendario
            </ToggleButton>
            <ToggleButton value="macro" sx={{ px: 2, textTransform: 'none', fontWeight: 600 }}>
              Planificador
            </ToggleButton>
          </ToggleButtonGroup>

          {/* PR-163: Month / Week toggle */}
          {calendarView === 'calendar' && (
            <ToggleButtonGroup
              size="small"
              exclusive
              value={calViewMode}
              onChange={(_, v) => { if (v) setCalViewMode(v); }}
            >
              <ToggleButton value="month" sx={{ px: 1.5, textTransform: 'none', fontWeight: 600, fontSize: '0.8rem' }}>
                Mes
              </ToggleButton>
              <ToggleButton value="week" sx={{ px: 1.5, textTransform: 'none', fontWeight: 600, fontSize: '0.8rem' }}>
                Semana
              </ToggleButton>
            </ToggleButtonGroup>
          )}

          {saving && (
            <Tooltip title="Guardando asignación…">
              <CircularProgress size={20} sx={{ color: '#00D4AA' }} />
            </Tooltip>
          )}

          {/* PR-163: Searchable athlete selector (athletes only, with recents) */}
          <AthleteSearchSelector
            athletes={athleteState.data}
            value={selectedTarget}
            onChange={(v) => {
              setSelectedTarget(v);
              sessionStorage.setItem('calendarSelectedTarget', v);
            }}
            loading={(athleteState.loading || teamState.loading) || !orgId}
          />
        </Box>

        {saveError && (
          <Alert
            severity="error"
            onClose={() => setSaveError(null)}
            sx={{ mb: 2 }}
          >
            {saveError}
          </Alert>
        )}

        {/* PR-155: Macro View */}
        {calendarView === 'macro' && orgId && (
          <Box sx={{ mt: 1 }}>
            <MacroView orgId={orgId} onNavigateToWeek={handleNavigateToWeek} />
          </Box>
        )}

        {/* ── Body: sidebar + calendar ── */}
        <Box
          sx={{
            display: calendarView === 'macro' ? 'none' : 'flex',
            gap: 2,
            height: 'calc(100vh - 220px)',
            minHeight: 560,
          }}
        >
          {/* Sidebar — hidden on mobile (xs), shown on sm+ */}
          {sidebarOpen && (
            <Paper
              sx={{
                width: 240,
                flexShrink: 0,
                bgcolor: '#0f1621',
                borderRadius: 2,
                p: 1.5,
                overflowY: 'auto',
                display: { xs: 'none', sm: 'flex' },
                flexDirection: 'column',
                gap: 1,
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  mb: 0.5,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    color: '#718096',
                    textTransform: 'uppercase',
                    letterSpacing: '0.07em',
                    fontWeight: 700,
                  }}
                >
                  Librería
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => setSidebarOpen(false)}
                  sx={{ color: '#4a5568' }}
                >
                  <MenuOpenIcon fontSize="small" />
                </IconButton>
              </Box>

              {orgId ? (
                <LibrarySidebar
                  orgId={orgId}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                />
              ) : (
                <CircularProgress size={20} sx={{ color: '#00D4AA' }} />
              )}
            </Paper>
          )}

          {/* Sidebar toggle when collapsed — desktop only */}
          {!sidebarOpen && (
            <Tooltip title="Abrir librería">
              <IconButton
                size="small"
                onClick={() => setSidebarOpen(true)}
                sx={{ alignSelf: 'flex-start', mt: 0.5, color: '#00D4AA', display: { xs: 'none', sm: 'flex' } }}
              >
                <MenuIcon />
              </IconButton>
            </Tooltip>
          )}

          {/* Calendar area */}
          <Box sx={{ flex: 1, position: 'relative', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 0 }}>
            {/* PR-158 hotfix: Group Planning View */}
            {planningWeek && orgId && (
              <GroupPlanningView
                orgId={orgId}
                weekStart={planningWeek.weekStart}
                teamId={planningWeek.teamId}
                onBack={() => { setPlanningWeek(null); setCalendarView('macro'); }}
                onNavigateWeek={(w) => setPlanningWeek({ weekStart: w, teamId: planningWeek.teamId })}
                draggingWorkoutRef={draggingWorkoutRef}
                onAssigned={() => setLoadTrigger((t) => t + 1)}
                representativeMembershipId={
                  athleteState.data.find((a) => a.team_id === planningWeek.teamId)?.membership_id ?? null
                }
              />
            )}

            {/* PR-158: Historial panel — shown in week view (individual) */}
            {!planningWeek && calViewMode === 'week' && orgId && (
              <HistorialPanel
                orgId={orgId}
                teamId={parseTarget(selectedTarget)?.type === 't' ? parseTarget(selectedTarget)?.id : null}
                targetWeek={format(currentDate, 'yyyy-MM-dd')}
                onCopyWeek={handleHistorialCopy}
              />
            )}

            {!planningWeek && eventsState.loading && (
              <Box
                sx={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}
              >
                <CircularProgress size={20} />
              </Box>
            )}

            {!planningWeek && eventsState.error && (
              <Alert severity="error" sx={{ mb: 1 }}>
                {eventsState.error}
              </Alert>
            )}

            {/* PR-163: Month view — custom grid or CoachWeekOverview */}
            {!planningWeek && calViewMode === 'month' && (() => {
              if (!selectedTarget) {
                return (
                  <Paper sx={{ flex: 1, borderRadius: 2, overflow: 'hidden', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column' }}>
                    <CoachWeekOverview
                      orgId={orgId}
                      athletes={athleteState.data}
                      onSelectAthlete={(v) => {
                        setSelectedTarget(v);
                        sessionStorage.setItem('calendarSelectedTarget', v);
                      }}
                    />
                  </Paper>
                );
              }
              const rawAssignments = eventsState.data.map((e) => e.resource);
              const goalDateMap = {};
              goalEvents.forEach((e) => {
                const g = e.resource?.goal;
                if (g?.target_date) goalDateMap[g.target_date] = g;
              });
              return (
                <Box sx={{ flex: 1, overflowY: 'auto' }}>
                  <CalendarGrid
                    assignments={rawAssignments}
                    goalDateMap={goalDateMap}
                    planVsRealMap={coachPlanVsRealMap}
                    pmcData={coachPmcData}
                    trainingPhaseMap={trainingPhaseMap}
                    role="coach"
                    currentDate={currentDate}
                    onNavigate={setCurrentDate}
                    loading={eventsState.loading}
                    onCardClick={(assignment) => {
                      const event = eventsState.data.find((e) => e.id === assignment.id);
                      if (event) setSelectedEvent(event);
                    }}
                    onCompleteClick={() => {}}
                    onContextMenu={(x, y, assignment) => {
                      const event = eventsState.data.find((e) => e.id === assignment.id);
                      if (event) handleContextMenu(x, y, event);
                    }}
                    onMoveAssignment={handleGridCardMove}
                    onDropFromLibrary={handleLibraryDropOnDate}
                    draggingWorkoutRef={draggingWorkoutRef}
                    availability={athleteAvailability}
                    athleteProfile={athleteProfile}
                    onGoalClick={(goal) => setSelectedGoal(goal)}
                  />
                </Box>
              );
            })()}

            {/* Week view — react-big-calendar (unchanged) */}
            {!planningWeek && calViewMode === 'week' && (!selectedTarget ? (
              <Paper
                sx={{
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 2,
                  bgcolor: '#fafafa',
                  border: '2px dashed #e2e8f0',
                }}
              >
                <Box sx={{ textAlign: 'center', px: 4 }}>
                  <Users
                    style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }}
                  />
                  <Typography variant="h6" fontWeight={600} sx={{ color: '#374151' }}>
                    Selecciona un atleta
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#6b7280', mt: 0.5 }}>
                    Elige en el desplegable de arriba para visualizar el calendario semanal.
                  </Typography>
                </Box>
              </Paper>
            ) : (
              <Paper sx={{ flex: 1, p: 1.5, borderRadius: 2 }}>
                <DnDCalendar
                  localizer={localizer}
                  events={[...eventsState.data, ...goalEvents]}
                  date={currentDate}
                  onNavigate={setCurrentDate}
                  view="week"
                  onView={setCalViewMode}
                  views={['week']}
                  culture="es"
                  style={{ height: '100%' }}
                  eventPropGetter={eventPropGetter}
                  components={{
                    event: (props) => (
                      <CoachEventComponent
                        {...props}
                        onContextMenu={handleContextMenu}
                      />
                    ),
                    dateCellWrapper: ({ value, children }) => {
                      const dayIndex = jsWeekdayToAvailIndex(value.getDay());
                      const avail = athleteAvailability.find((a) => a.day_of_week === dayIndex);
                      const isBlocked = avail && !avail.is_available;
                      const phase = athleteProfile?.menstrual_tracking_enabled
                        ? getMenstrualPhaseForDate(
                            value,
                            athleteProfile.last_period_date,
                            athleteProfile.menstrual_cycle_days,
                          )
                        : null;
                      const mondayKey = getMonday(value);
                      const trainingPhase = trainingPhaseMap[mondayKey];
                      const trainingPhaseMeta = trainingPhase ? TRAINING_PHASE_COLORS[trainingPhase] : null;
                      return (
                        <Tooltip
                          title={
                            isBlocked
                              ? `No disponible${avail.reason ? `: ${avail.reason}` : ''}${avail.preferred_time ? ` — ${avail.preferred_time}` : ''}`
                              : phase
                              ? phase.tip
                              : trainingPhaseMeta
                              ? trainingPhaseMeta.label
                              : ''
                          }
                          placement="top"
                          disableHoverListener={!isBlocked && !phase && !trainingPhaseMeta}
                        >
                          <div style={{ position: 'relative', height: '100%', width: '100%' }}>
                            {phase && (
                              <div style={{
                                position: 'absolute', top: 0, left: 0, right: 0,
                                height: 3, background: phase.color, borderRadius: '2px 2px 0 0',
                                zIndex: 1,
                              }} />
                            )}
                            {trainingPhaseMeta && (
                              <div style={{
                                position: 'absolute', top: phase ? 4 : 0, left: 0, right: 0,
                                height: 4, background: trainingPhaseMeta.color,
                                opacity: 0.55, zIndex: 1,
                              }} />
                            )}
                            <div style={{
                              height: '100%', width: '100%',
                              background: isBlocked ? '#F1F5F9' : 'transparent',
                            }}>
                              {isBlocked && (
                                <div style={{
                                  position: 'absolute', bottom: 2, left: 4,
                                  fontSize: '0.6rem', color: '#94A3B8', lineHeight: 1.2,
                                }}>
                                  {avail.reason || 'No disp.'}
                                  {avail.preferred_time ? ` · ${avail.preferred_time}` : ''}
                                </div>
                              )}
                              {children}
                            </div>
                          </div>
                        </Tooltip>
                      );
                    },
                  }}
                  dragFromOutsideItem={dragFromOutsideItem}
                  onDropFromOutside={handleDropFromOutside}
                  onEventDrop={handleEventDrop}
                  onSelectEvent={(event) => {
                    if (event.isGoal) {
                      setSelectedGoal(event.resource?.goal ?? null);
                    } else {
                      setSelectedEvent(event);
                    }
                  }}
                  messages={{
                    next: 'Siguiente',
                    previous: 'Anterior',
                    today: 'Hoy',
                    month: 'Mes',
                    week: 'Semana',
                    day: 'Día',
                    noEventsInRange: 'Sin entrenamientos en este período.',
                  }}
                />
              </Paper>
            ))}

            {/* PR-158: Weekly load estimate — shown in week view for individual athlete */}
            {!planningWeek && calViewMode === 'week' && (() => {
              const target = parseTarget(selectedTarget);
              if (target?.type !== 'a') return null;
              const athleteObj = athleteState.data.find((a) => a.id === target.id);
              const membershipId = athleteObj?.membership_id;
              if (!membershipId) return null;
              const weekStart = format(currentDate, 'yyyy-MM-dd');
              return (
                <WeeklyLoadEstimate
                  membershipId={membershipId}
                  weekStart={weekStart}
                  trigger={loadTrigger}
                />
              );
            })()}
          </Box>
        </Box>

        {/* PR-145g: Coach event drawer (key resets internal comment state on event change) */}
        <WorkoutCoachDrawer
          key={selectedEvent?.id ?? 'none'}
          event={selectedEvent}
          orgId={orgId}
          onClose={() => setSelectedEvent(null)}
          onSaved={(updatedWorkout) => {
            if (selectedEvent) {
              const updatedEvent = {
                ...selectedEvent,
                planned_workout: updatedWorkout,
                resource: { ...selectedEvent.resource, planned_workout: updatedWorkout },
              };
              eventsDispatch({
                type: 'UPDATE_EVENT',
                id: selectedEvent.id,
                updates: {
                  planned_workout: updatedWorkout,
                  resource: updatedEvent.resource,
                },
              });
              // Keep drawer open and show fresh data
              setSelectedEvent(updatedEvent);
            }
          }}
          onMarkComplete={() => {}}
        />

        {/* PR-145f: undo toast */}
        {undoToast && (
          <UndoToast
            message={undoToast.message}
            onUndo={undoToast.onUndo}
            onClose={() => setUndoToast(null)}
          />
        )}

        {/* PR-145f: context menu */}
        {contextMenu && (
          <CalendarContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            event={contextMenu.event}
            onClose={() => setContextMenu(null)}
            onEdit={handleEditEvent}
            onDuplicate={(ev) => { setDuplicating(ev); setContextMenu(null); }}
            onDelete={(ev) => { handleDeleteEvent(ev); setContextMenu(null); }}
            onCopyWeek={(ev) => { setCopyingWeek(ev); setContextMenu(null); }}
            onDeleteWeek={(ev) => { setDeletingWeek(ev); setContextMenu(null); }}
          />
        )}

        {/* PR-145f: modals */}
        <DuplicateSessionModal
          open={!!duplicating}
          assignment={duplicating}
          athletes={athleteState.data}
          onClose={() => setDuplicating(null)}
          onConfirm={handleDuplicate}
        />

        <CopyWeekModal
          open={!!copyingWeek}
          sourceEvent={copyingWeek}
          athletes={athleteState.data}
          orgId={orgId}
          onClose={() => setCopyingWeek(null)}
          onSuccess={handleCopyWeekSuccess}
        />

        <DeleteWeekModal
          open={!!deletingWeek}
          event={deletingWeek}
          orgId={orgId}
          athleteId={parseTarget(selectedTarget)?.type === 'a' ? parseTarget(selectedTarget)?.id : null}
          onClose={() => setDeletingWeek(null)}
          onSuccess={handleDeleteWeekSuccess}
        />

        {/* PR-161: Goal edit dialog */}
        {selectedGoal && (
          <GoalEditDialog
            goal={selectedGoal}
            orgId={orgId}
            onClose={() => setSelectedGoal(null)}
            onSaved={(updated) => {
              setGoalEvents(prev => prev.map(e =>
                e.id === `goal-${updated.id}`
                  ? {
                      ...e,
                      title: updated.target_distance_km || updated.target_elevation_gain_m
                        ? `🏆 ${updated.title} — ${[updated.target_distance_km ? `${updated.target_distance_km}km` : null, updated.target_elevation_gain_m ? `D+${updated.target_elevation_gain_m}m` : null].filter(Boolean).join(' · ')}`
                        : `🏆 ${updated.title}`,
                      resource: { type: 'goal', goal: updated },
                    }
                  : e
              ));
              setSelectedGoal(null);
            }}
          />
        )}

        {/* PR-154: Blocked-day drop confirmation dialog */}
        <Dialog
          open={!!blockedDropPending}
          onClose={() => setBlockedDropPending(null)}
          maxWidth="xs"
          fullWidth
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: '1rem' }}>
            Día bloqueado
          </DialogTitle>
          <DialogContent>
            <Typography variant="body2" sx={{ color: '#475569' }}>
              {blockedDropPending?.message}
            </Typography>
            <Typography variant="body2" sx={{ color: '#475569', mt: 1 }}>
              ¿Planificar igual?
            </Typography>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
            <Button
              variant="text"
              onClick={() => setBlockedDropPending(null)}
              sx={{ textTransform: 'none', color: '#64748B' }}
            >
              Cancelar
            </Button>
            <Button
              variant="contained"
              onClick={handleConfirmBlockedDrop}
              sx={{ textTransform: 'none', bgcolor: '#6366F1', '&:hover': { bgcolor: '#4F46E5' } }}
            >
              Planificar igual
            </Button>
          </DialogActions>
        </Dialog>

        {/* FAB — mobile only: opens library as bottom drawer */}
        <Fab
          size="medium"
          onClick={() => setLibDrawerOpen(true)}
          sx={{
            display: { xs: 'flex', sm: 'none' },
            position: 'fixed',
            bottom: 72,
            right: 16,
            zIndex: 1100,
            bgcolor: '#00D4AA',
            color: '#0D1117',
            '&:hover': { bgcolor: '#00BF99' },
          }}
        >
          <AddIcon />
        </Fab>

        {/* Mobile library drawer */}
        <SwipeableDrawer
          anchor="bottom"
          open={libDrawerOpen}
          onOpen={() => setLibDrawerOpen(true)}
          onClose={() => setLibDrawerOpen(false)}
          disableSwipeToOpen
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': {
              borderRadius: '16px 16px 0 0',
              bgcolor: '#0f1621',
              pb: 'env(safe-area-inset-bottom)',
              maxHeight: '70vh',
              p: 2,
            },
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'center', pt: 0.5, pb: 1.5 }}>
            <Box sx={{ width: 32, height: 4, bgcolor: 'rgba(255,255,255,0.2)', borderRadius: 2 }} />
          </Box>
          <Typography variant="caption" sx={{ color: '#718096', textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 700, mb: 1.5, display: 'block' }}>
            Librería
          </Typography>
          {orgId ? (
            <LibrarySidebar
              orgId={orgId}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
            />
          ) : (
            <CircularProgress size={20} sx={{ color: '#00D4AA' }} />
          )}
        </SwipeableDrawer>
      </>
    </Layout>
  );
}
