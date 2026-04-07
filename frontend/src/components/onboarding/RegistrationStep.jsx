import React, { useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';
import { TextField, CircularProgress, Alert } from '@mui/material';
import { Mail, Lock, User } from 'lucide-react';
import { registerWithEmail, registerWithGoogle } from '../../api/onboarding';
import { useAuth } from '../../context/AuthContext';

export default function RegistrationStep({ onComplete }) {
  const { loginWithTokens } = useAuth();
  const [mode, setMode] = useState('choice'); // choice | email
  const [form, setForm] = useState({ email: '', password: '', confirmPassword: '', first_name: '', last_name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await registerWithGoogle(credentialResponse.credential);
      await loginWithTokens(data);
      onComplete();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Error al registrarse con Google.');
    } finally {
      setLoading(false);
    }
  };

  const handleEmailSubmit = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data } = await registerWithEmail({
        email: form.email,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
      });
      await loginWithTokens(data);
      onComplete();
    } catch (err) {
      const detail = err?.response?.data;
      if (detail?.code === 'email_exists') {
        setError('email_exists');
      } else if (detail?.email) {
        setError(Array.isArray(detail.email) ? detail.email[0] : detail.email);
      } else if (detail?.password) {
        setError(Array.isArray(detail.password) ? detail.password[0] : detail.password);
      } else {
        setError(detail?.detail || 'Error al crear la cuenta.');
      }
    } finally {
      setLoading(false);
    }
  };

  const inputChange = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  return (
    <div className="p-6 sm:p-8">
      <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-1">
        Paso 1 de 2
      </p>
      <h2 className="text-xl font-bold text-slate-900 mb-1">Creá tu cuenta</h2>
      <p className="text-slate-500 text-sm mb-6">
        Registrate para unirte al equipo
      </p>

      {error && error === 'email_exists' ? (
        <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
          Ya existe una cuenta con ese email.{' '}
          <a href="/login" style={{ fontWeight: 700, color: 'inherit', textDecoration: 'underline' }}>
            Iniciá sesión aquí.
          </a>
        </Alert>
      ) : error ? (
        <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>
          {error}
        </Alert>
      ) : null}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <CircularProgress size={32} sx={{ color: '#6366f1' }} />
        </div>
      )}

      {!loading && (
        <>
          {/* Google Sign-In */}
          <div className="flex justify-center mb-4">
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => setError('Error al conectar con Google.')}
              text="continue_with"
              shape="rectangular"
              size="large"
              width="100%"
              locale="es"
            />
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-slate-200" />
            <span className="text-xs text-slate-400 uppercase tracking-wider">o registrate con email</span>
            <div className="flex-1 h-px bg-slate-200" />
          </div>

          {mode === 'choice' ? (
            <button
              onClick={() => setMode('email')}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-slate-200 hover:bg-slate-50 text-sm font-medium text-slate-700 transition-colors"
            >
              <Mail className="w-4 h-4" />
              Registrarme con email
            </button>
          ) : (
            <form onSubmit={handleEmailSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <TextField
                  size="small"
                  label="Nombre"
                  value={form.first_name}
                  onChange={inputChange('first_name')}
                  slotProps={{ input: { startAdornment: <User className="w-4 h-4 mr-2 text-slate-400" /> } }}
                  fullWidth
                />
                <TextField
                  size="small"
                  label="Apellido"
                  value={form.last_name}
                  onChange={inputChange('last_name')}
                  fullWidth
                />
              </div>
              <TextField
                size="small"
                label="Email"
                type="email"
                required
                value={form.email}
                onChange={inputChange('email')}
                slotProps={{ input: { startAdornment: <Mail className="w-4 h-4 mr-2 text-slate-400" /> } }}
                fullWidth
              />
              <TextField
                size="small"
                label="Contraseña"
                type="password"
                required
                value={form.password}
                onChange={inputChange('password')}
                slotProps={{ input: { startAdornment: <Lock className="w-4 h-4 mr-2 text-slate-400" /> } }}
                helperText="Mínimo 8 caracteres"
                fullWidth
              />
              <TextField
                size="small"
                label="Confirmar contraseña"
                type="password"
                required
                value={form.confirmPassword}
                onChange={inputChange('confirmPassword')}
                slotProps={{ input: { startAdornment: <Lock className="w-4 h-4 mr-2 text-slate-400" /> } }}
                fullWidth
              />
              <button
                type="submit"
                className="w-full px-4 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm transition-colors"
              >
                Crear cuenta
              </button>
            </form>
          )}
        </>
      )}
    </div>
  );
}
