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
const OnboardingChecklist = ({ hasDevice, orgName }) => {
  const navigate = useNavigate();

  const steps = [
    {
      label: `Te uniste a ${orgName || 'la organización'}`,
      done: true,
    },
    {
      label: 'Tu suscripción está activa',
      done: true,
    },
    {
      label: 'Conectá tu dispositivo',
      done: hasDevice,
      action: { label: 'Conectar', path: '/connections' },
    },
    {
      label: 'Completá tu perfil',
      done: false,
      action: { label: 'Completar', path: '/athlete/profile' },
    },
  ];

  const allDone = steps.every(s => s.done);
  if (allDone) return null;

  return (
    <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1E293B', mb: 2 }}>
        Para empezar, completá estos pasos:
      </Typography>
      <List dense disablePadding>
        {steps.map((step) => (
          <ListItem
            key={step.label}
            disablePadding
            sx={{ mb: 0.5 }}
            secondaryAction={
              !step.done && step.action ? (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate(step.action.path)}
                  sx={{ fontSize: '0.75rem', py: 0.25 }}
                >
                  {step.action.label} →
                </Button>
              ) : null
            }
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {step.done
                ? <CheckCircle sx={{ color: '#10B981', fontSize: 20 }} />
                : <RadioButtonUnchecked sx={{ color: '#CBD5E1', fontSize: 20 }} />}
            </ListItemIcon>
            <ListItemText
              primary={step.label}
              primaryTypographyProps={{
                fontSize: '0.875rem',
                color: step.done ? '#64748B' : '#1E293B',
                fontWeight: step.done ? 400 : 500,
              }}
            />
          </ListItem>
        ))}
      </List>
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

// ─── Main component ────────────────────────────────────────────────────────────
const AthleteDashboard = ({ user }) => {
  const { temp, description: weatherDesc, city, loading: weatherLoading } = useWeather();
  const [todayData, setTodayData] = useState(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [hasDevice, setHasDevice] = useState(false);
  const [billing, setBilling] = useState(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const orgName = user?.memberships?.[0]?.org_name || '';
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [pendingNotifications, setPendingNotifications] = useState([]);
  const [mySub, setMySub] = useState(null);

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

          {/* ── Onboarding checklist ── */}
          <OnboardingChecklist hasDevice={hasDevice} orgName={orgName} />
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
