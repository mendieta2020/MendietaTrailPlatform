import React from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { BarChart } from '@mui/icons-material';
import AthleteLayout from '../components/AthleteLayout';
import { useAuth } from '../context/AuthContext';

const AthleteProgress = () => {
  const { user } = useAuth();

  return (
    <AthleteLayout user={user}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Mi Progreso</Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>Análisis fisiológico de rendimiento</Typography>
      </Box>

      <Paper
        sx={{
          p: 6,
          borderRadius: 3,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          border: '2px dashed #E2E8F0',
          boxShadow: 'none',
          minHeight: 320,
        }}
      >
        <Box sx={{ bgcolor: '#F1F5F9', borderRadius: '50%', p: 2.5, mb: 3 }}>
          <BarChart sx={{ fontSize: 40, color: '#94A3B8' }} />
        </Box>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
          Tu análisis de rendimiento
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', maxWidth: 400 }}>
          Tu análisis de rendimiento (CTL/ATL/TSB) estará disponible próximamente.
          Aquí visualizarás tu carga de entrenamiento, fatiga acumulada y estado de forma a lo largo del tiempo.
        </Typography>
      </Paper>
    </AthleteLayout>
  );
};

export default AthleteProgress;
