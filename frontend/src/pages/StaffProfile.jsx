import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, TextField, Button, CircularProgress,
  Alert, Snackbar, Chip,
} from '@mui/material';
import { Person } from '@mui/icons-material';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { getStaffProfile, updateStaffProfile, getUserProfile, updateUserProfile } from '../api/p1';

export default function StaffProfile() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [staffTitle, setStaffTitle] = useState('');
  const [phone, setPhone] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  const [instagram, setInstagram] = useState('');

  useEffect(() => {
    if (!orgId) return;
    setLoading(true);
    Promise.all([getStaffProfile(orgId), getUserProfile()])
      .then(([staffRes, userRes]) => {
        setStaffTitle(staffRes.data.staff_title || '');
        setPhone(staffRes.data.phone || '');
        setBirthDate(staffRes.data.birth_date || '');
        setPhotoUrl(staffRes.data.photo_url || '');
        setInstagram(staffRes.data.instagram || '');
        setEmail(userRes.data.email || '');
        setFirstName(userRes.data.first_name || '');
        setLastName(userRes.data.last_name || '');
      })
      .catch(() => setError('No se pudo cargar el perfil.'))
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleSave = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      await Promise.all([
        updateStaffProfile({ org_id: orgId, staff_title: staffTitle, phone, birth_date: birthDate || null, photo_url: photoUrl, instagram }),
        updateUserProfile({ first_name: firstName, last_name: lastName }),
      ]);
      // Refetch to confirm persistence
      const [staffRes, userRes] = await Promise.all([getStaffProfile(orgId), getUserProfile()]);
      setStaffTitle(staffRes.data.staff_title || '');
      setPhone(staffRes.data.phone || '');
      setFirstName(userRes.data.first_name || '');
      setLastName(userRes.data.last_name || '');
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

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
            <CircularProgress sx={{ color: '#8b5cf6' }} />
          </Box>
        ) : (
          <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
              <TextField
                label="Email"
                value={email}
                fullWidth
                size="small"
                disabled
                helperText="El email no se puede modificar desde aquí."
              />
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
