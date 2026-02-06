import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { useLocation } from 'react-router-dom';
import AthleteLayout from '../components/AthleteLayout';
import client from '../api/client';
import { API_BASE_URL } from '../api/config';

const formatDateTime = (value) => {
  if (!value) return 'Sin datos';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Sin datos';
  return date.toLocaleString();
};

const AthleteIntegrations = () => {
  const location = useLocation();
  const [loading, setLoading] = useState(true);
  const [athlete, setAthlete] = useState(null);
  const [forbidden, setForbidden] = useState(false);

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const stravaStatus = query.get('strava');

  useEffect(() => {
    const fetchAthlete = async () => {
      try {
        const response = await client.get('/api/alumnos/me/');
        setAthlete(response.data);
        setForbidden(false);
      } catch (error) {
        if (error?.response?.status === 403) {
          setForbidden(true);
        }
      } finally {
        setLoading(false);
      }
    };
    fetchAthlete();
  }, []);

  const handleConnect = () => {
    window.location.href = `${API_BASE_URL}/accounts/strava/login/?role=athlete`;
  };

  const syncState = athlete?.sync_state;
  const isConnected = Boolean(athlete?.strava_athlete_id);

  return (
    <AthleteLayout>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, color: '#0F172A' }}>
            Integraciones
          </Typography>
          <Typography sx={{ color: '#64748B' }}>
            Conecta tus servicios deportivos para mantener tus actividades sincronizadas.
          </Typography>
        </Box>

        {stravaStatus === 'connected' && (
          <Alert severity="success">Strava conectado correctamente.</Alert>
        )}
        {stravaStatus === 'error' && (
          <Alert severity="error">No se pudo completar la conexión con Strava.</Alert>
        )}

        {forbidden && (
          <Alert severity="warning">
            Esta pantalla es solo para alumnos. Si eres coach, invita al alumno a conectar su cuenta.
          </Alert>
        )}

        <Paper sx={{ p: 3, borderRadius: 3 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center" justifyContent="space-between">
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  Strava
                </Typography>
                <Typography variant="body2" sx={{ color: '#64748B' }}>
                  Sincroniza tus actividades y métricas.
                </Typography>
              </Box>
              <Chip
                label={isConnected ? 'Conectado' : 'No conectado'}
                color={isConnected ? 'success' : 'default'}
                sx={{ fontWeight: 600 }}
              />
            </Stack>

            <Stack spacing={1}>
              <Typography variant="body2">
                Última sincronización: {formatDateTime(syncState?.last_sync_at)}
              </Typography>
              {syncState?.last_error ? (
                <Typography variant="body2" color="error">
                  Último error: {syncState.last_error}
                </Typography>
              ) : null}
            </Stack>

            <Box>
              <Button
                variant="contained"
                onClick={handleConnect}
                disabled={forbidden || loading}
                sx={{ textTransform: 'none', bgcolor: '#FC4C02' }}
              >
                Conectar con Strava
              </Button>
            </Box>
          </Stack>
        </Paper>
      </Stack>
    </AthleteLayout>
  );
};

export default AthleteIntegrations;
