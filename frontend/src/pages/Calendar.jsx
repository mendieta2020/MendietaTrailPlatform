import React, { useState, useEffect, useReducer, useRef, useCallback } from 'react';
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
import { DndProvider, useDrag } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import {
  Box,
  Paper,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tooltip,
} from '@mui/material';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { listAthletes, listLibraries, listPlannedWorkouts } from '../api/p1';
import { listAssignments, createAssignment } from '../api/assignments';

const DnDCalendar = withDragAndDrop(Calendar);

const locales = { es };
const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: (date) => startOfWeek(date, { weekStartsOn: 1 }),
  getDay,
  locales,
});

const WORKOUT_DRAG_TYPE = 'PLANNED_WORKOUT';

// ── Reducers ──────────────────────────────────────────────────────────────────

function fetchReducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':
      return { ...state, loading: true, error: null };
    case 'FETCH_SUCCESS':
      return { data: action.data, loading: false, error: null };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    case 'CLEAR':
      return { data: [], loading: false, error: null };
    default:
      return state;
  }
}

// ── Draggable workout card ────────────────────────────────────────────────────

function WorkoutCard({ workout, onDragStart, onDragEnd }) {
  const [{ isDragging }, drag] = useDrag({
    type: WORKOUT_DRAG_TYPE,
    item: () => {
      onDragStart(workout);
      return { workout };
    },
    end: () => onDragEnd(),
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  });

  return (
    <Box
      ref={drag}
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
      <Typography variant="caption" sx={{ color: '#718096', display: 'block', p: 1 }}>
        Sin librerías. Crea entrenamientos en /library.
      </Typography>
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
      resource: a,
    };
  });
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CalendarPage() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id ?? null;

  // Athletes
  const [athleteState, athleteDispatch] = useReducer(fetchReducer, {
    data: [],
    loading: false,
    error: null,
  });
  const [selectedAthleteId, setSelectedAthleteId] = useState('');

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

  // ── Load assignments for current month ────────────────────────────────────

  const dateFrom = format(startOfMonth(currentDate), 'yyyy-MM-dd');
  const dateTo = format(endOfMonth(currentDate), 'yyyy-MM-dd');

  useEffect(() => {
    if (!orgId || !selectedAthleteId) {
      eventsDispatch({ type: 'CLEAR' });
      return;
    }
    eventsDispatch({ type: 'FETCH_START' });
    listAssignments(orgId, { athleteId: selectedAthleteId, dateFrom, dateTo })
      .then((res) => {
        const data = res.data?.results ?? res.data ?? [];
        eventsDispatch({ type: 'FETCH_SUCCESS', data: toEvents(data) });
      })
      .catch(() =>
        eventsDispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar los entrenamientos.' })
      );
  }, [orgId, selectedAthleteId, dateFrom, dateTo]);

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

  // Called when a sidebar workout is dropped onto a calendar slot
  const handleDropFromOutside = useCallback(
    ({ start }) => {
      const workout = draggingWorkoutRef.current;
      draggingWorkoutRef.current = null;
      if (!workout || !selectedAthleteId || !orgId) return;

      const scheduledDate = format(start, 'yyyy-MM-dd');
      setSaving(true);
      setSaveError(null);

      createAssignment(orgId, {
        planned_workout: workout.id,
        athlete: selectedAthleteId,
        scheduled_date: scheduledDate,
      })
        .then((res) => {
          const a = res.data;
          const day = parseISO(a.effective_date ?? a.scheduled_date);
          eventsDispatch({
            type: 'FETCH_SUCCESS',
            data: [
              ...eventsState.data,
              {
                id: a.id,
                title: a.planned_workout_title ?? workout.name,
                start: day,
                end: day,
                allDay: true,
                resource: a,
              },
            ],
          });
        })
        .catch(() => setSaveError('Error al asignar el entrenamiento. Intenta de nuevo.'))
        .finally(() => setSaving(false));
    },
    [orgId, selectedAthleteId, eventsState.data]
  );

  // ── Calendar styling ──────────────────────────────────────────────────────

  const eventPropGetter = useCallback(
    () => ({
      style: {
        backgroundColor: '#F57C00',
        borderRadius: '5px',
        border: 'none',
        color: '#fff',
        fontSize: '0.72rem',
        padding: '2px 5px',
        fontWeight: 500,
      },
    }),
    []
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Layout>
      <DndProvider backend={HTML5Backend}>
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

          {saving && (
            <Tooltip title="Guardando asignación…">
              <CircularProgress size={20} sx={{ color: '#F57C00' }} />
            </Tooltip>
          )}

          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Atleta</InputLabel>
            <Select
              value={selectedAthleteId}
              label="Atleta"
              onChange={(e) => setSelectedAthleteId(e.target.value)}
              disabled={athleteState.loading || !orgId}
            >
              {athleteState.data.map((a) => (
                <MenuItem key={a.id} value={a.id}>
                  {a.first_name} {a.last_name}
                </MenuItem>
              ))}
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

        {/* ── Body: sidebar + calendar ── */}
        <Box
          sx={{
            display: 'flex',
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

            {!selectedAthleteId ? (
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
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h6" color="text.secondary" fontWeight={500}>
                    Selecciona un atleta
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mt: 0.5 }}
                  >
                    Elige un atleta en el desplegable para ver su calendario.
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
                  dragFromOutsideItem={dragFromOutsideItem}
                  onDropFromOutside={handleDropFromOutside}
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
      </DndProvider>
    </Layout>
  );
}
