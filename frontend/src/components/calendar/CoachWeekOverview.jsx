/**
 * CoachWeekOverview.jsx — Coach weekly snapshot when no athlete is selected (PR-163)
 *
 * Shows a table: Avatar+Name | Compliance% bar | CTL | Estado | "Ver →"
 * Data sources:
 *   - CTL/TSB: /api/coach/team-readiness/ (getTeamReadiness)
 *   - Compliance: /api/p1/orgs/{orgId}/assignments/ for the current week
 *
 * Props:
 *   orgId            — number | string | null
 *   athletes         — [{ id, first_name, last_name, email, membership_id }]
 *   onSelectAthlete  — (value: 'a:42') => void
 */
import React, { useEffect, useState } from 'react';
import { Box, Typography, CircularProgress, Alert } from '@mui/material';
import { getTeamReadiness } from '../../api/pmc';
import { listAssignments } from '../../api/assignments';

function getInitials(name) {
  return name.split(' ').slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '').join('');
}

function athleteDisplayName(a) {
  return [a.first_name, a.last_name].filter(Boolean).join(' ') || a.email?.split('@')[0] || `Atleta #${a.id}`;
}

/** Returns Monday of the week containing `date` as 'YYYY-MM-DD'. */
function weekBounds(date = new Date()) {
  const d = new Date(date);
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day; // shift to Monday
  d.setDate(d.getDate() + diff);
  const monday = d.toISOString().slice(0, 10);
  d.setDate(d.getDate() + 6);
  const sunday = d.toISOString().slice(0, 10);
  return { monday, sunday };
}

function ComplianceBar({ pct }) {
  if (pct == null) {
    return (
      <Typography variant="caption" sx={{ fontSize: '0.68rem', color: '#94a3b8' }}>
        —
      </Typography>
    );
  }
  const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ flex: 1, maxWidth: 80, height: 5, borderRadius: 2, bgcolor: '#e2e8f0', overflow: 'hidden' }}>
        <Box sx={{ height: '100%', width: `${Math.min(100, pct)}%`, bgcolor: color, borderRadius: 2 }} />
      </Box>
      <Typography variant="caption" sx={{ fontSize: '0.68rem', fontWeight: 600, color, minWidth: 32 }}>
        {pct}%
      </Typography>
    </Box>
  );
}

function StatusBadge({ tsbZone }) {
  if (tsbZone === 'optimal' || tsbZone === 'productive') return <Box sx={{ px: 0.75, py: 0.15, borderRadius: 1, bgcolor: '#f0fdf4', border: '1px solid #86efac', fontSize: '0.62rem', fontWeight: 700, color: '#16a34a' }}>✅ OK</Box>;
  if (tsbZone === 'stale') return <Box sx={{ px: 0.75, py: 0.15, borderRadius: 1, bgcolor: '#fef2f2', border: '1px solid #fca5a5', fontSize: '0.62rem', fontWeight: 700, color: '#dc2626' }}>🔴 Inactivo</Box>;
  if (tsbZone === 'overreaching' || tsbZone === 'fatigued') return <Box sx={{ px: 0.75, py: 0.15, borderRadius: 1, bgcolor: '#fffbeb', border: '1px solid #fde047', fontSize: '0.62rem', fontWeight: 700, color: '#d97706' }}>⚠️ Riesgo</Box>;
  if (tsbZone) return <Box sx={{ px: 0.75, py: 0.15, borderRadius: 1, bgcolor: '#f8fafc', border: '1px solid #e2e8f0', fontSize: '0.62rem', fontWeight: 700, color: '#64748b' }}>{tsbZone}</Box>;
  return <Box sx={{ px: 0.75, py: 0.15, borderRadius: 1, bgcolor: '#fef2f2', border: '1px solid #fca5a5', fontSize: '0.62rem', fontWeight: 700, color: '#dc2626' }}>🔴 Inactivo</Box>;
}

export default function CoachWeekOverview({ orgId, athletes = [], onSelectAthlete }) {
  const [readiness, setReadiness] = useState([]);
  const [complianceMap, setComplianceMap] = useState({}); // athleteId → pct
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const { monday, sunday } = weekBounds();

    Promise.all([
      getTeamReadiness(),
      orgId
        ? listAssignments(orgId, { dateFrom: monday, dateTo: sunday })
        : Promise.resolve({ data: [] }),
    ])
      .then(([readinessRes, assignmentsRes]) => {
        if (cancelled) return;

        const athletesData = readinessRes.data?.athletes ?? readinessRes.data ?? [];
        setReadiness(athletesData);

        // Calculate compliance per athlete from this week's assignments
        const rawAssignments = Array.isArray(assignmentsRes.data)
          ? assignmentsRes.data
          : assignmentsRes.data?.results ?? [];

        const byAthlete = {};
        for (const a of rawAssignments) {
          const aid = a.athlete_id ?? a.athlete;
          if (!aid) continue;
          if (!byAthlete[aid]) byAthlete[aid] = { total: 0, completed: 0 };
          byAthlete[aid].total += 1;
          if (a.status === 'completed') byAthlete[aid].completed += 1;
        }

        const pctMap = {};
        for (const [aid, counts] of Object.entries(byAthlete)) {
          if (counts.total > 0) {
            pctMap[aid] = Math.round((counts.completed / counts.total) * 100);
          }
        }
        setComplianceMap(pctMap);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError('No se pudo cargar el resumen del equipo.');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [orgId]);

  // Build readiness map by membership_id (what the API returns)
  const readinessMap = {};
  for (const r of readiness) {
    if (r.membership_id) readinessMap[r.membership_id] = r;
  }

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 280 }}>
        <CircularProgress size={28} sx={{ color: '#f97316' }} />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error" sx={{ mx: 2 }}>{error}</Alert>;
  }

  if (athletes.length === 0) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', py: 8, color: '#94a3b8' }}>
        <Typography variant="h6" sx={{ fontWeight: 600, color: '#374151' }}>No hay atletas en este equipo</Typography>
        <Typography variant="body2" sx={{ color: '#94a3b8', mt: 0.5 }}>Agrega atletas a tu organización para ver su resumen semanal.</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, overflowY: 'auto' }}>
      {/* Table header */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: '1fr 120px 60px 90px 52px',
          px: 2, py: 0.75,
          bgcolor: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
          gap: 1,
        }}
      >
        {['ATLETA', 'CUMPLIMIENTO', 'CTL', 'ESTADO', ''].map((h) => (
          <Typography key={h} variant="caption" sx={{ fontSize: '0.62rem', fontWeight: 700, color: '#94a3b8', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            {h}
          </Typography>
        ))}
      </Box>

      {/* Table rows */}
      {athletes.map((athlete) => {
        const rd = readinessMap[athlete.membership_id] ?? {};
        const name = athleteDisplayName(athlete);
        const initials = getInitials(name);
        const compliance = complianceMap[athlete.id] ?? null;
        const ctl = rd.ctl ?? null;
        const tsbZone = rd.tsb_zone ?? null;

        return (
          <Box
            key={athlete.id}
            sx={{
              display: 'grid',
              gridTemplateColumns: '1fr 120px 60px 90px 52px',
              px: 2, py: 1,
              borderBottom: '1px solid #f1f5f9',
              alignItems: 'center',
              gap: 1,
              '&:hover': { bgcolor: '#fafafa' },
            }}
          >
            {/* Avatar + Name */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
              <Box
                sx={{
                  width: 30, height: 30, borderRadius: '50%',
                  bgcolor: '#f97316', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#fff' }}>{initials}</Typography>
              </Box>
              <Typography sx={{ fontSize: '0.82rem', fontWeight: 500, color: '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {name}
              </Typography>
            </Box>

            {/* Compliance bar */}
            <ComplianceBar pct={compliance} />

            {/* CTL */}
            <Typography
              variant="caption"
              sx={{
                fontSize: '0.75rem', fontWeight: 600,
                color: ctl == null ? '#94a3b8' : ctl > 40 ? '#16a34a' : ctl > 20 ? '#d97706' : '#dc2626',
              }}
            >
              {ctl != null ? Math.round(ctl) : '—'}
            </Typography>

            {/* Estado */}
            <StatusBadge tsbZone={tsbZone} />

            {/* Ver → button */}
            <Box
              onClick={() => onSelectAthlete?.(`a:${athlete.id}`)}
              sx={{
                px: 1, py: 0.4,
                borderRadius: 1.5,
                bgcolor: '#fff7ed',
                border: '1px solid #fed7aa',
                color: '#f97316',
                fontSize: '0.7rem',
                fontWeight: 600,
                cursor: 'pointer',
                textAlign: 'center',
                whiteSpace: 'nowrap',
                '&:hover': { bgcolor: '#ffedd5' },
              }}
            >
              Ver →
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
