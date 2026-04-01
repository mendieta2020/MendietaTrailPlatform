import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Grid, CircularProgress, Chip,
  List, ListItem, ListItemIcon, ListItemText, Button, Alert,
  LinearProgress,
} from '@mui/material';
import {
  CheckCircle, RadioButtonUnchecked, DirectionsRun, WbSunny,
  CreditCard, ArrowForward, DevicesOther, LocalFireDepartment,
} from '@mui/icons-material';
import AthleteLayout from '../components/AthleteLayout';
import useWeather from '../hooks/useWeather';
import client from '../api/client';
import { getBillingStatus, getMySubscription } from '../api/billing';
import {
  getDeviceStatus,
  dismissDevicePreference,
  markNotificationRead,
} from '../api/athlete';
import { WellnessCheckIn } from '../components/WellnessCheckIn';
import { useNavigate } from 'react-router-dom';

// ─── Greeting based on time of day ────────────────────────────────────────────
function getGreeting() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return 'Buenos días';
  if (hour >= 12 && hour < 19) return 'Buenas tardes';
  return 'Buenas noches';
}

// ─── Workout card ──────────────────────────────────────────────────────────────
const WorkoutCard = ({ workout, loading }) => {
  const navigate = useNavigate();

  if (loading) {
    return (
      <Paper sx={{ p: 3, borderRadius: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
        <CircularProgress size={20} />
        <Typography variant="body2" sx={{ color: '#64748B' }}>Cargando tu entrenamiento...</Typography>
      </Paper>
    );
  }

  if (!workout) {
    return (
      <Paper sx={{ p: 3, borderRadius: 2, borderLeft: '4px solid #10B981' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <CheckCircle sx={{ color: '#10B981' }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#10B981' }}>
            DÍA DE RECUPERACIÓN
          </Typography>
        </Box>
        <Typography variant="body2" sx={{ color: '#475569' }}>
          Hoy no tenés sesión programada.
        </Typography>
        <Typography variant="body2" sx={{ color: '#94A3B8', mt: 0.5 }}>
          Aprovechá para descansar y hidratarte bien 💧
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3, borderRadius: 2, borderLeft: '4px solid #F57C00' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <DirectionsRun sx={{ color: '#F57C00' }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#F57C00', letterSpacing: 0.5 }}>
          ENTRENAMIENTO DE HOY
        </Typography>
      </Box>
      <Typography variant="h6" sx={{ fontWeight: 700, color: '#1E293B', mb: 0.5 }}>
        {workout.title}
      </Typography>
      {workout.description && (
        <Typography variant="body2" sx={{ color: '#475569', fontStyle: 'italic', mb: 2 }}>
          "{workout.description}"
        </Typography>
      )}
      <Button
        size="small"
        endIcon={<ArrowForward />}
        onClick={() => navigate('/athlete/training')}
        sx={{ color: '#F57C00', fontWeight: 600, px: 0, '&:hover': { background: 'none', textDecoration: 'underline' } }}
      >
        Ver detalle completo
      </Button>
    </Paper>
  );
};

// ─── Onboarding checklist ──────────────────────────────────────────────────────
// PR-151: Welcome Flow — BLOCKING personalized onboarding experience
// Shows as full-screen overlay BEFORE the dashboard until athlete dismisses or connects device
const WelcomeFlow = ({ hasDevice, orgName, firstName, onDismiss }) => {
  const navigate = useNavigate();

  // All done: show success screen
  if (hasDevice) {
    return (
        <Paper sx={{ p: 5, borderRadius: 4, maxWidth: 480, width: '100%', textAlign: 'center', background: 'linear-gradient(135deg, #ECFDF5 0%, #F0FDF4 100%)', border: '1px solid #A7F3D0', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)' }}>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#065F46', mb: 2 }}>
            ¡Todo listo, {firstName}! 🚀
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 3, alignItems: 'center' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CheckCircle sx={{ color: '#10B981', fontSize: 22 }} />
              <Typography variant="body2" sx={{ color: '#334155', fontWeight: 500 }}>Perfil completado</Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CheckCircle sx={{ color: '#10B981', fontSize: 22 }} />
              <Typography variant="body2" sx={{ color: '#334155', fontWeight: 500 }}>Dispositivo conectado</Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CheckCircle sx={{ color: '#10B981', fontSize: 22 }} />
              <Typography variant="body2" sx={{ color: '#334155', fontWeight: 500 }}>Listo para entrenar</Typography>
            </Box>
          </Box>
          <Typography variant="body2" sx={{ color: '#047857', mb: 3 }}>
            Tu coach ya puede ver tu perfil y asignarte entrenamientos.
          </Typography>
          <Button variant="contained" fullWidth onClick={onDismiss}
            sx={{ bgcolor: '#10B981', '&:hover': { bgcolor: '#059669' }, borderRadius: 3, textTransform: 'none', fontWeight: 700, py: 1.5, fontSize: '1rem' }}>
            ¡Empezar a entrenar! →
          </Button>
        </Paper>
    );
  }

  // Not done: show setup wizard
  return (
      <Paper sx={{ p: 5, borderRadius: 4, maxWidth: 480, width: '100%', background: 'linear-gradient(135deg, #EEF2FF 0%, #F5F3FF 100%)', border: '1px solid #C7D2FE', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#312E81', mb: 0.5 }}>
          ¡Bienvenido {firstName} a {orgName || 'tu equipo'}! 🎉
        </Typography>
        <Typography variant="body2" sx={{ color: '#6366F1', mb: 3 }}>
          Completá estos pasos para empezar a entrenar
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {/* Step 1: Profile ✅ */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2, bgcolor: 'white', borderRadius: 3, border: '1px solid #E0E7FF' }}>
            <CheckCircle sx={{ color: '#10B981', fontSize: 24 }} />
            <Typography variant="body1" sx={{ fontWeight: 500, color: '#64748B' }}>
              Perfil completado
            </Typography>
          </Box>

          {/* Step 2: Connect device */}
          <Box sx={{ p: 2, bgcolor: 'white', borderRadius: 3, border: '2px solid #6366F1' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <ArrowForward sx={{ color: '#6366F1', fontSize: 24 }} />
                <Typography variant="body1" sx={{ fontWeight: 600, color: '#1E293B' }}>
                  Conectá tu dispositivo
                </Typography>
              </Box>
            </Box>
            <Typography variant="caption" sx={{ color: '#6366F1', display: 'block', mt: 0.5, ml: 5 }}>
              Strava, Garmin, Suunto, Polar, COROS...
            </Typography>
            <Button variant="contained" fullWidth onClick={() => navigate('/connections')}
              sx={{ mt: 2, bgcolor: '#6366F1', '&:hover': { bgcolor: '#4F46E5' }, borderRadius: 2, textTransform: 'none', fontWeight: 600 }}>
              Conectar dispositivo →
            </Button>
          </Box>

          {/* Step 3: Ready (disabled) */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2, bgcolor: 'white', borderRadius: 3, border: '1px solid #E2E8F0', opacity: 0.4 }}>
            <RadioButtonUnchecked sx={{ color: '#CBD5E1', fontSize: 24 }} />
            <Typography variant="body1" sx={{ color: '#94A3B8' }}>
              Listo para entrenar
            </Typography>
          </Box>
        </Box>

        <Button variant="text" fullWidth onClick={onDismiss}
          sx={{ mt: 3, color: '#94A3B8', textTransform: 'none', fontWeight: 500, fontSize: '0.85rem' }}>
          Continuar sin conectar →
        </Button>
      </Paper>
  );
};

// ─── Subscription card ─────────────────────────────────────────────────────────
const SubscriptionCard = ({ billing, loading }) => {
  if (loading) return null;

  // null = unknown (API error or 403) — do NOT show inactive banner.
  // Only show the banner when the API explicitly returns is_active: false (200).
  if (billing === null) return null;

  const isActive = billing.is_active;

  if (!isActive) {
    return (
      <Paper sx={{ p: 2.5, borderRadius: 2, borderLeft: '4px solid #F59E0B', display: 'flex', alignItems: 'center', gap: 2 }}>
        <CreditCard sx={{ color: '#F59E0B' }} />
        <Typography variant="body2" sx={{ color: '#92400E' }}>
          Tu suscripción está inactiva — contactá a tu coach
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2.5, borderRadius: 2, display: 'flex', alignItems: 'center', gap: 2, borderLeft: `4px solid ${isActive ? '#10B981' : '#EF4444'}` }}>
      <CreditCard sx={{ color: isActive ? '#10B981' : '#EF4444' }} />
      <Box sx={{ flexGrow: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#1E293B' }}>
            {billing.plan_display || billing.plan || 'Plan'}
          </Typography>
          <Chip
            label={isActive ? 'Activo' : 'Inactivo'}
            size="small"
            sx={{
              bgcolor: isActive ? '#DCFCE7' : '#FEE2E2',
              color: isActive ? '#166534' : '#991B1B',
              fontWeight: 600,
              height: 20,
              fontSize: '0.7rem',
            }}
          />
        </Box>
        {billing.next_billing_date && (
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            Próximo pago: {billing.next_billing_date}
          </Typography>
        )}
      </Box>
    </Paper>
  );
};

// ─── Device connection banner ──────────────────────────────────────────────────
const DeviceBanner = ({ deviceStatus, onDismiss }) => {
  const navigate = useNavigate();
  if (!deviceStatus) return null;

  const { show_prompt, dismissed, unread_notifications } = deviceStatus;

  // Never show if dismissed, regardless of unread notifications
  if (dismissed) return null;
  // Show only if there's a prompt or unread notification
  if (!show_prompt && unread_notifications === 0) return null;

  const message = unread_notifications > 0
    ? 'Tu coach te invita a conectar tu dispositivo de entrenamiento'
    : 'Conecta tu dispositivo para sincronizar tus entrenamientos automáticamente';

  return (
    <Paper
      sx={{
        p: 2.5, mb: 3, borderRadius: 2,
        borderLeft: '4px solid #0EA5E9',
        bgcolor: '#F0F9FF',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 2,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1 }}>
        <DevicesOther sx={{ color: '#0EA5E9', flexShrink: 0 }} />
        <Typography variant="body2" sx={{ color: '#0C4A6E', fontWeight: 500 }}>
          {message}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', gap: 1, flexShrink: 0 }}>
        <Button
          size="small"
          variant="contained"
          onClick={() => navigate('/connections')}
          sx={{ bgcolor: '#0EA5E9', textTransform: 'none', fontWeight: 600, '&:hover': { bgcolor: '#0284C7' } }}
        >
          Conectar dispositivo
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={onDismiss}
          sx={{ color: '#64748B', textTransform: 'none' }}
        >
          No tengo dispositivo
        </Button>
      </Box>
    </Paper>
  );
};

// ─── Weekly Pulse (PR-148) ─────────────────────────────────────────────────────
const WeeklyPulse = ({ weeklySummary, streak }) => {
  if (!weeklySummary) return null;
  const { sessions_completed, sessions_planned, total_km } = weeklySummary;
  if (sessions_completed === 0 && total_km === 0) return null;

  const pct = sessions_planned > 0
    ? Math.min(Math.round((sessions_completed / sessions_planned) * 100), 150)
    : 0;
  const barColor =
    pct >= 120 ? '#3B82F6'
    : pct >= 100 ? '#22C55E'
    : pct >= 70  ? '#F59E0B'
    : '#EF4444';

  return (
    <Paper sx={{ p: 2.5, mt: 2, borderRadius: 2 }}>
      {streak >= 3 && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 1.5 }}>
          <LocalFireDepartment sx={{ color: '#F97316', fontSize: 20 }} />
          <Typography variant="body2" sx={{ color: '#F97316', fontWeight: 700 }}>
            {streak} días consecutivos
          </Typography>
        </Box>
      )}
      <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, display: 'block', mb: 0.75 }}>
        Esta semana: {sessions_completed}/{sessions_planned} sesiones
        {total_km > 0 ? ` · ${total_km} km` : ''}
      </Typography>
      <LinearProgress
        variant="determinate"
        value={Math.min(pct, 100)}
        sx={{
          height: 8, borderRadius: 4,
          bgcolor: 'rgba(0,0,0,0.08)',
          '& .MuiLinearProgress-bar': { bgcolor: barColor, borderRadius: 4 },
        }}
      />
    </Paper>
  );
};

// ─── PR-152: Trial Banner ───────────────────────────────────────────────────────
const TrialBanner = ({ mySub }) => {
  if (!mySub?.has_subscription) return null;
  if (mySub.status === 'active') return null; // Already paid

  const trialActive = mySub.trial_active;
  const daysLeft = mySub.trial_days_remaining ?? 0;
  const planName = mySub.plan_name;
  const price = mySub.price_ars;

  if (trialActive) {
    // Trial active: show countdown
    const progress = ((7 - daysLeft) / 7) * 100;
    return (
      <Paper sx={{ p: 2.5, borderRadius: 3, mb: 3, background: 'linear-gradient(135deg, #FEF3C7 0%, #FFFBEB 100%)', border: '1px solid #FCD34D' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 700, color: '#92400E' }}>
            ⏳ Tu periodo de prueba vence en {daysLeft} día{daysLeft !== 1 ? 's' : ''}
          </Typography>
          <Button variant="contained" size="small"
            onClick={async () => {
              try {
                const { getPaymentLink } = await import('../api/athlete');
                const { data } = await getPaymentLink();
                if (data.init_point) window.location.href = data.init_point;
              } catch {
                window.alert('Contactá a tu coach para activar tu plan.');
              }
            }}
            sx={{ bgcolor: '#F59E0B', '&:hover': { bgcolor: '#D97706' }, borderRadius: 2, textTransform: 'none', fontWeight: 600, fontSize: '0.8rem' }}>
            Activar plan →
          </Button>
        </Box>
        <LinearProgress variant="determinate" value={progress}
          sx={{ height: 6, borderRadius: 3, bgcolor: '#FDE68A', '& .MuiLinearProgress-bar': { bgcolor: '#F59E0B', borderRadius: 3 } }}
        />
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
          <Typography variant="caption" sx={{ color: '#B45309' }}>Día 1</Typography>
          <Typography variant="caption" sx={{ color: '#B45309' }}>Día 7</Typography>
        </Box>
      </Paper>
    );
  }

  // Trial expired: show lock screen
  return (
    <Box sx={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      bgcolor: 'rgba(15, 23, 42, 0.8)', backdropFilter: 'blur(8px)',
      zIndex: 1300, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
    }}>
      <Paper sx={{ p: 5, borderRadius: 4, maxWidth: 440, width: '100%', textAlign: 'center' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, color: '#1E293B', mb: 1 }}>
          🔒 Tu periodo de prueba finalizó
        </Typography>
        <Typography variant="body2" sx={{ color: '#64748B', mb: 3 }}>
          Para seguir viendo tus entrenamientos, calendario y progreso, activá tu plan.
        </Typography>
        <Paper sx={{ p: 2, borderRadius: 2, bgcolor: '#F8FAFC', mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#334155' }}>{planName}</Typography>
          <Typography variant="body1" sx={{ fontWeight: 700, color: '#6366F1' }}>
            ${new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(price)}/mes
          </Typography>
        </Paper>
        <Button variant="contained" fullWidth href="/athlete/profile"
          sx={{ bgcolor: '#6366F1', '&:hover': { bgcolor: '#4F46E5' }, borderRadius: 3, textTransform: 'none', fontWeight: 700, py: 1.5, fontSize: '1rem' }}>
          Activar mi plan →
        </Button>
      </Paper>
    </Box>
  );
};

// ─── Main component ────────────────────────────────────────────────────────────
const AthleteDashboard = ({ user }) => {
  const { temp, description: weatherDesc, city, loading: weatherLoading } = useWeather();
  const [todayData, setTodayData] = useState(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [hasDevice, setHasDevice] = useState(false);
  const [billing, setBilling] = useState(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const orgName = user?.memberships?.[0]?.org_name || '';
  const wellnessOrgId = user?.memberships?.[0]?.org_id ?? null;
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [pendingNotifications, setPendingNotifications] = useState([]);
  const [mySub, setMySub] = useState(null);
  const [welcomeDismissed, setWelcomeDismissed] = useState(
    () => localStorage.getItem('quantoryn_welcome_done') === 'true'
  );
  // PR-154: Wellness check-in overlay — show once per day (localStorage gate)
  const [wellnessVisible, setWellnessVisible] = useState(() => {
    const today = new Date().toISOString().split('T')[0];
    return localStorage.getItem('quantoryn_wellness_date') !== today;
  });

  const greeting = getGreeting();
  const displayName = user?.first_name || user?.username || 'Atleta';

  useEffect(() => {
    // Fetch today's workout
    client.get('/api/athlete/today/')
      .then(res => setTodayData(res.data))
      .catch(() => setTodayData({ has_workout: false }))
      .finally(() => setTodayLoading(false));

    // Fetch device status (PR-141: replaces raw /api/connections/ for prompt logic)
    getDeviceStatus()
      .then(res => {
        setDeviceStatus(res.data);
        setHasDevice(res.data.has_device);
        if (res.data.unread_notifications > 0) {
          // Also fetch notification IDs so we can mark them read on dismiss
          client.get('/api/athlete/notifications/')
            .then(nRes => setPendingNotifications(nRes.data || []))
            .catch(() => {});
        }
      })
      .catch(() => {
        // Fallback: check legacy connections endpoint for OnboardingChecklist
        client.get('/api/connections/')
          .then(res => {
            const connections = res.data?.connections || res.data || [];
            const connected = Array.isArray(connections)
              ? connections.some(c => c.connected || c.status === 'connected')
              : false;
            setHasDevice(connected);
          })
          .catch(() => setHasDevice(false));
      });

    // Fetch billing status. On any error (including 403) set null — the banner
    // only appears when the API explicitly returns is_active:false on a 200.
    getBillingStatus()
      .then(res => setBilling(res.data))
      .catch(() => setBilling(null))
      .finally(() => setBillingLoading(false));

    // Org name already initialized from user.memberships in useState

    // PR-150: Fetch athlete's coach subscription
    getMySubscription()
      .then(res => setMySub(res.data))
      .catch(() => setMySub(null));
  }, []);

  // PR-151: Welcome flow dismiss — stores in localStorage, shows only once
  const handleWelcomeDismiss = () => {
    localStorage.setItem('quantoryn_welcome_done', 'true');
    setWelcomeDismissed(true);
  };

  const handleDismissBanner = async () => {
    try {
      await dismissDevicePreference('no_device');
      // Mark all pending notifications as read
      await Promise.all(pendingNotifications.map(n => markNotificationRead(n.id)));
      setDeviceStatus(prev => prev ? { ...prev, dismissed: true, show_prompt: false } : prev);
    } catch {
      // Best-effort: hide banner locally regardless
      setDeviceStatus(prev => prev ? { ...prev, dismissed: true, show_prompt: false } : prev);
    }
  };

  const workout = todayData?.has_workout ? todayData.workout : null;

  return (
    <AthleteLayout user={user}>
      {/* PR-151: Welcome Flow OVERLAY — shows on top of dashboard, one time only */}
      {!welcomeDismissed && (
        <Box sx={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          bgcolor: 'rgba(15, 23, 42, 0.7)', backdropFilter: 'blur(8px)',
          zIndex: 1300, display: 'flex', alignItems: 'center', justifyContent: 'center',
          p: 2,
        }}>
          <WelcomeFlow
            hasDevice={hasDevice}
            orgName={orgName}
            firstName={user?.first_name || displayName}
            onDismiss={handleWelcomeDismiss}
          />
        </Box>
      )}

      {/* PR-154: Wellness Check-In OVERLAY — once per day (localStorage gate), only if welcome done */}
      {welcomeDismissed && wellnessVisible && wellnessOrgId && (
        <Box sx={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          bgcolor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(6px)',
          zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center',
          p: 2,
        }}>
          <WellnessCheckIn
            firstName={user?.first_name || displayName}
            orgId={wellnessOrgId}
            athleteId={user?.athlete_id ?? user?.id}
            onDismissSession={() => {
              localStorage.setItem('quantoryn_wellness_date', new Date().toISOString().split('T')[0]);
              setWellnessVisible(false);
            }}
          />
        </Box>
      )}

      {/* ── PR-152: Trial Banner ── */}
      <TrialBanner mySub={mySub} />

      {/* ── Header: greeting + weather ── */}
      <Box sx={{ mb: 4, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>
            {greeting}, {displayName} 👋
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>
            {new Date().toLocaleDateString('es-AR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </Typography>
        </Box>

        {!weatherLoading && temp !== null && (
          <Paper sx={{ px: 2, py: 1, borderRadius: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            <WbSunny sx={{ color: '#F59E0B', fontSize: 20 }} />
            <Typography variant="body2" sx={{ fontWeight: 600, color: '#1E293B' }}>
              {temp}°C
            </Typography>
            {weatherDesc && (
              <Typography variant="body2" sx={{ color: '#64748B' }}>
                · {weatherDesc}
              </Typography>
            )}
            {city && (
              <Typography variant="body2" sx={{ color: '#94A3B8' }}>
                · {city}
              </Typography>
            )}
          </Paper>
        )}
      </Box>

      {/* ── Device connection banner (PR-141) ── */}
      <DeviceBanner deviceStatus={deviceStatus} onDismiss={handleDismissBanner} />

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          {/* ── Today's workout card ── */}
          <Box sx={{ mb: 3 }}>
            <WorkoutCard workout={workout} loading={todayLoading} />
            {!todayLoading && (
              <WeeklyPulse
                weeklySummary={todayData?.weekly_summary}
                streak={todayData?.consecutive_days_active ?? 0}
              />
            )}
          </Box>

          {/* Welcome flow moved to top-level blocking mode (PR-151) */}
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          {/* ── Subscription card ── */}
          <SubscriptionCard billing={billing} loading={billingLoading} />

          {/* ── PR-150: Coach plan subscription widget ── */}
          {mySub?.has_subscription && (
            <Paper sx={{ p: 2.5, borderRadius: 2, mt: 2, borderLeft: `4px solid ${mySub.status === 'active' ? '#10B981' : mySub.status === 'overdue' ? '#EF4444' : '#F59E0B'}` }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <CreditCard sx={{ color: mySub.status === 'active' ? '#10B981' : '#F59E0B', fontSize: 20 }} />
                <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
                  Mi suscripción
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600, color: '#334155' }}>
                    {mySub.plan_name}
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#64748B' }}>
                    {mySub.next_payment_at ? `Próximo cobro: ${new Date(mySub.next_payment_at).toLocaleDateString('es-AR')}` : ''}
                  </Typography>
                </Box>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E293B' }}>
                    ${new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(mySub.price_ars)}
                    <Typography component="span" variant="caption" sx={{ color: '#94A3B8' }}>/mes</Typography>
                  </Typography>
                  <Chip
                    label={mySub.status === 'active' ? 'Al día' : mySub.status === 'overdue' ? 'Vencido' : 'Pendiente'}
                    size="small"
                    sx={{
                      bgcolor: mySub.status === 'active' ? '#DCFCE7' : mySub.status === 'overdue' ? '#FEE2E2' : '#FEF3C7',
                      color: mySub.status === 'active' ? '#166534' : mySub.status === 'overdue' ? '#991B1B' : '#92400E',
                      fontWeight: 600, height: 20, fontSize: '0.7rem',
                    }}
                  />
                </Box>
              </Box>
            </Paper>
          )}
        </Grid>
      </Grid>
    </AthleteLayout>
  );
};

export default AthleteDashboard;
