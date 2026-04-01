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
} from '@mui/material';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import { Users, BookOpen } from 'lucide-react';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { listAthletes, listTeams, listLibraries, listPlannedWorkouts, getAthleteAvailability, getAthleteProfile } from '../api/p1';
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
  { name: 'Folicular',  color: '#10B981', tip: 'Fase folicular — ideal para alta intensidad' },
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
        bgcolor: isDragging ? 'rgba(245, 124, 0, 0.12)' : '#1c2230',
        border: '1px solid',
        borderColor: isDragging ? '#F57C00' : 'rgba(255,255,255,0.07)',
        cursor: 'grab',
        transition: 'border-color 0.15s, background-color 0.15s',
        opacity: isDragging ? 0.45 : 1,
        '&:hover': {
          borderColor: '#F57C00',
          bgcolor: 'rgba(245, 124, 0, 0.07)',
        },
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: '#F57C00', fontWeight: 600, display: 'block', lineHeight: 1 }}
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
        <CircularProgress size={22} sx={{ color: '#F57C00' }} />
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
                <CircularProgress size={16} sx={{ color: '#F57C00' }} />
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

  return (
    <div
      style={{ fontSize: '11px', lineHeight: '1.2', overflow: 'hidden', height: '100%' }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (onContextMenu) onContextMenu(e.clientX, e.clientY, event);
      }}
    >
      <div style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
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
    setCurrentDate(targetDate); // eslint-disable-line react-hooks/set-state-in-effect
  }, []); // intentionally mount-only

  useEffect(() => {
    const assignmentId = sessionStorage.getItem('calendarOpenAssignment');
    if (!assignmentId || eventsState.loading || eventsState.data.length === 0) return;
    const targetId = parseInt(assignmentId, 10);
    const event = eventsState.data.find((e) => e.id === targetId);
    if (event) {
      sessionStorage.removeItem('calendarOpenAssignment');
      setSelectedEvent(event); // eslint-disable-line react-hooks/set-state-in-effect
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
      } catch {
        eventsDispatch({ type: 'MOVE_EVENT', id: event.id, newDate: oldDate });
        setSaveError('No se pudo mover la sesión.');
      }
    },
    [orgId, showUndo]
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

  // ── Calendar styling ──────────────────────────────────────────────────────

  const eventPropGetter = useCallback(
    (event) => {
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
          backgroundColor: '#F57C00',
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
              Macro
            </ToggleButton>
          </ToggleButtonGroup>

          {saving && (
            <Tooltip title="Guardando asignación…">
              <CircularProgress size={20} sx={{ color: '#F57C00' }} />
            </Tooltip>
          )}

          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Atleta o Grupo</InputLabel>
            <Select
              value={selectedTarget}
              label="Atleta o Grupo"
              onChange={(e) => {
                const v = e.target.value;
                setSelectedTarget(v);
                sessionStorage.setItem('calendarSelectedTarget', v);
              }}
              disabled={(athleteState.loading || teamState.loading) || !orgId}
            >
              {teamState.data.length > 0 && (
                <ListSubheader sx={{ lineHeight: '28px', fontSize: '0.7rem', letterSpacing: '0.06em' }}>
                  GRUPOS
                </ListSubheader>
              )}
              {teamState.data.map((t) => (
                <MenuItem key={`t:${t.id}`} value={`t:${t.id}`}>
                  {t.name}
                </MenuItem>
              ))}
              {athleteState.data.length > 0 && (
                <ListSubheader sx={{ lineHeight: '28px', fontSize: '0.7rem', letterSpacing: '0.06em' }}>
                  ATLETAS
                </ListSubheader>
              )}
              {athleteState.data.map((a) => {
                const name = [a.first_name, a.last_name].filter(Boolean).join(' ')
                  || a.email?.split('@')[0]
                  || `Atleta #${a.id}`;
                return (
                  <MenuItem key={`a:${a.id}`} value={`a:${a.id}`}>
                    {name}
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
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
            <MacroView orgId={orgId} />
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
          {/* Sidebar */}
          {sidebarOpen && (
            <Paper
              sx={{
                width: 240,
                flexShrink: 0,
                bgcolor: '#0f1621',
                borderRadius: 2,
                p: 1.5,
                overflowY: 'auto',
                display: 'flex',
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
                <CircularProgress size={20} sx={{ color: '#F57C00' }} />
              )}
            </Paper>
          )}

          {/* Sidebar toggle when collapsed */}
          {!sidebarOpen && (
            <Tooltip title="Abrir librería">
              <IconButton
                size="small"
                onClick={() => setSidebarOpen(true)}
                sx={{ alignSelf: 'flex-start', mt: 0.5, color: '#F57C00' }}
              >
                <MenuIcon />
              </IconButton>
            </Tooltip>
          )}

          {/* Calendar area */}
          <Box sx={{ flex: 1, position: 'relative', minWidth: 0 }}>
            {eventsState.loading && (
              <Box
                sx={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}
              >
                <CircularProgress size={20} />
              </Box>
            )}

            {eventsState.error && (
              <Alert severity="error" sx={{ mb: 1 }}>
                {eventsState.error}
              </Alert>
            )}

            {!selectedTarget ? (
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
                    Selecciona un atleta o grupo
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#6b7280', mt: 0.5 }}>
                    Elige en el desplegable de arriba para visualizar y gestionar el calendario de entrenamientos.
                  </Typography>
                </Box>
              </Paper>
            ) : (
              <Paper sx={{ height: '100%', p: 1.5, borderRadius: 2 }}>
                <DnDCalendar
                  localizer={localizer}
                  events={eventsState.data}
                  date={currentDate}
                  onNavigate={setCurrentDate}
                  defaultView="month"
                  views={['month', 'week']}
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
                      return (
                        <Tooltip
                          title={
                            isBlocked
                              ? `No disponible${avail.reason ? `: ${avail.reason}` : ''}${avail.preferred_time ? ` — ${avail.preferred_time}` : ''}`
                              : phase
                              ? phase.tip
                              : ''
                          }
                          placement="top"
                          disableHoverListener={!isBlocked && !phase}
                        >
                          <div style={{ position: 'relative', height: '100%', width: '100%' }}>
                            {phase && (
                              <div style={{
                                position: 'absolute', top: 0, left: 0, right: 0,
                                height: 3, background: phase.color, borderRadius: '2px 2px 0 0',
                                zIndex: 1,
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
                  onSelectEvent={(event) => setSelectedEvent(event)}
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
            )}
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
      </>
    </Layout>
  );
}
