import React from 'react';
import { useParams } from 'react-router-dom';
import { Typography } from '@mui/material';
import Layout from '../components/Layout';
import client from '../api/client';

// RECONSTRUCCIÓN SEGURA:
// - Sin date-fns
// - Sin WeeklyCalendar / TemplateLibrary
// - Sin @mui/icons-material
// - Sin lógica de cache / effects
const AthleteDetail = () => {
  const { id } = useParams();

  // Validar que el import exista (sin ejecutar nada)
  void client;

  return (
    <Layout>
      <Typography sx={{ p: 3, fontWeight: 800 }}>
        Cargando Atleta: {id}
      </Typography>
    </Layout>
  );
};

export default AthleteDetail;