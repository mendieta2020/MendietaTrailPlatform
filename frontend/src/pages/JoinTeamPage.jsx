/**
 * PR-165a: JoinTeamPage — public page for coaches/staff to accept a team invitation.
 * Route: /join/team/:token
 *
 * Fix 1: Uses loginWithTokens (not manual localStorage) so AuthContext updates.
 * Fix 2: Uses RegistrationStep for unauthenticated users (Google OAuth + email).
 */
import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box, Button, CircularProgress, Typography, Chip, Alert,
} from '@mui/material';
import { AlertTriangle, Clock, CheckCircle } from 'lucide-react';
import { getTeamJoinInfo, acceptTeamJoin } from '../api/p1';
import { useAuth } from '../context/AuthContext';
import RegistrationStep from '../components/onboarding/RegistrationStep';

const ROLE_COLORS = { coach: '#3b82f6', staff: '#8b5cf6', owner: '#00D4AA' };
const ROLE_LABELS = { coach: 'Coach', staff: 'Admin Staff', owner: 'Owner' };

function ErrorCard({ icon, color, title, subtitle }) {
  const CardIcon = icon;
  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0D1117 0%, #161B22 100%)', px: 2,
    }}>
      <Box sx={{
        bgcolor: '#fff', borderRadius: 3, p: 4, maxWidth: 400, width: '100%', textAlign: 'center',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      }}>
        <CardIcon style={{ width: 48, height: 48, color, marginBottom: 16 }} />
        <Typography variant="h6" fontWeight={700} sx={{ mb: 1 }}>{title}</Typography>
        <Typography variant="body2" sx={{ color: '#64748b' }}>{subtitle}</Typography>
      </Box>
    </Box>
  );
}

export default function JoinTeamPage() {
  const { token } = useParams();
  const { user, loading: authLoading } = useAuth();

  const [state, setState] = useState('loading'); // loading | pending | expired | already_used | not_found | error
  const [invite, setInvite] = useState(null);
  // step 0 = registration (unauthenticated), step 1 = confirm join
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  useEffect(() => {
    if (authLoading) return;
    getTeamJoinInfo(token)
      .then(({ data }) => {
        setInvite(data);
        // If already authenticated, skip registration step
        setStep(user ? 1 : 0);
        setState('pending');
      })
      .catch((err) => {
        const code = err.response?.data?.code;
        if (code === 'expired')           setState('expired');
        else if (code === 'already_used') setState('already_used');
        else if (code === 'not_found')    setState('not_found');
        else setState('error');
      });
  }, [token, authLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleJoin = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await acceptTeamJoin(token, {});
      // Full reload so OrgContext picks up the new membership (same pattern as JoinPage.jsx)
      window.location.href = '/dashboard';
    } catch (err) {
      const code = err.response?.data?.code;
      const detail = err.response?.data?.detail || 'No se pudo procesar la invitación.';
      if (code === 'expired')           setState('expired');
      else if (code === 'already_used') setState('already_used');
      else if (code === 'email_mismatch') setSubmitError('Este link no está destinado a tu email.');
      else setSubmitError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  if (state === 'loading' || authLoading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: '#0D1117' }}>
        <CircularProgress sx={{ color: '#00D4AA' }} />
      </Box>
    );
  }

  if (state === 'expired') {
    return <ErrorCard icon={Clock} color="#f59e0b" title="Invitación expirada" subtitle="Este link ya no es válido. Pide al owner de la organización que genere uno nuevo." />;
  }

  if (state === 'already_used') {
    return <ErrorCard icon={CheckCircle} color="#16a34a" title="Invitación ya usada" subtitle="Esta invitación ya fue aceptada. Si no eres tú, contacta al administrador." />;
  }

  if (state === 'not_found' || state === 'error') {
    return <ErrorCard icon={AlertTriangle} color="#ef4444" title="Link inválido" subtitle="No encontramos esta invitación. Verifica el link o solicita uno nuevo." />;
  }

  const role = invite?.role || 'coach';
  const roleColor = ROLE_COLORS[role] || '#64748b';
  const roleLabel = ROLE_LABELS[role] || role;

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0D1117 0%, #161B22 100%)', px: 2, py: 4,
    }}>
      <Box sx={{
        bgcolor: '#fff', borderRadius: 3, maxWidth: 440, width: '100%',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)', overflow: 'hidden',
      }}>
        {/* Accent bar */}
        <Box sx={{ height: 4, bgcolor: roleColor }} />

        <Box sx={{ p: 4 }}>
          {/* Header */}
          <Box sx={{ textAlign: 'center', mb: 3 }}>
            <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              {invite?.org_name || 'Quantoryn'}
            </Typography>
            <Typography variant="h5" fontWeight={800} sx={{ mt: 0.5, mb: 1.5 }}>
              Te invitan a unirte
            </Typography>
            <Chip
              label={roleLabel}
              sx={{ bgcolor: `${roleColor}18`, color: roleColor, fontWeight: 700, fontSize: '0.8rem' }}
            />
          </Box>

          {/* Step 0: Registration (unauthenticated) */}
          {step === 0 && (
            <RegistrationStep onComplete={() => setStep(1)} />
          )}

          {/* Step 1: Confirm join */}
          {step === 1 && (
            <Box sx={{ textAlign: 'center' }}>
              {submitError && <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }}>{submitError}</Alert>}

              {user && (
                <Typography variant="body2" sx={{ color: '#374151', mb: 3 }}>
                  Sesión activa como <strong>{user.email}</strong>
                </Typography>
              )}

              <Button
                fullWidth
                variant="contained"
                onClick={handleJoin}
                disabled={submitting}
                sx={{
                  bgcolor: roleColor, color: '#fff',
                  '&:hover': { bgcolor: roleColor, filter: 'brightness(0.9)' },
                  textTransform: 'none', fontWeight: 700, py: 1.5,
                }}
              >
                {submitting
                  ? <CircularProgress size={20} sx={{ color: '#fff' }} />
                  : `Unirme como ${roleLabel}`}
              </Button>
            </Box>
          )}

          <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: '#94a3b8', mt: 2 }}>
            No necesitas plan de pago. Tu acceso es gestionado por la organización.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
