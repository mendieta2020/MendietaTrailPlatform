import React, { useRef, useState, useEffect } from 'react';
import { 
  Box, Typography, Paper, Grid, IconButton, Button, Snackbar, Alert 
} from '@mui/material';
import { 
  format, startOfWeek, addDays, isSameDay, addWeeks, subWeeks, parseISO, startOfMonth, endOfMonth
} from 'date-fns';
import { es } from 'date-fns/locale';
import { 
    DirectionsRun, PedalBike, Terrain, AccessTime, 
    ArrowBackIos, ArrowForwardIos, Today, EmojiEvents
} from '@mui/icons-material';
import client from '../api/client';
import StatGauge from './widgets/StatGauge'; 
import TrainingCardPro from './widgets/TrainingCardPro';
import EditTrainingModal from './EditTrainingModal';
import TrainingDetailModal from './TrainingDetailModal'; // <--- IMPORTACIÓN CRÍTICA

const WeeklyCalendar = ({ trainings: initialTrainings, athleteId, onActiveDateChange, onNeedMonth }) => {
  const [trainings, setTrainings] = useState([]); 
  const [currentDate, setCurrentDate] = useState(new Date());
  const [activeDay, setActiveDay] = useState(new Date());
  const [overallCompliance, setOverallCompliance] = useState(0);
  
  // Estado de Modales
  const [editingTraining, setEditingTraining] = useState(null); // Editor (Entrenador)
  const [detailTraining, setDetailTraining] = useState(null);   // Ejecución (Alumno) - NUEVO
  
  const [feedback, setFeedback] = useState({ open: false, msg: '', type: 'success' });
  
  const [stats, setStats] = useState({
    distRun: { planned: 0, actual: 0 },
    distBike: { planned: 0, actual: 0 },
    elevation: { planned: 0, actual: 0 },
    hours: { planned: 0, actual: 0 },
  });

  useEffect(() => {
    setTrainings(initialTrainings);
  }, [initialTrainings]);

  const startOfVisibleWeek = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDays = Array.from({ length: 7 }).map((_, i) => addDays(startOfVisibleWeek, i));

  const lastMonthRequestedRef = useRef(null);

  // Lazy loading: pedir solo el mes visible (cache en el parent).
  useEffect(() => {
    if (!athleteId) return;
    if (typeof onNeedMonth !== 'function') return;
    const monthKey = format(currentDate, 'yyyy-MM');
    if (lastMonthRequestedRef.current === monthKey) return;
    const startISO = format(startOfMonth(currentDate), 'yyyy-MM-dd');
    const endISO = format(endOfMonth(currentDate), 'yyyy-MM-dd');
    lastMonthRequestedRef.current = monthKey;
    onNeedMonth({ monthKey, startISO, endISO });
  }, [athleteId, currentDate, onNeedMonth]);

  // Fecha activa para “click-to-assign” desde librería
  useEffect(() => {
    if (typeof onActiveDateChange !== 'function') return;
    onActiveDateChange(format(activeDay, 'yyyy-MM-dd'));
  }, [activeDay, onActiveDateChange]);

  // --- CÁLCULOS DE ESTADÍSTICAS ---
  useEffect(() => {
    const newStats = {
        distRun: { planned: 0, actual: 0 },
        distBike: { planned: 0, actual: 0 },
        elevation: { planned: 0, actual: 0 },
        hours: { planned: 0, actual: 0 },
    };

    const weekTrainings = trainings.filter(t => {
        if (!t.fecha_asignada) return false;
        const tDate = parseISO(t.fecha_asignada);
        return tDate >= startOfVisibleWeek && tDate <= addDays(startOfVisibleWeek, 6);
    });

    weekTrainings.forEach(t => {
        if (t.tipo_actividad?.includes('RUN') || t.tipo_actividad?.includes('TRAIL')) {
            newStats.distRun.planned += parseFloat(t.distancia_planificada_km || 0);
            newStats.distRun.actual += parseFloat(t.distancia_real_km || 0);
        }
        if (t.tipo_actividad?.includes('BIKE') || t.tipo_actividad?.includes('MTB')) {
            newStats.distBike.planned += parseFloat(t.distancia_planificada_km || 0);
            newStats.distBike.actual += parseFloat(t.distancia_real_km || 0);
        }
        newStats.elevation.planned += parseInt(t.desnivel_planificado_m || 0);
        newStats.elevation.actual += parseInt(t.desnivel_real_m || 0);
        newStats.hours.planned += parseInt(t.tiempo_planificado_min || 0);
        newStats.hours.actual += parseInt(t.tiempo_real_min || 0);
    });

    setStats(newStats);

    let totalPlanned = newStats.hours.planned;
    let totalActual = newStats.hours.actual;
    const globalScore = totalPlanned > 0 ? Math.min(100, Math.round((totalActual / totalPlanned) * 100)) : 0;
    setOverallCompliance(globalScore);

  }, [currentDate, trainings]);

  // --- MANEJADORES DE INTERACCIÓN ---

  const handleDragStart = (e, trainingId) => {
      e.dataTransfer.setData("trainingId", trainingId);
      e.dataTransfer.effectAllowed = "move";
  };

  const handleDropOnDay = async (e, dayDate) => {
      e.preventDefault();
      const templateId = e.dataTransfer.getData("templateId");
      const trainingId = e.dataTransfer.getData("trainingId");

      const newDateStr = format(dayDate, 'yyyy-MM-dd');

      // A) Drop desde Librería (Plantilla -> crear instancia individual)
      if (templateId) {
          if (!athleteId) {
              setFeedback({ open: true, msg: 'No se pudo asignar: falta athleteId.', type: 'error' });
              return;
          }
          try {
              const res = await client.post(`/api/plantillas/${templateId}/aplicar_a_alumno/`, {
                  alumno_id: athleteId,
                  fecha_asignada: newDateStr,
              });
              setTrainings((prev) => [res.data, ...prev]);
              setFeedback({ open: true, msg: 'Sesión asignada ✅', type: 'success' });
          } catch (error) {
              console.error("Error asignando plantilla:", error);
              setFeedback({ open: true, msg: 'Error al asignar. Reintenta.', type: 'error' });
          }
          return;
      }

      // B) Move de un Entrenamiento existente (drag interno)
      if (!trainingId) return;

      // Optimistic update
      const updatedTrainings = trainings.map(t => {
          if (t.id.toString() === trainingId) {
              return { ...t, fecha_asignada: newDateStr };
          }
          return t;
      });
      setTrainings(updatedTrainings);

      try {
          await client.patch(`/api/entrenamientos/${trainingId}/`, {
              fecha_asignada: newDateStr
          });
          setFeedback({ open: true, msg: 'Entrenamiento movido 📅', type: 'success' });
      } catch (error) {
          console.error("Error moviendo entrenamiento:", error);
          setFeedback({ open: true, msg: 'Error al mover. Recarga la página.', type: 'error' });
      }
  };

  const getTrainingsForDay = (day) => {
    return trainings.filter(t => t.fecha_asignada === format(day, 'yyyy-MM-dd'));
  };

  // --- 🔥 GESTIÓN DE CLICS (MODO PRUEBA DE FUEGO) ---
  const handleCardClick = (training) => {
      // Pantalla de coach: click = ajustar sesión individual (solo este día).
      setEditingTraining(training);
  };

  const handleFeedbackSaved = () => {
      // Recargar datos para ver el cambio de color (VERDE)
      window.location.reload(); 
  };

  return (
    <Box>
      {/* HEADER DE NAVEGACIÓN */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, bgcolor: 'white', p: 0.5, borderRadius: 3, border: '1px solid #E2E8F0' }}>
            <IconButton onClick={() => setCurrentDate(subWeeks(currentDate, 1))} size="small">
                <ArrowBackIos fontSize="small" />
            </IconButton>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#1E293B', minWidth: 180, textAlign: 'center', textTransform: 'capitalize' }}>
                {format(startOfVisibleWeek, "MMMM yyyy", { locale: es })}
            </Typography>
            <IconButton onClick={() => setCurrentDate(addWeeks(currentDate, 1))} size="small">
                <ArrowForwardIos fontSize="small" />
            </IconButton>
        </Box>
        <Button 
            size="small" 
            variant="outlined" 
            startIcon={<Today />} 
            onClick={() => setCurrentDate(new Date())}
            sx={{ borderRadius: 3, textTransform: 'none', color: '#64748B', borderColor: '#E2E8F0' }}
        >
            Hoy
        </Button>
      </Box>

      {/* DASHBOARD DE MÉTRICAS */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={2.4}>
            <StatGauge title="Cumplimiento" value={overallCompliance} target={100} unit="%" icon={EmojiEvents} color="#8B5CF6" />
        </Grid>
        <Grid item xs={6} md={2.4}>
            <StatGauge title="Volumen (H)" value={stats.hours.actual / 60} target={stats.hours.planned / 60} unit="h" icon={AccessTime} color="#64748B" />
        </Grid>
        <Grid item xs={6} md={2.4}>
            <StatGauge title="Running" value={stats.distRun.actual} target={stats.distRun.planned} unit="km" icon={DirectionsRun} color="#F59E0B" />
        </Grid>
        <Grid item xs={6} md={2.4}>
            <StatGauge title="Ciclismo" value={stats.distBike.actual} target={stats.distBike.planned} unit="km" icon={PedalBike} color="#3B82F6" />
        </Grid>
        <Grid item xs={6} md={2.4}>
            <StatGauge title="Desnivel (+)" value={stats.elevation.actual} target={stats.elevation.planned} unit="m" icon={Terrain} color="#10B981" />
        </Grid>
      </Grid>

      {/* CALENDARIO SEMANAL */}
      <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ overflowX: 'auto' }}>
            <Box sx={{ display: 'flex', minWidth: { xs: 780, sm: 980, md: 1200 } }}> 
                {weekDays.map((day, index) => {
                    const isToday = isSameDay(day, new Date());
                    const isActive = isSameDay(day, activeDay);
                    const dayTrainings = getTrainingsForDay(day);
                    const isWeekend = index >= 5;

                    return (
                    <Box 
                        key={day.toString()} 
                        onDragOver={(e) => e.preventDefault()} 
                        onDrop={(e) => handleDropOnDay(e, day)} 
                        onClick={() => setActiveDay(day)}
                        sx={{ 
                            flex: 1, minWidth: 0, minHeight: { xs: 300, md: 400 }, 
                            borderRight: index < 6 ? '1px solid #E2E8F0' : 'none', 
                            outline: isActive ? '2px solid #F57C00' : 'none',
                            outlineOffset: isActive ? '-2px' : undefined,
                            bgcolor: isToday ? '#FFF7ED' : (isWeekend ? '#F8FAFC' : 'white'),
                            display: 'flex', flexDirection: 'column',
                            transition: 'background-color 0.2s'
                        }}
                    >
                        {/* Cabecera Día */}
                        <Box sx={{ 
                            p: 1.5, textAlign: 'center', borderBottom: '1px solid #E2E8F0',
                            bgcolor: isToday ? '#F57C00' : 'transparent',
                            color: isToday ? 'white' : 'inherit'
                        }}>
                            <Typography variant="caption" sx={{ textTransform: 'uppercase', fontWeight: 700, opacity: 0.8, display: 'block' }}>
                                {format(day, 'EEE', { locale: es })}
                            </Typography>
                            <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1 }}>
                                {format(day, 'd')}
                            </Typography>
                        </Box>

                        {/* Cuerpo Día (Tarjetas) */}
                        <Box sx={{ p: 1, flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
                            {dayTrainings.map((t) => (
                                <div 
                                    key={t.id} 
                                    draggable 
                                    onDragStart={(e) => handleDragStart(e, t.id)}
                                >
                                    <TrainingCardPro 
                                        training={t} 
                                        onClick={(e) => {
                                            e.stopPropagation(); 
                                            handleCardClick(t); // <--- Llama al manejador inteligente
                                        }}
                                    />
                                </div>
                            ))}
                            
                            <Button 
                                fullWidth 
                                variant="text" 
                                size="small" 
                                sx={{ mt: 'auto', color: '#CBD5E1', fontSize: '1.2rem', minWidth: 0, '&:hover': { color: '#F57C00', bgcolor: '#FFF7ED' } }}
                            >
                                +
                            </Button>
                        </Box>
                    </Box>
                    );
                })}
            </Box>
        </Box>
      </Paper>

      {/* 1. MODAL DE EDICIÓN (ENTRENADOR) */}
      {editingTraining && (
          <EditTrainingModal 
            open={true}
            onClose={() => setEditingTraining(null)} 
            training={editingTraining}
            onUpdated={(updated) => {
              if (!updated?.id) return;
              setTrainings((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
              setFeedback({ open: true, msg: 'Sesión actualizada ✅', type: 'success' });
            }} 
          />
      )}

      {/* 2. MODAL DE EJECUCIÓN (ALUMNO - PRUEBA DE FUEGO) */}
      {detailTraining && (
          <TrainingDetailModal
            open={true}
            onClose={() => setDetailTraining(null)}
            training={detailTraining}
            onFeedbackSaved={handleFeedbackSaved}
          />
      )}

      {/* FEEDBACK VISUAL */}
      <Snackbar open={feedback.open} autoHideDuration={3000} onClose={() => setFeedback({...feedback, open: false})}>
        <Alert severity={feedback.type} variant="filled" sx={{ width: '100%' }}>{feedback.msg}</Alert>
      </Snackbar>
    </Box>
  );
};

export default WeeklyCalendar;