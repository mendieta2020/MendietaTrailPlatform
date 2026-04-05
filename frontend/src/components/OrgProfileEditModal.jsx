import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Box, Typography, CircularProgress,
} from '@mui/material';
import { updateOrgProfile } from '../api/p1';

export default function OrgProfileEditModal({ open, onClose, orgId, initialData, onSaved }) {
  const [form, setForm] = useState({
    description: '',
    contact_email: '',
    phone: '',
    instagram: '',
    website: '',
    city: '',
    disciplines: '',
    founded_year: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (initialData) {
      setForm({
        description: initialData.description || '',
        contact_email: initialData.contact_email || '',
        phone: initialData.phone || '',
        instagram: initialData.instagram || '',
        website: initialData.website || '',
        city: initialData.city || '',
        disciplines: initialData.disciplines || '',
        founded_year: initialData.founded_year ?? '',
      });
    }
  }, [initialData, open]);

  const handleChange = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      if (payload.founded_year === '') payload.founded_year = null;
      else payload.founded_year = parseInt(payload.founded_year, 10) || null;
      await updateOrgProfile(orgId, payload);
      onSaved?.();
      onClose();
    } catch {
      setError('No se pudo guardar. Intentá de nuevo.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>Editar perfil de organización</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          <TextField
            label="Descripción"
            value={form.description}
            onChange={handleChange('description')}
            multiline
            rows={3}
            fullWidth
            size="small"
          />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField
              label="Ciudad"
              value={form.city}
              onChange={handleChange('city')}
              fullWidth
              size="small"
            />
            <TextField
              label="Año de fundación"
              value={form.founded_year}
              onChange={handleChange('founded_year')}
              type="number"
              sx={{ width: 160 }}
              size="small"
            />
          </Box>
          <TextField
            label="Disciplinas (separadas por coma)"
            value={form.disciplines}
            onChange={handleChange('disciplines')}
            fullWidth
            size="small"
            placeholder="Trail Running, Ultra, Maratón"
          />
          <TextField
            label="Email de contacto"
            value={form.contact_email}
            onChange={handleChange('contact_email')}
            type="email"
            fullWidth
            size="small"
          />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField
              label="Teléfono"
              value={form.phone}
              onChange={handleChange('phone')}
              fullWidth
              size="small"
            />
            <TextField
              label="Instagram"
              value={form.instagram}
              onChange={handleChange('instagram')}
              fullWidth
              size="small"
              placeholder="@usuario"
            />
          </Box>
          <TextField
            label="Sitio web"
            value={form.website}
            onChange={handleChange('website')}
            type="url"
            fullWidth
            size="small"
            placeholder="https://..."
          />
          {error && (
            <Typography variant="caption" color="error">{error}</Typography>
          )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
        <Button onClick={onClose} disabled={saving} sx={{ color: '#64748B', textTransform: 'none' }}>
          Cancelar
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          sx={{ bgcolor: '#00D4AA', '&:hover': { bgcolor: '#00BF99' }, textTransform: 'none', fontWeight: 600 }}
        >
          {saving ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
