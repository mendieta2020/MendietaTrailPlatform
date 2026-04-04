import React, { useState } from 'react';
import {
    Box, Typography, Paper, Grid, IconButton, Button, Snackbar, Alert
} from '@mui/material';
import {
    format, startOfWeek, addDays, isSameDay, addWeeks, subWeeks, parseISO
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

const WeeklyCalendar = ({ trainings: initialTrainings, athleteId, onTrainingCreated }) => {
    const trainings = React.useMemo(() => Array.isArray(initialTrainings) ? initialTrainings : [], [initialTrainings]);
    const [currentDate, setCurrentDate] = useState(new Date());

    // Estado de Modales
    const [editingTraining, setEditingTraining] = useState(null); // Editor (Entrenador)
    const [detailTraining, setDetailTraining] = useState(null);   // Ejecución (Alumno) - NUEVO

    const [feedback, setFeedback] = useState({ open: false, msg: '', type: 'success' });

    const startOfVisibleWeek = React.useMemo(() => startOfWeek(currentDate, { weekStartsOn: 1 }), [currentDate]);
    const weekDays = React.useMemo(() => Array.from({ length: 7 }).map((_, i) => addDays(startOfVisibleWeek, i)), [startOfVisibleWeek]);

    // --- CÁLCULOS DE ESTADÍSTICAS ---
    const { stats, overallCompliance } = React.useMemo(() => {
        const newStats = {
            distRun: { planned: 0, actual: 0 },
            distBike: { planned: 0, actual: 0 },
            elevation: { planned: 0, actual: 0 },
            hours: { planned: 0, actual: 0 },
        };

        const weekTrainings = (Array.isArray(trainings) ? trainings : []).filter(t => {
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

        let totalPlanned = newStats.hours.planned;
        let totalActual = newStats.hours.actual;
        const globalScore = totalPlanned > 0 ? Math.min(100, Math.round((totalActual / totalPlanned) * 100)) : 0;

        return { stats: newStats, overallCompliance: globalScore };
    }, [trainings, startOfVisibleWeek]);

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

        if (templateId) {
            if (!athleteId) {
                setFeedback({ open: true, msg: 'Selecciona un atleta antes de asignar.', type: 'error' });
                return;
            }
            try {
                const res = await client.post(`/api/plantillas/${templateId}/asignar_a_alumno/`, {
                    alumno_id: athleteId,
                    fecha: newDateStr
                });
                const newTraining = res.data;
                if (onTrainingCreated) {
                    onTrainingCreated(newTraining);
                }
                setFeedback({ open: true, msg: 'Plantilla asignada ✅', type: 'success' });
            } catch (error) {
                console.error("Error asignando plantilla:", error);
                setFeedback({ open: true, msg: 'Error al asignar plantilla.', type: 'error' });
            }
            return;
        }

        if (!trainingId) return;

        // Optimistic updaté is ignored since trainings is derived from initialTrainings.
        // A reload or an upstream refetch happens otherwise.
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
        return (Array.isArray(trainings) ? trainings : []).filter(t => t.fecha_asignada === format(day, 'yyyy-MM-dd'));
    };

    // --- 🔥 GESTIÓN DE CLICS (MODO PRUEBA DE FUEGO) ---
    const handleCardClick = (training) => {
        // ⚠️ MODO ALUMNO ACTIVADO PARA TESTING ⚠️
        // En el futuro, aquí pondremos un 'if (isCoach) setEditingTraining(training) else setDetailTraining(training)'
        setDetailTraining(training);

        // Si quisieras editar como entrenador, descomenta esto y comenta la línea de arriba:
        // setEditingTraining(training);
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
                <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
                    <StatGauge title="Cumplimiento" value={overallCompliance} target={100} unit="%" icon={EmojiEvents} color="#8B5CF6" />
                </Grid>
                <Grid size={{ xs: 6, md: 2.4 }}>
                    <StatGauge title="Volumen (H)" value={stats.hours.actual / 60} target={stats.hours.planned / 60} unit="h" icon={AccessTime} color="#64748B" />
                </Grid>
                <Grid size={{ xs: 6, md: 2.4 }}>
                    <StatGauge title="Running" value={stats.distRun.actual} target={stats.distRun.planned} unit="km" icon={DirectionsRun} color="#F59E0B" />
                </Grid>
                <Grid size={{ xs: 6, md: 2.4 }}>
                    <StatGauge title="Ciclismo" value={stats.distBike.actual} target={stats.distBike.planned} unit="km" icon={PedalBike} color="#3B82F6" />
                </Grid>
                <Grid size={{ xs: 6, md: 2.4 }}>
                    <StatGauge title="Desnivel (+)" value={stats.elevation.actual} target={stats.elevation.planned} unit="m" icon={Terrain} color="#00D4AA" />
                </Grid>
            </Grid>

            {/* CALENDARIO SEMANAL */}
            <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 3, overflow: 'hidden' }}>
                <Box sx={{ overflowX: 'auto' }}>
                    <Box sx={{ display: 'flex', minWidth: 1200 }}>
                        {weekDays.map((day, index) => {
                            const isToday = isSameDay(day, new Date());
                            const dayTrainings = getTrainingsForDay(day);
                            const isWeekend = index >= 5;

                            return (
                                <Box
                                    key={day.toString()}
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={(e) => handleDropOnDay(e, day)}
                                    sx={{
                                        flex: 1, minWidth: 0, minHeight: 400,
                                        borderRight: index < 6 ? '1px solid #E2E8F0' : 'none',
                                        bgcolor: isToday ? '#FFF7ED' : (isWeekend ? '#F8FAFC' : 'white'),
                                        display: 'flex', flexDirection: 'column',
                                        transition: 'background-color 0.2s'
                                    }}
                                >
                                    {/* Cabecera Día */}
                                    <Box sx={{
                                        p: 1.5, textAlign: 'center', borderBottom: '1px solid #E2E8F0',
                                        bgcolor: isToday ? '#00D4AA' : 'transparent',
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
                                            sx={{ mt: 'auto', color: '#CBD5E1', fontSize: '1.2rem', minWidth: 0, '&:hover': { color: '#00D4AA', bgcolor: '#FFF7ED' } }}
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
                    onUpdated={() => window.location.reload()}
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
            <Snackbar open={feedback.open} autoHideDuration={3000} onClose={() => setFeedback({ ...feedback, open: false })}>
                <Alert severity={feedback.type} variant="filled" sx={{ width: '100%' }}>{feedback.msg}</Alert>
            </Snackbar>
        </Box>
    );
};

export default WeeklyCalendar;
