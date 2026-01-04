import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Box, Typography, Paper, Grid, Avatar, Chip, Button, 
  CircularProgress, Stack
} from '@mui/material';
import { 
  ArrowBack, Edit, Email, LocationOn
} from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';
// DIAGNÓSTICO AGRESIVO:
// Comentamos temporalmente Calendar/Library/Charts para aislar qué rompe el render.
// import WeeklyCalendar from '../components/WeeklyCalendar';
// import StudentPerformanceChart from '../components/widgets/StudentPerformanceChart';
// import TemplateLibrary from '../components/TemplateLibrary';
// import ErrorBoundary from '../components/ErrorBoundary';
// import RiskBadge from '../components/RiskBadge';
// import CoachDecisionsPanel from '../components/CoachDecisionsPanel';
// import { format, parseISO } from 'date-fns';

const AthleteDetail = () => {
  console.log('RENDER_CHECK: Componente cargado');
  const { id } = useParams();
  const navigate = useNavigate();
  const [athlete, setAthlete] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // 1. Datos del Alumno
        const resAthlete = await client.get(`/api/alumnos/${id}/`);
        setAthlete(resAthlete.data);
      } catch (err) {
        console.error("Error cargando perfil:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <Layout><Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box></Layout>;
  if (!athlete) return <Layout><Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box></Layout>;

  // Try-catch “visual” (best-effort): si algo rompe este header, mostramos fallback.
  try {
    return (
      <Layout>
        {/* HEADER DE NAVEGACIÓN */}
        <Button startIcon={<ArrowBack />} onClick={() => navigate(-1)} sx={{ mb: 2, color: '#64748B' }}>
          Volver
        </Button>

        {/* TARJETA DE PERFIL (HEADER) */}
        <Paper sx={{ p: 4, borderRadius: 3, mb: 4, background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
          <Grid container spacing={3} alignItems="center">
            <Grid item>
              <Avatar 
                sx={{ width: 100, height: 100, bgcolor: '#F57C00', fontSize: 40, boxShadow: '0 4px 12px rgba(245, 124, 0, 0.3)' }}
              >
                {athlete.nombre ? athlete.nombre.charAt(0) : '?'}
              </Avatar>
            </Grid>
            <Grid item xs>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                <Typography variant="h4" sx={{ fontWeight: 800, color: '#1E293B' }}>
                  {athlete.nombre} {athlete.apellido}
                </Typography>
                <Chip label={athlete.estado_actual || "Activo"} color="success" size="small" sx={{ fontWeight: 600 }} />
              </Box>
              
              <Stack direction="row" spacing={3} sx={{ color: '#64748B' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Email fontSize="small" /> <Typography variant="body2">{athlete.email}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <LocationOn fontSize="small" /> <Typography variant="body2">{athlete.ciudad || "Ciudad no especificada"}</Typography>
                </Box>
              </Stack>
            </Grid>
            <Grid item>
              <Button variant="outlined" startIcon={<Edit />} sx={{ borderRadius: 2, textTransform: 'none' }}>
                  Editar Perfil
              </Button>
            </Grid>
          </Grid>
        </Paper>

        {/* DIAGNÓSTICO: Componentes comentados temporalmente */}
        {/*
          <WeeklyCalendar ... />
          <TemplateLibrary ... />
        */}
      </Layout>
    );
  } catch (err) {
    console.error("FATAL_RENDER - AthleteDetail header crashed:", err);
    return (
      <Layout>
        <Paper sx={{ p: 3, borderRadius: 3, bgcolor: '#FEF2F2', border: '1px solid #FECACA' }}>
          <Typography sx={{ fontWeight: 900, color: '#991B1B' }}>
            Error renderizando AthleteDetail (modo diagnóstico).
          </Typography>
          <Typography variant="body2" sx={{ color: '#B91C1C', mt: 1 }}>
            Revisá la consola para el stacktrace.
          </Typography>
        </Paper>
      </Layout>
    );
  }
};

export default AthleteDetail;