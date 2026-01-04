import React, { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Box, Typography, Paper, Grid, Avatar, Chip, Button, 
  CircularProgress, Stack, Fab, Drawer, Dialog, DialogTitle, DialogContent, DialogActions, TextField
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
import { format, parseISO } from 'date-fns';

const AthleteDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [athlete, setAthlete] = useState(null);
  const [injuryRisk, setInjuryRisk] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Estado para la Librería Lateral
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [activeDateISO, setActiveDateISO] = useState(format(new Date(), 'yyyy-MM-dd'));

  // Lazy loading por mes (cache)
  const [trainingCache, setTrainingCache] = useState({}); // { [monthKey]: Entrenamiento[] }
  const [loadingMonths, setLoadingMonths] = useState({}); // { [monthKey]: true }
  const [monthOrder, setMonthOrder] = useState([]); // LRU simple para no acumular meses

  // Refs para evitar closures stale en callbacks (y prevenir loops por props inestables)
  const trainingCacheRef = useRef(trainingCache);
  const loadingMonthsRef = useRef(loadingMonths);
  useEffect(() => {
    trainingCacheRef.current = trainingCache;
  }, [trainingCache]);
  useEffect(() => {
    loadingMonthsRef.current = loadingMonths;
  }, [loadingMonths]);

  // Quick assign (click-to-assign)
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignTemplate, setAssignTemplate] = useState(null);
  const [assignDate, setAssignDate] = useState(format(new Date(), 'yyyy-MM-dd'));

  // DEBUG (solicitado)
  console.log('DEBUG - Athlete Data:', athlete);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // 1. Datos del Alumno
        const resAthlete = await client.get(`/api/alumnos/${id}/`);
        setAthlete(resAthlete.data);

        // 1.1 Riesgo de lesión (snapshot materializado)
        const resRisk = await client.get(`/api/alumnos/${id}/injury-risk/`);
        // Normalizamos al formato del componente
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
        console.error("Error cargando perfil:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <Layout><Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box></Layout>;
  if (!athlete) return <Layout><Typography>Atleta no encontrado</Typography></Layout>;

  const trainings = useMemo(() => {
    // Unimos meses cargados (el calendario filtra por semana internamente)
    const merged = [];
    Object.values(trainingCache).forEach((arr) => {
      if (Array.isArray(arr)) merged.push(...arr);
    });
    // dedupe defensivo (por id)
    const seen = new Set();
    return merged.filter((t) => {
      const key = String(t?.id ?? '');
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [trainingCache]);

  // DEBUG (solicitado)
  console.log('DEBUG - Trainings:', trainings);

  // DEBUG más útil: cuando cambian los datos
  useEffect(() => {
    console.log('DEBUG - Athlete Data (effect):', athlete);
  }, [athlete]);
  useEffect(() => {
    console.log('DEBUG - Trainings (effect):', trainings);
  }, [trainings]);

  const fetchMonthIfNeeded = useCallback(async ({ monthKey, startISO, endISO }) => {
    if (!monthKey || !startISO || !endISO) return;
    const cache = trainingCacheRef.current || {};
    const loadingMap = loadingMonthsRef.current || {};
    if (cache[monthKey]) return;
    if (loadingMap[monthKey]) return;

    try {
      setLoadingMonths((prev) => ({ ...prev, [monthKey]: true }));
      const res = await client.get(
        `/api/entrenamientos/?alumno=${id}&fecha_asignada__gte=${startISO}&fecha_asignada__lte=${endISO}`
      );
      setTrainingCache((prev) => ({ ...prev, [monthKey]: res.data || [] }));
      setMonthOrder((prev) => {
        const next = prev.filter((k) => k !== monthKey).concat(monthKey);
        // Mantener solo los últimos 4 meses vistos (suficiente para navegación fluida)
        return next.slice(Math.max(0, next.length - 4));
      });
    } catch (err) {
      console.error("Error cargando entrenamientos del mes:", err);
    } finally {
      setLoadingMonths((prev) => {
        const next = { ...prev };
        delete next[monthKey];
        return next;
      });
    }
  }, [id]);

  const handleOpenAssign = (tpl) => {
    setAssignTemplate(tpl);
    // default: día activo del calendario
    setAssignDate(activeDateISO || format(new Date(), 'yyyy-MM-dd'));
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!assignTemplate?.id) return;
    try {
      const res = await client.post(`/api/plantillas/${assignTemplate.id}/aplicar_a_alumno/`, {
        alumno_id: id,
        fecha_asignada: assignDate,
      });
      const created = res.data;
      // insertar en cache del mes correspondiente (sin refetch)
      const d = parseISO(created.fecha_asignada);
      const monthKey = format(d, 'yyyy-MM');
      setTrainingCache((prev) => {
        const existing = Array.isArray(prev[monthKey]) ? prev[monthKey] : [];
        return { ...prev, [monthKey]: [created, ...existing] };
      });
      setMonthOrder((prev) => {
        const next = prev.filter((k) => k !== monthKey).concat(monthKey);
        return next.slice(Math.max(0, next.length - 4));
      });
      setAssignOpen(false);
      setIsLibraryOpen(false);
    } catch (err) {
      console.error("Error asignando plantilla:", err);
      alert("Error al asignar la sesión. Reintenta.");
    }
  };

  // Eviction: si monthOrder reduce, limpiamos cache viejo (best-effort)
  useEffect(() => {
    if (monthOrder.length === 0) return;
    setTrainingCache((prev) => {
      const keep = new Set(monthOrder);
      const next = {};
      Object.keys(prev).forEach((k) => {
        if (keep.has(k)) next[k] = prev[k];
      });
      return next;
    });
  }, [monthOrder]);

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
          {/* El ErrorBoundary atrapa cualquier crash dentro del gráfico y evita la pantalla blanca */}
          <ErrorBoundary height={550}>
              <StudentPerformanceChart alumnoId={id} />
          </ErrorBoundary>
      </Box>

      {/* SECCIÓN AGENDA - CALENDARIO SEMANAL */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1, color: '#0F172A' }}>
                <CalendarMonth color="primary" /> Agenda de Entrenamientos
            </Typography>
        </Box>

        {trainings.length === 0 && Object.keys(loadingMonths).length === 0 && (
          <Paper sx={{ p: 2, mb: 2, borderRadius: 3, bgcolor: '#FFF7ED', border: '1px solid #FED7AA' }}>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#9A3412' }}>
              Tip: abre la Librería y asigna sesiones con un click (o arrástralas al día).
            </Typography>
          </Paper>
        )}

        <WeeklyCalendar
          trainings={trainings}
          athleteId={id}
          onActiveDateChange={setActiveDateISO}
          onNeedMonth={fetchMonthIfNeeded}
        />
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
        <Box sx={{ width: { xs: '100vw', sm: 380 }, maxWidth: '100vw', height: '100%' }}>
            <TemplateLibrary onSelectTemplate={handleOpenAssign} />
        </Box>
      </Drawer>

      {/* Quick Assign Dialog */}
      <Dialog open={assignOpen} onClose={() => setAssignOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontWeight: 800, color: '#0F172A' }}>Asignar sesión</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ color: '#64748B', mb: 2 }}>
            {assignTemplate?.titulo || 'Plantilla'}
          </Typography>
          <TextField
            fullWidth
            type="date"
            label="Fecha"
            value={assignDate}
            onChange={(e) => setAssignDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ bgcolor: 'white' }}
          />
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setAssignOpen(false)} color="inherit">Cancelar</Button>
          <Button onClick={handleAssign} variant="contained" sx={{ bgcolor: '#F57C00', fontWeight: 800, textTransform: 'none' }}>
            Asignar
          </Button>
        </DialogActions>
      </Dialog>

    </Layout>
  );
};

export default AthleteDetail;