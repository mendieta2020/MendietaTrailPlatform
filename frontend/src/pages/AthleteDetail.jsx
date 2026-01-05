import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Avatar,
  Chip,
  Button,
  CircularProgress,
  Stack,
  Fab,
  Drawer,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material';
import {
  ArrowBack,
  Edit,
  Email,
  LocationOn,
  CalendarMonth,
  LibraryBooks,
  FitnessCenter,
} from '@mui/icons-material';
import { format, parseISO } from 'date-fns';

import Layout from '../components/Layout';
import client from '../api/client';
import WeeklyCalendar from '../components/WeeklyCalendar';
import StudentPerformanceChart from '../components/widgets/StudentPerformanceChart';
import TemplateLibrary from '../components/TemplateLibrary';
import ErrorBoundary from '../components/ErrorBoundary';
import RiskBadge from '../components/RiskBadge';
import CoachDecisionsPanel from '../components/CoachDecisionsPanel';

const AthleteDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [athlete, setAthlete] = useState(null);
  const [injuryRisk, setInjuryRisk] = useState(null);
  const [loading, setLoading] = useState(true);

  // Librería lateral
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

  // Fecha activa del calendario (para asignación rápida)
  const [activeDateISO, setActiveDateISO] = useState(format(new Date(), 'yyyy-MM-dd'));

  // Lazy loading por mes (cache)
  const [trainingCache, setTrainingCache] = useState({}); // { [monthKey]: Entrenamiento[] }
  const [loadingMonths, setLoadingMonths] = useState({}); // { [monthKey]: true }
  const [monthOrder, setMonthOrder] = useState([]); // LRU

  // Quick assign (click-to-assign)
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignTemplate, setAssignTemplate] = useState(null);
  const [assignDate, setAssignDate] = useState(format(new Date(), 'yyyy-MM-dd'));

  // Refs para evitar closures stale en callbacks
  const trainingCacheRef = useRef(trainingCache);
  const loadingMonthsRef = useRef(loadingMonths);
  useEffect(() => {
    trainingCacheRef.current = trainingCache;
  }, [trainingCache]);
  useEffect(() => {
    loadingMonthsRef.current = loadingMonths;
  }, [loadingMonths]);

  // Carga inicial (perfil + riesgo)
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);

        const resAthlete = await client.get(`/api/alumnos/${id}/`);
        setAthlete(resAthlete.data);

        // Snapshot riesgo (no debe tumbar la pantalla si falla)
        try {
          const resRisk = await client.get(`/api/alumnos/${id}/injury-risk/`);
          if (resRisk?.data?.data_available) {
            setInjuryRisk({
              risk_level: resRisk.data.risk_level,
              risk_score: resRisk.data.risk_score,
              risk_reasons: resRisk.data.risk_reasons,
            });
          } else {
            setInjuryRisk(null);
          }
        } catch (e) {
          console.warn('Injury risk unavailable:', e);
          setInjuryRisk(null);
        }
      } catch (err) {
        console.error("Error cargando perfil:", err);
        setAthlete(null);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  // Merge seguro de entrenamientos desde cache
  const trainings = useMemo(() => {
    try {
      const merged = [];
      const cache = trainingCache && typeof trainingCache === 'object' ? trainingCache : {};
      Object.values(cache).forEach((arr) => {
        if (arr && Array.isArray(arr)) merged.push(...arr);
      });
      const seen = new Set();
      return merged.filter((t) => {
        if (!t || typeof t !== 'object') return false;
        const key = String(t?.id ?? '');
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    } catch (err) {
      console.error('trainings merge crashed:', err);
      return [];
    }
  }, [trainingCache]);

  // Lazy-load month: estable + guard estricto
  const fetchMonthIfNeeded = useCallback(async ({ monthKey, startISO, endISO }) => {
    console.log('RENDER_CHECK: fetchMonthIfNeeded', { monthKey, startISO, endISO });

    const cache = trainingCacheRef.current || {};
    const loadingMap = loadingMonthsRef.current || {};

    if (!monthKey || loadingMap[monthKey]) return;
    if (!startISO || !endISO) return;
    if (cache[monthKey]) return;

    try {
      setLoadingMonths((prev) => ({ ...prev, [monthKey]: true }));
      const res = await client.get(
        `/api/entrenamientos/?alumno=${id}&fecha_asignada__gte=${startISO}&fecha_asignada__lte=${endISO}`
      );
      setTrainingCache((prev) => ({ ...prev, [monthKey]: Array.isArray(res.data) ? res.data : [] }));
      setMonthOrder((prev) => {
        const next = prev.filter((k) => k !== monthKey).concat(monthKey);
        return next.slice(Math.max(0, next.length - 4));
      });
    } catch (err) {
      console.error("Error cargando entrenamientos del mes:", err);
      setTrainingCache((prev) => ({ ...prev, [monthKey]: [] }));
    } finally {
      setLoadingMonths((prev) => {
        const next = { ...prev };
        delete next[monthKey];
        return next;
      });
    }
  }, [id]);

  // Eviction LRU (best-effort)
  useEffect(() => {
    if (!monthOrder.length) return;
    setTrainingCache((prev) => {
      const keep = new Set(monthOrder);
      const next = {};
      Object.keys(prev || {}).forEach((k) => {
        if (keep.has(k)) next[k] = prev[k];
      });
      return next;
    });
  }, [monthOrder]);

  const handleOpenAssign = (tpl) => {
    setAssignTemplate(tpl);
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

      // Backend devuelve JSON en `estructura` (y también alias `descripcion_detallada_json`)
      // Normalizamos a estructura para el editor/calendario
      const created = res.data || {};
      if (!created.estructura && created.descripcion_detallada_json) {
        created.estructura = created.descripcion_detallada_json;
      }

      const d = created.fecha_asignada ? parseISO(created.fecha_asignada) : parseISO(assignDate);
      const monthKey = format(d, 'yyyy-MM');
      setTrainingCache((prev) => {
        const existing = Array.isArray(prev?.[monthKey]) ? prev[monthKey] : [];
        return { ...(prev || {}), [monthKey]: [created, ...existing] };
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

  if (loading) {
    return (
      <Layout>
        <Box sx={{ p: 5, textAlign: 'center' }}>
          <CircularProgress />
        </Box>
      </Layout>
    );
  }

  if (!athlete) {
    return (
      <Layout>
        <Paper sx={{ p: 3, borderRadius: 3 }}>
          <Typography sx={{ fontWeight: 800 }}>Atleta no encontrado</Typography>
        </Paper>
      </Layout>
    );
  }

  return (
    <Layout>
      {/* Header navegación */}
      <Button startIcon={<ArrowBack />} onClick={() => navigate(-1)} sx={{ mb: 2, color: '#64748B' }}>
        Volver
      </Button>

      {/* Cabecera atleta */}
      <Paper
        sx={{
          p: 4,
          borderRadius: 3,
          mb: 4,
          background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Grid container spacing={3} alignItems="center">
          <Grid item>
            <Avatar
              sx={{
                width: 100,
                height: 100,
                bgcolor: '#F57C00',
                fontSize: 40,
                boxShadow: '0 4px 12px rgba(245, 124, 0, 0.3)',
              }}
            >
              {athlete.nombre ? athlete.nombre.charAt(0) : '?'}
            </Avatar>
          </Grid>
          <Grid item xs>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1, flexWrap: 'wrap' }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#1E293B' }}>
                {athlete.nombre} {athlete.apellido}
              </Typography>
              <Chip label={athlete.estado_actual || 'Activo'} color="success" size="small" sx={{ fontWeight: 700 }} />
              <RiskBadge risk={injuryRisk} />
            </Box>

            <Stack direction="row" spacing={3} sx={{ color: '#64748B', flexWrap: 'wrap' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Email fontSize="small" /> <Typography variant="body2">{athlete.email}</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <LocationOn fontSize="small" />{' '}
                <Typography variant="body2">{athlete.ciudad || 'Ciudad no especificada'}</Typography>
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

      {/* Coach decision layer */}
      <CoachDecisionsPanel athleteId={id} />

      {/* Gráficas Strava (protegidas) */}
      <Box sx={{ mb: 4 }}>
        <ErrorBoundary height={550}>
          <StudentPerformanceChart alumnoId={id} />
        </ErrorBoundary>
      </Box>

      {/* Agenda */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, gap: 2 }}>
          <Typography
            variant="h6"
            sx={{ fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1, color: '#0F172A' }}
          >
            <CalendarMonth /> Agenda de Entrenamientos
          </Typography>
        </Box>

        {trainings.length === 0 && Object.keys(loadingMonths).length === 0 && (
          <Paper sx={{ p: 2, mb: 2, borderRadius: 3, bgcolor: '#FFF7ED', border: '1px solid #FED7AA' }}>
            <Typography variant="body2" sx={{ fontWeight: 800, color: '#9A3412' }}>
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

      {/* FAB Librería */}
      <Fab
        color="primary"
        aria-label="library"
        sx={{ position: 'fixed', bottom: 32, right: 32, bgcolor: '#0F172A', zIndex: 1000 }}
        onClick={() => setIsLibraryOpen(true)}
      >
        <LibraryBooks />
      </Fab>

      {/* Drawer Librería */}
      <Drawer anchor="right" open={isLibraryOpen} onClose={() => setIsLibraryOpen(false)}>
        <Box sx={{ width: { xs: '100vw', sm: 380 }, maxWidth: '100vw', height: '100%' }}>
          <TemplateLibrary onSelectTemplate={handleOpenAssign} />
        </Box>
      </Drawer>

      {/* Quick assign dialog */}
      <Dialog open={assignOpen} onClose={() => setAssignOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontWeight: 900, color: '#0F172A' }}>Asignar sesión</DialogTitle>
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
          <Button onClick={() => setAssignOpen(false)} color="inherit">
            Cancelar
          </Button>
          <Button onClick={handleAssign} variant="contained" sx={{ bgcolor: '#F57C00', fontWeight: 900, textTransform: 'none' }}>
            Asignar
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default AthleteDetail;