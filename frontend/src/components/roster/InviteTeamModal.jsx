/**
 * PR-165a: InviteTeamModal — create a tokenized team invitation (coach or staff).
 */
import React, { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Select, MenuItem, FormControl, InputLabel,
  Typography, Box, Chip, Alert, CircularProgress,
} from '@mui/material';
import { ContentCopy, Check } from '@mui/icons-material';
import { createTeamInvitation } from '../../api/p1';

export default function InviteTeamModal({ open, defaultRole, orgId, onClose, onCreated }) {
  const [role, setRole] = useState(defaultRole || 'coach');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { join_url, role, expires_at }
  const [copied, setCopied] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await createTeamInvitation(orgId, { role, email: email.trim() });
      setResult(res.data);
      if (onCreated) onCreated(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.role?.[0] || 'No se pudo crear la invitación.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result?.join_url) return;
    navigator.clipboard?.writeText(result.join_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  const handleClose = () => {
    setRole(defaultRole || 'coach');
    setEmail('');
    setError(null);
    setResult(null);
    setCopied(false);
    onClose();
  };

  const roleLabel = role === 'coach' ? 'Coach' : 'Admin Staff';
  const roleColor = role === 'coach' ? '#3b82f6' : '#8b5cf6';

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>
        Invitar {roleLabel}
      </DialogTitle>

      <DialogContent>
        {!result ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}

            <FormControl fullWidth size="small">
              <InputLabel>Rol</InputLabel>
              <Select value={role} label="Rol" onChange={(e) => setRole(e.target.value)}>
                <MenuItem value="coach">Coach</MenuItem>
                <MenuItem value="staff">Admin Staff</MenuItem>
              </Select>
            </FormControl>

            <TextField
              label="Email (opcional)"
              size="small"
              fullWidth
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              helperText="Si lo especificas, solo esa persona podrá usar el link."
              type="email"
            />
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
            <Box sx={{ textAlign: 'center', py: 1 }}>
              <Chip
                label={roleLabel}
                sx={{ bgcolor: `${roleColor}20`, color: roleColor, fontWeight: 700, mb: 1.5 }}
              />
              <Typography variant="body2" sx={{ color: '#374151', mb: 2 }}>
                Comparte este link con el nuevo {roleLabel}:
              </Typography>
              <Box
                sx={{
                  bgcolor: '#f8fafc', borderRadius: 2, p: 1.5,
                  border: '1px solid #e2e8f0', wordBreak: 'break-all',
                  fontFamily: 'monospace', fontSize: '0.8rem', color: '#1e293b',
                  mb: 1.5,
                }}
              >
                {result.join_url}
              </Box>
              <Button
                variant="contained"
                startIcon={copied ? <Check /> : <ContentCopy />}
                onClick={handleCopy}
                sx={{
                  bgcolor: copied ? '#16a34a' : '#00D4AA',
                  color: '#fff',
                  '&:hover': { bgcolor: copied ? '#15803d' : '#00b896' },
                  textTransform: 'none', fontWeight: 700,
                }}
              >
                {copied ? '¡Copiado!' : 'Copiar link'}
              </Button>
              <Typography variant="caption" sx={{ display: 'block', color: '#64748b', mt: 1.5 }}>
                Expira en 7 días · Solo uso único
              </Typography>
            </Box>
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={handleClose} sx={{ textTransform: 'none', color: '#64748b' }}>
          {result ? 'Cerrar' : 'Cancelar'}
        </Button>
        {!result && (
          <Button
            onClick={handleSubmit}
            disabled={loading}
            variant="contained"
            sx={{
              bgcolor: '#00D4AA', color: '#fff',
              '&:hover': { bgcolor: '#00b896' },
              textTransform: 'none', fontWeight: 700,
            }}
          >
            {loading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Generar link'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
