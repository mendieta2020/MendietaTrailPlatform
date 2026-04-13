import React, { useState } from 'react';
import { Box, Button, TextField, Typography, Paper, Alert, CircularProgress, LinearProgress } from '@mui/material';
import { Link, useNavigate, useParams } from 'react-router-dom';
import QuantorynLogo from '../components/QuantorynLogo';
import { confirmPasswordReset } from '../api/onboarding';

function passwordStrength(pwd) {
  let score = 0;
  if (pwd.length >= 8) score += 25;
  if (pwd.length >= 12) score += 25;
  if (/[A-Z]/.test(pwd)) score += 25;
  if (/[0-9!@#$%^&*]/.test(pwd)) score += 25;
  return score;
}

const strengthColor = (score) => {
  if (score <= 25) return '#ef4444';
  if (score <= 50) return '#f59e0b';
  if (score <= 75) return '#3b82f6';
  return '#00D4AA';
};

export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const strength = passwordStrength(password);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirm) { setError('Las contraseñas no coinciden.'); return; }
    if (password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres.'); return; }
    setLoading(true);
    setError(null);
    try {
      await confirmPasswordReset(token, password);
      const storedEmail = sessionStorage.getItem('qtn_reset_email') || '';
      sessionStorage.removeItem('qtn_reset_email');
      const dest = storedEmail
        ? `/login?email=${encodeURIComponent(storedEmail)}`
        : '/login';
      navigate(dest, { state: { resetSuccess: true } });
    } catch (err) {
      setError(err?.response?.data?.detail || 'Link inválido o expirado. Pedí un nuevo link.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0D1117 0%, #1A2332 100%)', p: 2,
    }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 400, borderRadius: 3, textAlign: 'center' }}>
        <Box sx={{ mb: 3 }}>
          <QuantorynLogo size={40} />
        </Box>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A', mb: 0.5 }}>
          Creá tu nueva contraseña
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
          Elegí una contraseña segura para tu cuenta.
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{error}</Alert>}

        <Box component="form" onSubmit={handleSubmit}>
          <TextField
            fullWidth label="Nueva contraseña" type="password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            required autoFocus sx={{ mb: 1 }}
          />
          {password.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <LinearProgress
                variant="determinate" value={strength}
                sx={{ height: 6, borderRadius: 3,
                  '& .MuiLinearProgress-bar': { bgcolor: strengthColor(strength) },
                  bgcolor: '#e2e8f0' }}
              />
              <Typography variant="caption" sx={{ color: strengthColor(strength), fontWeight: 600 }}>
                {strength <= 25 ? 'Muy débil' : strength <= 50 ? 'Débil' : strength <= 75 ? 'Buena' : 'Muy segura'}
              </Typography>
            </Box>
          )}
          <TextField
            fullWidth label="Confirmar contraseña" type="password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
            required sx={{ mb: 3 }}
            error={confirm.length > 0 && password !== confirm}
            helperText={confirm.length > 0 && password !== confirm ? 'No coinciden' : ''}
          />
          <Button
            type="submit" fullWidth variant="contained" disabled={loading}
            sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, '&:hover': { bgcolor: '#00BF99' } }}
          >
            {loading ? <CircularProgress size={22} sx={{ color: '#0D1117' }} /> : 'Cambiar contraseña'}
          </Button>
        </Box>
        <Box sx={{ mt: 2 }}>
          <Link to="/login" style={{ color: '#64748B', fontSize: 14, textDecoration: 'none' }}>
            Volver al inicio de sesión
          </Link>
        </Box>
      </Paper>
    </Box>
  );
}
