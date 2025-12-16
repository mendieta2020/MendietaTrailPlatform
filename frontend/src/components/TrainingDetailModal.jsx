import React, { useState, useEffect } from 'react';
import { 
  Dialog, DialogTitle, DialogContent, DialogActions, 
  Button, Typography, Box, IconButton, Slider, TextField, 
  Card, CardContent, CardMedia, Checkbox, Chip, Stack, useMediaQuery, useTheme, Alert
} from '@mui/material';
import { 
  Close, CheckCircle, SentimentVeryDissatisfied, SentimentSatisfied, SentimentVerySatisfied,
  LockClock, EventAvailable, Info
} from '@mui/icons-material';
import { isFuture, isToday, parseISO } from 'date-fns';
import client from '../api/client';

// --- CONFIGURACIÓN DE RPE ---
const RPE_MARKS = [
  { value: 1, label: 'Muy Suave' },
  { value: 5, label: 'Moderado' },
  { value: 10, label: 'Máximo' },
];

const INTENSITY_ZONES = {
    1: { label: 'Z1 - Recuperación', color: '#A3E635' },
    2: { label: 'Z2 - Suave', color: '#84CC16' },
    3: { label: 'Z3 - Tempo', color: '#FACC15' },
    4: { label: 'Z4 - Umbral', color: '#F97316' },
    5: { label: 'Z5 - VO2 Max', color: '#EF4444' },
};

const TrainingDetailModal = ({ open, onClose, training, onFeedbackSaved }) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'));
  
  const [mode, setMode] = useState('VIEW');
  const [completedSteps, setCompletedSteps] = useState({});
  const [rpe, setRpe] = useState(5);
  const [comments, setComments] = useState('');
  const [loading, setLoading] = useState(false);

  // --- LÓGICA DE TIEMPO Y ESTADO ---
  const trainingDate = training ? parseISO(training.fecha_asignada) : new Date();
  
  // 1. Es Futuro: Mañana en adelante (Bloquea edición, permite lectura)
  const isFutureTraining = isFuture(trainingDate) && !isToday(trainingDate);
  // 2. Es Completado: Ya tiene el check en BD
  const isCompleted = training?.completado;
  // 3. Se puede completar: Si es Hoy/Pasado y NO está hecho
  const canComplete = !isFutureTraining && !isCompleted;

  useEffect(() => {
      if (open && training) {
          setMode('VIEW');
          setRpe(training.rpe || 5);
          setComments(training.feedback_alumno || '');
          setCompletedSteps({});
      }
  }, [open, training]);

  if (!training) return null;

  const isStrength = training.tipo_actividad === 'STRENGTH';
  // Aseguramos que structure exista para evitar errores
  const structure = training.estructura || { bloques: [] };
  const hasBlocks = structure.bloques && structure.bloques.length > 0;

  // --- MANEJADORES ---
  const toggleStep = (blockId, stepId) => {
      // Bloqueamos interacción si es futuro o ya está hecho
      if (isFutureTraining || isCompleted) return; 
      
      setCompletedSteps(prev => ({
          ...prev,
          [`${blockId}-${stepId}`]: !prev[`${blockId}-${stepId}`]
      }));
  };

  const handleSaveFeedback = async () => {
      if (!training.id) return;
      try {
          setLoading(true);
          const payload = { rpe, feedback_alumno: comments, completado: true };
          await client.patch(`/api/entrenamientos/${training.id}/feedback/`, payload);
          if (onFeedbackSaved) onFeedbackSaved(); 
          onClose();
      } catch (error) {
          console.error("Error:", error);
          alert("Error de conexión al guardar.");
      } finally {
          setLoading(false);
      }
  };

  const renderRPEIcon = (val) => {
      if (val < 4) return <SentimentVerySatisfied sx={{ fontSize: 40, color: '#84CC16' }} />;
      if (val < 8) return <SentimentSatisfied sx={{ fontSize: 40, color: '#FACC15' }} />;
      return <SentimentVeryDissatisfied sx={{ fontSize: 40, color: '#EF4444' }} />;
  };

  // --- VISTAS DE CONTENIDO ---
  
  const renderEmptyState = () => (
      <Box sx={{ p: 4, textAlign: 'center', opacity: 0.6 }}>
          <Info sx={{ fontSize: 40, mb: 1, color: '#94A3B8' }} />
          <Typography variant="body1" fontWeight="bold" color="textSecondary">
              Sin detalles estructurados
          </Typography>
          <Typography variant="caption" color="textSecondary">
              El entrenador no ha especificado series o bloques para esta sesión.
          </Typography>
          {training.descripcion_detallada && (
              <Paper sx={{ mt: 2, p: 2, bgcolor: '#F1F5F9', textAlign: 'left' }}>
                  <Typography variant="body2" style={{ whiteSpace: 'pre-line' }}>
                      {training.descripcion_detallada}
                  </Typography>
              </Paper>
          )}
      </Box>
  );

  const renderStrengthView = () => (
      <Stack spacing={3}>
          {structure.bloques?.map((block, bIndex) => (
              <Card key={bIndex} variant="outlined" sx={{ borderRadius: 3, border: '1px solid #E2E8F0' }}>
                  <Box sx={{ bgcolor: '#F8FAFC', p: 1.5 }}>
                      <Typography variant="subtitle2" fontWeight="bold" color="textSecondary">
                          {block.repeats > 1 ? `🔁 CIRCUITO (${block.repeats} Vueltas)` : 'BLOQUE'}
                      </Typography>
                  </Box>
                  <CardContent sx={{ p: 0 }}>
                      {block.steps?.map((step, sIndex) => {
                          const isChecked = completedSteps[`${block.id}-${step.id}`];
                          return (
                              <Box key={sIndex} sx={{ p: 2, borderBottom: '1px solid #F1F5F9', bgcolor: isChecked ? '#F0FDF4' : 'white' }}>
                                  <Box sx={{ display: 'flex', gap: 2 }}>
                                      <Checkbox 
                                          checked={!!isChecked} 
                                          onChange={() => toggleStep(block.id, step.id)} 
                                          disabled={!canComplete} // 🔒 Solo habilitado si se puede completar hoy
                                          sx={{ '& .MuiSvgIcon-root': { fontSize: 28 }, p: 0, mt: 0.5 }} 
                                      />
                                      <Box sx={{ flex: 1 }}>
                                          <Typography variant="body1" fontWeight="bold" sx={{ textDecoration: isChecked ? 'line-through' : 'none', color: isChecked ? '#94A3B8' : '#1E293B' }}>
                                              {step.exercise || 'Ejercicio'}
                                          </Typography>
                                          
                                          <Stack direction="row" spacing={1} sx={{ mt: 0.5, mb: 1 }}>
                                              <Chip label={`${step.duration_value || 0} ${step.duration_unit}`} size="small" sx={{ fontWeight: 'bold' }} />
                                              {step.notes && <Chip label="📝 Nota" size="small" variant="outlined" />}
                                          </Stack>

                                          {step.notes && (
                                              <Typography variant="caption" sx={{ display: 'block', bgcolor: '#FFFBEB', p: 1, borderRadius: 1, color: '#B45309' }}>
                                                  💡 {step.notes}
                                              </Typography>
                                          )}

                                          {step.video_url && (
                                              <Box sx={{ mt: 1, borderRadius: 2, overflow: 'hidden', bgcolor: 'black' }}>
                                                  <CardMedia component="video" src={step.video_url} controls muted sx={{ width: '100%', maxHeight: 200 }} />
                                              </Box>
                                          )}
                                      </Box>
                                  </Box>
                              </Box>
                          );
                      })}
                  </CardContent>
              </Card>
          ))}
      </Stack>
  );

  const renderEnduranceView = () => (
      <Stack spacing={2}>
          {structure.bloques?.map((block, bIndex) => (
              <Card key={bIndex} sx={{ borderLeft: '4px solid', borderColor: block.type === 'WARMUP' ? '#84CC16' : '#F59E0B' }}>
                  <CardContent>
                      <Typography variant="overline" color="textSecondary" fontWeight="bold">
                          {block.repeats > 1 ? `${block.repeats}x REPETICIONES` : block.type}
                      </Typography>
                      {block.steps?.map((step, sIndex) => {
                          const zone = INTENSITY_ZONES[step.intensity] || INTENSITY_ZONES[1];
                          return (
                              <Box key={sIndex} sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
                                  <Box sx={{ width: 8, height: 40, borderRadius: 4, bgcolor: zone.color }} />
                                  <Box>
                                      <Typography variant="h6" fontWeight="bold">
                                          {step.duration_value} {step.duration_unit}
                                      </Typography>
                                      <Typography variant="body2" sx={{ color: zone.color, fontWeight: 'bold' }}>
                                          @ {zone.label}
                                      </Typography>
                                      {step.description && <Typography variant="caption" color="textSecondary">{step.description}</Typography>}
                                  </Box>
                              </Box>
                          );
                      })}
                  </CardContent>
              </Card>
          ))}
      </Stack>
  );

  const renderFeedbackView = () => (
      <Box sx={{ p: 2, textAlign: 'center' }}>
          <Typography variant="h5" fontWeight="bold" gutterBottom>¡Entrenamiento Terminado! 🎉</Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 4 }}>¿Qué tan duro fue?</Typography>
          <Box sx={{ mb: 4, px: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>{renderRPEIcon(rpe)}</Box>
              <Typography variant="h4" fontWeight="bold" color="primary" gutterBottom>{rpe} / 10</Typography>
              <Slider value={rpe} onChange={(_, val) => setRpe(val)} step={1} marks={RPE_MARKS} min={1} max={10} valueLabelDisplay="auto" />
          </Box>
          <TextField fullWidth multiline rows={3} label="Comentarios" value={comments} onChange={(e) => setComments(e.target.value)} variant="outlined" sx={{ mb: 3 }} />
          <Button fullWidth variant="contained" size="large" onClick={handleSaveFeedback} disabled={loading} sx={{ py: 1.5, borderRadius: 2 }}>{loading ? 'Guardando...' : 'Guardar y Cerrar'}</Button>
      </Box>
  );

  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} fullWidth maxWidth="sm">
      {/* HEADER */}
      {mode === 'VIEW' && (
          <DialogTitle sx={{ borderBottom: '1px solid #E2E8F0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box>
                  <Typography variant="h6" fontWeight="bold">{training.titulo}</Typography>
                  <Stack direction="row" spacing={1} alignItems="center">
                      <Chip label={isStrength ? "Gimnasio" : "Running"} size="small" color="primary" variant="outlined" />
                      {isCompleted && <Chip icon={<CheckCircle sx={{fontSize: 14}}/>} label="Completado" size="small" color="success" />}
                      {isFutureTraining && <Chip icon={<LockClock sx={{fontSize: 14}}/>} label="Programado" size="small" sx={{bgcolor: '#F1F5F9', color: '#64748B'}} />}
                  </Stack>
              </Box>
              <IconButton onClick={onClose}><Close /></IconButton>
          </DialogTitle>
      )}

      {/* CONTENIDO */}
      <DialogContent sx={{ p: mode === 'FEEDBACK' ? 0 : 2, bgcolor: '#F8FAFC' }}>
          
          {/* AVISOS DE ESTADO (User Experience) */}
          {mode === 'VIEW' && isFutureTraining && (
              <Alert severity="info" icon={<LockClock />} sx={{ mb: 2, borderRadius: 2 }}>
                  Entrenamiento programado. Puedes ver los detalles, pero aún no puedes completarlo.
              </Alert>
          )}
          {mode === 'VIEW' && isCompleted && (
              <Alert severity="success" icon={<EventAvailable />} sx={{ mb: 2, borderRadius: 2 }}>
                  ¡Ya realizaste esta actividad! RPE: {training.rpe}/10
              </Alert>
          )}

          {/* RENDERIZADO CONDICIONAL: Si no hay bloques, muestra estado vacío */}
          {mode === 'VIEW' ? (
              !hasBlocks ? renderEmptyState() : (isStrength ? renderStrengthView() : renderEnduranceView())
          ) : (
              renderFeedbackView()
          )}
      </DialogContent>

      {/* FOOTER */}
      {mode === 'VIEW' && (
          <DialogActions sx={{ p: 2, bgcolor: 'white', borderTop: '1px solid #E2E8F0' }}>
              <Button onClick={onClose} color="inherit" sx={{ mr: 'auto' }}>Cerrar</Button>
              
              {canComplete && (
                  <Button variant="contained" color="success" size="large" startIcon={<CheckCircle />} onClick={() => setMode('FEEDBACK')} sx={{ px: 4, fontWeight: 'bold' }}>
                      Finalizar Actividad
                  </Button>
              )}
          </DialogActions>
      )}
    </Dialog>
  );
};

export default TrainingDetailModal;