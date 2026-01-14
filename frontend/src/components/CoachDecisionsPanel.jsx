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
import { LocalFireDepartment, Terrain, Timer, Straighten, Layers, FitnessCenter } from '@mui/icons-material';
import { getISOWeek, getISOWeekYear } from 'date-fns';
import client from '../api/client';
import { getSportLabel, splitPerSportTotals } from './sportsConfig';

function isoWeekString(d = new Date()) {
  const year = getISOWeekYear(d);
  const week = getISOWeek(d);
  return `${year}-W${String(week).padStart(2, '0')}`;
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

function formatDurationValue(minutes) {
  if (!Number.isFinite(minutes)) return '—';
  return formatDuration(minutes);
}

function formatLoadValue(load) {
  if (!Number.isFinite(load)) return '—';
  const rounded = Math.round(load * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatStrengthDuration(seconds) {
  const totalMinutes = Number.isFinite(seconds) ? Math.max(0, Math.round(seconds / 60)) : 0;
  if (totalMinutes < 60) {
    return `${totalMinutes} min`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  return `${hours}h ${mins}m`;
}

function normalizeWeekSummary(payload) {
  if (!payload) return null;
  const distanceKm = payload.total_distance_km ?? payload.distance_km ?? payload.distanceKm;
  const durationMin = payload.total_duration_minutes ?? payload.duration_minutes ?? payload.durationMin;
  const elevationGain = payload.total_elevation_gain_m ?? payload.elevation_gain_m ?? payload.elevationGain;
  const elevationLoss = payload.total_elevation_loss_m ?? payload.elevation_loss_m ?? payload.elevationLoss;
  const elevationTotal =
    payload.total_elevation_total_m ??
    payload.elevation_total_m ??
    payload.elevationTotal ??
    (Number.isFinite(elevationGain) && Number.isFinite(elevationLoss) ? elevationGain + elevationLoss : undefined);
  const caloriesKcal = payload.total_calories_kcal ?? payload.total_calories ?? payload.kcal ?? payload.caloriesKcal;
  const sessionsCount = payload.sessions_count ?? payload.sessionsCount;
  const sessionsByType = payload.sessions_by_type ?? payload.sessionsByType ?? {};
  const rawPerSportTotals = payload.per_sport_totals ?? payload.perSportTotals ?? {};
  const perSportTotals = Object.entries(rawPerSportTotals || {}).reduce((acc, [code, totals]) => {
    const entry = totals || {};
    acc[code] = {
      code,
      label: getSportLabel(code),
      durationMinutes: entry.duration_minutes ?? entry.durationMinutes ?? null,
      durationSeconds: entry.duration_s ?? entry.durationSeconds ?? null,
      caloriesKcal: entry.calories_kcal ?? entry.caloriesKcal ?? null,
      load: entry.load ?? null,
      distanceKm: entry.distance_km ?? entry.distanceKm ?? null,
      elevationGainM: entry.elevation_gain_m ?? entry.elevationGainM ?? null,
      elevationLossM: entry.elevation_loss_m ?? entry.elevationLossM ?? null,
      elevationTotalM: entry.elevation_total_m ?? entry.elevationTotalM ?? null,
    };
    return acc;
  }, {});

  return {
    ...payload,
    distanceKm,
    durationMin,
    elevationGain,
    elevationLoss,
    elevationTotal,
    caloriesKcal,
    sessionsCount,
    sessionsByType,
    perSportTotals,
  };
}

function hasWeekSummaryData(summary) {
  if (!summary) return false;
  if (summary.no_data === true) return false;
  const totals = [
    summary.distanceKm,
    summary.durationMin,
    summary.elevationGain,
    summary.elevationLoss,
    summary.elevationTotal,
    summary.caloriesKcal,
  ];
  const hasTotals = totals.some((value) => Number.isFinite(value) && value > 0);
  const sessionsCount = Number(summary.sessionsCount ?? 0);
  return sessionsCount > 0 || hasTotals;
}

function SportTotalsGrid({ sports }) {
  return (
    <Grid container spacing={1.5}>
      {sports.map((sport) => (
        <Grid item xs={12} sm={6} md={4} key={sport.code}>
          <Paper sx={{ p: 2, borderRadius: 2, border: '1px solid #E2E8F0' }}>
            <Stack spacing={0.75}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A' }}>
                {sport.label}
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5 }}>
                <Typography variant="body2" sx={{ color: '#475569' }}>
                  Duración
                </Typography>
                <Typography variant="body2" sx={{ color: '#0F172A', fontWeight: 600 }}>
                  {formatDurationValue(sport.durationMinutes)}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5 }}>
                <Typography variant="body2" sx={{ color: '#475569' }}>
                  Calorías
                </Typography>
                <Typography variant="body2" sx={{ color: '#0F172A', fontWeight: 600 }}>
                  {Number.isFinite(sport.caloriesKcal) ? `${sport.caloriesKcal} kcal` : '—'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5 }}>
                <Typography variant="body2" sx={{ color: '#475569' }}>
                  Load
                </Typography>
                <Typography variant="body2" sx={{ color: '#0F172A', fontWeight: 600 }}>
                  {formatLoadValue(sport.load)}
                </Typography>
              </Box>
              {Number.isFinite(sport.distanceKm) && (
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5 }}>
                  <Typography variant="body2" sx={{ color: '#475569' }}>
                    Distancia
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#0F172A', fontWeight: 600 }}>
                    {sport.distanceKm} km
                  </Typography>
                </Box>
              )}
              {Number.isFinite(sport.elevationGainM) && (
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5 }}>
                  <Typography variant="body2" sx={{ color: '#475569' }}>
                    Desnivel +
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#0F172A', fontWeight: 600 }}>
                    {sport.elevationGainM} m
                  </Typography>
                </Box>
              )}
            </Stack>
          </Paper>
        </Grid>
      ))}
    </Grid>
  );
}

export default function CoachDecisionsPanel({ athleteId }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [emptyState, setEmptyState] = useState(false);
  const [data, setData] = useState(null);

  const week = useMemo(() => isoWeekString(new Date()), []);
  const summary = useMemo(() => normalizeWeekSummary(data), [data]);

  useEffect(() => {
    let cancelled = false;
    async function fetchWeekSummary() {
      try {
        setLoading(true);
        setError('');
        setEmptyState(false);
        const resp = await client.get(`/api/coach/athletes/${athleteId}/week-summary/`, { params: { week } });
        if (cancelled) return;
        const normalized = normalizeWeekSummary(resp.data);
        if (!hasWeekSummaryData(normalized)) {
          setEmptyState(true);
          setData(null);
          return;
        }
        setData(resp.data);
      } catch (e) {
        if (cancelled) return;
        const status = e?.response?.status;
        if (status === 404 || status === 204) {
          setEmptyState(true);
          setError('');
          setData(null);
        } else {
          if (status >= 500) {
            // eslint-disable-next-line no-console
            console.error('Coach Decisions: error al cargar week summary.', e);
          }
          setError('No se pudo cargar “Coach Decisions”.');
          setData(null);
        }
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

  const c = summary?.compliance || {};
  const sessionsByType = summary?.sessionsByType || {};
  const durationMinutes = summary?.durationMin ?? 0;
  const distanceKm = summary?.distanceKm ?? 0;
  const kcal = summary?.caloriesKcal ?? 0;
  const elevationGain = summary?.elevationGain ?? 0;
  const elevationLoss = summary?.elevationLoss ?? 0;
  const rangeStart = summary?.start_date || summary?.range?.start;
  const rangeEnd = summary?.end_date || summary?.range?.end;
  const displayRangeStart = rangeStart || '—';
  const displayRangeEnd = rangeEnd || '—';
  const perSportTotals = summary?.perSportTotals || {};
  const { distanceTotals, nonDistanceTotals } = splitPerSportTotals(perSportTotals);
  const strengthDurationSeconds = nonDistanceTotals.reduce((acc, sport) => {
    if (Number.isFinite(sport.durationSeconds)) {
      return acc + sport.durationSeconds;
    }
    if (Number.isFinite(sport.durationMinutes)) {
      return acc + sport.durationMinutes * 60;
    }
    return acc;
  }, 0);
  const strengthDurationLabel = formatStrengthDuration(strengthDurationSeconds);

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
            Semana {summary?.week || week} · {displayRangeStart} → {displayRangeEnd}
          </Typography>
        </Box>
        {loading && <Chip size="small" label="Cargando…" />}
      </Box>

      {error && <MUIAlert severity="error" sx={{ mt: 2 }}>{error}</MUIAlert>}
      {!error && emptyState && <MUIAlert severity="info" sx={{ mt: 2 }}>Sin datos para esta semana.</MUIAlert>}

      {!error && !emptyState && (
        <>
          <Grid container spacing={1.5} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Duración" value={formatDuration(durationMinutes)} icon={<Timer fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Distancia" value={`${distanceKm} km`} icon={<Straighten fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard
                label="Elev +"
                value={`${elevationGain} m`}
                icon={<Terrain fontSize="small" />}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Elev -" value={`${elevationLoss} m`} icon={<Terrain fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Fuerza" value={strengthDurationLabel} icon={<FitnessCenter fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Kcal" value={`${kcal} kcal`} icon={<LocalFireDepartment fontSize="small" />} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <MetricCard label="Sesiones" value={summary?.sessionsCount ?? 0} icon={<Layers fontSize="small" />} />
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

          {distanceTotals.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
                Trabajo por deporte
              </Typography>
              <SportTotalsGrid sports={distanceTotals} />
            </Box>
          )}

          {nonDistanceTotals.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
                Otras actividades
              </Typography>
              <SportTotalsGrid sports={nonDistanceTotals} />
            </Box>
          )}

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
