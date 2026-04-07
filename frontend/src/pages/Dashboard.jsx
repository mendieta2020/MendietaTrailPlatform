import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Grid, Paper, Typography, Box, CircularProgress, Alert, Divider,
  MenuItem, Select, FormControl, InputLabel, Table, TableBody,
  TableCell, TableHead, TableRow, Chip, Skeleton, IconButton, Avatar,
} from '@mui/material';
import {
  MonitorHeart, TrendingUp, LocalHospital, OpenInNew, CheckCircle,
} from '@mui/icons-material';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Line,
} from 'recharts';
import Layout from '../components/Layout';
import { useOrg } from '../context/OrgContext';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { getTeamReadiness, getCoachAthletePMC } from '../api/pmc';

// --- KPI CARD ---
const StatCard = ({ title, value, sub, color, icon: Icon, loading }) => (
  <Paper sx={{
    p: 3, height: '100%', display: 'flex', flexDirection: 'column',
    justifyContent: 'space-between', borderLeft: `4px solid ${color}`,
    borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.07)',
    border: '1px solid #E2E8F0',
  }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' }}>
        {title}
      </Typography>
      {Icon && <Icon sx={{ color, opacity: 0.7 }} />}
    </Box>
    <Box sx={{ mt: 2 }}>
      {loading
        ? <CircularProgress size={20} sx={{ color }} />
        : <Typography variant="h4" sx={{ fontWeight: 700, color: '#1E293B' }}>{value}</Typography>
      }
      <Typography variant="body2" sx={{ color, fontWeight: 500, mt: 0.5, fontSize: '0.875rem' }}>{sub}</Typography>
    </Box>
  </Paper>
);

// --- SEMAPHORE CARD ---
const SemaCard = ({ label, count, color, loading }) => (
  <Paper sx={{
    p: 2, height: '100%', borderTop: `3px solid ${color}`,
    borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.07)',
    border: '1px solid #E2E8F0', textAlign: 'center',
  }}>
    {loading
      ? <Skeleton variant="text" width={40} sx={{ mx: 'auto', fontSize: '2.5rem' }} />
      : <Typography variant="h3" sx={{ fontWeight: 700, color, lineHeight: 1.2 }}>{count ?? 0}</Typography>
    }
    <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, letterSpacing: 0.3 }}>{label}</Typography>
  </Paper>
);

// --- ACWR HELPERS ---
const computeAcwr = (atl, ctl) => (ctl && ctl > 0 ? atl / ctl : null);

const getAcwrZone = (acwr) => {
  if (acwr === null) return null;
  if (acwr > 1.5)  return { label: 'Riesgo alto',       color: '#DC2626', bg: '#FEF2F2' };
  if (acwr > 1.3)  return { label: 'Precaución',         color: '#D97706', bg: '#FFFBEB' };
  if (acwr >= 0.8) return { label: 'Óptimo',             color: '#16A34A', bg: '#ECFDF5' };
  return               { label: 'Desentrenamiento',       color: '#2563EB', bg: '#EFF6FF' };
};

const TSB_ZONE = {
  overreaching: { label: 'Sobreentrenando', color: '#DC2626', bg: '#FEF2F2' },
  fatigued:     { label: 'Fatigado',         color: '#D97706', bg: '#FFFBEB' },
  productive:   { label: 'Productivo',        color: '#2563EB', bg: '#EFF6FF' },
  optimal:      { label: 'Óptimo',            color: '#16A34A', bg: '#ECFDF5' },
  fresh:        { label: 'Fresco',            color: '#0891B2', bg: '#ECFEFF' },
};

const SEMAPHORE = [
  { key: 'overreaching', label: 'Sobreentrenando', color: '#EF4444' },
  { key: 'fatigued',     label: 'Fatigado',         color: '#F59E0B' },
  { key: 'productive',   label: 'Productivo',        color: '#3B82F6' },
  { key: 'optimal',      label: 'Óptimo',            color: '#22C55E' },
  { key: 'fresh',        label: 'Fresco',            color: '#06B6D4' },
];

const PERIOD_DAYS = { THIS_MONTH: 30, LAST_3_MONTHS: 90, THIS_YEAR: 365 };

const Dashboard = () => {
  const navigate = useNavigate();
  const { activeOrg, orgLoading } = useOrg();
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState('');
  const [periodo, setPeriodo]             = useState('THIS_MONTH');
  const [teamReadiness, setTeamReadiness] = useState(null);
  const [repMembershipId, setRepMembershipId] = useState(null);
  const [repAthleteName, setRepAthleteName]   = useState('');
  const [repPmcData, setRepPmcData]       = useState([]);
  const [pmcLoading, setPmcLoading]       = useState(false);

  // Load team readiness
  useEffect(() => {
    if (!activeOrg) return;
    const fetchData = async () => {
      try {
        setLoading(true);
        const resTeam = await getTeamReadiness();
        const team = resTeam.data;
        setTeamReadiness(team);

        // Pick representative athlete (highest CTL) for the PMC chart
        const teamAthletes = team?.athletes || [];
        if (teamAthletes.length > 0) {
          const rep = teamAthletes.reduce(
            (best, a) => (a.ctl > (best.ctl || 0) ? a : best),
            teamAthletes[0],
          );
          setRepMembershipId(rep.membership_id);
          setRepAthleteName(rep.name);
        }
      } catch (err) {
        console.error('Error Dashboard:', err);
        setError('Error de conexión. Verifica tu internet.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOrg?.org_id]);

  // Load representative athlete PMC when period or rep athlete changes
  useEffect(() => {
    if (!repMembershipId) return;
    const days = PERIOD_DAYS[periodo] || 90;
    setPmcLoading(true);
    getCoachAthletePMC(repMembershipId, days)
      .then(res => setRepPmcData(res.data?.days || []))
      .catch(() => setRepPmcData([]))
      .finally(() => setPmcLoading(false));
  }, [repMembershipId, periodo]);

  // Derived data
  const summary      = teamReadiness?.summary || {};
  const teamAthletes = teamReadiness?.athletes || [];

  const avgCtl = teamAthletes.length > 0
    ? Math.round(teamAthletes.reduce((sum, a) => sum + (a.ctl || 0), 0) / teamAthletes.length)
    : null;

  const highRiskCount = teamAthletes.filter(a => {
    const acwr = computeAcwr(a.atl, a.ctl);
    return acwr !== null && acwr > 1.5;
  }).length;

  const attentionAthletes = useMemo(() => {
    const athletes = teamReadiness?.athletes || [];
    return athletes
      .map(a => ({ ...a, acwr: computeAcwr(a.atl, a.ctl) }))
      .filter(a =>
        a.tsb_zone === 'overreaching' ||
        a.tsb_zone === 'fatigued' ||
        (a.acwr !== null && a.acwr > 1.5) ||
        (a.acwr !== null && a.acwr < 0.8) ||
        (a.ctl === 0 && a.atl === 0),
      )
      .sort((a, b) => {
        const diff = (b.acwr ?? 0) - (a.acwr ?? 0);
        return diff !== 0 ? diff : (a.tsb || 0) - (b.tsb || 0);
      });
  }, [teamReadiness]);

  const safeParse = (str) => { try { return parseISO(str); } catch { return null; } };

  if (orgLoading) return (
    <Layout><Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box></Layout>
  );
  if (!activeOrg) return (
    <Layout><Alert severity="info" sx={{ m: 4 }}>Sin organización asignada.</Alert></Layout>
  );

  return (
    <Layout>
      {/* ORG IDENTITY CARD — gives coach a sense of belonging */}
      <Box sx={{
        mx: { xs: 2, sm: 3 }, mt: { xs: 2, sm: 3 }, mb: 2,
        display: 'flex', alignItems: 'center', gap: 2,
        bgcolor: 'rgba(0,212,170,0.06)',
        border: '1px solid rgba(0,212,170,0.18)',
        borderRadius: 3, px: 3, py: 2,
      }}>
        <Avatar sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 800, width: 44, height: 44 }}>
          {(activeOrg?.org_name?.[0] ?? 'Q').toUpperCase()}
        </Avatar>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="caption" sx={{ color: '#64748b', display: 'block' }}>
            {activeOrg?.role === 'owner' ? 'Organización' : 'Trabajás como coach en'}
          </Typography>
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A', lineHeight: 1.2 }}>
            {activeOrg?.org_name}
          </Typography>
        </Box>
        <Chip
          label={activeOrg?.role === 'owner' ? 'Owner' : 'Coach'}
          size="small"
          sx={{ bgcolor: '#00D4AA', color: '#0D1117', fontWeight: 700, fontSize: '0.72rem' }}
        />
      </Box>

      {/* HEADER */}
      <Box sx={{ mb: 4, p: { xs: 2, sm: 3 }, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A' }}>Panel de Control</Typography>
          <Typography variant="body2" sx={{ color: '#64748B' }}>Visión científica de tu equipo en tiempo real.</Typography>
        </Box>
        <FormControl size="small" sx={{ minWidth: 150, bgcolor: 'white' }}>
          <InputLabel>Período</InputLabel>
          <Select value={periodo} label="Período" onChange={e => setPeriodo(e.target.value)}>
            <MenuItem value="THIS_MONTH">Este Mes</MenuItem>
            <MenuItem value="LAST_3_MONTHS">Últimos 3 Meses</MenuItem>
            <MenuItem value="THIS_YEAR">Este Año</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {/* ROW 1 — KPI CARDS */}
      <Grid container spacing={{ xs: 2, sm: 3 }} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, sm: 6 }}>
          <StatCard
            title="Fitness Promedio"
            value={loading ? '—' : (avgCtl !== null ? `${avgCtl} CTL` : '—')}
            sub={avgCtl !== null ? 'Promedio real del equipo' : 'Sin datos de carga aún'}
            color="#F59E0B"
            icon={TrendingUp}
            loading={loading}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 6 }}>
          <StatCard
            title="Riesgo Lesión"
            value={loading ? '—' : highRiskCount}
            sub={highRiskCount > 0 ? 'Atletas con ACWR > 1.5' : 'Sin alertas críticas'}
            color="#EF4444"
            icon={LocalHospital}
            loading={loading}
          />
        </Grid>
      </Grid>

      {/* ROW 2 — TEAM SEMAPHORE */}
      <Box sx={{ display: 'flex', gap: 2, mb: 4, flexWrap: 'wrap' }}>
        {SEMAPHORE.map(({ key, label, color }) => (
          <Box key={key} sx={{ flex: '1 1 120px', minWidth: 100 }}>
            <SemaCard label={label} count={summary[key]} color={color} loading={loading} />
          </Box>
        ))}
      </Box>

      {/* ROW 3 — ATTENTION TABLE */}
      <Paper sx={{ p: 3, borderRadius: '12px', mb: 4, boxShadow: '0 1px 3px rgba(0,0,0,0.07)', border: '1px solid #E2E8F0' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, color: '#0F172A' }}>Atletas que Necesitan Atención</Typography>
          {!loading && attentionAthletes.length > 0 && (
            <Typography variant="caption" sx={{ color: '#64748B' }}>{attentionAthletes.length} atleta{attentionAthletes.length !== 1 ? 's' : ''}</Typography>
          )}
        </Box>
        <Divider sx={{ mb: 2 }} />

        {loading ? (
          [1, 2, 3].map(i => <Skeleton key={i} height={52} sx={{ mb: 0.5, borderRadius: 1 }} />)
        ) : attentionAthletes.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 5 }}>
            <CheckCircle sx={{ fontSize: 44, color: '#22C55E', mb: 1 }} />
            <Typography variant="body1" sx={{ fontWeight: 600, color: '#16A34A' }}>Todo el equipo en buen estado</Typography>
            <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>Ningún atleta presenta alertas de carga o riesgo de lesión.</Typography>
          </Box>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: '#F8FAFC' }}>
              <TableRow>
                {['NOMBRE', 'CTL', 'ATL', 'TSB', 'ACWR', 'RIESGO', 'ZONA', ''].map(col => (
                  <TableCell key={col} sx={{ fontWeight: 600, color: '#475569', fontSize: '0.7rem', letterSpacing: 0.5, py: 1.5 }}>
                    {col}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {attentionAthletes.map(athlete => {
                const acwrZone = getAcwrZone(athlete.acwr);
                const tsbZone  = TSB_ZONE[athlete.tsb_zone];
                const tsbColor = (athlete.tsb ?? 0) >= 0 ? '#16A34A' : '#DC2626';
                return (
                  <TableRow
                    key={athlete.membership_id}
                    hover
                    sx={{ cursor: 'pointer', '&:hover': { bgcolor: '#F8FAFC' } }}
                    onClick={() => navigate(`/coach/athletes/${athlete.membership_id}/pmc`)}
                  >
                    <TableCell sx={{ fontWeight: 600, color: '#0F172A', py: 1.5 }}>{athlete.name}</TableCell>
                    <TableCell sx={{ color: '#475569', py: 1.5 }}>{athlete.ctl ?? '—'}</TableCell>
                    <TableCell sx={{ color: '#475569', py: 1.5 }}>{athlete.atl ?? '—'}</TableCell>
                    <TableCell sx={{ py: 1.5 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600, color: tsbColor }}>
                        {athlete.tsb ?? '—'}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ fontWeight: 600, color: '#0F172A', py: 1.5 }}>
                      {athlete.acwr !== null ? athlete.acwr.toFixed(2) : '—'}
                    </TableCell>
                    <TableCell sx={{ py: 1.5 }}>
                      {acwrZone ? (
                        <Chip label={acwrZone.label} size="small" sx={{ bgcolor: acwrZone.bg, color: acwrZone.color, fontWeight: 600, fontSize: '0.68rem', height: 20 }} />
                      ) : '—'}
                    </TableCell>
                    <TableCell sx={{ py: 1.5 }}>
                      {tsbZone ? (
                        <Chip label={tsbZone.label} size="small" sx={{ bgcolor: tsbZone.bg, color: tsbZone.color, fontWeight: 600, fontSize: '0.68rem', height: 20 }} />
                      ) : '—'}
                    </TableCell>
                    <TableCell align="right" sx={{ py: 1.5 }}>
                      <IconButton size="small" sx={{ color: '#0EA5E9' }} onClick={e => { e.stopPropagation(); navigate(`/coach/athletes/${athlete.membership_id}/pmc`); }}>
                        <OpenInNew fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          </Box>
        )}
      </Paper>

      {/* ROW 4 — PMC CHART */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid size={{ xs: 12 }}>
          <Paper sx={{ p: 3, borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.07)', border: '1px solid #E2E8F0', height: 420, minHeight: 250 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <MonitorHeart sx={{ color: '#64748B' }} />
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#0F172A' }}>PMC del Equipo</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                {repAthleteName && (
                  <Typography variant="caption" sx={{ color: '#64748B' }}>PMC representativo: <strong>{repAthleteName}</strong></Typography>
                )}
                <Typography variant="caption" sx={{ bgcolor: '#F1F5F9', px: 1, py: 0.5, borderRadius: 1, color: '#475569' }}>Modelo Banister</Typography>
              </Box>
            </Box>
            <Divider sx={{ mb: 2 }} />
            <Box sx={{ height: 300, width: '100%', minWidth: 0 }}>
              {pmcLoading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                  <CircularProgress size={32} sx={{ color: '#0EA5E9' }} />
                </Box>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={repPmcData}>
                    <defs>
                      <linearGradient id="colorFit" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0EA5E9" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#0EA5E9" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={str => {
                        const d = safeParse(str);
                        return d ? format(d, 'd MMM', { locale: es }) : str;
                      }}
                      axisLine={false} tickLine={false}
                      tick={{ fill: '#64748B', fontSize: 12 }}
                      minTickGap={30}
                    />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748B', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                      labelFormatter={str => {
                        const d = safeParse(str);
                        return d ? format(d, 'PPPP', { locale: es }) : str;
                      }}
                    />
                    <Legend verticalAlign="top" height={36} />
                    <Area type="monotone" dataKey="ctl" stroke="#0EA5E9" strokeWidth={3} fillOpacity={1} fill="url(#colorFit)" name="Fitness (CTL)" />
                    <Line type="monotone" dataKey="atl" stroke="#EC4899" strokeWidth={2} dot={false} name="Fatiga (ATL)" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Layout>
  );
};

export default Dashboard;
