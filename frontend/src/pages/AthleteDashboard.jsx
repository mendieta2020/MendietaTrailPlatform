import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Grid, CircularProgress, Chip,
  List, ListItem, ListItemIcon, ListItemText, Button, Alert
} from '@mui/material';
import {
  CheckCircle, RadioButtonUnchecked, DirectionsRun, WbSunny,
  CreditCard, ArrowForward
} from '@mui/icons-material';
import AthleteLayout from '../components/AthleteLayout';
import useWeather from '../hooks/useWeather';
import client from '../api/client';
import { getBillingStatus } from '../api/billing';
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

  if (!billing) {
    return (
      <Paper sx={{ p: 2.5, borderRadius: 2, borderLeft: '4px solid #F59E0B', display: 'flex', alignItems: 'center', gap: 2 }}>
        <CreditCard sx={{ color: '#F59E0B' }} />
        <Typography variant="body2" sx={{ color: '#92400E' }}>
          Tu suscripción está inactiva — contactá a tu coach
        </Typography>
      </Paper>
    );
  }

  const isActive = billing.is_active;

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

// ─── Main component ────────────────────────────────────────────────────────────
const AthleteDashboard = ({ user }) => {
  const { temp, description: weatherDesc, city, loading: weatherLoading } = useWeather();
  const [todayData, setTodayData] = useState(null);
  const [todayLoading, setTodayLoading] = useState(true);
  const [hasDevice, setHasDevice] = useState(false);
  const [billing, setBilling] = useState(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const [orgName, setOrgName] = useState('');

  const greeting = getGreeting();
  const displayName = user?.first_name || user?.username || 'Atleta';

  useEffect(() => {
    // Fetch today's workout
    client.get('/api/athlete/today/')
      .then(res => setTodayData(res.data))
      .catch(() => setTodayData({ has_workout: false }))
      .finally(() => setTodayLoading(false));

    // Fetch device connection status
    client.get('/api/connections/')
      .then(res => {
        const connections = res.data;
        const connected = Array.isArray(connections)
          ? connections.some(c => c.connected)
          : false;
        setHasDevice(connected);
      })
      .catch(() => setHasDevice(false));

    // Fetch billing status
    getBillingStatus()
      .then(res => setBilling(res.data))
      .catch(() => setBilling(null))
      .finally(() => setBillingLoading(false));

    // Fetch org name from /api/me
    client.get('/api/me')
      .then(res => {
        if (res.data?.org_name) setOrgName(res.data.org_name);
      })
      .catch(() => {});
  }, []);

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

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          {/* ── Today's workout card ── */}
          <Box sx={{ mb: 3 }}>
            <WorkoutCard workout={workout} loading={todayLoading} />
          </Box>

          {/* ── Onboarding checklist ── */}
          <OnboardingChecklist hasDevice={hasDevice} orgName={orgName} />
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          {/* ── Subscription card ── */}
          <SubscriptionCard billing={billing} loading={billingLoading} />
        </Grid>
      </Grid>
    </AthleteLayout>
  );
};

export default AthleteDashboard;
