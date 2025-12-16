import React, { useState } from 'react';
import { Calendar as BigCalendar, dateFnsLocalizer } from 'react-big-calendar';
import format from 'date-fns/format';
import parse from 'date-fns/parse';
import startOfWeek from 'date-fns/startOfWeek';
import getDay from 'date-fns/getDay';
import esES from 'date-fns/locale/es'; // 🇪🇸 Calendario en Español
import 'react-big-calendar/lib/css/react-big-calendar.css'; // Estilos base
import { Box, Paper, Typography, Button } from '@mui/material';
import { Add } from '@mui/icons-material';
import Layout from '../components/Layout';

// Configuración de idioma (Español)
const locales = {
  'es': esES,
};

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales,
});

// Eventos de prueba (Luego vendrán de la API)
const myEventsList = [
  {
    title: 'Carrera Suave 10k 🏃',
    start: new Date(2025, 11, 15, 10, 0), // Ojo: Mes 11 es Diciembre en JS (0-11)
    end: new Date(2025, 11, 15, 11, 0),
    type: 'run'
  },
  {
    title: 'Gimnasio Fuerza 💪',
    start: new Date(2025, 11, 16, 18, 0),
    end: new Date(2025, 11, 16, 19, 30),
    type: 'gym'
  },
];

const CalendarPage = () => {
  return (
    <Layout>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Calendario de Temporada</Typography>
            <Typography variant="body2" sx={{ color: '#64748B' }}>Planificación visual de macrociclos.</Typography>
        </Box>
        <Button 
            variant="contained" 
            startIcon={<Add />}
            sx={{ bgcolor: '#1A2027', borderRadius: 2, textTransform: 'none' }}
        >
            Nueva Sesión
        </Button>
      </Box>

      <Paper sx={{ p: 2, height: '75vh', borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}>
        <BigCalendar
          localizer={localizer}
          events={myEventsList}
          startAccessor="start"
          endAccessor="end"
          culture='es' // Forzamos español
          messages={{
            next: "Sig",
            previous: "Ant",
            today: "Hoy",
            month: "Mes",
            week: "Semana",
            day: "Día"
          }}
          eventPropGetter={(event) => {
            // Estilizar eventos según tipo (Verde Running, Rojo Gym)
            const backgroundColor = event.type === 'gym' ? '#D32F2F' : '#2E7D32';
            return { style: { backgroundColor, borderRadius: '6px', border: 'none' } }
          }}
        />
      </Paper>
    </Layout>
  );
};

export default CalendarPage;