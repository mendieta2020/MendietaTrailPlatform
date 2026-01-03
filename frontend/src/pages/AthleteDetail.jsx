import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Box, Typography, Paper, Grid, Avatar, Chip, Button, 
  CircularProgress, Stack, Fab, Drawer, ToggleButtonGroup, ToggleButton
} from '@mui/material';
import { 
  ArrowBack, Edit, Email, LocationOn, CalendarMonth, FitnessCenter,
  LibraryBooks 
} from '@mui/icons-material';
import Layout from '../components/Layout';
import client from '../api/client';
import WeeklyCalendar from '../components/WeeklyCalendar'; 
import StudentPerformanceChart from '../components/widgets/StudentPerformanceChart'; 
import TemplateLibrary from '../components/TemplateLibrary'; 
import ErrorBoundary from '../components/ErrorBoundary'; // <--- 1. IMPORTACIÓN DE SEGURIDAD
import RiskBadge from '../components/RiskBadge';
import CoachDecisionsPanel from '../components/CoachDecisionsPanel';

const AthleteDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [athlete, setAthlete] = useState(null);
  const [trainings, setTrainings] = useState([]);
  const [injuryRisk, setInjuryRisk] = useState(null);
  const [loading, setLoading] = useState(true);
  const [granularity, setGranularity] = useState('DAILY');
  
  // Estado para la Librería Lateral
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const fetchAthlete = async () => {
      try {
        setLoading(true);
        const resAthlete = await client.get(`/api/alumnos/${id}/`);
        if (!cancelled) setAthlete(resAthlete.data);
      } catch (err) {
        console.error("Error cargando alumno:", err);
        if (!cancelled) setAthlete(null);
      } finally {
        // IMPORTANTE: loading depende SOLO de la carga inicial del alumno
        if (!cancelled) setLoading(false);
      }
    };

    const fetchExtras = async () => {
      try {
        // Riesgo de lesión (best-effort, no bloquea pantalla)
        const resRisk = await client.get(`/api/alumnos/${id}/injury-risk/`);
        if (cancelled) return;
        if (resRisk?.data?.data_available) {
          setInjuryRisk({
            risk_level: resRisk.data.risk_level,
            risk_score: resRisk.data.risk_score,
            risk_reasons: resRisk.data.risk_reasons,
          });
        } else {
          setInjuryRisk(null);
        }
      } catch (err) {
        console.error("Error cargando injury risk:", err);
        if (!cancelled) setInjuryRisk(null);
      }

      try {
        // Entrenamientos (best-effort, no bloquea pantalla)
        const resTrainings = await client.get(`/api/entrenamientos/?alumno=${id}`);
        const data = resTrainings.data.results || resTrainings.data || [];
        if (!cancelled) setTrainings(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error("Error cargando entrenamientos:", err);
        if (!cancelled) setTrainings([]);
      }
    };

    fetchAthlete();
    fetchExtras();

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 5 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!athlete) return <Layout><Typography>Atleta no encontrado</Typography></Layout>;

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
              <RiskBadge risk={injuryRisk} />
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

      {/* COACH DECISION LAYER (v1) */}
      <CoachDecisionsPanel athleteId={id} />

      {/* --- SECCIÓN DE ANALYTICS (BLINDADA) --- */}
      <Box sx={{ mb: 4 }}>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
              <ToggleButtonGroup
                  value={granularity}
                  exclusive
                  size="small"
                  onChange={(e, val) => val && setGranularity(val)}
              >
                  <ToggleButton value="DAILY" sx={{ textTransform: 'none', fontWeight: 700 }}>
                      Diaria
                  </ToggleButton>
                  <ToggleButton value="WEEKLY" sx={{ textTransform: 'none', fontWeight: 700 }}>
                      Semanal
                  </ToggleButton>
              </ToggleButtonGroup>
          </Box>
          {/* El ErrorBoundary atrapa cualquier crash dentro del gráfico y evita la pantalla blanca */}
          <ErrorBoundary height={550}>
              <StudentPerformanceChart
                alumnoId={id}
                granularity={granularity}
                weeklyStats={athlete?.stats_semanales || []}
              />
          </ErrorBoundary>
      </Box>

      {/* SECCIÓN AGENDA - CALENDARIO SEMANAL */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1, color: '#0F172A' }}>
                <CalendarMonth color="primary" /> Agenda de Entrenamientos
            </Typography>
        </Box>

        {trainings.length === 0 ? (
            <Paper sx={{ p: 6, textAlign: 'center', border: '2px dashed #e2e8f0', bgcolor: '#f8fafc', borderRadius: 3 }}>
                <FitnessCenter sx={{ fontSize: 50, color: '#cbd5e1', mb: 1 }} />
                <Typography color="textSecondary" sx={{ fontWeight: 500 }}>No hay entrenamientos asignados aún.</Typography>
                <Typography variant="caption" color="textSecondary">Asigna plantillas desde la librería o crea una sesión individual.</Typography>
            </Paper>
        ) : (
            <WeeklyCalendar trainings={trainings} />
        )}
      </Box>

      {/* --- HERRAMIENTAS FLOTANTES (LIBRERÍA) --- */}
      <Fab 
        color="primary" 
        aria-label="library" 
        sx={{ position: 'fixed', bottom: 32, right: 32, bgcolor: '#0F172A', zIndex: 1000 }}
        onClick={() => setIsLibraryOpen(true)}
      >
        <LibraryBooks />
      </Fab>

      <Drawer
        anchor="right"
        open={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
      >
        <Box sx={{ width: 350, height: '100%' }}>
            <TemplateLibrary />
        </Box>
      </Drawer>

    </Layout>
  );
};

export default AthleteDetail;