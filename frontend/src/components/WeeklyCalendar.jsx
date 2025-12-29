import React, { useMemo, useState, useCallback } from "react";
import {
  Box,
  Typography,
  Paper,
  Grid,
  IconButton,
  Button,
  Snackbar,
  Alert,
} from "@mui/material";
import {
  format,
  startOfWeek,
  addDays,
  isSameDay,
  addWeeks,
  subWeeks,
  parseISO,
} from "date-fns";
import { es } from "date-fns/locale";
import {
  DirectionsRun,
  PedalBike,
  Terrain,
  AccessTime,
  ArrowBackIos,
  ArrowForwardIos,
  Today,
  EmojiEvents,
} from "@mui/icons-material";

import client from "../api/client";
import StatGauge from "./widgets/StatGauge";
import TrainingCardPro from "./widgets/TrainingCardPro";
import EditTrainingModal from "./EditTrainingModal";
import TrainingDetailModal from "./TrainingDetailModal"; // <--- IMPORTACIÓN CRÍTICA

const WeeklyCalendar = ({ trainings: initialTrainings }) => {
  const [currentDate, setCurrentDate] = useState(() => new Date());

  // Modales
  const [editingTraining, setEditingTraining] = useState(null); // Coach
  const [detailTraining, setDetailTraining] = useState(null); // Alumno (Prueba de fuego)

  // Feedback
  const [feedback, setFeedback] = useState({
    open: false,
    msg: "",
    type: "success",
  });

  /**
   * Overrides locales para UI optimista (drag&drop, cambios sin esperar backend).
   * Estructura: { [trainingId]: { fecha_asignada: "yyyy-MM-dd" } }
   * No duplicamos todo el array en state → escalable.
   */
  const [overridesById, setOverridesById] = useState({});

  const startOfVisibleWeek = useMemo(
    () => startOfWeek(currentDate, { weekStartsOn: 1 }),
    [currentDate]
  );

  const weekDays = useMemo(
    () => Array.from({ length: 7 }).map((_, i) => addDays(startOfVisibleWeek, i)),
    [startOfVisibleWeek]
  );

  // Fuente segura
  const baseTrainings = useMemo(
    () => (Array.isArray(initialTrainings) ? initialTrainings : []),
    [initialTrainings]
  );

  // Trainings “mergeados” con overrides (sin setState en effects)
  const trainings = useMemo(() => {
    if (!baseTrainings.length) return [];

    return baseTrainings.map((t) => {
      const id = t?.id;
      if (id === null || id === undefined) return t;

      const ov = overridesById[id];
      if (!ov) return t;

      // Si el backend ya refleja el cambio, el override es redundante
      if (ov.fecha_asignada && ov.fecha_asignada === t.fecha_asignada) return t;

      return { ...t, ...ov };
    });
  }, [baseTrainings, overridesById]);

  // Week trainings (derivado)
  const weekTrainings = useMemo(() => {
    const weekEnd = addDays(startOfVisibleWeek, 6);

    return trainings.filter((t) => {
      if (!t?.fecha_asignada) return false;
      const tDate = parseISO(t.fecha_asignada);
      return tDate >= startOfVisibleWeek && tDate <= weekEnd;
    });
  }, [trainings, startOfVisibleWeek]);

  // Stats (derivado, sin setStats)
  const stats = useMemo(() => {
    const newStats = {
      distRun: { planned: 0, actual: 0 },
      distBike: { planned: 0, actual: 0 },
      elevation: { planned: 0, actual: 0 },
      hours: { planned: 0, actual: 0 },
    };

    for (const t of weekTrainings) {
      const tipo = t?.tipo_actividad || "";

      if (tipo.includes("RUN") || tipo.includes("TRAIL")) {
        newStats.distRun.planned += Number.parseFloat(t.distancia_planificada_km || 0);
        newStats.distRun.actual += Number.parseFloat(t.distancia_real_km || 0);
      }

      if (tipo.includes("BIKE") || tipo.includes("MTB")) {
        newStats.distBike.planned += Number.parseFloat(t.distancia_planificada_km || 0);
        newStats.distBike.actual += Number.parseFloat(t.distancia_real_km || 0);
      }

      newStats.elevation.planned += Number.parseInt(t.desnivel_planificado_m || 0, 10);
      newStats.elevation.actual += Number.parseInt(t.desnivel_real_m || 0, 10);

      newStats.hours.planned += Number.parseInt(t.tiempo_planificado_min || 0, 10);
      newStats.hours.actual += Number.parseInt(t.tiempo_real_min || 0, 10);
    }

    return newStats;
  }, [weekTrainings]);

  const overallCompliance = useMemo(() => {
    const totalPlanned = stats.hours.planned;
    const totalActual = stats.hours.actual;
    return totalPlanned > 0
      ? Math.min(100, Math.round((totalActual / totalPlanned) * 100))
      : 0;
  }, [stats.hours.planned, stats.hours.actual]);

  // --- Helpers ---
  const getTrainingsForDay = useCallback(
    (day) => {
      const dayStr = format(day, "yyyy-MM-dd");
      return trainings.filter((t) => t?.fecha_asignada === dayStr);
    },
    [trainings]
  );

  // --- Interacciones ---
  const handleDragStart = (e, trainingId) => {
    e.dataTransfer.setData("trainingId", String(trainingId));
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDropOnDay = async (e, dayDate) => {
    e.preventDefault();
    const trainingIdStr = e.dataTransfer.getData("trainingId");
    if (!trainingIdStr) return;

    const trainingId = Number(trainingIdStr);
    const newDateStr = format(dayDate, "yyyy-MM-dd");

    // UI optimista: set override
    setOverridesById((prev) => ({
      ...prev,
      [trainingId]: { fecha_asignada: newDateStr },
    }));

    try {
      await client.patch(`/api/entrenamientos/${trainingId}/`, {
        fecha_asignada: newDateStr,
      });

      setFeedback({ open: true, msg: "Entrenamiento movido 📅", type: "success" });

      // Limpieza opcional: si backend ya está, el override se vuelve redundante.
      // Lo dejamos porque no rompe nada y mantiene la UI estable si el padre no refetch.
    } catch (error) {
      console.error("Error moviendo entrenamiento:", error);

      // rollback del override
      setOverridesById((prev) => {
        const next = { ...prev };
        delete next[trainingId];
        return next;
      });

      setFeedback({
        open: true,
        msg: "Error al mover. Recarga la página.",
        type: "error",
      });
    }
  };

  // --- Click inteligente ---
  const handleCardClick = (training) => {
    // MODO ALUMNO (prueba de fuego)
    setDetailTraining(training);

    // Si querés modo coach:
    // setEditingTraining(training);
  };

  const handleFeedbackSaved = () => {
    // En producción: mejor invalidar cache/refetch (React Query/SWR).
    // Por ahora, mantenemos tu comportamiento actual.
    window.location.reload();
  };

  return (
    <Box>
      {/* HEADER DE NAVEGACIÓN */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 3,
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            bgcolor: "white",
            p: 0.5,
            borderRadius: 3,
            border: "1px solid #E2E8F0",
          }}
        >
          <IconButton onClick={() => setCurrentDate(subWeeks(currentDate, 1))} size="small">
            <ArrowBackIos fontSize="small" />
          </IconButton>

          <Typography
            variant="subtitle1"
            sx={{
              fontWeight: 800,
              color: "#1E293B",
              minWidth: 180,
              textAlign: "center",
              textTransform: "capitalize",
            }}
          >
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
          sx={{
            borderRadius: 3,
            textTransform: "none",
            color: "#64748B",
            borderColor: "#E2E8F0",
          }}
        >
          Hoy
        </Button>
      </Box>

      {/* DASHBOARD DE MÉTRICAS */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatGauge
            title="Cumplimiento"
            value={overallCompliance}
            target={100}
            unit="%"
            icon={EmojiEvents}
            color="#8B5CF6"
          />
        </Grid>

        <Grid item xs={6} md={2.4}>
          <StatGauge
            title="Volumen (H)"
            value={stats.hours.actual / 60}
            target={stats.hours.planned / 60}
            unit="h"
            icon={AccessTime}
            color="#64748B"
          />
        </Grid>

        <Grid item xs={6} md={2.4}>
          <StatGauge
            title="Running"
            value={stats.distRun.actual}
            target={stats.distRun.planned}
            unit="km"
            icon={DirectionsRun}
            color="#F59E0B"
          />
        </Grid>

        <Grid item xs={6} md={2.4}>
          <StatGauge
            title="Ciclismo"
            value={stats.distBike.actual}
            target={stats.distBike.planned}
            unit="km"
            icon={PedalBike}
            color="#3B82F6"
          />
        </Grid>

        <Grid item xs={6} md={2.4}>
          <StatGauge
            title="Desnivel (+)"
            value={stats.elevation.actual}
            target={stats.elevation.planned}
            unit="m"
            icon={Terrain}
            color="#10B981"
          />
        </Grid>
      </Grid>

      {/* CALENDARIO SEMANAL */}
      <Paper
        elevation={0}
        sx={{
          border: "1px solid #E2E8F0",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <Box sx={{ overflowX: "auto" }}>
          <Box sx={{ display: "flex", minWidth: 1200 }}>
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
                    flex: 1,
                    minWidth: 0,
                    minHeight: 400,
                    borderRight: index < 6 ? "1px solid #E2E8F0" : "none",
                    bgcolor: isToday ? "#FFF7ED" : isWeekend ? "#F8FAFC" : "white",
                    display: "flex",
                    flexDirection: "column",
                    transition: "background-color 0.2s",
                  }}
                >
                  {/* Cabecera Día */}
                  <Box
                    sx={{
                      p: 1.5,
                      textAlign: "center",
                      borderBottom: "1px solid #E2E8F0",
                      bgcolor: isToday ? "#F57C00" : "transparent",
                      color: isToday ? "white" : "inherit",
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        textTransform: "uppercase",
                        fontWeight: 700,
                        opacity: 0.8,
                        display: "block",
                      }}
                    >
                      {format(day, "EEE", { locale: es })}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1 }}>
                      {format(day, "d")}
                    </Typography>
                  </Box>

                  {/* Cuerpo Día */}
                  <Box
                    sx={{
                      p: 1,
                      flexGrow: 1,
                      display: "flex",
                      flexDirection: "column",
                      gap: 1,
                    }}
                  >
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
                            handleCardClick(t);
                          }}
                        />
                      </div>
                    ))}

                    <Button
                      fullWidth
                      variant="text"
                      size="small"
                      sx={{
                        mt: "auto",
                        color: "#CBD5E1",
                        fontSize: "1.2rem",
                        minWidth: 0,
                        "&:hover": { color: "#F57C00", bgcolor: "#FFF7ED" },
                      }}
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

      {/* MODAL EDICIÓN (COACH) */}
      {editingTraining && (
        <EditTrainingModal
          open={true}
          onClose={() => setEditingTraining(null)}
          training={editingTraining}
          onUpdated={() => window.location.reload()}
        />
      )}

      {/* MODAL EJECUCIÓN (ALUMNO) */}
      {detailTraining && (
        <TrainingDetailModal
          open={true}
          onClose={() => setDetailTraining(null)}
          training={detailTraining}
          onFeedbackSaved={handleFeedbackSaved}
        />
      )}

      {/* FEEDBACK */}
      <Snackbar
        open={feedback.open}
        autoHideDuration={3000}
        onClose={() => setFeedback((f) => ({ ...f, open: false }))}
      >
        <Alert severity={feedback.type} variant="filled" sx={{ width: "100%" }}>
          {feedback.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default WeeklyCalendar;
