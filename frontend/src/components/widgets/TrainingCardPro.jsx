import React from 'react';
import { Card, CardContent, Box, Typography, Chip, Divider, Stack } from '@mui/material';
import {
  DirectionsRun,
  PedalBike,
  FitnessCenter,
  WatchLater,
  Straighten,
  FormatListBulleted,
  WbSunny,
  Bolt,
  AcUnit,
  PauseCircleOutline,
} from '@mui/icons-material';

const TrainingCardPro = ({ training, onClick }) => { 
  
  // 1. Colores de Cumplimiento
  const getComplianceColor = (percent) => {
      if (!percent) return { border: '#E2E8F0', bg: 'white' };
      if (percent <= 30) return { border: '#EF4444', bg: '#FEF2F2' }; 
      if (percent <= 60) return { border: '#F59E0B', bg: '#FFFBEB' }; 
      if (percent <= 90) return { border: '#84CC16', bg: '#ECFCCB' }; 
      return { border: '#15803D', bg: '#DCFCE7' }; 
  };

  // 2. Estilos de Deporte
  const getSportDetails = (type) => {
      const t = type ? type.toUpperCase() : 'RUN';
      if (t.includes('RUN') || t.includes('TRAIL')) return { color: '#F97316', icon: DirectionsRun, label: 'Running' };
      if (t.includes('BIKE') || t.includes('CICLISMO')) return { color: '#3B82F6', icon: PedalBike, label: 'Ciclismo' };
      if (t.includes('GYM') || t.includes('FUERZA')) return { color: '#EF4444', icon: FitnessCenter, label: 'Gym' };
      return { color: '#64748B', icon: FitnessCenter, label: 'Otro' };
  };

  const style = getSportDetails(training.tipo_actividad);
  const complianceStyle = getComplianceColor(training.porcentaje_cumplimiento);
  const SportIcon = style.icon;

  // --- 3. LÓGICA DE VISUALIZACIÓN DE ESTRUCTURA (JSON vs TEXTO) ---
  const BLOCK_STYLE = {
    WARMUP: { label: 'Calentamiento', color: '#84CC16', bg: '#ECFCCB', icon: WbSunny },
    MAIN: { label: 'Principal', color: '#F57C00', bg: '#FFF7ED', icon: Bolt },
    COOLDOWN: { label: 'Vuelta a la calma', color: '#3B82F6', bg: '#EFF6FF', icon: AcUnit },
    REST: { label: 'Pausa', color: '#94A3B8', bg: '#F1F5F9', icon: PauseCircleOutline },
  };

  const ZONE_COLOR = {
    1: '#A3E635',
    2: '#84CC16',
    3: '#FACC15',
    4: '#F97316',
    5: '#EF4444',
  };

  const summarizeStep = (s) => {
    if (!s || typeof s !== 'object') return null;
    const dv = s.duration_value ?? s.durationValue ?? s.duration ?? '';
    const du = s.duration_unit ?? s.durationUnit ?? '';
    const intensity = s.intensity ?? null;
    const parts = [];
    if (dv !== '' && du) parts.push(`${dv}${du}`);
    else if (dv !== '') parts.push(String(dv));
    if (intensity) parts.push(`Z${intensity}`);
    return parts.length ? parts.join(' · ') : (s.description || '').trim();
  };

  const summarizeBlock = (bloque) => {
    if (!bloque || typeof bloque !== 'object') return '';
    if (typeof bloque.content === 'string' && bloque.content.trim()) return bloque.content.trim();
    const steps = Array.isArray(bloque.steps) ? bloque.steps : [];
    const reps = parseInt(bloque.repeats || 1, 10) || 1;
    const stepSummaries = steps
      .map(summarizeStep)
      .filter(Boolean)
      .slice(0, 2);
    let base = stepSummaries.join(' | ');
    if (!base) base = 'Sin detalle';
    if (reps > 1) base = `x${reps} · ${base}`;
    return base;
  };

  const renderStructure = () => {
      // Opción A: Tenemos JSON estructurado (La nueva era)
      // Usamos ?. para evitar errores si 'estructura' es null
      if (training?.estructura?.bloques && training.estructura.bloques.length > 0) {
          return (
              <Stack spacing={0.75} sx={{ mt: 1 }}>
                  {training.estructura.bloques.slice(0, 3).map((bloque, index) => {
                      const type = (bloque?.type || 'MAIN').toUpperCase();
                      const cfg = BLOCK_STYLE[type] || { label: type, color: '#64748B', bg: '#F1F5F9', icon: FormatListBulleted };
                      const BlockIcon = cfg.icon;

                      // Color por intensidad (si hay)
                      const firstIntensity = Array.isArray(bloque?.steps) && bloque.steps[0]?.intensity ? bloque.steps[0].intensity : null;
                      const accent = (firstIntensity && ZONE_COLOR[firstIntensity]) ? ZONE_COLOR[firstIntensity] : cfg.color;

                      return (
                          <Box
                            key={index}
                            sx={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 1,
                              px: 1,
                              py: 0.75,
                              borderRadius: 1.5,
                              bgcolor: cfg.bg,
                              border: `1px solid ${accent}33`,
                            }}
                          >
                              <Box sx={{ width: 28, height: 28, borderRadius: 1.5, bgcolor: accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <BlockIcon sx={{ fontSize: 16, color: 'white' }} />
                              </Box>
                              <Box sx={{ minWidth: 0 }}>
                                <Typography variant="caption" sx={{ fontWeight: 900, color: '#0F172A', display: 'block', lineHeight: 1 }}>
                                  {cfg.label}
                                </Typography>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontSize: '0.72rem',
                                    color: '#475569',
                                    lineHeight: 1.2,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                    maxWidth: '100%',
                                  }}
                                >
                                  {summarizeBlock(bloque)}
                                </Typography>
                              </Box>
                          </Box>
                      );
                  })}
              </Stack>
          );
      }

      // Opción B: Texto plano (Legacy / Compatibilidad)
      const texto = training.descripcion_detallada || "Sin estructura definida.";
      return (
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
            <FormatListBulleted sx={{ fontSize: 12, color: '#94A3B8', mt: 0.3 }} />
            <Typography variant="body2" sx={{ fontSize: '0.7rem', color: '#475569', fontFamily: 'monospace', lineHeight: 1.3 }}>
                {texto.substring(0, 70)}{texto.length > 70 ? '...' : ''}
            </Typography>
        </Box>
      );
  };

  return (
    <Card 
        elevation={0}
        onClick={onClick} 
        sx={{ 
            border: '1px solid',
            borderColor: complianceStyle.border, 
            borderLeft: `5px solid ${style.color}`, 
            bgcolor: complianceStyle.bg,
            borderRadius: 2,
            cursor: 'pointer', 
            transition: 'all 0.2s ease-in-out',
            mb: 1,
            '&:hover': { transform: 'translateY(-2px)', boxShadow: '0 8px 16px -4px rgba(0, 0, 0, 0.1)', borderColor: style.color }
        }}
    >
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        
        {/* HEADER */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <SportIcon sx={{ fontSize: 16, color: style.color }} />
                <Typography variant="caption" fontWeight="800" sx={{ color: style.color, textTransform: 'uppercase', fontSize: '0.65rem' }}>
                    {style.label}
                </Typography>
            </Box>
            {training.porcentaje_cumplimiento > 0 && (
                <Chip label={`${training.porcentaje_cumplimiento}%`} size="small" sx={{ height: 16, fontSize: '0.6rem', fontWeight: 700, bgcolor: complianceStyle.border, color: 'white' }} />
            )}
        </Box>

        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: '0.85rem', lineHeight: 1.2, mb: 1, color: '#0F172A' }}>
            {training.titulo}
        </Typography>

        {/* MÉTRICAS */}
        <Box sx={{ display: 'flex', gap: 1.5, mb: 1, color: '#64748B' }}>
            {training.tiempo_planificado_min > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <WatchLater sx={{ fontSize: 14 }} />
                    <Typography variant="caption" fontWeight="600">{training.tiempo_planificado_min}'</Typography>
                </Box>
            )}
             {training.distancia_planificada_km > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Straighten sx={{ fontSize: 14, transform: 'rotate(-45deg)' }} />
                    <Typography variant="caption" fontWeight="600">{training.distancia_planificada_km}k</Typography>
                </Box>
            )}
        </Box>

        <Divider sx={{ my: 0.5, borderColor: 'rgba(0,0,0,0.05)' }} />

        {/* ESTRUCTURA VISUAL (JSON RENDER) */}
        {renderStructure()}

      </CardContent>
    </Card>
  );
};

export default TrainingCardPro;