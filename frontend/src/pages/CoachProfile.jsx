import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, TextField, Button, CircularProgress,
  Alert, Snackbar, Chip,
} from '@mui/material';
import { Person } from '@mui/icons-material';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { getCoachProfile, updateCoachProfile } from '../api/p1';

export default function CoachProfile() {
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.org_id;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' });

  const [bio, setBio] = useState('');
  const [specialties, setSpecialties] = useState('');
  const [certifications, setCertifications] = useState('');
  const [yearsExperience, setYearsExperience] = useState('');

  useEffect(() => {
    if (!orgId) return;
    setLoading(true);
    getCoachProfile(orgId)
      .then((res) => {
        setBio(res.data.bio || '');
        setSpecialties(res.data.specialties || '');
        setCertifications(res.data.certifications || '');
        setYearsExperience(res.data.years_experience ?? '');
      })
      .catch(() => setError('No se pudo cargar el perfil de coach.'))
      .finally(() => setLoading(false));
  }, [orgId]);

  const handleSave = async () => {
    if (!orgId) return;
    setSaving(true);
    try {
      await updateCoachProfile({
        org_id: orgId,
        bio,
        specialties,
        certifications,
        years_experience: yearsExperience === '' ? 0 : Number(yearsExperience),
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
          <Person sx={{ color: '#00D4AA', fontSize: 28 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>
              Mi Perfil de Coach
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B' }}>
              Información visible para tus atletas
            </Typography>
          </Box>
          <Chip
            label="Coach"
            size="small"
            sx={{ ml: 'auto', bgcolor: 'rgba(59,130,246,0.1)', color: '#3b82f6', fontWeight: 700 }}
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
              <TextField
                label="Bio"
                multiline
                rows={4}
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder="Contale a tus atletas quién sos, tu historia, tu filosofía de entrenamiento..."
                fullWidth
                size="small"
              />
              <TextField
                label="Especialidades"
                value={specialties}
                onChange={(e) => setSpecialties(e.target.value)}
                placeholder="Ej: Trail running, ultramaratón, montaña"
                helperText="Separadas por comas"
                fullWidth
                size="small"
              />
              <TextField
                label="Certificaciones y formación"
                multiline
                rows={2}
                value={certifications}
                onChange={(e) => setCertifications(e.target.value)}
                placeholder="Ej: IAAF Level 2, Running Coach certificado CABB..."
                fullWidth
                size="small"
              />
              <TextField
                label="Años de experiencia"
                type="number"
                value={yearsExperience}
                onChange={(e) => setYearsExperience(e.target.value)}
                fullWidth
                size="small"
                inputProps={{ min: 0, max: 50 }}
              />

              <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving}
                sx={{
                  alignSelf: 'flex-end',
                  bgcolor: '#00D4AA',
                  color: '#0D1117',
                  fontWeight: 700,
                  textTransform: 'none',
                  '&:hover': { bgcolor: '#00BF99' },
                  minWidth: 140,
                }}
              >
                {saving ? <CircularProgress size={18} sx={{ color: '#0D1117' }} /> : 'Guardar perfil'}
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
