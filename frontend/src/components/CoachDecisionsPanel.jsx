import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert as MUIAlert,
  Box,
  Button,
  Chip,
  Divider,
  Grid,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { LocalFireDepartment, Terrain, Timer, Straighten, Layers } from '@mui/icons-material';
import { getISOWeek, getISOWeekYear } from 'date-fns';
import client from '../api/client';

function isoWeekString(d = new Date()) {
  const year = getISOWeekYear(d);
  const week = getISOWeek(d);
  return `${year}-${String(week).padStart(2, '0')}`;
}

function severityChipColor(sev) {
  const s = String(sev || '').toLowerCase();
  if (s === 'critical' || s === 'high') return 'error';
  if (s === 'warn' || s === 'medium') return 'warning';
  return 'default';
}

function MetricCard({ label, value, icon }) {
  return (
    <Paper sx={{ p: 2, borderRadius: 2, border: '1px solid #E2E8F0', boxShadow: '0 2px 10px rgba(0,0,0,0.03)' }}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Box sx={{ color: '#0F172A', display: 'flex', alignItems: 'center' }}>{icon}</Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, letterSpacing: 0.3 }}>
            {label}
          </Typography>
          <Typography variant="h6" sx={{ fontWeight: 800, color: '#0F172A', lineHeight: 1.1 }}>
            {value}
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );
}

function formatDuration(minutes) {
  const total = Number.isFinite(minutes) ? Math.max(0, Math.round(minutes)) : 0;
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  return `${hours}h ${mins}m`;
}

export default function CoachDecisionsPanel({ athleteId }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);

  const week = useMemo(() => isoWeekString(new Date()), []);

  useEffect(() => {
    let cancelled = false;
    async function fetchWeekSummary() {
      try {
        setLoading(true);
        setError('');
        const resp = await client.get(`/api/coach/athletes/${athleteId}/week-summary/`, { params: { week } });
        if (cancelled) return;
        setData(resp.data);
      } catch (e) {
        if (cancelled) return;
        setError('No se pudo cargar “Coach Decisions”.');
        setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (athleteId) fetchWeekSummary();
    return () => {
      cancelled = true;
    };
  }, [athleteId, week]);

  async function markSeen(alertId) {
    try {
      await client.patch(`/api/coach/alerts/${alertId}/`, { visto_por_coach: true });
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          alerts: (prev.alerts || []).map((a) => (a.id === alertId ? { ...a, visto_por_coach: true } : a)),
        };
      });
    } catch {
      // noop: UX mínima
    }
  }

  const c = data?.compliance || {};
  const sessionsByType = data?.sessions_by_type || {};
  const rangeStart = data?.start_date || data?.range?.start;
  const rangeEnd = data?.end_date || data?.range?.end;

  return (
    <Paper sx={{ p: 3, borderRadius: 3, mb: 4, border: '1px solid #E2E8F0', boxShadow: '0 4px 18px rgba(0,0,0,0.04)' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 2, mb: 1 }}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h6" sx={{ fontWeight: 900, color: '#0F172A' }}>
              Coach Decisions
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            Semana {data?.week || week} · {rangeStart} → {rangeEnd}
          </Typography>
        </Box>
        {loading && <Chip size="small" label="Cargando…" />}
      </Box>

      {error && <MUIAlert severity="error" sx={{ mt: 2 }}>{error}</MUIAlert>}

      {!error && (
        <>
          <Grid container spacing={1.5} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6} md={2.4}>
              <MetricCard label="Duración" value={formatDuration(data?.total_duration_minutes)} icon={<Timer fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={2.4}>
              <MetricCard label="Distancia" value={`${data?.total_distance_km ?? 0} km`} icon={<Straighten fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={2.4}>
              <MetricCard
                label="Elev +"
                value={`${data?.total_elevation_gain_m ?? 0} m`}
                icon={<Terrain fontSize="small" />}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2.4}>
              <MetricCard label="Kcal" value={`${data?.total_calories ?? 0} kcal`} icon={<LocalFireDepartment fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={2.4}>
              <MetricCard label="Sesiones" value={data?.sessions_count ?? 0} icon={<Layers fontSize="small" />} />
            </Grid>
          </Grid>

          <Divider sx={{ my: 2 }} />

          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
              Sesiones por tipo
            </Typography>
            {Object.keys(sessionsByType).length === 0 ? (
              <Typography variant="body2" sx={{ color: '#64748B' }}>
                Sin sesiones registradas.
              </Typography>
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {Object.entries(sessionsByType).map(([type, count]) => (
                  <Chip key={type} label={`${type}: ${count}`} size="small" />
                ))}
              </Stack>
            )}
          </Box>

          <Grid container spacing={2}>
            <Grid item xs={12} md={5}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
                Compliance (plan vs real)
              </Typography>
              <Stack spacing={0.75}>
                {['duration', 'distance', 'elev', 'load'].map((key) => (
                  <Box key={key} sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                    <Typography variant="body2" sx={{ color: '#334155', fontWeight: 700, textTransform: 'capitalize' }}>
                      {key}
                    </Typography>
                    <Typography variant="body2" sx={{ color: '#0F172A' }}>
                      {c?.[key]?.pct != null ? `${c[key].pct}%` : '—'}
                      {c?.[key]?.delta != null ? ` (Δ ${c[key].delta})` : ''}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Grid>
            <Grid item xs={12} md={7}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
                Alertas (top 5)
              </Typography>
              {(data?.alerts || []).length === 0 ? (
                <MUIAlert severity="info">Sin alertas abiertas.</MUIAlert>
              ) : (
                <Stack spacing={1}>
                  {(data?.alerts || []).map((a) => (
                    <Paper key={a.id} variant="outlined" sx={{ p: 1.5, borderRadius: 2, borderColor: '#E2E8F0' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                        <Box sx={{ minWidth: 0 }}>
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                            <Chip size="small" label={a.severity} color={severityChipColor(a.severity)} />
                            <Chip size="small" variant="outlined" label={a.type} />
                            {!a.visto_por_coach && <Chip size="small" label="Nuevo" color="warning" />}
                          </Stack>
                          <Typography variant="body2" sx={{ fontWeight: 800, color: '#0F172A' }}>
                            {a.message}
                          </Typography>
                          {a.recommended_action && (
                            <Typography variant="caption" sx={{ color: '#475569' }}>
                              Acción: {a.recommended_action}
                            </Typography>
                          )}
                        </Box>
                        <Box sx={{ flexShrink: 0 }}>
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={!!a.visto_por_coach}
                            onClick={() => markSeen(a.id)}
                            sx={{ textTransform: 'none' }}
                          >
                            {a.visto_por_coach ? 'Visto' : 'Marcar visto'}
                          </Button>
                        </Box>
                      </Box>
                    </Paper>
                  ))}
                </Stack>
              )}
            </Grid>
          </Grid>
        </>
      )}
    </Paper>
  );
}
