import React, { useState } from 'react';
import { Box, Button, TextField, Typography, Paper, Alert, CircularProgress } from '@mui/material';
import { Link } from 'react-router-dom';
import QuantorynLogo from '../components/QuantorynLogo';
import { requestPasswordReset } from '../api/onboarding';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim().toLowerCase());
      setSent(true);
    } catch {
      setError('No se pudo enviar el email. Intentá de nuevo.');
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

        {sent ? (
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A', mb: 1 }}>
              ¡Listo! Revisá tu email
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
              Si el email existe en Quantoryn, te enviamos las instrucciones para restablecer tu contraseña.
            </Typography>
            <Link to="/login" style={{ color: '#00D4AA', fontWeight: 600, textDecoration: 'none' }}>
              Volver al inicio de sesión
            </Link>
          </Box>
        ) : (
          <Box component="form" onSubmit={handleSubmit}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A', mb: 0.5 }}>
              Recuperar contraseña
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
              Ingresá tu email y te enviamos el link para crear una nueva.
            </Typography>

            {error && <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{error}</Alert>}

            <TextField
              fullWidth label="Email" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              required autoFocus sx={{ mb: 2 }}
            />
            <Button
              type="submit" fullWidth variant="contained" disabled={loading}
              sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, '&:hover': { bgcolor: '#00BF99' } }}
            >
              {loading ? <CircularProgress size={22} sx={{ color: '#0D1117' }} /> : 'Enviar instrucciones'}
            </Button>
            <Box sx={{ mt: 2 }}>
              <Link to="/login" style={{ color: '#64748B', fontSize: 14, textDecoration: 'none' }}>
                Volver al inicio de sesión
              </Link>
            </Box>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
