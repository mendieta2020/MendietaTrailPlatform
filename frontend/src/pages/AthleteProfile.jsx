import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Button, CircularProgress, Alert, TextField,
} from '@mui/material';
import { DevicesOther, CheckCircle, LocationOn } from '@mui/icons-material';
import AthleteLayout from '../components/AthleteLayout';
import { useAuth } from '../context/AuthContext';
import { getDeviceStatus, reactivateDevicePreference } from '../api/athlete';
import client from '../api/client';

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';

async function geocodeCity(cityName) {
  try {
    const res = await fetch(
      `${NOMINATIM_URL}?q=${encodeURIComponent(cityName)}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'es' } }
    );
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.length) return null;
    return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
  } catch {
    return null;
  }
}

const AthleteProfile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const orgId = user?.memberships?.[0]?.org_id;

  const [deviceStatus, setDeviceStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reactivating, setReactivating] = useState(false);
  const [reactivateSuccess, setReactivateSuccess] = useState(false);

  // Location state
  const [locationCity, setLocationCity] = useState('');
  const [athleteId, setAthleteId] = useState(null);
  const [locationSaving, setLocationSaving] = useState(false);
  const [locationSuccess, setLocationSuccess] = useState(false);
  const [locationError, setLocationError] = useState('');

  useEffect(() => {
    getDeviceStatus()
      .then(res => setDeviceStatus(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load athlete's current location from roster endpoint
  useEffect(() => {
    if (!orgId) return;
    client.get(`/api/p1/orgs/${orgId}/roster/athletes/`)
      .then(res => {
        const data = res.data?.results ?? res.data ?? [];
        const athletes = Array.isArray(data) ? data : [];
        if (athletes.length > 0) {
          setAthleteId(athletes[0].id);
          setLocationCity(athletes[0].location_city ?? '');
        }
      })
      .catch(() => {});
  }, [orgId]);

  const handleReactivate = async () => {
    setReactivating(true);
    try {
      await reactivateDevicePreference();
      setDeviceStatus(prev => prev ? { ...prev, dismissed: false, show_prompt: true } : prev);
      setReactivateSuccess(true);
    } catch {
      // no-op
    } finally {
      setReactivating(false);
    }
  };

  const handleSaveLocation = async () => {
    if (!orgId || !athleteId) return;
    setLocationSaving(true);
    setLocationError('');
    setLocationSuccess(false);
    try {
      const payload = { location_city: locationCity };

      // Geocode via Nominatim (free, no key needed)
      if (locationCity.trim()) {
        const coords = await geocodeCity(locationCity.trim());
        if (coords) {
          payload.location_lat = coords.lat;
          payload.location_lon = coords.lon;
        }
      } else {
        payload.location_lat = null;
        payload.location_lon = null;
      }

      await client.patch(`/api/p1/orgs/${orgId}/roster/athletes/${athleteId}/`, payload);
      setLocationSuccess(true);
    } catch {
      setLocationError('Error al guardar la ubicación. Intenta de nuevo.');
    } finally {
      setLocationSaving(false);
    }
  };

  return (
    <AthleteLayout user={user}>
      <Box sx={{ maxWidth: 640, mx: 'auto' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A', mb: 4 }}>
          Mi Perfil
        </Typography>

        {/* ── Location section ── */}
        <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <LocationOn sx={{ color: '#f97316' }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A' }}>
              Ubicación de entrenamiento
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: '#64748B', mb: 2 }}>
            Indicá tu ciudad o lugar habitual de entrenamiento para ver el pronóstico del clima en tus sesiones.
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <TextField
              label="Ciudad o lugar de entrenamiento habitual"
              placeholder="ej: Mendoza, Argentina"
              size="small"
              fullWidth
              value={locationCity}
              onChange={(e) => { setLocationCity(e.target.value); setLocationSuccess(false); }}
              helperText="Lo usamos para mostrarte el pronóstico del clima en tus sesiones"
            />
            <Button
              variant="contained"
              size="small"
              disabled={locationSaving}
              onClick={handleSaveLocation}
              sx={{
                bgcolor: '#f97316', '&:hover': { bgcolor: '#ea6c0a' },
                textTransform: 'none', flexShrink: 0, mt: 0.25,
              }}
              endIcon={locationSaving ? <CircularProgress size={12} color="inherit" /> : null}
            >
              Guardar
            </Button>
          </Box>
          {locationSuccess && (
            <Alert severity="success" sx={{ mt: 1.5, py: 0 }}>
              Ubicación guardada correctamente.
            </Alert>
          )}
          {locationError && (
            <Alert severity="error" sx={{ mt: 1.5, py: 0 }}>
              {locationError}
            </Alert>
          )}
        </Paper>

        {/* ── Device connection section ── */}
        <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <DevicesOther sx={{ color: '#0EA5E9' }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A' }}>
              Conexión de dispositivo
            </Typography>
          </Box>

          {loading ? (
            <CircularProgress size={20} />
          ) : deviceStatus?.dismissed ? (
            <Box>
              <Alert severity="info" sx={{ mb: 2 }}>
                Has indicado que no tienes dispositivo de entrenamiento.
              </Alert>
              {reactivateSuccess ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: '#10B981' }}>
                  <CheckCircle />
                  <Typography variant="body2">Puedes conectar tu dispositivo desde Conexiones.</Typography>
                </Box>
              ) : (
                <Button
                  variant="outlined"
                  size="small"
                  disabled={reactivating}
                  onClick={handleReactivate}
                  sx={{ textTransform: 'none' }}
                >
                  {reactivating ? 'Reactivando...' : 'Reactivar conexión de dispositivo'}
                </Button>
              )}
            </Box>
          ) : deviceStatus?.has_device ? (
            <Box>
              <Alert severity="success" sx={{ mb: 2 }}>
                Tu dispositivo está conectado.
              </Alert>
              <Button
                variant="outlined"
                size="small"
                onClick={() => navigate('/connections')}
                sx={{ textTransform: 'none' }}
              >
                Gestionar conexiones
              </Button>
            </Box>
          ) : (
            <Box>
              <Typography variant="body2" sx={{ color: '#475569', mb: 2 }}>
                Ve a Conexiones para vincular tu dispositivo de entrenamiento.
              </Typography>
              <Button
                variant="contained"
                size="small"
                onClick={() => navigate('/connections')}
                sx={{ bgcolor: '#0EA5E9', textTransform: 'none', '&:hover': { bgcolor: '#0284C7' } }}
              >
                Ir a Conexiones
              </Button>
            </Box>
          )}
        </Paper>
      </Box>
    </AthleteLayout>
  );
};

export default AthleteProfile;
