import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, TextField, Button, CircularProgress,
  Alert, Snackbar, Chip,
} from '@mui/material';
import { Person } from '@mui/icons-material';
import Layout from '../components/Layout';
import { getUserProfile, updateUserProfile } from '../api/p1';

export default function OwnerProfile() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');

  useEffect(() => {
    getUserProfile()
      .then((res) => {
        setFirstName(res.data.first_name || '');
        setLastName(res.data.last_name || '');
        setEmail(res.data.email || '');
      })
      .catch(() => setError('No se pudo cargar el perfil.'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updateUserProfile({ first_name: firstName, last_name: lastName });
      setFirstName(res.data.first_name || '');
      setLastName(res.data.last_name || '');
      setToast({ open: true, message: 'Perfil actualizado correctamente', severity: 'success' });
    } catch {
      setToast({ open: true, message: 'Error al guardar el perfil', severity: 'error' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: 680 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
          <Person sx={{ color: '#00D4AA', fontSize: 28 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>
              Mi Perfil
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B' }}>
              Información personal de tu cuenta
            </Typography>
          </Box>
          <Chip
            label="Owner"
            size="small"
            sx={{ ml: 'auto', bgcolor: 'rgba(0,212,170,0.1)', color: '#00D4AA', fontWeight: 700 }}
          />
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
            <CircularProgress sx={{ color: '#00D4AA' }} />
          </Box>
        ) : (
          <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
              <Box sx={{ display: 'flex', gap: 2 }}>
                <TextField
                  label="Nombre"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Apellido"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  fullWidth
                  size="small"
                />
              </Box>
              <TextField
                label="Email"
                value={email}
                disabled
                fullWidth
                size="small"
                helperText="El email no se puede cambiar desde aquí."
              />

              <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving}
                sx={{
                  bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, alignSelf: 'flex-start',
                  '&:hover': { bgcolor: '#00b894' },
                }}
              >
                {saving ? <CircularProgress size={20} sx={{ color: '#0D1117' }} /> : 'Guardar cambios'}
              </Button>
            </Box>
          </Paper>
        )}

        <Snackbar open={toast.open} autoHideDuration={4000} onClose={() => setToast(t => ({ ...t, open: false }))}>
          <Alert severity={toast.severity} onClose={() => setToast(t => ({ ...t, open: false }))}>
            {toast.message}
          </Alert>
        </Snackbar>
      </Box>
    </Layout>
  );
}
