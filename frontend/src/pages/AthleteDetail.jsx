import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Grid, Avatar, Chip, Button,
  CircularProgress, Stack, Fab, Drawer
} from '@mui/material';
import {
  ArrowBack, Edit, Email, LocationOn, CalendarMonth, FitnessCenter,
  LibraryBooks
} from '@mui/icons-material';
import Layout from '../components/Layout';
import { AthleteProfileCards } from '../components/AthleteProfileCards';
import client from '../api/client';
import { getAthlete } from '../api/p1';
import { getAthleteProfile, getInjuries, getAvailability, getGoals } from '../api/athlete';
import { useOrg } from '../context/OrgContext';
import WeeklyCalendar from '../components/WeeklyCalendar';
import StudentPerformanceChart from '../components/widgets/StudentPerformanceChart';
import TemplateLibrary from '../components/TemplateLibrary';
import ErrorBoundary from '../components/ErrorBoundary'; // <--- 1. IMPORTACIÓN DE SEGURIDAD
import RiskBadge from '../components/RiskBadge';
import CoachDecisionsPanel from '../components/CoachDecisionsPanel';

const AthleteDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeOrg, orgLoading } = useOrg();
  const [athlete, setAthlete] = useState(null);
  const [trainings, setTrainings] = useState([]);
  const [injuryRisk] = useState(null);
  const [loading, setLoading] = useState(true);

  // Athlete profile data for coach read-only view
  const [athleteProfile, setAthleteProfile] = useState(null);
  const [athleteInjuries, setAthleteInjuries] = useState([]);
  const [athleteAvailability, setAthleteAvailability] = useState([]);
  const [athleteGoals, setAthleteGoals] = useState([]);
  const [showProfile, setShowProfile] = useState(false);
  // Sections collapsed by default to keep the page focused
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);

  // Estado para la Librería Lateral
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const handleTrainingCreated = (training) => {
    setTrainings((prev) => [...(Array.isArray(prev) ? prev : []), training]);
  };

  useEffect(() => {
    if (!activeOrg) return;
    const fetchData = async () => {
      try {
        setLoading(true);
        // 1. Datos del Athlete (P1 roster endpoint — organization-scoped)
        const resAthlete = await getAthlete(activeOrg.org_id, id);
        setAthlete(resAthlete.data);

        // 2. Entrenamientos (legacy; silently ignored if not available)
        try {
          const resTrainings = await client.get(`/api/entrenamientos/?alumno=${id}`);
          const trainingsData = Array.isArray(resTrainings.data)
            ? resTrainings.data
            : Array.isArray(resTrainings.data?.results)
              ? resTrainings.data.results
              : [];
          setTrainings(trainingsData);
        } catch {
          setTrainings([]);
        }

        // 3. Athlete profile data (for coach read-only view)
        try {
          const [profRes, injRes, availRes, goalRes] = await Promise.all([
            getAthleteProfile(activeOrg.org_id, id).catch(() => ({ data: null })),
            getInjuries(activeOrg.org_id, id).catch(() => ({ data: [] })),
            getAvailability(activeOrg.org_id, id).catch(() => ({ data: [] })),
            getGoals(activeOrg.org_id, id).catch(() => ({ data: [] })),
          ]);
          if (profRes.data) setAthleteProfile(profRes.data);
          setAthleteInjuries(Array.isArray(injRes.data) ? injRes.data : injRes.data?.results ?? []);
          setAthleteAvailability(Array.isArray(availRes.data) ? availRes.data : availRes.data?.results ?? []);
          const allGoals = Array.isArray(goalRes.data) ? goalRes.data : goalRes.data?.results ?? [];
          setAthleteGoals(allGoals.filter(g => g.status === 'active'));
        } catch {
          // Profile section silently hidden on error
        }
      } catch (err) {
        if (import.meta.env.DEV) {
          console.error("Error cargando perfil:", err);
        }
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, activeOrg?.org_id]);

  if (orgLoading || loading) return <Layout><Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box></Layout>;
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
          <Grid>
            <Avatar
              sx={{ width: 100, height: 100, bgcolor: '#F57C00', fontSize: 40, boxShadow: '0 4px 12px rgba(245, 124, 0, 0.3)' }}
            >
              {athlete.first_name ? athlete.first_name.charAt(0) : '?'}
            </Avatar>
          </Grid>
          <Grid size="grow">
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#1E293B' }}>
                {athlete.first_name} {athlete.last_name}
              </Typography>
              <Chip label={athlete.is_active !== false ? "Activo" : "Inactivo"} color={athlete.is_active !== false ? "success" : "default"} size="small" sx={{ fontWeight: 600 }} />
              <RiskBadge risk={injuryRisk} />
            </Box>

            <Stack direction="row" spacing={3} sx={{ color: '#64748B' }}>
              {athlete.email && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Email fontSize="small" /> <Typography variant="body2">{athlete.email}</Typography>
                </Box>
              )}
            </Stack>
          </Grid>
          <Grid>
            <Button variant="outlined" startIcon={<Edit />} sx={{ borderRadius: 2, textTransform: 'none' }}>
              Editar Perfil
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* COACH DECISION LAYER (v1) */}
      <CoachDecisionsPanel athleteId={id} />

      {/* PERFIL DEL ATLETA (read-only) */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 4, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', mb: showProfile ? 2 : 0 }}
          onClick={() => setShowProfile(v => !v)}
        >
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A' }}>
            Perfil del Atleta
          </Typography>
          <Typography variant="body2" sx={{ color: '#6366F1', fontWeight: 600 }}>
            {showProfile ? 'Ocultar ▲' : 'Ver perfil ▼'}
          </Typography>
        </Box>
        {showProfile && (
          <AthleteProfileCards
            profile={athleteProfile}
            injuries={athleteInjuries}
            availability={athleteAvailability}
            goals={athleteGoals}
            userName={`${athlete?.first_name || ''} ${athlete?.last_name || ''}`.trim()}
            readOnly
            orgId={activeOrg?.org_id}
            athleteId={id}
          />
        )}
      </Paper>

      {/* --- SECCIÓN DE ANALYTICS (colapsable) --- */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setShowAnalytics(v => !v)}
        >
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A' }}>
            Rendimiento
          </Typography>
          <Typography variant="body2" sx={{ color: '#6366F1', fontWeight: 600 }}>
            {showAnalytics ? 'Ocultar ▲' : 'Ver gráfico ▼'}
          </Typography>
        </Box>
        {showAnalytics && (
          <Box sx={{ mt: 2 }}>
            <ErrorBoundary height={550}>
              <StudentPerformanceChart alumnoId={id} />
            </ErrorBoundary>
          </Box>
        )}
      </Paper>

      {/* --- SECCIÓN AGENDA - CALENDARIO SEMANAL (colapsable) --- */}
      <Paper sx={{ p: 3, borderRadius: 3, mb: 3, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setShowCalendar(v => !v)}
        >
          <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1, color: '#0F172A' }}>
            <CalendarMonth color="primary" /> Agenda de Entrenamientos
          </Typography>
          <Typography variant="body2" sx={{ color: '#6366F1', fontWeight: 600 }}>
            {showCalendar ? 'Ocultar ▲' : 'Ver agenda ▼'}
          </Typography>
        </Box>
        {showCalendar && (
          <Box sx={{ mt: 2 }}>
            {trainings.length === 0 && (
              <Paper sx={{ p: 3, textAlign: 'center', border: '2px dashed #e2e8f0', bgcolor: '#f8fafc', borderRadius: 3, mb: 2 }}>
                <FitnessCenter sx={{ fontSize: 40, color: '#cbd5e1', mb: 1 }} />
                <Typography color="textSecondary" sx={{ fontWeight: 500 }}>No hay entrenamientos asignados aún.</Typography>
                <Typography variant="caption" color="textSecondary">Arrastra una plantilla al calendario para empezar.</Typography>
              </Paper>
            )}
            <WeeklyCalendar trainings={trainings} athleteId={id} onTrainingCreated={handleTrainingCreated} />
          </Box>
        )}
      </Paper>

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
