import React from 'react';
import { Box, Typography, Paper, CircularProgress } from '@mui/material';

const StatGauge = ({ title, value, target, unit, icon: Icon, color }) => {
  // Calculamos el porcentaje (evitamos división por cero)
  const percentage = target > 0 ? Math.min(100, Math.round((value / target) * 100)) : 0;
  
  return (
    <Paper 
      elevation={0}
      sx={{ 
        p: 2, 
        borderRadius: 4, 
        bgcolor: 'white',
        border: '1px solid #F1F5F9',
        boxShadow: '0 4px 20px rgba(0,0,0,0.03)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 130,
        height: '100%'
      }}
    >
      {/* Título e Icono */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, color: '#64748B' }}>
        {Icon && <Icon sx={{ fontSize: 16 }} />}
        <Typography variant="caption" fontWeight="700" sx={{ textTransform: 'uppercase', fontSize: '0.65rem' }}>
          {title}
        </Typography>
      </Box>

      {/* Gráfico Circular (Gauge) */}
      <Box sx={{ position: 'relative', display: 'inline-flex', mb: 1 }}>
        {/* Fondo Gris */}
        <CircularProgress
          variant="determinate"
          value={100}
          size={70}
          thickness={4}
          sx={{ color: '#F1F5F9' }}
        />
        {/* Progreso Color */}
        <CircularProgress
          variant="determinate"
          value={percentage}
          size={70}
          thickness={4}
          sx={{ 
            color: color,
            position: 'absolute',
            left: 0,
            strokeLinecap: 'round',
          }}
        />
        {/* Datos Centrales */}
        <Box
          sx={{
            top: 0, left: 0, bottom: 0, right: 0,
            position: 'absolute',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'column'
          }}
        >
          <Typography variant="h6" fontWeight="800" sx={{ color: '#1E293B', lineHeight: 1, fontSize: '1rem' }}>
            {Math.round(value)}
          </Typography>
          <Typography variant="caption" sx={{ color: '#94A3B8', fontSize: '0.6rem' }}>
            / {Math.round(target)} {unit}
          </Typography>
        </Box>
      </Box>

      {/* Estado Texto */}
      <Typography variant="caption" fontWeight="700" sx={{ color: percentage >= 100 ? '#10B981' : color, fontSize: '0.7rem' }}>
        {percentage}% Completado
      </Typography>
    </Paper>
  );
};

export default StatGauge;