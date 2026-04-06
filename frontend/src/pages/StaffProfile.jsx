import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, TextField, Button, CircularProgress,
  Alert, Snackbar, Chip,
} from '@mui/material';
import { Person } from '@mui/icons-material';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import client from '../api/client';

export default function StaffProfile() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [staffTitle, setStaffTitle] = useState('');
  const [phone, setPhone] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  const [instagram, setInstagram] = useState('');

  useEffect(() => {
    if (!orgId) return;
    setLoading(true);
    client.get(`/api/p1/orgs/${orgId}/memberships/`)
      .then((res) => {
        const items = res.data?.results ?? res.data ?? [];
        const own = items.find((m) => m.is_self);
        if (own) {
          setStaffTitle(own.staff_title || '');
          setPhone(own.phone || '');
          setBirthDate(own.birth_date || '');
          setPhotoUrl(own.photo_url || '');
          setInstagram(own.instagram || '');
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleSave = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      await client.patch(`/api/p1/orgs/${orgId}/memberships/me/`, {
        staff_title: staffTitle,
        phone,
        birth_date: birthDate || null,
        photo_url: photoUrl,
        instagram,
      });
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
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
          <Person sx={{ color: '#8b5cf6', fontSize: 28 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>
              Mi Perfil de Staff
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B' }}>
              Información visible dentro de la organización
            </Typography>
          </Box>
          <Chip
            label="Staff"
            size="small"
            sx={{ ml: 'auto', bgcolor: 'rgba(139,92,246,0.1)', color: '#8b5cf6', fontWeight: 700 }}
          />
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
            <CircularProgress sx={{ color: '#8b5cf6' }} />
          </Box>
        ) : (
          <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
              <TextField
                label="Cargo / Posición"
                value={staffTitle}
                onChange={(e) => setStaffTitle(e.target.value)}
                placeholder="Ej: Coordinadora de equipo, Nutricionista, Fisioterapeuta..."
                fullWidth
                size="small"
              />

              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', mt: 0.5 }}>
                Contacto y redes
              </Typography>

              <TextField
                label="Teléfono"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="Ej: +5491112345678"
                fullWidth
                size="small"
              />
              <TextField
                label="Instagram"
                value={instagram}
                onChange={(e) => setInstagram(e.target.value)}
                placeholder="Ej: @nombre"
                fullWidth
                size="small"
              />
              <TextField
                label="Fecha de nacimiento"
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
                fullWidth
                size="small"
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                label="URL de foto de perfil"
                value={photoUrl}
                onChange={(e) => setPhotoUrl(e.target.value)}
                placeholder="https://..."
                fullWidth
                size="small"
              />

              <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving}
                sx={{
                  alignSelf: 'flex-end',
                  bgcolor: '#8b5cf6',
                  color: '#fff',
                  fontWeight: 700,
                  textTransform: 'none',
                  '&:hover': { bgcolor: '#7c3aed' },
                  minWidth: 140,
                }}
              >
                {saving ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Guardar perfil'}
              </Button>
            </Box>
          </Paper>
        )}
      </Box>

      <Snackbar
        open={toast.open}
        autoHideDuration={3000}
        onClose={() => setToast((t) => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity={toast.severity} onClose={() => setToast((t) => ({ ...t, open: false }))}>
          {toast.message}
        </Alert>
      </Snackbar>
    </Layout>
  );
}
