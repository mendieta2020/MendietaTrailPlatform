import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Button, CircularProgress, Alert
} from '@mui/material';
import { DevicesOther, CheckCircle } from '@mui/icons-material';
import AthleteLayout from '../components/AthleteLayout';
import { useAuth } from '../context/AuthContext';
import { getDeviceStatus, reactivateDevicePreference } from '../api/athlete';

const AthleteProfile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reactivating, setReactivating] = useState(false);
  const [reactivateSuccess, setReactivateSuccess] = useState(false);

  useEffect(() => {
    getDeviceStatus()
      .then(res => setDeviceStatus(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <AthleteLayout user={user}>
      <Box sx={{ maxWidth: 640, mx: 'auto' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A', mb: 4 }}>
          Mi Perfil
        </Typography>

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
