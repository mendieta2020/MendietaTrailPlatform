import React, { useEffect, useReducer, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  CircularProgress,
  Chip,
  Button,
  Skeleton,
} from '@mui/material';
import LinkIcon from '@mui/icons-material/Link';
import { Building2, Users, TrendingUp, Activity } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import Layout from '../components/Layout';
import RosterSection from '../components/roster/RosterSection';
import AssignmentCalendar from '../components/AssignmentCalendar';
import ManageConnectionsModal from '../components/roster/ManageConnectionsModal';
import { useOrg } from '../context/OrgContext';
import { listExternalIdentities, getDashboardAnalytics } from '../api/p1';
import { getCoachBriefing } from '../api/teams';

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({ title, value, sub, color, icon: Icon, loading }) {
  return (
    <Paper
      sx={{
        p: 3,
        borderRadius: 3,
        border: '1px solid',
        borderColor: 'divider',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        borderLeft: `4px solid ${color}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        minWidth: 0,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Typography
          variant="caption"
          sx={{ color: '#64748B', fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' }}
        >
          {title}
        </Typography>
        {Icon && <Icon style={{ width: 18, height: 18, color, opacity: 0.8 }} />}
      </Box>
      {loading ? (
        <Skeleton variant="text" width={60} height={40} />
      ) : (
        <Typography variant="h4" sx={{ fontWeight: 700, color: '#1E293B', lineHeight: 1 }}>
          {value ?? '—'}
        </Typography>
      )}
      {sub && (
        <Typography variant="caption" sx={{ color: '#94A3B8' }}>
          {sub}
        </Typography>
      )}
    </Paper>
  );
}

// ── PMC Chart Tooltip ─────────────────────────────────────────────────────────

function PmcTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <Paper sx={{ p: 1.5, borderRadius: 2, border: '1px solid', borderColor: 'divider', boxShadow: 2 }}>
      <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 0.5 }}>
        {label}
      </Typography>
      {payload.map((entry) => (
        <Typography key={entry.dataKey} variant="caption" sx={{ color: entry.color, display: 'block' }}>
          {entry.name}: <strong>{entry.value?.toFixed(1)}</strong>
        </Typography>
      ))}
    </Paper>
  );
}

// ── PMC Section ───────────────────────────────────────────────────────────────

function pmcReducer(state, action) {
  switch (action.type) {
    case 'SUCCESS': return { loading: false, analytics: action.data, error: null };
    case 'ERROR':   return { loading: false, analytics: null, error: action.message };
    default:        return state;
  }
}

// key={orgId} on the parent ensures remount (and therefore fresh state) when org changes.
function PmcSection({ orgId }) {
  const [{ loading, analytics, error }, dispatch] = useReducer(pmcReducer, {
    loading: true,
    analytics: null,
    error: null,
  });

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    getDashboardAnalytics(orgId)
      .then((res) => { if (!cancelled) dispatch({ type: 'SUCCESS', data: res.data }); })
      .catch(() => { if (!cancelled) dispatch({ type: 'ERROR', message: 'No se pudieron cargar los datos de rendimiento.' }); });
    return () => { cancelled = true; };
  }, [orgId]);

  const latestEntry = analytics?.pmc_series?.[analytics.pmc_series.length - 1] ?? null;
  const hasData = analytics?.pmc_series?.some((d) => d.ctl > 0 || d.atl > 0);

  // Subsample series to ~30 points for legibility
  const chartData = React.useMemo(() => {
    const series = analytics?.pmc_series ?? [];
    if (series.length <= 30) return series;
    const step = Math.ceil(series.length / 30);
    return series.filter((_, i) => i % step === 0 || i === series.length - 1);
  }, [analytics]);

  return (
    <Paper
      sx={{
        p: 3,
        mb: 3,
        borderRadius: 3,
        border: '1px solid',
        borderColor: 'divider',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
      }}
    >
      {/* Section header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
        <TrendingUp style={{ width: 18, height: 18, color: '#F57C00' }} />
        <Typography variant="subtitle1" fontWeight={700} color="text.primary">
          Rendimiento Fisiológico (PMC)
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
          Últimos 90 días · TSS planificado
        </Typography>
      </Box>

      {/* KPI cards row */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2, mb: 3 }}>
        <KpiCard
          title="Atletas Activos"
          value={analytics?.active_athletes_count}
          sub="en esta organización"
          color="#3B82F6"
          icon={Users}
          loading={loading}
        />
        <KpiCard
          title="Fitness (CTL)"
          value={latestEntry ? latestEntry.ctl.toFixed(1) : null}
          sub="carga crónica actual"
          color="#10B981"
          icon={TrendingUp}
          loading={loading}
        />
        <KpiCard
          title="Fatiga (ATL)"
          value={latestEntry ? latestEntry.atl.toFixed(1) : null}
          sub="carga aguda actual"
          color="#EF4444"
          icon={Activity}
          loading={loading}
        />
      </Box>

      {/* Chart area */}
      {loading ? (
        <Skeleton variant="rectangular" height={220} sx={{ borderRadius: 2 }} />
      ) : error ? (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 8,
            color: '#94A3B8',
          }}
        >
          <Activity style={{ width: 36, height: 36, marginBottom: 8, opacity: 0.5 }} />
          <Typography variant="body2" color="text.secondary">
            {error}
          </Typography>
        </Box>
      ) : !hasData ? (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 10,
            textAlign: 'center',
          }}
        >
          <TrendingUp style={{ width: 44, height: 44, color: '#CBD5E1', marginBottom: 12 }} />
          <Typography variant="subtitle2" fontWeight={600} color="text.primary" gutterBottom>
            Sin datos de rendimiento aún
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 360 }}>
            Asigna entrenamientos con TSS planificado a tus atletas para ver la evolución del fitness y la fatiga.
          </Typography>
        </Box>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#94A3B8' }}
              tickLine={false}
              axisLine={{ stroke: '#E2E8F0' }}
              tickFormatter={(d) => d.slice(5)} // MM-DD
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#94A3B8' }}
              tickLine={false}
              axisLine={false}
              width={36}
            />
            <Tooltip content={<PmcTooltip />} />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: 12, color: '#64748B', paddingTop: 8 }}
            />
            <Line
              type="monotone"
              dataKey="ctl"
              name="Fitness (CTL)"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="atl"
              name="Fatiga (ATL)"
              stroke="#EF4444"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Paper>
  );
}

// ── Coach Briefing Card (PR-148) ──────────────────────────────────────────────

function CoachBriefingCard({ orgId }) {
  const [briefing, setBriefing] = React.useState(null);

  React.useEffect(() => {
    if (!orgId) return;
    getCoachBriefing(orgId)
      .then((res) => setBriefing(res.data))
      .catch(() => {});
  }, [orgId]);

  if (!briefing || briefing.athletes_total === 0) return null;

  const dateLabel = briefing.yesterday_date
    ? new Date(briefing.yesterday_date + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
    : '';

  const rows = [
    {
      icon: '✅',
      text: `${briefing.athletes_trained_yesterday}/${briefing.athletes_total} atletas entrenaron`,
    },
    briefing.athletes_overloaded > 0 && {
      icon: '🔵',
      text: `${briefing.athletes_overloaded} con sobrecarga esta semana`,
    },
    briefing.athletes_inactive_4d > 0 && {
      icon: '⚠️',
      text: `${briefing.athletes_inactive_4d} sin actividad (4+ días)`,
    },
    briefing.unread_messages > 0 && {
      icon: '💬',
      text: `${briefing.unread_messages} mensaje${briefing.unread_messages !== 1 ? 's' : ''} sin leer`,
    },
  ].filter(Boolean);

  return (
    <Paper
      sx={{
        p: 2.5, mb: 3, borderRadius: 3,
        border: '1px solid', borderColor: 'divider',
        boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        borderLeft: '4px solid #F57C00',
      }}
    >
      <Typography variant="subtitle2" fontWeight={700} color="text.primary" sx={{ mb: 1.5 }}>
        Resumen de Ayer — {dateLabel}
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        {rows.map((row, i) => (
          <Typography key={i} variant="body2" color="text.secondary">
            {row.icon} {row.text}
          </Typography>
        ))}
      </Box>
    </Paper>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function CoachDashboard() {
  const { activeOrg, orgLoading } = useOrg();
  const [selectedAthleteId, setSelectedAthleteId] = useState(null);
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [activeConnectionCount, setActiveConnectionCount] = useState(null);

  useEffect(() => {
    if (!activeOrg) return;
    listExternalIdentities(activeOrg.org_id)
      .then((res) => {
        const identities = res.data?.results ?? res.data ?? [];
        setActiveConnectionCount(identities.filter((i) => i.status === 'linked').length);
      })
      .catch(() => setActiveConnectionCount(null));
  }, [activeOrg]);

  if (orgLoading) {
    return (
      <Layout>
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress />
        </Box>
      </Layout>
    );
  }

  if (!activeOrg) {
    return (
      <Layout>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 16,
            textAlign: 'center',
          }}
        >
          <Building2 style={{ width: 48, height: 48, color: '#cbd5e1', marginBottom: 16 }} />
          <Typography variant="h6" fontWeight={600} color="text.primary" gutterBottom>
            Sin organización asignada
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Contacta a tu administrador para que te asigne a una organización.
          </Typography>
        </Box>
      </Layout>
    );
  }

  return (
    <Layout>
      {/* Org header */}
      <Paper
        sx={{
          p: 3,
          mb: 3,
          borderRadius: 3,
          border: '1px solid',
          borderColor: 'divider',
          boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)',
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            flexWrap: 'wrap',
            justifyContent: 'space-between',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <Typography variant="h5" fontWeight={700}>
              {activeOrg.org_name}
            </Typography>
            <Chip
              label={activeOrg.role}
              size="small"
              variant="outlined"
              sx={{ borderColor: '#F57C00', color: '#F57C00', fontWeight: 600 }}
            />
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {activeConnectionCount !== null && (
              <Chip
                label={
                  activeConnectionCount > 0
                    ? `${activeConnectionCount} conexión${activeConnectionCount !== 1 ? 'es' : ''} activa${activeConnectionCount !== 1 ? 's' : ''}`
                    : 'Sin conexiones activas'
                }
                size="small"
                color={activeConnectionCount > 0 ? 'success' : 'default'}
                variant="outlined"
              />
            )}
            <Button
              size="small"
              variant="outlined"
              startIcon={<LinkIcon />}
              onClick={() => setConnectionsOpen(true)}
              sx={{
                color: '#F57C00',
                borderColor: '#F57C00',
                '&:hover': { borderColor: '#e65100', bgcolor: 'rgba(245,124,0,0.04)' },
              }}
            >
              Gestionar Conexiones
            </Button>
          </Box>
        </Box>
      </Paper>

      {/* PR-148: Morning briefing card */}
      <CoachBriefingCard orgId={activeOrg.org_id} />

      {/* Analytics section — key ensures fresh state on org switch */}
      <PmcSection key={activeOrg.org_id} orgId={activeOrg.org_id} />

      {/* Roster */}
      <RosterSection orgId={activeOrg.org_id} onSelectAthlete={setSelectedAthleteId} />

      {selectedAthleteId !== null && (
        <AssignmentCalendar athleteId={selectedAthleteId} orgId={activeOrg.org_id} />
      )}

      <ManageConnectionsModal
        open={connectionsOpen}
        onClose={() => setConnectionsOpen(false)}
        orgId={activeOrg.org_id}
      />
    </Layout>
  );
}
