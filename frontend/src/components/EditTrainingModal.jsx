import React, { useState, useEffect, useRef } from 'react';
import { 
  Dialog, DialogTitle, DialogContent, DialogActions, 
  TextField, Button, MenuItem, Box, Typography, 
  IconButton, InputAdornment, Paper, Stack, Chip, Grid, Tooltip, CardMedia
} from '@mui/material';
import { 
  Close, Delete, Save, DirectionsRun, PedalBike, FitnessCenter, Pool,
  AddCircleOutline, DragIndicator, RemoveCircleOutline,
  BarChart, Repeat, Calculate, Add, VideoCameraBack, Terrain, Timer,
  Edit, DeleteForever
} from '@mui/icons-material';
import client from '../api/client';

// --- CONFIGURACIÓN MAESTRA ---
const ACTIVITY_TYPES = [
  { value: 'RUN', label: 'Running', icon: <DirectionsRun fontSize="small" />, color: '#F59E0B', mode: 'ENDURANCE' },
  { value: 'TRAIL', label: 'Trail Running', icon: <Terrain fontSize="small" />, color: '#D97706', mode: 'ENDURANCE' },
  { value: 'BIKE', label: 'Ciclismo', icon: <PedalBike fontSize="small" />, color: '#3B82F6', mode: 'ENDURANCE' },
  { value: 'SWIM', label: 'Natación', icon: <Pool fontSize="small" />, color: '#0EA5E9', mode: 'ENDURANCE' },
  { value: 'STRENGTH', label: 'Fuerza / Gym', icon: <FitnessCenter fontSize="small" />, color: '#EF4444', mode: 'STRENGTH' },
];

const ACTIVITY_SUBTYPES = {
    'RUN': [{ value: 'EASY', label: 'Rodaje Suave' }, { value: 'INTERVALS', label: 'Series' }, { value: 'LONG', label: 'Fondo' }, { value: 'TEMPO', label: 'Tempo' }],
    'TRAIL': [{ value: 'ROLLING', label: 'Ondulado' }, { value: 'TECHNICAL', label: 'Técnico' }, { value: 'SHORT_HILL', label: 'Cuesta Corta' }, { value: 'LONG_HILL', label: 'Cuesta Larga' }, { value: 'VERT', label: 'Km Vertical' }],
    'BIKE': [{ value: 'ROAD', label: 'Ruta' }, { value: 'MTB', label: 'MTB' }, { value: 'INDOOR', label: 'Rodillo' }],
    'SWIM': [{ value: 'POOL', label: 'Piscina' }, { value: 'OPEN', label: 'Aguas Abiertas' }],
    'STRENGTH': [
        { value: 'GYM', label: 'Musculación Tradicional' },
        { value: 'FUNCTIONAL', label: 'Funcional / HIIT' },
        { value: 'CORE', label: 'Zona Media / Core' },
        { value: 'PROPRIOCEPTION', label: 'Propiocepción' },
        { value: 'POWER', label: 'Potencia / Pliometría' }
    ]
};

const TERRAIN_TYPES = [ { value: 'FLAT', label: 'Plano' }, { value: 'HILLY', label: 'Ondulado' }, { value: 'MOUNTAIN', label: 'Montaña' } ];

const BLOCK_TYPES_ENDURANCE = [
    { value: 'WARMUP', label: 'Calentamiento', color: '#84CC16', bg: '#ECFCCB' },
    { value: 'MAIN', label: 'Trabajo Principal', color: '#F59E0B', bg: '#FFFBEB' },
    { value: 'COOLDOWN', label: 'Vuelta a la calma', color: '#3B82F6', bg: '#EFF6FF' },
    { value: 'REST', label: 'Pausa', color: '#94A3B8', bg: '#F1F5F9' },
];

const BLOCK_TYPES_STRENGTH = [
    { value: 'WARMUP', label: 'Movilidad / Activación', color: '#84CC16', bg: '#ECFCCB' },
    { value: 'CIRCUIT', label: 'Circuito / Bloque', color: '#EF4444', bg: '#FEE2E2' },
    { value: 'CORE', label: 'Core / Abdominales', color: '#F59E0B', bg: '#FFFBEB' },
];

const INTENSITY_ZONES = [
    { value: 1, label: 'Z1 (Recup)', height: '20%', color: '#A3E635', factor: 0.60 },
    { value: 2, label: 'Z2 (Suave)', height: '40%', color: '#84CC16', factor: 0.70 },
    { value: 3, label: 'Z3 (Tempo)', height: '60%', color: '#FACC15', factor: 0.85 },
    { value: 4, label: 'Z4 (Umbral)', height: '80%', color: '#F97316', factor: 0.95 },
    { value: 5, label: 'Z5 (VO2Max)', height: '100%', color: '#EF4444', factor: 1.10 },
];

const BASE_SPEEDS = { 'RUN': 11.0, 'TRAIL': 9.0, 'BIKE': 28.0, 'SWIM': 3.5, 'STRENGTH': 0 };

const EditTrainingModal = ({ open, onClose, training, onUpdated }) => {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    titulo: '', tipo_actividad: 'RUN', subtipo_actividad: '', terreno: 'FLAT',
    distancia_planificada_km: '', tiempo_planificado_min: '', notas_entrenador: ''
  });
  const [blocks, setBlocks] = useState([]);
  
  const fileInputRefs = useRef({});

  const currentSportConfig = ACTIVITY_TYPES.find(t => t.value === formData.tipo_actividad) || ACTIVITY_TYPES[0];
  const isStrengthMode = currentSportConfig.mode === 'STRENGTH';

  useEffect(() => {
    if (training) {
        const sport = training.tipo_actividad || 'RUN';
        const defaultSubtype = training.estructura?.config?.workout_type || ACTIVITY_SUBTYPES[sport]?.[0]?.value || '';
        
        setFormData({
            titulo: training.titulo || '',
            tipo_actividad: sport,
            subtipo_actividad: defaultSubtype,
            terreno: training.estructura?.config?.terrain || 'FLAT',
            distancia_planificada_km: training.distancia_planificada_km !== null ? training.distancia_planificada_km : '',
            tiempo_planificado_min: training.tiempo_planificado_min !== null ? training.tiempo_planificado_min : '',
            notas_entrenador: ''
        });

        if (training.estructura && Array.isArray(training.estructura.bloques)) {
            setBlocks(training.estructura.bloques);
        } else {
            setBlocks([]);
        }
        
        if (training.descripcion_detallada && training.descripcion_detallada.includes('--- NOTAS')) {
             const parts = training.descripcion_detallada.split('--- NOTAS DEL COACH ---');
             if(parts[1]) setFormData(prev => ({...prev, notas_entrenador: parts[1].trim()}));
        }
    }
  }, [training]);

  const handleSportChange = (e) => {
      const newSport = e.target.value;
      const newConfig = ACTIVITY_TYPES.find(t => t.value === newSport);
      
      setFormData({ 
          ...formData, 
          tipo_actividad: newSport, 
          subtipo_actividad: ACTIVITY_SUBTYPES[newSport]?.[0]?.value || '' 
      });

      if (newConfig?.mode !== currentSportConfig.mode) setBlocks([]);
  };

  const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  // --- MANEJADORES ---
  const handleAddBlock = () => {
      if (isStrengthMode) {
          setBlocks([...blocks, { 
              id: Date.now(), type: 'CIRCUIT', repeats: 1, 
              steps: [{ id: Date.now()+1, exercise: '', duration_value: '10', duration_unit: 'reps', notes: '', video_preview: null }] 
          }]);
      } else {
          setBlocks([...blocks, { id: Date.now(), type: 'MAIN', repeats: 1, steps: [{ id: Date.now()+1, duration_value: '', duration_unit: 'min', intensity: 3, description: '' }] }]);
      }
  };
  const handleRemoveBlock = (id) => setBlocks(blocks.filter(b => b.id !== id));
  const handleBlockChange = (id, field, value) => setBlocks(blocks.map(b => b.id === id ? { ...b, [field]: value } : b));

  const handleAddStep = (blockId) => {
      if (isStrengthMode) {
          setBlocks(blocks.map(b => b.id === blockId ? { ...b, steps: [...b.steps, { id: Date.now(), exercise: '', duration_value: '', duration_unit: 'reps', notes: '', video_preview: null }] } : b));
      } else {
          setBlocks(blocks.map(b => b.id === blockId ? { ...b, steps: [...b.steps, { id: Date.now(), duration_value: '', duration_unit: 'min', intensity: 3, description: '' }] } : b));
      }
  };
  const handleRemoveStep = (blockId, stepId) => setBlocks(blocks.map(b => b.id === blockId && b.steps.length > 1 ? { ...b, steps: b.steps.filter(s => s.id !== stepId) } : b));
  const handleStepChange = (blockId, stepId, field, value) => setBlocks(blocks.map(b => b.id === blockId ? { ...b, steps: b.steps.map(s => s.id === stepId ? { ...s, [field]: value } : s) } : b));

  const handleVideoUpload = async (blockId, stepId, file) => {
      if (!file) return;
      const tempUrl = URL.createObjectURL(file);
      handleStepChange(blockId, stepId, 'video_preview', tempUrl);
      
      const formPayload = new FormData();
      formPayload.append('archivo', file);
      formPayload.append('titulo', `Upload-${Date.now()}`);

      try {
          const res = await client.post('/api/upload-video/', formPayload, { headers: { 'Content-Type': 'multipart/form-data' } });
          handleStepChange(blockId, stepId, 'video_url', res.data.url);
      } catch (err) {
          console.error(err);
          alert("Error al subir video.");
      }
  };

  const handleRemoveVideo = (blockId, stepId) => {
      setBlocks(blocks.map(b => b.id === blockId ? { 
          ...b, 
          steps: b.steps.map(s => s.id === stepId ? { ...s, video_preview: null, video_url: null } : s) 
      } : b));
  };

  // --- 🧠 CÁLCULOS MATEMÁTICOS CIENTÍFICOS (LOGICA DE NEGOCIO ACTUALIZADA) ---
  useEffect(() => {
      // 1. LÓGICA DE FUERZA (ALGORITMO PERSONALIZADO)
      if (isStrengthMode) {
          // Subtipos que SÍ llevan transición de 30s (cambio de máquina)
          const SUBTYPES_WITH_TRANSITION = ['GYM', 'PROPRIOCEPTION', 'POWER'];
          const applyTransition = SUBTYPES_WITH_TRANSITION.includes(formData.subtipo_actividad);

          let totalGymMin = 0;
          blocks.forEach(block => {
              const vueltas = parseInt(block.repeats) || 1;
              let tiempoBloque = 0;
              
              block.steps?.forEach(step => {
                  const val = parseFloat(step.duration_value) || 0;
                  
                  // Tiempo de Ejecución (Time Under Tension)
                  if (step.duration_unit === 'reps') {
                      tiempoBloque += (val * 4 / 60); // 4 seg por rep
                  } else if (step.duration_unit === 'min') {
                      tiempoBloque += val; 
                  } else if (step.duration_unit === 'sec') {
                      tiempoBloque += (val / 60);
                  }
                  
                  // Tiempo de Transición / Pausa Intra-ejercicio
                  if (applyTransition) {
                      tiempoBloque += 0.5; // +30 seg si aplica la regla
                  }
              });
              
              totalGymMin += (tiempoBloque * vueltas);
          });
          
          setFormData(prev => ({
              ...prev,
              tiempo_planificado_min: Math.ceil(totalGymMin)
          }));
          return;
      }

      // 2. LÓGICA ENDURANCE (VAM / ZONAS)
      let totalTimeMin = 0; 
      let totalDistKm = 0;
      const baseSpeedKmh = BASE_SPEEDS[formData.tipo_actividad] || 12.0;

      blocks.forEach(block => {
          const reps = parseInt(block.repeats) || 1;
          block.steps?.forEach(step => {
              const val = parseFloat(step.duration_value) || 0;
              const unit = step.duration_unit;
              const intensityFactor = INTENSITY_ZONES.find(z => z.value === step.intensity)?.factor || 0.70;
              const speedKmh = baseSpeedKmh * intensityFactor;

              let stepTime = 0; 
              let stepDist = 0;

              if (val > 0) {
                  if (unit === 'min') {
                      stepTime = val;
                      stepDist = (val / 60) * speedKmh; 
                  } else if (unit === 'km') {
                      stepDist = val;
                      stepTime = (val / speedKmh) * 60; 
                  } else if (unit === 'm') {
                      stepDist = val / 1000;
                      stepTime = (stepDist / speedKmh) * 60;
                  }
              }
              totalTimeMin += stepTime * reps; 
              totalDistKm += stepDist * reps;
          });
      });

      setFormData(prev => ({
          ...prev,
          distancia_planificada_km: totalDistKm > 0 ? totalDistKm.toFixed(2) : '',
          tiempo_planificado_min: totalTimeMin > 0 ? Math.round(totalTimeMin) : ''
      }));
  }, [blocks, isStrengthMode, formData.tipo_actividad, formData.subtipo_actividad]);

  const getPaceLabel = (intensityVal) => {
    if (formData.tipo_actividad === 'STRENGTH') return '';
    const zone = INTENSITY_ZONES.find(z => z.value === intensityVal);
    if (!zone) return "-";
    const baseSpeed = BASE_SPEEDS[formData.tipo_actividad] || 12.0;
    const targetSpeed = baseSpeed * zone.factor;
    if (formData.tipo_actividad === 'BIKE') return `${Math.round(targetSpeed)} km/h`;
    if (formData.tipo_actividad === 'SWIM') {
        const speedMmin = targetSpeed * 1000 / 60;
        const pace100 = 100 / speedMmin; const min = Math.floor(pace100); const sec = Math.round((pace100 - min) * 60);
        return `${min}:${sec < 10 ? '0' : ''}${sec}/100m`;
    }
    const paceDec = 60 / targetSpeed; const min = Math.floor(paceDec); const sec = Math.round((paceDec - min) * 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}/km`;
  };

  const renderGraph = () => {
      if (blocks.length === 0 || isStrengthMode) return null;
      return (
          <Box sx={{ mt: 3, p: 2, bgcolor: 'white', borderRadius: 2, border: '1px solid #E2E8F0' }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-end', height: 80, gap: 0.5, width: '100%', overflowX: 'auto', pb: 1 }}>
                  {blocks.flatMap((block) => {
                      const reps = parseInt(block.repeats) || 1;
                      return Array(reps).fill(0).flatMap((_, repIdx) => block.steps?.map((step) => {
                              const intensity = INTENSITY_ZONES.find(z => z.value === step.intensity) || INTENSITY_ZONES[2];
                              let widthFlex = step.duration_value ? (step.duration_unit === 'km' ? parseFloat(step.duration_value) * 5 : parseFloat(step.duration_value)) : 1;
                              return (<Tooltip key={`${block.id}-${repIdx}-${step.id}`} title={`Z${step.intensity}`}><Box sx={{ height: intensity.height, bgcolor: intensity.color, flex: widthFlex, minWidth: 8, borderRadius: '2px 2px 0 0', opacity: 0.9, borderRight: '1px solid white' }} /></Tooltip>);
                          })
                      );
                  })}
              </Box>
          </Box>
      );
  };

  const renderStrengthBuilder = () => (
      <Stack spacing={2} sx={{ mt: 3 }}>
          {blocks.length === 0 && (
              <Box sx={{ p: 4, textAlign: 'center', border: '2px dashed #E2E8F0', borderRadius: 2, color: '#94A3B8' }}>
                  <FitnessCenter sx={{ fontSize: 40, mb: 1, opacity: 0.5 }} />
                  <Typography variant="body2">Crea tu primer circuito o bloque de ejercicios.</Typography>
              </Box>
          )}

          {blocks.map((block) => {
              const blockType = BLOCK_TYPES_STRENGTH.find(t => t.value === block.type) || BLOCK_TYPES_STRENGTH[1];
              return (
              <Paper key={block.id} elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2, overflow: 'hidden' }}>
                  <Box sx={{ bgcolor: blockType.bg, p: 1.5, display: 'flex', gap: 2, alignItems: 'center', borderBottom: '1px solid #E2E8F0' }}>
                      <DragIndicator sx={{ color: blockType.color, fontSize: 18, opacity: 0.5 }} />
                      <TextField select variant="standard" value={block.type} onChange={(e) => handleBlockChange(block.id, 'type', e.target.value)} InputProps={{ disableUnderline: true, sx: { fontWeight: 800, fontSize: '0.9rem', color: blockType.color } }}>{BLOCK_TYPES_STRENGTH.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}</TextField>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, bgcolor: 'white', px: 1.5, py: 0.5, borderRadius: 4, border: '1px solid #E2E8F0' }}><Repeat sx={{ fontSize: 16, color: '#64748B' }} /><TextField variant="standard" type="number" value={block.repeats || 1} onChange={(e) => handleBlockChange(block.id, 'repeats', e.target.value)} InputProps={{ disableUnderline: true, sx: { fontSize: '0.8rem', width: 25, textAlign: 'center', fontWeight: 'bold' } }} /><Typography variant="caption" color="textSecondary" fontWeight="bold">Vueltas</Typography></Box>
                      <Box sx={{ flexGrow: 1 }} />
                      <IconButton size="small" onClick={() => handleRemoveBlock(block.id)} sx={{ color: '#94A3B8' }}><RemoveCircleOutline /></IconButton>
                  </Box>
                  
                  <Box sx={{ p: 2 }}>
                      <Stack spacing={2}>
                          {block.steps?.map((step, index) => (
                              <Grid container spacing={1} key={step.id} alignItems="flex-start" sx={{ pb: 1, borderBottom: '1px dashed #F1F5F9' }}>
                                  <Grid item xs={1}><Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>#{index+1}</Typography></Grid>
                                  
                                  <Grid item xs={5}>
                                      <TextField fullWidth size="small" placeholder="Ejercicio (ej: Burpees)" value={step.exercise} onChange={(e) => handleStepChange(block.id, step.id, 'exercise', e.target.value)} />
                                      <TextField fullWidth multiline rows={2} variant="filled" placeholder="Técnica..." value={step.notes} onChange={(e) => handleStepChange(block.id, step.id, 'notes', e.target.value)} InputProps={{ disableUnderline: true, sx: { fontSize: '0.75rem', bgcolor: '#F8FAFC', mt: 0.5, borderRadius: 1 } }} />
                                  </Grid>
                                  
                                  <Grid item xs={2}>
                                      <TextField size="small" type="number" placeholder="0" value={step.duration_value} onChange={(e) => handleStepChange(block.id, step.id, 'duration_value', e.target.value)} />
                                  </Grid>
                                  <Grid item xs={2}>
                                       <TextField select size="small" value={step.duration_unit} onChange={(e) => handleStepChange(block.id, step.id, 'duration_unit', e.target.value)} fullWidth><MenuItem value="reps">Reps</MenuItem><MenuItem value="min">Min</MenuItem><MenuItem value="sec">Seg</MenuItem></TextField>
                                  </Grid>
                                  
                                  <Grid item xs={2} sx={{ textAlign: 'right', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 1 }}>
                                      <input type="file" accept="video/*" style={{ display: 'none' }} ref={el => fileInputRefs.current[`${block.id}-${step.id}`] = el} onChange={(e) => handleVideoUpload(block.id, step.id, e.target.files[0])} />
                                      
                                      {(step.video_preview || step.video_url) ? (
                                          <Box sx={{ position: 'relative', width: 100, height: 60, borderRadius: 1, overflow: 'hidden', bgcolor: 'black', border: '1px solid #E2E8F0' }}>
                                              <CardMedia component="video" src={step.video_preview || step.video_url} controls sx={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                              <Tooltip title="Cambiar Video">
                                                  <IconButton size="small" onClick={() => fileInputRefs.current[`${block.id}-${step.id}`]?.click()} sx={{ position: 'absolute', top: 2, right: 2, bgcolor: 'rgba(255,255,255,0.8)', padding: 0.5, '&:hover': { bgcolor: 'white' }, zIndex: 10 }}><Edit sx={{ fontSize: 12, color: '#334155' }} /></IconButton>
                                              </Tooltip>
                                              <Tooltip title="Eliminar Video">
                                                  <IconButton size="small" onClick={() => handleRemoveVideo(block.id, step.id)} sx={{ position: 'absolute', bottom: 2, right: 2, bgcolor: 'rgba(239,68,68,0.9)', padding: 0.5, '&:hover': { bgcolor: '#DC2626' }, zIndex: 10 }}><DeleteForever sx={{ fontSize: 12, color: 'white' }} /></IconButton>
                                              </Tooltip>
                                          </Box>
                                      ) : (
                                          <Button size="small" startIcon={<VideoCameraBack />} variant="outlined" color="inherit" onClick={() => fileInputRefs.current[`${block.id}-${step.id}`]?.click()} sx={{ fontSize: '0.65rem', borderColor: '#CBD5E1', color: '#64748B', textTransform: 'none' }}>Subir</Button>
                                      )}
                                      
                                      <IconButton size="small" onClick={() => handleRemoveStep(block.id, step.id)} sx={{ color: '#EF4444' }}><RemoveCircleOutline fontSize="small" /></IconButton>
                                  </Grid>
                              </Grid>
                          ))}
                      </Stack>
                      <Button startIcon={<Add />} size="small" onClick={() => handleAddStep(block.id)} sx={{ mt: 2, textTransform: 'none' }}>Agregar Ejercicio</Button>
                  </Box>
              </Paper>
          )})}
      </Stack>
  );

  const renderEnduranceBuilder = () => (
      <Stack spacing={3} sx={{ mt: 3 }}>
          {blocks.map((block) => {
              const blockType = BLOCK_TYPES_ENDURANCE.find(t => t.value === block.type) || BLOCK_TYPES_ENDURANCE[1];
              return (
                  <Paper key={block.id} elevation={0} sx={{ overflow: 'hidden', border: `1px solid ${blockType.color}40` }}>
                      <Box sx={{ bgcolor: blockType.bg, p: 1, px: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                              <DragIndicator sx={{ color: blockType.color, fontSize: 18, opacity: 0.5 }} />
                              <TextField select variant="standard" value={block.type} onChange={(e) => handleBlockChange(block.id, 'type', e.target.value)} InputProps={{ disableUnderline: true, sx: { fontSize: '0.8rem', fontWeight: 800, color: blockType.color } }}>{BLOCK_TYPES_ENDURANCE.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}</TextField>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, bgcolor: 'white', px: 1, borderRadius: 1, border: '1px solid #E2E8F0' }}><Repeat sx={{ fontSize: 16, color: '#64748B' }} /><TextField variant="standard" type="number" value={block.repeats || 1} onChange={(e) => handleBlockChange(block.id, 'repeats', e.target.value)} InputProps={{ disableUnderline: true, sx: { fontSize: '0.8rem', width: 30, textAlign: 'center' } }} /></Box>
                          </Box>
                          <IconButton size="small" onClick={() => handleRemoveBlock(block.id)}><RemoveCircleOutline fontSize="small" /></IconButton>
                      </Box>
                      <Box sx={{ p: 2 }}>
                          <Stack spacing={1.5}>
                              {block.steps?.map((step, index) => (
                                  <Box key={step.id} sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                                      <Box sx={{ display: 'flex', width: 150, gap: 0.5 }}>
                                          <TextField size="small" type="number" value={step.duration_value} onChange={(e) => handleStepChange(block.id, step.id, 'duration_value', e.target.value)} placeholder="0" sx={{ flex: 1 }} />
                                          <TextField select size="small" value={step.duration_unit} onChange={(e) => handleStepChange(block.id, step.id, 'duration_unit', e.target.value)} sx={{ width: 70 }}><MenuItem value="min">min</MenuItem><MenuItem value="km">km</MenuItem><MenuItem value="m">mts</MenuItem></TextField>
                                      </Box>
                                      <TextField select size="small" value={step.intensity || 3} onChange={(e) => handleStepChange(block.id, step.id, 'intensity', e.target.value)} sx={{ width: 140 }}>{INTENSITY_ZONES.map(z => <MenuItem key={z.value} value={z.value}><Box sx={{width:10,height:10,bgcolor:z.color,borderRadius:'50%',mr:1}}/>{z.label}</MenuItem>)}</TextField>
                                      <Box sx={{ flex: 1 }}>
                                          <TextField fullWidth size="small" placeholder="Descripción" value={step.description} onChange={(e) => handleStepChange(block.id, step.id, 'description', e.target.value)} />
                                          <Typography variant="caption" sx={{ color: '#059669', fontWeight: 600, display: 'block', mt: 0.5, fontSize: '0.65rem' }}>⚡ {getPaceLabel(step.intensity)}</Typography>
                                      </Box>
                                      <IconButton size="small" onClick={() => handleRemoveStep(block.id, step.id)} disabled={block.steps.length === 1}><RemoveCircleOutline fontSize="small" /></IconButton>
                                  </Box>
                              ))}
                          </Stack>
                          <Button size="small" onClick={() => handleAddStep(block.id)} sx={{ mt: 1 }}>+ Paso</Button>
                      </Box>
                  </Paper>
              )
          })}
      </Stack>
  );

  const handleSave = async () => {
    try {
      setLoading(true);
      const estructuraJSON = { 
          version: isStrengthMode ? "STRENGTH_3.0_LOOPS" : "ENDURANCE_3.0", 
          config: { workout_type: formData.subtipo_actividad, terrain: formData.terreno }, 
          bloques: blocks 
      };
      
      let desc = '';
      if (isStrengthMode) {
          desc = blocks.map(b => {
              const reps = b.repeats > 1 ? `${b.repeats} Vueltas de:` : 'Bloque:';
              const exercises = b.steps.map(s => ` - ${s.exercise} (${s.duration_value} ${s.duration_unit})`).join('\n');
              return `${reps}\n${exercises}`;
          }).join('\n\n');
      } else {
          desc = blocks.map(b => {
              const typeLabel = BLOCK_TYPES_ENDURANCE.find(t => t.value === b.type)?.label || 'Bloque';
              const reps = parseInt(b.repeats) || 1;
              let prefix = reps > 1 ? `[${typeLabel}] x${reps}:` : `[${typeLabel}]:`;
              const stepsText = b.steps?.map(s => ` • ${s.duration_value || '?'}${s.duration_unit || ''} @ Z${s.intensity} ${s.description ? `(${s.description})` : ''}`).join('\n') || '';
              return `${prefix}\n${stepsText}`;
          }).join('\n\n');
      }
      if (formData.notas_entrenador) desc += `\n\n--- NOTAS ---\n${formData.notas_entrenador}`;

      const payload = {
          ...formData,
          distancia_planificada_km: isStrengthMode ? null : (formData.distancia_planificada_km === '' ? null : parseFloat(formData.distancia_planificada_km)),
          tiempo_planificado_min: formData.tiempo_planificado_min === '' ? null : parseInt(formData.tiempo_planificado_min),
          estructura: estructuraJSON,
          descripcion_detallada: desc
      };
      
      await client.patch(`/api/entrenamientos/${training.id}/`, payload);
      onUpdated(); onClose();
    } catch (err) { alert("Error al guardar."); } finally { setLoading(false); }
  };

  if (!training) return null;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle sx={{ borderBottom: '1px solid #E2E8F0', bgcolor: '#F8FAFC', display: 'flex', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6" fontWeight={800} sx={{ color: '#1E293B' }}>{isStrengthMode ? 'Editor Fuerza' : 'Planificador Endurance'}</Typography>
            {isStrengthMode && <Chip label="Gym Pro" size="small" color="error" variant="outlined" sx={{height:20, fontSize:'0.6rem'}}/>}
        </Box>
        <IconButton onClick={onClose} size="small"><Close /></IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: 0, bgcolor: '#F1F5F9', display: 'flex', height: '80vh' }}>
          <Box sx={{ width: '30%', p: 3, bgcolor: 'white', borderRight: '1px solid #E2E8F0', overflowY: 'auto' }}>
              <Stack spacing={3}>
                  <TextField fullWidth size="small" label="Título" name="titulo" value={formData.titulo} onChange={handleChange} />
                  <TextField select fullWidth size="small" label="Deporte" name="tipo_actividad" value={formData.tipo_actividad} onChange={handleSportChange}>
                      {ACTIVITY_TYPES.map(t => <MenuItem key={t.value} value={t.value}><Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: t.color }}>{t.icon} {t.label}</Box></MenuItem>)}
                  </TextField>
                  <TextField select fullWidth size="small" label="Tipo Específico" name="subtipo_actividad" value={formData.subtipo_actividad} onChange={handleChange}>
                      {ACTIVITY_SUBTYPES[formData.tipo_actividad]?.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
                  </TextField>
                  {!isStrengthMode && <TextField select fullWidth size="small" label="Terreno" name="terreno" value={formData.terreno} onChange={handleChange}>{TERRAIN_TYPES.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}</TextField>}
                  {!isStrengthMode ? (
                      <Box sx={{ p: 2, bgcolor: '#F0F9FF', borderRadius: 2, border: '1px solid #BAE6FD' }}>
                        <Typography variant="caption" fontWeight={800} color="primary" sx={{ mb: 1, display: 'block' }}>TOTALES ENDURANCE</Typography>
                        <Box sx={{ display: 'flex', gap: 1 }}>
                            <TextField fullWidth size="small" label="Km" value={formData.distancia_planificada_km} InputProps={{ readOnly: true }} sx={{ bgcolor: 'white' }} />
                            <TextField fullWidth size="small" label="Min" value={formData.tiempo_planificado_min} InputProps={{ readOnly: true }} sx={{ bgcolor: 'white' }} />
                        </Box>
                      </Box>
                  ) : (
                      <Box sx={{ p: 2, bgcolor: '#FEF2F2', borderRadius: 2, border: '1px solid #FECACA' }}>
                          <Typography variant="caption" fontWeight={800} color="error" sx={{ mb: 1, display: 'block' }}>ESTIMACIÓN CARGA</Typography>
                          <TextField fullWidth size="small" label="Tiempo Total (min)" type="number" name="tiempo_planificado_min" value={formData.tiempo_planificado_min} onChange={handleChange} sx={{ bgcolor: 'white' }} />
                      </Box>
                  )}
                  <TextField fullWidth multiline rows={4} label="Notas Privadas" name="notas_entrenador" value={formData.notas_entrenador} onChange={handleChange} sx={{ bgcolor: '#FFFBEB' }} />
              </Stack>
          </Box>

          <Box sx={{ width: '70%', p: 3, overflowY: 'auto' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                  <Typography variant="subtitle1" fontWeight={800}>Rutina</Typography>
                  <Button startIcon={<AddCircleOutline />} onClick={handleAddBlock} variant="contained" sx={{ bgcolor: isStrengthMode ? '#EF4444' : '#0F172A', textTransform: 'none' }}>{isStrengthMode ? "Nuevo Circuito" : "Nuevo Bloque"}</Button>
              </Box>
              {renderGraph()}
              {isStrengthMode ? renderStrengthBuilder() : renderEnduranceBuilder()}
          </Box>
      </DialogContent>

      <DialogActions sx={{ p: 2, bgcolor: 'white', borderTop: '1px solid #E2E8F0' }}>
          <Button onClick={onClose} color="inherit">Cancelar</Button>
          <Button onClick={handleSave} variant="contained" disabled={loading} sx={{ bgcolor: currentSportConfig.color, px: 4, fontWeight: 700 }}>Guardar</Button>
      </DialogActions>
    </Dialog>
  );
};

export default EditTrainingModal;