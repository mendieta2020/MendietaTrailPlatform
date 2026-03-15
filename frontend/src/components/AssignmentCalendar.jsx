import React, { useState, useEffect, useReducer } from 'react';
import { Calendar, dateFnsLocalizer } from 'react-big-calendar';
import { format, parse, startOfWeek, getDay, startOfMonth, endOfMonth } from 'date-fns';
import { es } from 'date-fns/locale';
import 'react-big-calendar/lib/css/react-big-calendar.css';
import { Box, CircularProgress, Alert } from '@mui/material';
import { listAssignments } from '../api/assignments';

const locales = { es };

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: (date) => startOfWeek(date, { weekStartsOn: 1 }),
  getDay,
  locales,
});

const initialState = { events: [], loading: false, error: null };

function calendarReducer(state, action) {
  switch (action.type) {
    case 'FETCH_START':
      return { events: [], loading: true, error: null };
    case 'FETCH_SUCCESS':
      return { events: action.events, loading: false, error: null };
    case 'FETCH_ERROR':
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

function toEvents(assignments) {
  return assignments.map((a) => {
    const day = new Date(a.effective_date ?? a.scheduled_date);
    return {
      title: a.planned_workout_title ?? 'Entrenamiento',
      start: day,
      end: day,
      allDay: true,
      resource: a,
    };
  });
}

export default function AssignmentCalendar({ athleteId, orgId }) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [state, dispatch] = useReducer(calendarReducer, initialState);

  const dateFrom = format(startOfMonth(currentDate), 'yyyy-MM-dd');
  const dateTo = format(endOfMonth(currentDate), 'yyyy-MM-dd');

  useEffect(() => {
    if (!orgId || !athleteId) return;
    dispatch({ type: 'FETCH_START' });
    listAssignments(orgId, { athleteId, dateFrom, dateTo })
      .then((res) => {
        const data = res.data?.results ?? res.data ?? [];
        dispatch({ type: 'FETCH_SUCCESS', events: toEvents(data) });
      })
      .catch(() =>
        dispatch({ type: 'FETCH_ERROR', error: 'No se pudieron cargar los entrenamientos.' })
      );
  }, [orgId, athleteId, dateFrom, dateTo]);

  if (state.loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (state.error) {
    return <Alert severity="error" sx={{ mt: 2 }}>{state.error}</Alert>;
  }

  return (
    <Box sx={{ height: 600, mt: 3 }}>
      <Calendar
        localizer={localizer}
        events={state.events}
        date={currentDate}
        onNavigate={setCurrentDate}
        defaultView="month"
        views={['month']}
        culture="es"
      />
    </Box>
  );
}
